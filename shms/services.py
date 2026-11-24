"""Business logic: the hazard workflow, risk scoring, routing and dashboard figures.

Web and API routes are thin wrappers around these functions, so the whole
workflow can be tested without HTTP.

Reports move from draft to open and optionally planned. Closing a report, including
a repair at the point of reporting, sends it for independent verification.
See ALLOWED_TRANSITIONS for verification, rejection and reopening.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import risk, taxonomy
from .detection import DetectorResult
from .models import Area, Hazard, HazardEvent, Role, Status, User, utcnow
from .photo_metadata import PhotoCapture
from .site_layout import UNITS

# The safety workflow as a state machine. Every status change goes through _move(), which checks this table and
# writes an audit event with the from/to status.
ALLOWED_TRANSITIONS: dict[Status, set[Status]] = {
    Status.DRAFT: {Status.OPEN, Status.PENDING_VERIFICATION},  # confirm (routed) / confirm "fixed on the spot"
    Status.OPEN: {Status.PLANNED, Status.PENDING_VERIFICATION},  # plan action / close
    Status.PLANNED: {Status.PENDING_VERIFICATION},  # close
    Status.PENDING_VERIFICATION: {Status.CLOSED, Status.OPEN},  # verify / reject
    Status.CLOSED: {Status.OPEN},  # reopen
}
# Hazards that still need work (shown as "open" on dashboards and queues).
ACTIVE: frozenset[Status] = frozenset({Status.OPEN, Status.PLANNED, Status.PENDING_VERIFICATION})
# Hazards waiting for the owner's action (these can become overdue and escalate).
AWAITING_ACTION: frozenset[Status] = frozenset({Status.OPEN, Status.PLANNED})


class WorkflowError(ValueError):
    """Invalid input or an illegal state transition."""


class PermissionDenied(PermissionError):
    pass


# ---------------------------------------------------------------- helpers


def _require_state(h: Hazard, allowed: set[Status], action: str) -> None:
    """Each action names the states it may start from. The shared transition table alone is not enough: several
    actions lead to the same target state (e.g. confirm/reject/reopen -> OPEN), so the table would let one action
    be used to bypass another's checks (security review, Phase 1b)."""
    if h.status not in allowed:
        raise WorkflowError(f"Cannot {action} hazard #{h.id}: it is {h.status.value.replace('_', ' ')}")


def _check_move(h: Hazard, new: Status) -> None:
    if new not in ALLOWED_TRANSITIONS[h.status]:
        raise WorkflowError(f"Cannot move hazard #{h.id} from {h.status.value} to {new.value}")


def _move(db: Session, h: Hazard, actor: User, new: Status, kind: str, note: str = "", at: datetime | None = None):
    """The only place a hazard's status changes: checked against the table and recorded with from/to."""
    _check_move(h, new)
    old = h.status
    h.status = new
    db.add(
        HazardEvent(
            hazard=h,
            actor_id=actor.id,
            kind=kind,
            note=note,
            at=at or utcnow(),
            from_status=old.value,
            to_status=new.value,
        )
    )


def _event(db: Session, h: Hazard, actor: User, kind: str, note: str = "", at: datetime | None = None) -> None:
    db.add(HazardEvent(hazard=h, actor_id=actor.id, kind=kind, note=note, at=at or utcnow()))


def _clear_closure(h: Hazard) -> None:
    h.closed_at = h.closed_by_id = h.closure_action = h.closure_photo_path = None
    h.closed_on_spot = False
    h.verified_at = h.verified_by_id = None


def can_act_on(user: User, h: Hazard) -> bool:
    """Area Owner of the hazard's area, its assignee, or any supervisor."""
    return user.role == Role.SUPERVISOR or user.id in {h.assignee_id, h.area.owner_id}


