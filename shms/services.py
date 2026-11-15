"""Business logic: the hazard workflow, risk scoring, routing and dashboard figures.

Web and API routes are thin wrappers around these functions, so the whole
workflow can be tested without HTTP.

Workflow (state machine)::

    DRAFT --confirm(fixed_on_spot=False)--> OPEN --close--> CLOSED
      \\--confirm(fixed_on_spot=True)----------------------> CLOSED
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
from .models import Area, Hazard, HazardEvent, Notification, Role, Status, User, utcnow

ALLOWED_TRANSITIONS: dict[Status, set[Status]] = {
    Status.DRAFT: {Status.OPEN, Status.CLOSED},
    Status.OPEN: {Status.CLOSED},
    Status.CLOSED: set(),
}


class WorkflowError(ValueError):
    """Invalid input or an illegal state transition."""


class PermissionDenied(PermissionError):
    pass


# ---------------------------------------------------------------- helpers

def _transition(h: Hazard, new: Status) -> None:
    if new not in ALLOWED_TRANSITIONS[h.status]:
        raise WorkflowError(f"Cannot move hazard #{h.id} from {h.status.value} to {new.value}")
    h.status = new


def _event(db: Session, h: Hazard, actor: User, kind: str, note: str = "", at: datetime | None = None) -> None:
    db.add(HazardEvent(hazard=h, actor_id=actor.id, kind=kind, note=note, at=at or utcnow()))


def can_act_on(user: User, h: Hazard) -> bool:
    """Area Owner of the hazard's area, its assignee, or any supervisor."""
    return user.role == Role.SUPERVISOR or user.id in {h.assignee_id, h.area.owner_id}


def similar_count(db: Session, area_id: int, category_code: str, now: datetime,
                  exclude_id: int | None = None) -> int:
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

def create_draft(db: Session, reporter: User, area: Area, photo_path: str | None,
                 result: DetectorResult | None, at: datetime | None = None) -> Hazard:
    h = Hazard(area=area, reporter_id=reporter.id, status=Status.DRAFT, photo_path=photo_path,
               created_at=at or utcnow())
    if result is not None:
        # The AI checks the photo against the PPE this area requires; anything else is kept for
        # traceability but marked as not required and never pre-selected.
        required = set(area.check_codes)
        h.ai_model = result.model
        h.ai_latency_ms = round(result.latency_ms, 1)
        h.ai_error = result.error
        h.ai_suggestions = json.dumps([{**s.to_dict(), "required": s.code in required} for s in result.suggestions])
        top = max((s for s in result.suggestions if s.code in required), key=lambda s: s.confidence, default=None)
        h.ai_top_code = top.code if top else None
    db.add(h)
    db.flush()
    _event(db, h, reporter, "reported",
           f"AI ({h.ai_model}) suggested {h.ai_top_code or 'no PPE hazard'}" if result else "Reported without AI",
           at=h.created_at)
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
    if actor.id != h.reporter_id and actor.role != Role.SUPERVISOR:
        raise PermissionDenied("Only the reporter can confirm this report")
    if c.category_code not in taxonomy.categories():
        raise WorkflowError(f"Unknown hazard category: {c.category_code!r}")
    if c.category_code not in h.area.check_codes:
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
    _event(db, h, actor, "confirmed",
           f"{taxonomy.get(c.category_code).name}; C{r.consequence} x L{r.likelihood} = {r.score} ({r.level})", at=now)

    if c.fixed_on_spot:
        _transition(h, Status.CLOSED)
        h.closed_on_spot = True
        h.closed_at, h.closed_by_id = now, actor.id
        h.closure_action = c.closure_action.strip()
        h.closure_photo_path = c.closure_photo_path
        _event(db, h, actor, "closed", f"Fixed on the spot: {h.closure_action}", at=now)
    else:
        _transition(h, Status.OPEN)
        h.assignee_id = h.area.owner_id
        _event(db, h, actor, "assigned", f"Routed to Area Owner {h.area.owner.name}", at=now)

    if risk.is_alert_level(r.level):
        _alert(db, h, actor, now)
    db.flush()
    return h


def _alert(db: Session, h: Hazard, actor: User, now: datetime) -> None:
    recipients = list(db.scalars(select(User).where(User.role == Role.SUPERVISOR)))
    if h.area.owner not in recipients:
        recipients.append(h.area.owner)
    msg = (f"{h.risk_level} risk: {taxonomy.get(h.category_code).name} in {h.area.name} "
           f"(score {h.risk_score}, status {h.status.value})")
    for u in recipients:
        db.add(Notification(user_id=u.id, hazard=h, message=msg, created_at=now))
    _event(db, h, actor, "alerted", f"Notified {', '.join(u.name for u in recipients)}", at=now)


