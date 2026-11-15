"""JSON API (documented automatically at /docs). Used by tests and evaluation scripts."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services
from ..db import get_session
from ..detection import get_detector
from ..models import Area, Hazard, Status, User
from .deps import current_user, photo_file, save_photo

router = APIRouter(prefix="/api", tags=["api"])


class ConfirmIn(BaseModel):
    category_code: str
    consequence: int = Field(ge=1, le=5)
    description: str = ""
    fixed_on_spot: bool = False
    closure_action: str = ""


class CloseIn(BaseModel):
    action: str


def hazard_out(h: Hazard) -> dict:
    return {
        "id": h.id, "status": h.status.value, "area": h.area.code, "reporter_id": h.reporter_id,
        "created_at": h.created_at.isoformat(), "category_code": h.category_code,
        "ai_model": h.ai_model, "ai_top_code": h.ai_top_code, "ai_latency_ms": h.ai_latency_ms,
        "ai_suggestions": json.loads(h.ai_suggestions or "[]"), "ai_accepted": h.ai_accepted,
        "consequence": h.consequence, "likelihood": h.likelihood, "risk_score": h.risk_score,
        "risk_level": h.risk_level, "assignee_id": h.assignee_id,
        "due_at": h.due_at.isoformat() if h.due_at else None,
        "closed_at": h.closed_at.isoformat() if h.closed_at else None,
        "closure_action": h.closure_action, "closed_on_spot": h.closed_on_spot,
        "events": [{"kind": e.kind, "actor_id": e.actor_id, "note": e.note, "at": e.at.isoformat()} for e in h.events],
    }


def _get(db: Session, hazard_id: int) -> Hazard:
    h = db.get(Hazard, hazard_id)
    if h is None:
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
    return {"model": r.model, "latency_ms": round(r.latency_ms, 1), "error": r.error,
            "suggestions": [s.to_dict() for s in r.suggestions]}


@router.post("/hazards", status_code=201)
async def create_hazard(area_code: str = Form(...), photo: UploadFile | None = File(None),
                        user: User = Depends(current_user), db: Session = Depends(get_session)) -> dict:
    area = db.scalar(select(Area).where(Area.code == area_code))
    if area is None:
        raise HTTPException(422, f"Unknown area {area_code}")
    name = await save_photo(photo)
    result = get_detector().detect(photo_file(name)) if name else None
    h = services.create_draft(db, user, area, name, result)
    db.commit()
    return hazard_out(h)


@router.post("/hazards/{hazard_id}/confirm")
def confirm_hazard(hazard_id: int, body: ConfirmIn, user: User = Depends(current_user),
                   db: Session = Depends(get_session)) -> dict:
    h = services.confirm(db, _get(db, hazard_id), user, services.Confirmation(**body.model_dump()))
    db.commit()
    return hazard_out(h)


@router.post("/hazards/{hazard_id}/close")
def close_hazard(hazard_id: int, body: CloseIn, user: User = Depends(current_user),
                 db: Session = Depends(get_session)) -> dict:
    h = services.close(db, _get(db, hazard_id), user, body.action)
    db.commit()
    return hazard_out(h)


@router.get("/hazards")
def list_hazards(status: Status | None = None, area: str | None = None,
                 db: Session = Depends(get_session)) -> list[dict]:
    q = select(Hazard).where(Hazard.status != Status.DRAFT).order_by(Hazard.created_at.desc())
    if status:
        q = q.where(Hazard.status == status)
    if area:
        q = q.join(Area).where(Area.code == area)
    return [hazard_out(h) for h in db.scalars(q.limit(500))]


@router.get("/hazards/{hazard_id}")
def get_hazard(hazard_id: int, db: Session = Depends(get_session)) -> dict:
    return hazard_out(_get(db, hazard_id))


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_session)) -> dict:
    d = services.dashboard(db)
    d["areas"] = [{**{k: v for k, v in r.items() if k != "area"}, "code": r["area"].code} for r in d["areas"]]
    return d