def similar_count(db: Session, area_id: int, category_code: str, now: datetime, exclude_id: int | None = None) -> int:
    """Confirmed hazards of the same category in the same area within the look-back window."""
    since = now - timedelta(days=risk.lookback_days())
    q = select(func.count(Hazard.id)).where(
        Hazard.area_id == area_id,
        Hazard.category_code == category_code,
        Hazard.status != Status.DRAFT,
        Hazard.created_at >= since,
        Hazard.created_at <= now,
    )
    if exclude_id is not None:
        q = q.where(Hazard.id != exclude_id)
    return db.scalar(q) or 0


# ---------------------------------------------------------------- stage 1: report and score


class IdempotencyConflict(WorkflowError):
    """The same idempotency key was reused for a different report."""


def find_by_idem_key(db: Session, reporter: User, key: str | None) -> Hazard | None:
    if not key:
        return None
    return db.scalar(select(Hazard).where(Hazard.reporter_id == reporter.id, Hazard.idem_key == key))


def validate_pin(area: Area, x: int | None, y: int | None) -> None:
    if x is None and y is None:
        return
    if type(x) is not int or type(y) is not int:
        raise WorkflowError("Enter both map coordinates as whole numbers, or clear both to report by area.")
    unit = next((u for u in UNITS if u.reporting and u.code == area.code), None)
    if unit is None or not (unit.x <= x <= unit.x + unit.w and unit.y <= y <= unit.y + unit.h):
        raise WorkflowError(f"Choose a point inside {area.name} or clear the pin.")


def replay_or_conflict(
    db: Session, reporter: User, area: Area, key: str | None, x: int | None = None, y: int | None = None
) -> Hazard | None:
    """Idempotency (microservices lab): same key + same request -> the existing report; same key + a
    different request -> refuse, because one key must never mean two different reports."""
    existing = find_by_idem_key(db, reporter, key)
    if existing is not None and existing.area_id != area.id:
        raise IdempotencyConflict("This idempotency key was already used for a report in another area")
    if existing is not None and (existing.x, existing.y) != (x, y):
        raise IdempotencyConflict("This idempotency key was already used for a different location")
    return existing


def _ai_note(h: Hazard) -> str:
    if h.ai_error:
        return f"AI ({h.ai_model}) could not analyse the photo"
    if h.ai_top_code:
        return f"AI ({h.ai_model}) suggested {h.ai_top_code}"
    return f"AI ({h.ai_model}) found none of the checked items missing"


def create_draft(
    db: Session,
    reporter: User,
    area: Area,
    photo_path: str | None,
    result: DetectorResult | None,
    at: datetime | None = None,
    idem_key: str | None = None,
    experimental: list[dict] | None = None,
    x: int | None = None,
    y: int | None = None,
    capture: PhotoCapture = PhotoCapture(),
) -> Hazard:
    validate_pin(area, x, y)
    h = Hazard(
        area=area,
        x=x,
        y=y,
        reporter_id=reporter.id,
        status=Status.DRAFT,
        photo_path=photo_path,
        photo_captured_at=capture.taken_at,
        photo_latitude=capture.latitude,
        photo_longitude=capture.longitude,
        created_at=at or utcnow(),
        idem_key=idem_key,
    )
    if result is not None:
        # The AI checks the photo against the PPE this area requires; anything else is kept for
        # traceability but marked as not required and never pre-selected.
        required = set(area.check_codes)
        h.ai_model = result.model
        h.ai_latency_ms = round(result.latency_ms, 1)
        h.ai_error = result.error
        h.ai_suggestions = json.dumps(
            [{**s.to_dict(), "required": s.code in required} for s in result.suggestions] + list(experimental or [])
        )
        top = max((s for s in result.suggestions if s.code in required), key=lambda s: s.confidence, default=None)
        h.ai_top_code = top.code if top else None
    db.add(h)
    db.flush()
    _event(
        db,
        h,
        reporter,
        "reported",
        _ai_note(h) if result else "Reported without AI",
        at=h.created_at,
    )
    return h


@dataclass
class Confirmation:
    category_code: str
    consequence: int
    description: str = ""
    fixed_on_spot: bool = False
    closure_action: str = ""
    closure_photo_path: str | None = None


