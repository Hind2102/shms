"""Server-rendered HTML pages (mobile-friendly, no JavaScript build step)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import area_profiles, auth, escalate, heatmap, policy, risk, services, site_layout, taxonomy
from ..db import get_session
from ..detection import DetectorResult, get_detector
from ..models import Area, Hazard, Notification, Role, Status, User, utcnow
from ..settings import PACKAGE_DIR, get_settings
from .deps import MAX_UPLOAD_MB, PHOTO_NAME, PhotoRejected, current_user_optional, photo_file, save_photo, store_photo

log = logging.getLogger("shms")
router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.globals.update(
    taxonomy=taxonomy,
    risk=risk,
    Status=Status,
    Role=Role,
    site_layout=site_layout,
    get_settings=get_settings,
    area_profiles=area_profiles,
)
templates.env.filters["cat"] = lambda code: taxonomy.get(code).name if code else "Not classified"
templates.env.filters["ppe"] = lambda code: taxonomy.get(code).ppe
templates.env.filters["dt"] = lambda d: d.strftime("%d %b %Y %H:%M") if d else ""
templates.env.filters["localtime"] = lambda d: d + timedelta(hours=get_settings().site_utc_offset_h) if d else d
templates.env.filters["fromjson"] = lambda s: json.loads(s or "[]")
# Legacy closures have no control type: shown as "not recorded", never guessed.
templates.env.filters["control"] = lambda code: risk.control_types()[code]["name"] if code else "not recorded"


class LoginRequired(Exception):
    pass


def page_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise LoginRequired
    return user


def render(request: Request, name: str, user: User | None, db: Session, status_code: int = 200, **ctx) -> HTMLResponse:
    unread = 0
    if user is not None:
        _escalate_on_page_load(db)
        unread = db.query(Notification).filter_by(user_id=user.id, read=False).count()
    token = request.cookies.get(auth.CSRF_COOKIE)
    if not auth.csrf_valid(token, token):
        token = auth.new_csrf_token()
    resp = templates.TemplateResponse(
        request, name, {"user": user, "unread": unread, "csrf_token": token, **ctx}, status_code=status_code
    )
    resp.set_cookie(auth.CSRF_COOKIE, token, httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return resp


class CsrfError(Exception):
    pass


async def csrf_protect(request: Request) -> None:
    """Every HTML form POST must echo the CSRF cookie in its hidden csrf_token field (double-submit, signed)."""
    if request.method == "POST":
        form = await request.form()
        if not auth.csrf_valid(request.cookies.get(auth.CSRF_COOKIE), form.get("csrf_token")):
            raise CsrfError


# Applies to every route declared below (FastAPI copies router dependencies when a route is added).
router.dependencies.append(Depends(csrf_protect))


def _escalate_on_page_load(db: Session) -> None:
    """Overdue escalation also runs on page loads (at most once a minute), so a demo needs no scheduler.
    A failure here must never break the page; it is logged instead."""
    try:
        escalate.maybe_run(db)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("Escalation check failed")


def _hazard(db: Session, hazard_id: int, user: User | None = None) -> Hazard:
    """The hazard, or 404 if it does not exist or this user may not see it (no hint that it exists)."""
    h = db.get(Hazard, hazard_id)
    if h is None or (user is not None and not policy.can_view(user, h)):
        raise HTTPException(404, "Hazard not found")
    return h


# ------------------------------------------------------------------ sign in


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_session)):
    return render(request, "login.html", None, db)


@router.post("/login")
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_session),
):
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    if user is None or not auth.check_password(password, user.password_hash):
        # Same message whether the user exists or not.
        return render(request, "login.html", None, db, status_code=401, error="Wrong username or password.")
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        auth.SESSION_COOKIE,
        auth.sign_session(user.id),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=auth.SESSION_SECONDS,
    )
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


# ------------------------------------------------------------------ dashboard & areas


@router.get("/")
def home(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    """Role-specific home: the list this person has to act on first."""
    return render(request, "home.html", user, db, home=services.role_home(db, user))


@router.get("/site")
def site_plan(
    request: Request,
    window: str = "",
    category: str = "",
    status: str = "",
    unit: str = "",
    route: str = "",
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    """Weather-style risk heat map from live data, with the check-before-entering card for a chosen zone."""
    filters = heatmap.Filters.parse(window, category, status)
    heat = heatmap.compute(db, filters)
    selected = site_layout.REPORTING.get(unit)
    area = db.scalar(select(Area).where(Area.code == unit)) if selected else None
    detail = services.area_overview(db, area) if area else None
    if detail:
        now = utcnow()
        detail["overdue"] = sum(
            1 for h in detail["open"] if h.status in services.AWAITING_ACTION and h.due_at and h.due_at < now
        )
    flagged = site_layout.flagged_areas(db) if route == "1" and area else set()
    path = site_layout.walk_route(unit, flagged) if route == "1" and area else []
    return render(
        request,
        "site.html",
        user,
        db,
        heat=heat,
        v={"pin_groups": services.pin_groups(heat.hazards), "overlay": "heat"},
        statuses=heatmap.STATUSES,
        windows=heatmap.WINDOWS,
        calculation=heatmap.CALCULATION,
        zones=site_layout.REPORTING,
        detail=detail,
        route_requested=route == "1",
        path=path,
        flagged=flagged,
    )


@router.get("/site/heat.png")
def site_heat(
    window: str = "",
    category: str = "",
    status: str = "",
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    """The heat layer for the current filters, computed from the live database on every request."""
    heat = heatmap.compute(db, heatmap.Filters.parse(window, category, status))
    return Response(heatmap.png(heat), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/dashboard")
def dashboard(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    d = services.dashboard(db)
    recent = list(
        db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT).order_by(Hazard.created_at.desc()).limit(8))
    )
    return render(request, "dashboard.html", user, db, d=d, recent=recent, hotspots=services.repeat_hotspots(db)[:6])


@router.get("/areas/{code}")
def area_page(code: str, request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    area = db.scalar(select(Area).where(Area.code == code))
    if area is None:
        raise HTTPException(404, "Area not found")
    return render(request, "area.html", user, db, **services.area_overview(db, area))


@router.get("/monitoring")
def monitoring(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    from .telemetry import snapshot

    calls = [r for r in snapshot() if r["count"]]
    for r in calls:
        r["avg_ms"] = 1000 * r["seconds"] / r["count"]
    return render(
        request,
        "monitoring.html",
        user,
        db,
        m=services.ai_monitoring(db),
        calls=sorted(calls, key=lambda r: -r["count"])[:12],
    )


@router.get("/board")
def board(request: Request, theme: str = "light", user: User = Depends(page_user), db: Session = Depends(get_session)):
    """Read-only control-room view for a large screen: open-risk map, High/Extreme list, overdue count.
    Refreshes every 60 s; sign-in required like every other page."""
    now = utcnow()
    active = list(db.scalars(select(Hazard).where(Hazard.status.in_(services.ACTIVE))))
    urgent = sorted(
        (h for h in active if h.risk_level in services.HIGH_LEVELS), key=lambda h: (-(h.risk_score or 0), h.id)
    )
    overdue = sum(1 for h in active if h.status in services.AWAITING_ACTION and h.due_at and h.due_at < now)
    return render(
        request,
        "board.html",
        user,
        db,
        heat=heatmap.compute(db, heatmap.Filters(), now=now),
        calculation=heatmap.CALCULATION,
        zones=site_layout.REPORTING,
        urgent=urgent,
        overdue=overdue,
        active=len(active),
        now=now,
        dark=theme == "dark",
        refresh_s=60,
    )


@router.get("/matrix")
def matrix(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    return render(request, "matrix.html", user, db, table=risk.matrix_table())


# ------------------------------------------------------------------ stage 1: report and score


def _report_form(request: Request, user: User, db: Session, idem_key: str, **fields) -> HTMLResponse:
    return render(
        request,
        "report.html",
        user,
        db,
        areas=list(db.scalars(select(Area).order_by(Area.name))),
        bounds=site_layout.REPORTING,
        idem_key=idem_key,
        max_upload_mb=MAX_UPLOAD_MB,
        **fields,
    )


@router.get("/report")
def report_form(request: Request, area: str = "", user: User = Depends(page_user), db: Session = Depends(get_session)):
    # A fresh idempotency key per form: a double submit or a browser retry returns the same draft.
    # The area is pre-selected: ?area=CODE (from an area card), else the area of this reporter's last report.
    chosen = db.scalar(select(Area).where(Area.code == area)) if area else None
    if chosen is None:
        last = db.scalar(
            select(Hazard).where(Hazard.reporter_id == user.id).order_by(Hazard.created_at.desc()).limit(1)
        )
        chosen = last.area if last else None
    fields = {"area_id": chosen.id, "area_source": "link" if area and chosen else "last"} if chosen else {}
    return _report_form(request, user, db, uuid.uuid4().hex, **fields)


@router.post("/report")
async def report_submit(
    request: Request,
    area_id: int | None = Form(None),
    x: int | None = Form(None),
    y: int | None = Form(None),
    photo: UploadFile | None = File(None),
    idem_key: str = Form(""),
    device_lat: str = Form(""),
    device_lon: str = Form(""),
    device_accuracy: str = Form(""),
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    area = db.get(Area, area_id) if area_id is not None else None
    if area is None:
        return _report_form(
            request, user, db, idem_key, error="Choose the area where you saw the hazard.", status_code=422
        )
    fields = {"area_id": area.id, "x": x, "y": y}
    try:
        device = services.parse_device_location(device_lat, device_lon, device_accuracy)
        services.validate_pin(area, x, y)
        existing = services.replay_or_conflict(db, user, area, idem_key or None, x, y)
    except services.IdempotencyConflict as exc:
        return _report_form(request, user, db, uuid.uuid4().hex, error=str(exc), status_code=409, **fields)
    except services.WorkflowError as exc:
        return _report_form(request, user, db, idem_key, error=str(exc), status_code=422, **fields)
    if existing is not None:
        return RedirectResponse(f"/hazards/{existing.id}/confirm", status_code=303)
    try:
        name, capture = await store_photo(photo, capture=True)
    except PhotoRejected as exc:
        return _report_form(request, user, db, idem_key, error=exc.detail, status_code=exc.status_code, **fields)
    if name is None:
        return _report_form(request, user, db, idem_key, error="Please add a photo.", status_code=422, **fields)
    h = services.create_draft(
        db,
        user,
        area,
        name,
        run_detector(photo_file(name)),
        idem_key=idem_key or None,
        x=x,
        y=y,
        experimental=_experimental(photo_file(name)),
        capture=capture,
        device=device,
    )
    db.commit()
    return RedirectResponse(f"/hazards/{h.id}/confirm", status_code=303)


def run_detector(path) -> DetectorResult:
    """Analysis always gives the reporter a visible result: if the detector itself fails, the draft is still created
    and the confirm page says the AI could not analyse the photo, so the reporter classifies it by hand."""
    try:
        return get_detector().detect(path)
    except Exception as exc:  # noqa: BLE001 - any detector failure must not lose the report
        log.error("Detector failed on %s", path, exc_info=exc)
        return DetectorResult(model=get_settings().detector, suggestions=[], latency_ms=0.0, error="analysis failed")


def _experimental(path) -> list[dict]:
    """EXPERIMENTAL unsafe-condition observations, only when SHMS_EXPERIMENTAL_CONDITIONS=1."""
    from ..detection import conditions_vlm
    from ..settings import get_settings

    return conditions_vlm.observe(path) if get_settings().experimental_conditions else []


@router.get("/hazards/{hazard_id}/confirm")
def confirm_form(
    hazard_id: int,
    request: Request,
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
    error: str | None = None,
):
    h = _hazard(db, hazard_id, user)
    if h.status != Status.DRAFT:
        return RedirectResponse(f"/hazards/{h.id}", status_code=303)
    return render(
        request,
        "confirm.html",
        user,
        db,
        h=h,
        suggestions=json.loads(h.ai_suggestions or "[]"),
        consequences=risk.consequence_levels(),
        error=error,
    )


@router.post("/hazards/{hazard_id}/confirm")
async def confirm_submit(
    hazard_id: int,
    request: Request,
    category_code: str = Form(...),
    consequence: int = Form(...),
    description: str = Form(""),
    fixed_on_spot: bool = Form(False),
    closure_action: str = Form(""),
    closure_photo: UploadFile | None = File(None),
    control_type: str = Form(""),
    residual_consequence: str = Form(""),
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    h = _hazard(db, hazard_id, user)
    if h.status != Status.DRAFT:  # refuse before anything is stored (security review, Phase 1b)
        return RedirectResponse(
            f"/hazards/{h.id}?error=This report has already been confirmed and cannot be confirmed again.",
            status_code=303,
        )
    try:
        photo = await save_photo(closure_photo, prefix="closed_") if fixed_on_spot else None
        services.confirm(
            db,
            h,
            user,
            services.Confirmation(
                category_code,
                consequence,
                description,
                fixed_on_spot,
                closure_action,
                photo,
                control_type=control_type or None,
                residual_consequence=_level(residual_consequence),
            ),
        )
    except (services.WorkflowError, services.PermissionDenied, PhotoRejected) as exc:
        db.rollback()
        return render(
            request,
            "confirm.html",
            user,
            db,
            status_code=exc.status_code if isinstance(exc, PhotoRejected) else 200,
            h=h,
            suggestions=json.loads(h.ai_suggestions or "[]"),
            consequences=risk.consequence_levels(),
            error=exc.detail if isinstance(exc, PhotoRejected) else str(exc),
        )
    db.commit()
    return RedirectResponse(f"/hazards/{h.id}?created=1", status_code=303)


# ------------------------------------------------------------------ stage 2: close and document


@router.get("/hazards")
def hazard_list(
    request: Request,
    status: str = "",
    area: str = "",
    level: str = "",
    category: str = "",
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    q = select(Hazard).where(Hazard.status != Status.DRAFT).order_by(Hazard.created_at.desc())
    if status in {s.value for s in Status if s != Status.DRAFT}:
        q = q.where(Hazard.status == Status(status))
    if area:
        q = q.join(Area).where(Area.code == area)
    if level:
        q = q.where(Hazard.risk_level == level)
    if category:
        q = q.where(Hazard.category_code == category)
    hazards = list(db.scalars(q.limit(300)))
    areas = list(db.scalars(select(Area).order_by(Area.name)))
    return render(
        request,
        "hazards.html",
        user,
        db,
        hazards=hazards,
        areas=areas,
        f={"status": status, "area": area, "level": level, "category": category},
    )


@router.get("/queue")
def my_queue(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    q = select(Hazard).where(Hazard.status.in_(services.AWAITING_ACTION))
    if user.role != Role.SUPERVISOR:
        q = q.where(Hazard.assignee_id == user.id)
    hazards = sorted(db.scalars(q), key=lambda h: (-(h.risk_score or 0), h.due_at))
    # Closures this user may verify: supervisors all, reporters their own reports; never one they closed themselves.
    pq = select(Hazard).where(Hazard.status == Status.PENDING_VERIFICATION)
    if user.role != Role.SUPERVISOR:
        pq = pq.where(Hazard.reporter_id == user.id)
    to_verify = [h for h in db.scalars(pq.order_by(Hazard.closed_at)) if h.closed_by_id != user.id]
    return render(request, "queue.html", user, db, hazards=hazards, to_verify=to_verify)


@router.get("/hazards/{hazard_id}")
def hazard_detail(
    hazard_id: int,
    request: Request,
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
    created: int = 0,
    error: str | None = None,
):
    h = _hazard(db, hazard_id, user)
    if h.status == Status.DRAFT:
        return RedirectResponse(f"/hazards/{h.id}/confirm", status_code=303)
    return render(
        request,
        "hazard.html",
        user,
        db,
        h=h,
        can_act=services.can_act_on(user, h),
        can_verify=services.can_verify(user, h) and user.id != h.closed_by_id,
        can_reopen=services.can_verify(user, h),
        owners=list(
            db.scalars(select(User).where(User.role.in_([Role.AREA_OWNER, Role.SUPERVISOR])).order_by(User.id))
        ),
        suggestions=json.loads(h.ai_suggestions or "[]"),
        created=created,
        error=error,
    )


def _do(db: Session, h: Hazard, fn) -> RedirectResponse:
    """Run one workflow step; show the rule that refused it instead of failing."""
    try:
        fn()
    except (services.WorkflowError, services.PermissionDenied) as exc:
        db.rollback()
        return RedirectResponse(f"/hazards/{h.id}?error={exc}", status_code=303)
    db.commit()
    return RedirectResponse(f"/hazards/{h.id}", status_code=303)


@router.post("/hazards/{hazard_id}/plan")
def plan(
    hazard_id: int,
    planned_action: str = Form(...),
    owner_id: int | None = Form(None),
    due: str = Form(""),
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    h = _hazard(db, hazard_id, user)
    try:
        due_at = datetime.strptime(due, "%Y-%m-%d").replace(hour=17) if due else None
    except ValueError:
        return RedirectResponse(f"/hazards/{h.id}?error=Invalid deadline date", status_code=303)
    return _do(db, h, lambda: services.plan_action(db, h, user, planned_action, owner_id=owner_id, due=due_at))


@router.post("/hazards/{hazard_id}/verify")
def verify(hazard_id: int, note: str = Form(""), user: User = Depends(page_user), db: Session = Depends(get_session)):
    h = _hazard(db, hazard_id, user)
    return _do(db, h, lambda: services.verify(db, h, user, note))


@router.post("/hazards/{hazard_id}/reject")
def reject(hazard_id: int, reason: str = Form(""), user: User = Depends(page_user), db: Session = Depends(get_session)):
    h = _hazard(db, hazard_id, user)
    return _do(db, h, lambda: services.reject(db, h, user, reason))


@router.post("/hazards/{hazard_id}/reopen")
def reopen(hazard_id: int, reason: str = Form(""), user: User = Depends(page_user), db: Session = Depends(get_session)):
    h = _hazard(db, hazard_id, user)
    return _do(db, h, lambda: services.reopen(db, h, user, reason))


def _level(value: str) -> int | None:
    """A 1-5 level from a form field; anything else is None and rejected by the service with a clear message."""
    return int(value) if value.strip().isdigit() else None


@router.post("/hazards/{hazard_id}/close")
async def close(
    hazard_id: int,
    action: str = Form(...),
    control_type: str = Form(""),
    residual_consequence: str = Form(""),
    photo: UploadFile | None = File(None),
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    h = _hazard(db, hazard_id, user)
    try:
        name = await save_photo(photo, prefix="closed_")
        services.close(
            db,
            h,
            user,
            action,
            name,
            control_type=control_type or None,
            residual_consequence=_level(residual_consequence),
        )
    except (services.WorkflowError, services.PermissionDenied, PhotoRejected) as exc:
        db.rollback()
        message = exc.detail if isinstance(exc, PhotoRejected) else str(exc)
        return RedirectResponse(f"/hazards/{h.id}?error={quote(message)}", status_code=303)
    db.commit()
    return RedirectResponse(f"/hazards/{h.id}", status_code=303)


# ------------------------------------------------------------------ notifications


@router.get("/notifications")
def notifications(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    items = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(50)
        )
    )
    resp = render(request, "notifications.html", user, db, items=items)
    for n in items:
        n.read = True
    db.commit()
    return resp


# ------------------------------------------------------------------ photos (replaces the public /uploads folder)


@router.get("/photos/{name}")
def photo(name: str, user: User = Depends(page_user), db: Session = Depends(get_session)):
    if not PHOTO_NAME.match(name):
        raise HTTPException(404, "Not found")
    owner = db.scalar(select(Hazard).where((Hazard.photo_path == name) | (Hazard.closure_photo_path == name)))
    path = photo_file(name)
    if not policy.can_view_photo(user, owner) or not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