# ---------------------------------------------------------------- stage 2: close and document

def plan_action(db: Session, h: Hazard, actor: User, planned_action: str) -> Hazard:
    if h.status != Status.OPEN:
        raise WorkflowError("Actions can only be planned for open hazards")
    if not can_act_on(actor, h):
        raise PermissionDenied("Only the Area Owner or a supervisor can plan actions")
    if not planned_action.strip():
        raise WorkflowError("Planned action cannot be empty")
    h.planned_action = planned_action.strip()
    _event(db, h, actor, "planned", h.planned_action)
    db.flush()
    return h


def close(db: Session, h: Hazard, actor: User, action: str, photo_path: str | None = None,
          at: datetime | None = None) -> Hazard:
    if not can_act_on(actor, h):
        raise PermissionDenied("Only the Area Owner or a supervisor can close this hazard")
    if not action.strip():
        raise WorkflowError("Describe the action taken to close the hazard")
    now = at or utcnow()
    _transition(h, Status.CLOSED)
    h.closed_at, h.closed_by_id = now, actor.id
    h.closure_action, h.closure_photo_path = action.strip(), photo_path
    _event(db, h, actor, "closed", h.closure_action, at=now)
    db.flush()
    return h


# ---------------------------------------------------------------- stage 3: dashboard

def _open(db: Session):
    return select(Hazard).where(Hazard.status == Status.OPEN)


def dashboard(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    since90 = now - timedelta(days=90)
    confirmed = list(db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT)))
    open_ = [h for h in confirmed if h.status == Status.OPEN]
    closed90 = [h for h in confirmed if h.status == Status.CLOSED and h.closed_at and h.closed_at >= since90]
    days_to_close = [(h.closed_at - h.created_at).total_seconds() / 86400 for h in closed90]

    ai_judged = [h for h in confirmed if h.ai_accepted is not None]
    kpis = {
        "open": len(open_),
        "open_high": sum(1 for h in open_ if h.risk_level in ("High", "Extreme")),
        "overdue": sum(1 for h in open_ if h.due_at and h.due_at < now),
        "reported_30d": sum(1 for h in confirmed if h.created_at >= now - timedelta(days=30)),
        "closed_30d": sum(1 for h in confirmed if h.closed_at and h.closed_at >= now - timedelta(days=30)),
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
        area_rows.append({
            "area": a, "open": len(a_open), "heat": heat, "heat_ratio": heat / max_heat,
            "worst_level": worst.risk_level if worst else None,
            "reported_90d": sum(1 for h in confirmed if h.area_id == a.id and h.created_at >= since90),
        })

    # Weekly trend (12 weeks): reported vs closed
    weeks = []
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(11, -1, -1):
        ws, we = start - timedelta(weeks=i), start - timedelta(weeks=i - 1)
        weeks.append({
            "label": ws.strftime("%d %b"),
            "reported": sum(1 for h in confirmed if ws <= h.created_at < we),
            "closed": sum(1 for h in confirmed if h.closed_at and ws <= h.closed_at < we),
        })

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
    open_ = sorted((h for h in area.hazards if h.status == Status.OPEN),
                   key=lambda h: h.risk_score or 0, reverse=True)
    recent_closed = sorted((h for h in area.hazards if h.status == Status.CLOSED),
                           key=lambda h: h.closed_at, reverse=True)[:5]
    return {"area": area, "open": open_, "recent_closed": recent_closed}


def repeat_hotspots(db: Session, now: datetime | None = None, min_count: int = 3) -> list[dict]:
    """Area x category pairs with repeated reports in the look-back window (problem 1: connect the cases)."""
    now = now or utcnow()
    since = now - timedelta(days=risk.lookback_days())
    counts: dict[tuple[int, str], int] = defaultdict(int)
    for h in db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT, Hazard.created_at >= since)):
        counts[(h.area_id, h.category_code)] += 1
    areas = {a.id: a for a in db.scalars(select(Area))}
    rows = [{"area": areas[a], "category": taxonomy.get(c).name, "count": n}
            for (a, c), n in counts.items() if n >= min_count]
    return sorted(rows, key=lambda r: r["count"], reverse=True)