def confirm(db: Session, h: Hazard, actor: User, c: Confirmation, at: datetime | None = None) -> Hazard:
    """Reporter confirms or corrects the AI suggestion; risk is scored and the hazard is routed or closed."""
    if h.status != Status.DRAFT:
        raise WorkflowError("Only a draft report can be confirmed; this one has already been confirmed")
    if actor.id != h.reporter_id and actor.role != Role.SUPERVISOR:
        raise PermissionDenied("Only the reporter can confirm this report")
    if c.category_code not in taxonomy.categories():
        raise WorkflowError(f"Unknown hazard category: {c.category_code!r}")
    if c.category_code not in h.area.report_codes:
        raise WorkflowError(f"{taxonomy.get(c.category_code).name} is not a PPE requirement in {h.area.name}")
    if c.consequence not in risk.LEVELS:
        raise WorkflowError("Consequence must be 1-5")
    if c.fixed_on_spot and not c.closure_action.strip():
        raise WorkflowError("Describe the action taken when the hazard was fixed on the spot")
    now = at or utcnow()

    h.category_code = c.category_code
    h.description = c.description.strip()
    h.ai_accepted = (c.category_code == h.ai_top_code) if h.ai_top_code else None
    h.likelihood = risk.likelihood_from_history(similar_count(db, h.area_id, c.category_code, now, exclude_id=h.id))
    r = risk.score(c.consequence, h.likelihood)
    h.consequence, h.risk_score, h.risk_level = r.consequence, r.score, r.level
    h.due_at = now + timedelta(days=r.target_days)
    h.confirmed_at = now
    _event(
        db,
        h,
        actor,
        "confirmed",
        f"{taxonomy.get(c.category_code).name}; C{r.consequence} x L{r.likelihood} = {r.score} ({r.level})",
        at=now,
    )

    if c.fixed_on_spot:
        h.closed_on_spot = True
        h.closed_at, h.closed_by_id = now, actor.id
        h.closure_action = c.closure_action.strip()
        h.closure_photo_path = c.closure_photo_path
        h.assignee_id = h.area.owner_id
        _move(db, h, actor, Status.PENDING_VERIFICATION, "closed", f"Fixed on the spot: {h.closure_action}", at=now)
    else:
        h.assignee_id = h.area.owner_id
        _move(db, h, actor, Status.OPEN, "assigned", f"Routed to Area Owner {h.area.owner.name}", at=now)

    if risk.is_alert_level(r.level):
        _alert(db, h, actor, now)
    db.flush()
    return h


def _alert(db: Session, h: Hazard, actor: User, now: datetime) -> None:
    from . import notify

    recipients = list(db.scalars(select(User).where(User.role == Role.SUPERVISOR)))
    if h.area.owner not in recipients:
        recipients.append(h.area.owner)
    msg = (
        f"{h.risk_level} risk: {taxonomy.get(h.category_code).name} in {h.area.name} "
        f"(score {h.risk_score}, status {h.status.value})"
    )
    notify.send(db, recipients, h, msg, f"Hazard #{h.id}: {msg}. Target close {h.due_at:%Y-%m-%d}.", at=now)
    _event(db, h, actor, "alerted", f"Notified {', '.join(u.name for u in recipients)}", at=now)


# ---------------------------------------------------------------- stage 2: close and document


