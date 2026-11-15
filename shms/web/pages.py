"""Server-rendered HTML pages (mobile-friendly, no JavaScript build step)."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import risk, services, taxonomy
from ..db import get_session
from ..detection import get_detector
from ..models import Area, Hazard, Notification, Role, Status, User
from ..settings import PACKAGE_DIR
from .deps import COOKIE, current_user_optional, photo_file, save_photo

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.globals.update(taxonomy=taxonomy, risk=risk, Status=Status, Role=Role)
templates.env.filters["cat"] = lambda code: taxonomy.get(code).name if code else "Not classified"
templates.env.filters["ppe"] = lambda code: taxonomy.get(code).ppe
templates.env.filters["dt"] = lambda d: d.strftime("%d %b %Y %H:%M") if d else ""
templates.env.filters["fromjson"] = lambda s: json.loads(s or "[]")


class LoginRequired(Exception):
    pass


def page_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise LoginRequired
    return user


def render(request: Request, name: str, user: User | None, db: Session, **ctx) -> HTMLResponse:
    unread = 0
    if user is not None:
        unread = db.query(Notification).filter_by(user_id=user.id, read=False).count()
    return templates.TemplateResponse(request, name, {"user": user, "unread": unread, **ctx})


def _hazard(db: Session, hazard_id: int) -> Hazard:
    h = db.get(Hazard, hazard_id)
    if h is None:
        raise HTTPException(404, "Hazard not found")
    return h


# ------------------------------------------------------------------ sign in


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_session)):
    users = list(db.scalars(select(User).order_by(User.id)))
    return render(request, "login.html", None, db, users=users)


@router.post("/login")
def login(user_id: int = Form(...)):
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE, str(user_id), httponly=True, samesite="lax")
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


# ------------------------------------------------------------------ dashboard & areas


@router.get("/")
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


@router.get("/matrix")
def matrix(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    return render(request, "matrix.html", user, db, table=risk.matrix_table())


# ------------------------------------------------------------------ stage 1: report and score


@router.get("/report")
def report_form(request: Request, user: User = Depends(page_user), db: Session = Depends(get_session)):
    areas = list(db.scalars(select(Area).order_by(Area.name)))
    # A fresh idempotency key per form: a double submit or a browser retry returns the same draft.
    return render(request, "report.html", user, db, areas=areas, error=None, idem_key=uuid.uuid4().hex)


@router.post("/report")
async def report_submit(
    request: Request,
    area_id: int = Form(...),
    photo: UploadFile | None = File(None),
    idem_key: str = Form(""),
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    area = db.get(Area, area_id)
    if area is None:
        raise HTTPException(422, "Unknown area")
    areas = list(db.scalars(select(Area).order_by(Area.name)))
    try:
        existing = services.replay_or_conflict(db, user, area, idem_key or None)
    except services.IdempotencyConflict as exc:
        return render(request, "report.html", user, db, areas=areas, error=str(exc), idem_key=uuid.uuid4().hex)
    if existing is not None:
        return RedirectResponse(f"/hazards/{existing.id}/confirm", status_code=303)
    name = await save_photo(photo)
    if name is None:
        return render(request, "report.html", user, db, areas=areas, error="Please add a photo.", idem_key=idem_key)
    h = services.create_draft(db, user, area, name, get_detector().detect(photo_file(name)), idem_key=idem_key or None)
    db.commit()
    return RedirectResponse(f"/hazards/{h.id}/confirm", status_code=303)


@router.get("/hazards/{hazard_id}/confirm")
def confirm_form(
    hazard_id: int,
    request: Request,
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
    error: str | None = None,
):
    h = _hazard(db, hazard_id)
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
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    h = _hazard(db, hazard_id)
    try:
        photo = await save_photo(closure_photo, prefix="closed_") if fixed_on_spot else None
        services.confirm(
            db,
            h,
            user,
            services.Confirmation(category_code, consequence, description, fixed_on_spot, closure_action, photo),
        )
    except (services.WorkflowError, services.PermissionDenied) as exc:
        db.rollback()
        return render(
            request,
            "confirm.html",
            user,
            db,
            h=h,
            suggestions=json.loads(h.ai_suggestions or "[]"),
            consequences=risk.consequence_levels(),
            error=str(exc),
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
    if status:
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
    q = select(Hazard).where(Hazard.status == Status.OPEN)
    if user.role != Role.SUPERVISOR:
        q = q.where(Hazard.assignee_id == user.id)
    hazards = sorted(db.scalars(q), key=lambda h: (-(h.risk_score or 0), h.due_at))
    return render(request, "queue.html", user, db, hazards=hazards)


@router.get("/hazards/{hazard_id}")
def hazard_detail(
    hazard_id: int,
    request: Request,
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
    created: int = 0,
    error: str | None = None,
):
    h = _hazard(db, hazard_id)
    if h.status == Status.DRAFT:
        return RedirectResponse(f"/hazards/{h.id}/confirm", status_code=303)
    return render(
        request,
        "hazard.html",
        user,
        db,
        h=h,
        can_act=services.can_act_on(user, h),
        suggestions=json.loads(h.ai_suggestions or "[]"),
        created=created,
        error=error,
    )


@router.post("/hazards/{hazard_id}/plan")
def plan(
    hazard_id: int, planned_action: str = Form(...), user: User = Depends(page_user), db: Session = Depends(get_session)
):
    h = _hazard(db, hazard_id)
    try:
        services.plan_action(db, h, user, planned_action)
    except (services.WorkflowError, services.PermissionDenied) as exc:
        db.rollback()
        return RedirectResponse(f"/hazards/{h.id}?error={exc}", status_code=303)
    db.commit()
    return RedirectResponse(f"/hazards/{h.id}", status_code=303)


@router.post("/hazards/{hazard_id}/close")
async def close(
    hazard_id: int,
    action: str = Form(...),
    photo: UploadFile | None = File(None),
    user: User = Depends(page_user),
    db: Session = Depends(get_session),
):
    h = _hazard(db, hazard_id)
    try:
        name = await save_photo(photo, prefix="closed_")
        services.close(db, h, user, action, name)
    except (services.WorkflowError, services.PermissionDenied) as exc:
        db.rollback()
        return RedirectResponse(f"/hazards/{h.id}?error={exc}", status_code=303)
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
