"""JSON API (documented automatically at /docs). Used by tests and evaluation scripts."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import policy, services
from ..db import get_session
from ..detection import get_detector
from ..models import Area, Hazard, Status, User
from .deps import current_user, photo_file, save_photo, store_photo

router = APIRouter(prefix="/api", tags=["api"])


class ConfirmIn(BaseModel):
    category_code: str
    consequence: int = Field(ge=1, le=5)
    description: str = ""
    fixed_on_spot: bool = False
    closure_action: str = ""
    control_type: str | None = None  # required with fixed_on_spot (ADOSH-SF hierarchy of controls)
    residual_consequence: int | None = None  # required with fixed_on_spot


class CloseIn(BaseModel):
    action: str
    control_type: str | None = None  # elimination | substitution | engineering | procedural | ppe (required)
    residual_consequence: int | None = None  # 1-5 after the control (required)


class PlanIn(BaseModel):
    action: str
    owner_id: int | None = None
    due: datetime | None = None


class NoteIn(BaseModel):
    note: str = ""


class ReasonIn(BaseModel):
    reason: str


def hazard_out(h: Hazard) -> dict:
    suggestions = json.loads(h.ai_suggestions or "[]")
    for observation in suggestions:
        if observation.get("experimental"):
            # Older reports stored free text which could speculate about the liquid.
            observation["explanation"] = ""
    return {
        "id": h.id,
        "status": h.status.value,
        "area": h.area.code,
        "x": h.x,
        "y": h.y,
        "reporter_id": h.reporter_id,
        "created_at": h.created_at.isoformat(),
        "photo_captured_at": h.photo_captured_at,
        "photo_latitude": h.photo_latitude,
        "photo_longitude": h.photo_longitude,
        "category_code": h.category_code,
        "ai_model": h.ai_model,
        "ai_top_code": h.ai_top_code,
        "ai_latency_ms": h.ai_latency_ms,
        "ai_suggestions": suggestions,
        "ai_accepted": h.ai_accepted,
        "consequence": h.consequence,
        "likelihood": h.likelihood,
        "risk_score": h.risk_score,
        "risk_level": h.risk_level,
        "assignee_id": h.assignee_id,
        "due_at": h.due_at.isoformat() if h.due_at else None,
        "closed_at": h.closed_at.isoformat() if h.closed_at else None,
        "closure_action": h.closure_action,
        "closed_on_spot": h.closed_on_spot,
        "control_type": h.control_type,
        "residual_consequence": h.residual_consequence,
        "residual_score": h.residual_score,
        "residual_level": h.residual_level,
        "photo_path": h.photo_path,
        "closure_photo_path": h.closure_photo_path,
        "planned_action": h.planned_action,
        "action_owner_id": h.action_owner_id,
        "action_due_at": h.action_due_at.isoformat() if h.action_due_at else None,
        "verified_at": h.verified_at.isoformat() if h.verified_at else None,
        "verified_by_id": h.verified_by_id,
        "events": [
            {
                "kind": e.kind,
                "actor_id": e.actor_id,
                "note": e.note,
                "at": e.at.isoformat(),
                "from_status": e.from_status,
                "to_status": e.to_status,
            }
            for e in h.events
        ],
    }


def _get(db: Session, hazard_id: int, user: User | None = None) -> Hazard:
    h = db.get(Hazard, hazard_id)
    if h is None or (user is not None and not policy.can_view(user, h)):
        raise HTTPException(404, "Hazard not found")
    return h


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/detect")
async def detect(photo: UploadFile = File(...), user: User = Depends(current_user)) -> dict:
    """Run the configured AI detector on a photo without creating a report."""
    name = await save_photo(photo, prefix="detect_")
    r = get_detector().detect(photo_file(name))
    return {
        "model": r.model,
        "latency_ms": round(r.latency_ms, 1),
        "error": r.error,
        "suggestions": [s.to_dict() for s in r.suggestions],
    }


@router.post("/hazards", status_code=201)
async def create_hazard(
    response: Response,
    area_code: str = Form(...),
    x: int | None = Form(None),
    y: int | None = Form(None),
    photo: UploadFile = File(...),
    idempotency_key: str | None = Header(None, max_length=64),
    user: User = Depends(current_user),
    db: Session = Depends(get_session),
) -> dict:
    area = db.scalar(select(Area).where(Area.code == area_code))
    if area is None:
        raise HTTPException(422, f"Unknown area {area_code}")
    services.validate_pin(area, x, y)
    try:
        existing = services.replay_or_conflict(db, user, area, idempotency_key, x, y)
    except services.IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    if existing is not None:
        response.status_code = 200
        return {**hazard_out(existing), "replayed": True}
    name, capture = await store_photo(photo, capture=True)
    if name is None:
        raise HTTPException(422, "A photo is required")
    from .pages import _experimental

    h = services.create_draft(
        db,
        user,
        area,
        name,
        get_detector().detect(photo_file(name)),
        idem_key=idempotency_key,
        x=x,
        y=y,
        experimental=_experimental(photo_file(name)),
        capture=capture,
    )
    db.commit()
    return {**hazard_out(h), "replayed": False}


@router.post("/hazards/{hazard_id}/confirm")
def confirm_hazard(
    hazard_id: int, body: ConfirmIn, user: User = Depends(current_user), db: Session = Depends(get_session)
) -> dict:
    h = _get(db, hazard_id, user)
    if h.status != Status.DRAFT:  # same rule as services.confirm, refused before any work (security review)
        raise HTTPException(422, "Only a draft report can be confirmed; this one has already been confirmed")
    h = services.confirm(db, h, user, services.Confirmation(**body.model_dump()))
    db.commit()
    return hazard_out(h)


@router.post("/hazards/{hazard_id}/close")
def close_hazard(
    hazard_id: int, body: CloseIn, user: User = Depends(current_user), db: Session = Depends(get_session)
) -> dict:
    h = services.close(
        db,
        _get(db, hazard_id, user),
        user,
        body.action,
        control_type=body.control_type,
        residual_consequence=body.residual_consequence,
    )
    db.commit()
    return hazard_out(h)


@router.post("/hazards/{hazard_id}/plan")
def plan_hazard(
    hazard_id: int, body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_session)
) -> dict:
    due = body.due.replace(tzinfo=None) if body.due else None
    h = services.plan_action(db, _get(db, hazard_id, user), user, body.action, owner_id=body.owner_id, due=due)
    db.commit()
    return hazard_out(h)


@router.post("/hazards/{hazard_id}/verify")
def verify_hazard(
    hazard_id: int, body: NoteIn, user: User = Depends(current_user), db: Session = Depends(get_session)
) -> dict:
    h = services.verify(db, _get(db, hazard_id, user), user, body.note)
    db.commit()
    return hazard_out(h)


@router.post("/hazards/{hazard_id}/reject")
def reject_hazard(
    hazard_id: int, body: ReasonIn, user: User = Depends(current_user), db: Session = Depends(get_session)
) -> dict:
    h = services.reject(db, _get(db, hazard_id, user), user, body.reason)
    db.commit()
    return hazard_out(h)


@router.post("/hazards/{hazard_id}/reopen")
def reopen_hazard(
    hazard_id: int, body: ReasonIn, user: User = Depends(current_user), db: Session = Depends(get_session)
) -> dict:
    h = services.reopen(db, _get(db, hazard_id, user), user, body.reason)
    db.commit()
    return hazard_out(h)


@router.get("/hazards")
def list_hazards(
    status: Status | None = None,
    area: str | None = None,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
) -> list[dict]:
    q = select(Hazard).where(Hazard.status != Status.DRAFT).order_by(Hazard.created_at.desc())
    if status:
        q = q.where(Hazard.status == status)
    if area:
        q = q.join(Area).where(Area.code == area)
    return [hazard_out(h) for h in db.scalars(q.limit(500))]


@router.get("/hazards/{hazard_id}")
def get_hazard(hazard_id: int, db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    return hazard_out(_get(db, hazard_id, user))


@router.get("/monitoring")
def monitoring(db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    return services.ai_monitoring(db)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    d = services.dashboard(db)
    d["areas"] = [{**{k: v for k, v in r.items() if k != "area"}, "code": r["area"].code} for r in d["areas"]]
    return d