def plan_action(
    db: Session,
    h: Hazard,
    actor: User,
    planned_action: str,
    owner_id: int | None = None,
    due: datetime | None = None,
    at: datetime | None = None,
) -> Hazard:
    """OPEN -> PLANNED: a corrective action with an action owner (default: Area Owner) and a deadline
    (default: the target date from the risk band)."""
    _require_state(h, {Status.OPEN}, "plan an action for")
    if not can_act_on(actor, h):
        raise PermissionDenied("Only the Area Owner or a supervisor can plan actions")
    _check_move(h, Status.PLANNED)
    if not planned_action.strip():
        raise WorkflowError("Planned action cannot be empty")
    now = at or utcnow()
    owner = db.get(User, owner_id) if owner_id is not None else h.area.owner
    if owner is None:
        raise WorkflowError("Unknown action owner")
    due = due or h.due_at
    if due is not None and due <= now:
        raise WorkflowError("The action deadline must be in the future")
    h.planned_action, h.action_owner_id, h.action_due_at = planned_action.strip(), owner.id, due
    note = f"{h.planned_action} (owner {owner.name}, due {due:%Y-%m-%d})" if due else h.planned_action
    _move(db, h, actor, Status.PLANNED, "planned", note, at=now)
    db.flush()
    return h


def close(
    db: Session, h: Hazard, actor: User, action: str, photo_path: str | None = None, at: datetime | None = None
) -> Hazard:
    """OPEN/PLANNED -> PENDING_VERIFICATION: the owner documents what was done; someone else verifies it."""
    _require_state(h, {Status.OPEN, Status.PLANNED}, "close")
    if not can_act_on(actor, h):
        raise PermissionDenied("Only the Area Owner or a supervisor can close this hazard")
    _check_move(h, Status.PENDING_VERIFICATION)
    if not action.strip():
        raise WorkflowError("Describe the action taken to close the hazard")
    now = at or utcnow()
    h.closed_at, h.closed_by_id = now, actor.id
    h.closure_action, h.closure_photo_path = action.strip(), photo_path
    _move(db, h, actor, Status.PENDING_VERIFICATION, "closed", h.closure_action, at=now)
    db.flush()
    return h


def can_verify(user: User, h: Hazard) -> bool:
    """A supervisor or the reporter, but never the person who closed it (four-eyes principle)."""
    return user.role == Role.SUPERVISOR or user.id == h.reporter_id


def verify(db: Session, h: Hazard, actor: User, note: str = "", at: datetime | None = None) -> Hazard:
    """PENDING_VERIFICATION -> CLOSED."""
    _require_state(h, {Status.PENDING_VERIFICATION}, "verify")
    if not can_verify(actor, h) or actor.id == h.closed_by_id:
        raise PermissionDenied("A supervisor or the reporter, not the person who closed it, must verify the closure")
    now = at or utcnow()
    _move(db, h, actor, Status.CLOSED, "verified", note.strip() or "Closure verified", at=now)
    h.verified_at, h.verified_by_id = now, actor.id
    db.flush()
    return h


def reject(db: Session, h: Hazard, actor: User, reason: str, at: datetime | None = None) -> Hazard:
    """PENDING_VERIFICATION -> OPEN: the closure was not good enough. A reason is mandatory."""
    _require_state(h, {Status.PENDING_VERIFICATION}, "reject the closure of")
    if not can_verify(actor, h) or actor.id == h.closed_by_id:
        raise PermissionDenied("A supervisor or the reporter, not the person who closed it, must review the closure")
    if not reason.strip():
        raise WorkflowError("Give a reason for rejecting the closure")
    _move(db, h, actor, Status.OPEN, "rejected", reason.strip(), at=at)
    _clear_closure(h)
    db.flush()
    return h


def reopen(db: Session, h: Hazard, actor: User, reason: str, at: datetime | None = None) -> Hazard:
    """CLOSED -> OPEN, e.g. when the hazard recurs. A reason is mandatory; the earlier closure stays in the audit trail."""
    _require_state(h, {Status.CLOSED}, "reopen")
    if not can_verify(actor, h):
        raise PermissionDenied("Only a supervisor or the reporter can reopen a hazard")
    if not reason.strip():
        raise WorkflowError("Give a reason for reopening the hazard")
    now = at or utcnow()
    _move(db, h, actor, Status.OPEN, "reopened", reason.strip(), at=now)
    _clear_closure(h)
    # A reopened hazard gets a fresh target date from its risk band and starts escalation again.
    h.due_at = now + timedelta(days=risk.score(h.consequence, h.likelihood).target_days)
    h.escalation_level = 0
    db.flush()
    return h


# ---------------------------------------------------------------- stage 3: dashboard


def _open(db: Session):
    return select(Hazard).where(Hazard.status.in_(ACTIVE))


def dashboard(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    since90 = now - timedelta(days=90)
    confirmed = list(db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT)))
    open_ = [h for h in confirmed if h.status in ACTIVE]
    verified = [h for h in confirmed if h.status == Status.CLOSED and h.closed_at]  # closure performance: verified only
    closed90 = [h for h in verified if h.closed_at >= since90]
    days_to_close = [(h.closed_at - h.created_at).total_seconds() / 86400 for h in closed90]

    ai_judged = [h for h in confirmed if h.ai_accepted is not None]
    kpis = {
        "open": len(open_),
        "open_high": sum(1 for h in open_ if h.risk_level in ("High", "Extreme")),
        "overdue": sum(1 for h in open_ if h.status in AWAITING_ACTION and h.due_at and h.due_at < now),
        "pending_verification": sum(1 for h in open_ if h.status == Status.PENDING_VERIFICATION),
        "reported_30d": sum(1 for h in confirmed if h.created_at >= now - timedelta(days=30)),
        "closed_30d": sum(1 for h in verified if h.closed_at >= now - timedelta(days=30)),
        "median_days_to_close": round(median(days_to_close), 1) if days_to_close else None,
        "ai_acceptance": round(100 * sum(h.ai_accepted for h in ai_judged) / len(ai_judged)) if ai_judged else None,
    }

    # Heat map: open risk per area (sum of open risk scores) + 90-day history
    areas = list(db.scalars(select(Area).order_by(Area.id)))
    max_heat = max([sum(h.risk_score or 0 for h in open_ if h.area_id == a.id) for a in areas] + [1])
    area_rows = []
    for a in areas:
        a_open = [h for h in open_ if h.area_id == a.id]
        heat = sum(h.risk_score or 0 for h in a_open)
        worst = max(a_open, key=lambda h: h.risk_score or 0, default=None)
        area_rows.append(
            {
                "area": a,
                "open": len(a_open),
                "heat": heat,
                "heat_ratio": heat / max_heat,
                "worst_level": worst.risk_level if worst else None,
                "reported_90d": sum(1 for h in confirmed if h.area_id == a.id and h.created_at >= since90),
            }
        )

    # Weekly trend (12 weeks): reported vs closed
    weeks = []
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(11, -1, -1):
        ws, we = start - timedelta(weeks=i), start - timedelta(weeks=i - 1)
        weeks.append(
            {
                "label": ws.strftime("%d %b"),
                "reported": sum(1 for h in confirmed if ws <= h.created_at < we),
                "closed": sum(1 for h in verified if ws <= h.closed_at < we),
            }
        )

    by_cat = Counter(h.category_code for h in confirmed if h.created_at >= since90)
    by_level = Counter(h.risk_level for h in open_)
    return {
        "kpis": kpis,
        "areas": area_rows,
        "weeks": weeks,
        "by_category": [(taxonomy.get(c).name, n) for c, n in by_cat.most_common()],
        "by_level": {lvl: by_level.get(lvl, 0) for lvl in ("Extreme", "High", "Medium", "Low")},
    }


def area_overview(db: Session, area: Area) -> dict:
    """What a field operator sees before entering an area."""
    open_ = sorted((h for h in area.hazards if h.status in ACTIVE), key=lambda h: h.risk_score or 0, reverse=True)
    recent_closed = sorted(
        (h for h in area.hazards if h.status == Status.CLOSED), key=lambda h: h.closed_at, reverse=True
    )[:5]
    return {"area": area, "open": open_, "recent_closed": recent_closed}


def repeat_hotspots(db: Session, now: datetime | None = None, min_count: int = 3) -> list[dict]:
    """Area x category pairs with repeated reports in the look-back window (problem 1: connect the cases)."""
    now = now or utcnow()
    since = now - timedelta(days=risk.lookback_days())
    counts: dict[tuple[int, str], int] = defaultdict(int)
    for h in db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT, Hazard.created_at >= since)):
        counts[(h.area_id, h.category_code)] += 1
    areas = {a.id: a for a in db.scalars(select(Area))}
    rows = [
        {"area": areas[a], "category": taxonomy.get(c).name, "count": n}
        for (a, c), n in counts.items()
        if n >= min_count
    ]
    return sorted(rows, key=lambda r: r["count"], reverse=True)


# ---------------------------------------------------------------- MLOps: monitoring the AI in production


def slo_config() -> dict:
    from .settings import PACKAGE_DIR

    return json.loads((PACKAGE_DIR / "config" / "slo.json").read_text())


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def ai_monitoring(db: Session, now: datetime | None = None) -> dict:
    """Production signals for the AI: latency, errors, how often reporters accept or correct it, and which
    corrections they make. A falling acceptance rate is an early warning of drift (new cameras, lighting,
    PPE models) and a reason to re-evaluate the model before trusting it further."""
    now = now or utcnow()
    slo = slo_config()
    since = now - timedelta(days=slo["window_days"])
    rows = list(db.scalars(select(Hazard).where(Hazard.ai_model.is_not(None), Hazard.created_at >= since)))
    confirmed = [h for h in rows if h.status != Status.DRAFT]
    latencies = [h.ai_latency_ms for h in rows if h.ai_latency_ms is not None and not h.ai_error]
    errors = sum(1 for h in rows if h.ai_error)
    judged = [h for h in confirmed if h.ai_accepted is not None]
    missed = [h for h in confirmed if h.ai_top_code is None]  # AI saw nothing, reporter reported a hazard
    acceptance = (sum(h.ai_accepted for h in judged) / len(judged)) if judged else None

    corrections = Counter(
        (h.ai_top_code or "nothing detected", h.category_code) for h in confirmed if h.ai_top_code != h.category_code
    )
    by_model: dict[str, dict] = {}
    for h in rows:
        m = by_model.setdefault(h.ai_model, {"reports": 0, "accepted": 0, "judged": 0, "lat": []})
        m["reports"] += 1
        if h.ai_accepted is not None:
            m["judged"] += 1
            m["accepted"] += int(h.ai_accepted)
        if h.ai_latency_ms is not None and not h.ai_error:
            m["lat"].append(h.ai_latency_ms)
    models = [
        {
            "model": k,
            "reports": v["reports"],
            "acceptance": v["accepted"] / v["judged"] if v["judged"] else None,
            "p95_ms": _pct(v["lat"], 95),
        }
        for k, v in sorted(by_model.items())
    ]

    weeks = []
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(7, -1, -1):
        ws, we = start - timedelta(weeks=i), start - timedelta(weeks=i - 1)
        wk = [
            h
            for h in db.scalars(
                select(Hazard).where(Hazard.ai_accepted.is_not(None), Hazard.created_at >= ws, Hazard.created_at < we)
            )
        ]
        weeks.append(
            {
                "label": ws.strftime("%d %b"),
                "n": len(wk),
                "acceptance": (sum(h.ai_accepted for h in wk) / len(wk)) if wk else None,
            }
        )

    p95 = _pct(latencies, 95)
    err_rate = errors / len(rows) if rows else 0.0
    enough = len(judged) >= slo["min_reports_for_alert"]
    checks = [
        {
            "name": "AI latency p95",
            "target": f"≤ {slo['ai_latency_p95_ms'] / 1000:.0f} s",
            "value": None if p95 is None else f"{p95 / 1000:.2f} s",
            "ok": None if p95 is None else p95 <= slo["ai_latency_p95_ms"],
        },
        {
            "name": "AI error rate",
            "target": f"≤ {100 * slo['ai_error_rate_max']:.0f}%",
            "value": f"{100 * err_rate:.1f}%" if rows else None,
            "ok": (err_rate <= slo["ai_error_rate_max"]) if rows else None,
        },
        {
            "name": "Reporter acceptance",
            "target": f"≥ {100 * slo['ai_acceptance_min']:.0f}%",
            "value": None if acceptance is None else f"{100 * acceptance:.0f}%",
            "ok": None if acceptance is None or not enough else acceptance >= slo["ai_acceptance_min"],
        },
    ]
    return {
        "window_days": slo["window_days"],
        "reports": len(rows),
        "confirmed": len(confirmed),
        "errors": errors,
        "acceptance": acceptance,
        "missed": len(missed),
        "latency": {"p50_ms": _pct(latencies, 50), "p95_ms": p95, "n": len(latencies)},
        "checks": checks,
        "models": models,
        "weeks": weeks,
        "corrections": [{"ai": a, "reporter": b, "n": n} for (a, b), n in corrections.most_common(8)],
    }


# ---------------------------------------------------------------- role home pages (Phase 3)

HIGH_LEVELS = ("High", "Extreme")
LEVEL_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Extreme": 4}


def role_home(db: Session, user: User, now: datetime | None = None) -> dict:
    """What each role needs to act on first. Every list is computed on the server from the same data as the
    dashboard; nothing here is a rating of how safe an area is."""
    now = now or utcnow()
    active = list(db.scalars(select(Hazard).where(Hazard.status.in_(ACTIVE))))
    by_risk = sorted(active, key=lambda h: (-(h.risk_score or 0), h.due_at or now))
    out: dict = {"role": user.role.value, "now": now}
    if user.role == Role.REPORTER:
        mine = db.scalars(select(Hazard).where(Hazard.reporter_id == user.id).order_by(Hazard.created_at.desc()))
        out["my_reports"] = list(mine.all())[:20]
        out["to_verify"] = [h for h in active if h.status == Status.PENDING_VERIFICATION and h.reporter_id == user.id]
    elif user.role == Role.AREA_OWNER:
        mine = [h for h in active if h.status in AWAITING_ACTION and user.id in (h.assignee_id, h.action_owner_id)]
        out["my_work"] = sorted(mine, key=lambda h: h.due_at or now)
        out["due_soon"] = [h for h in out["my_work"] if h.due_at and h.due_at <= now + timedelta(days=3)]
        out["waiting_verification"] = [
            h for h in active if h.status == Status.PENDING_VERIFICATION and h.closed_by_id == user.id
        ]
    elif user.role == Role.SUPERVISOR:
        out["to_verify"] = sorted(
            (h for h in active if h.status == Status.PENDING_VERIFICATION and h.closed_by_id != user.id),
            key=lambda h: h.closed_at or now,
        )
        out["urgent"] = [h for h in by_risk if h.risk_level in HIGH_LEVELS]
        out["escalated"] = sorted(
            (h for h in active if (h.escalation_level or 0) > 0), key=lambda h: -(h.escalation_level or 0)
        )
    else:  # manager
        out["priorities"] = by_risk[:8]
        out["overdue"] = [h for h in by_risk if h.status in AWAITING_ACTION and h.due_at and h.due_at < now]
        out["closure"] = closure_performance(db, now)
        out["weeks"] = dashboard(db, now)["weeks"]
    return out


def closure_performance(db: Session, now: datetime | None = None, window_days: int = 90) -> dict:
    """Verified closures in the window: how many, how many by their target date, median days to verified close."""
    now = now or utcnow()
    since = now - timedelta(days=window_days)
    done = [
        h
        for h in db.scalars(select(Hazard).where(Hazard.status == Status.CLOSED, Hazard.verified_at.is_not(None)))
        if h.verified_at >= since
    ]
    on_time = sum(1 for h in done if h.closed_at and h.due_at and h.closed_at <= h.due_at)
    days = [(h.verified_at - h.created_at).total_seconds() / 86400 for h in done]
    reopened = db.scalar(
        select(func.count()).select_from(HazardEvent).where(HazardEvent.kind == "reopened", HazardEvent.at >= since)
    )
    return {
        "window_days": window_days,
        "verified_closures": len(done),
        "on_time": on_time,
        "on_time_share": on_time / len(done) if done else None,
        "median_days_to_verified_close": round(median(days), 1) if days else None,
        "reopened": reopened,
    }


# ---------------------------------------------------------------- refinery plan view (Phase 3)

OVERLAYS = ("open_risk", "overdue", "reports")
WINDOWS = (30, 90, 180)


def _pin_groups(pool: list[Hazard]) -> list[list[Hazard]]:
    """Group nearby active cases within a unit. The highest-risk member anchors and colours each marker."""
    pinned = (h for h in pool if h.status in ACTIVE and h.x is not None and h.y is not None)
    groups: list[list[Hazard]] = []
    for hazard in sorted(pinned, key=lambda h: (-(h.risk_score or 0), h.id)):
        for group in groups:
            anchor = group[0]
            if hazard.area_id == anchor.area_id and (hazard.x - anchor.x) ** 2 + (hazard.y - anchor.y) ** 2 <= 30**2:
                group.append(hazard)
                break
        else:
            groups.append([hazard])
    return groups


def site_overview(
    db: Session,
    overlay: str = "open_risk",
    window_days: int = 90,
    min_level: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Per-area values for the plan view. Each overlay states its calculation, time window and denominator.
    An area with nothing recorded is labelled as such – never as safe – and report volume is not shown as danger."""
    now = now or utcnow()
    overlay = overlay if overlay in OVERLAYS else "open_risk"
    window_days = window_days if window_days in WINDOWS else 90
    since = now - timedelta(days=window_days)
    floor = LEVEL_ORDER.get(min_level or "", 0)

    def level_ok(h: Hazard) -> bool:
        return LEVEL_ORDER.get(h.risk_level or "", 0) >= floor

    confirmed = [h for h in db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT)) if level_ok(h)]
    if overlay == "open_risk":
        pool = [h for h in confirmed if h.status in ACTIVE and h.created_at >= since]
        value = lambda hs: sum(h.risk_score or 0 for h in hs)  # noqa: E731
        basis = (
            f"Sum of risk scores (consequence × likelihood) of active hazards – open, planned or awaiting "
            f"verification – reported in the last {window_days} days, per area."
        )
        empty = "No recorded hazards in this window"
        scale = "risk"
    elif overlay == "overdue":
        pool = [h for h in confirmed if h.status in AWAITING_ACTION and h.due_at and h.due_at < now]
        value = len
        basis = "Number of open or planned hazards past their target close date (any report date), per area."
        empty = "No overdue hazards"
        scale = "risk"
    else:
        pool = [h for h in confirmed if h.created_at >= since]
        value = len
        basis = (
            f"Number of confirmed reports in the last {window_days} days, per area. Report volume reflects how much "
            "people report – it is not a measure of danger."
        )
        empty = "No reports in this window"
        scale = "neutral"
    areas = list(db.scalars(select(Area).order_by(Area.id)))
    rows = []
    for a in areas:
        hs = [h for h in pool if h.area_id == a.id]
        v = value(hs)
        rows.append(
            {
                "code": a.code,
                "name": a.name,
                "x": a.x,
                "y": a.y,
                "w": a.w,
                "h": a.h,
                "value": v,
                "count": len(hs),
                "label": f"{v}" if v else empty,
            }
        )
    total = sum(r["value"] for r in rows)
    peak = max([r["value"] for r in rows] + [1])
    for r in rows:
        r["ratio"] = r["value"] / peak
    return {
        "overlay": overlay,
        "window_days": window_days,
        "min_level": min_level if floor else None,
        "basis": basis,
        "scale": scale,
        "areas": rows,
        "site_total": total,
        "hazards_counted": len(pool),
        "pin_groups": _pin_groups(pool),
    }
