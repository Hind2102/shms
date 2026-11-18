"""ORM data model.

User ──< Area (owner)            User ──< Hazard (reporter / assignee / closer)
Area ──< Hazard ──< HazardEvent  (audit trail of every state change)
User ──< Notification >── Hazard (alerts for High / Extreme risk)
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Role(str, enum.Enum):
    REPORTER = "reporter"  # field operator, contractor or visitor
    AREA_OWNER = "area_owner"  # accountable for closing hazards in their areas
    SUPERVISOR = "supervisor"  # safety supervisor: alerted on High/Extreme, can act on any hazard
    MANAGER = "manager"  # read-only site-wide view


class Status(str, enum.Enum):
    DRAFT = "draft"  # observation: photo uploaded and AI has run; reporter has not confirmed yet
    OPEN = "open"  # human-confirmed hazard, assigned to the Area Owner
    PLANNED = "planned"  # corrective action planned with an action owner and a deadline
    PENDING_VERIFICATION = "pending_verification"  # closed by the owner, waiting for an independent check
    CLOSED = "closed"  # closure verified by a supervisor or the reporter


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(Enum(Role))

    areas: Mapped[list[Area]] = relationship(back_populates="owner")


class Area(Base):
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    required_ppe: Mapped[str] = mapped_column(Text, default="")  # comma-separated, shown to people entering
    # Hazard codes the AI checks in this area (the PPE this area requires), comma-separated
    ai_checks: Mapped[str] = mapped_column(Text, default="no_hard_hat,no_eye_protection,no_gloves,no_hi_vis_vest")
    # Rectangle on the synthesized refinery layout (SVG user units, 1000 x 600 canvas)
    x: Mapped[int] = mapped_column(Integer, default=0)
    y: Mapped[int] = mapped_column(Integer, default=0)
    w: Mapped[int] = mapped_column(Integer, default=100)
    h: Mapped[int] = mapped_column(Integer, default=100)

    owner: Mapped[User] = relationship(back_populates="areas")
    hazards: Mapped[list[Hazard]] = relationship(back_populates="area")

    @property
    def ppe_list(self) -> list[str]:
        return [p.strip() for p in self.required_ppe.split(",") if p.strip()]

    @property
    def check_codes(self) -> list[str]:
        """PPE this area requires that the AI is released to check (area rule ∩ release gate)."""
        from . import taxonomy

        enabled = set(taxonomy.enabled_codes())
        return [c.strip() for c in self.ai_checks.split(",") if c.strip() in enabled]


class Hazard(Base):
    __tablename__ = "hazards"
    # Integrity rules live in the database too, so no program (app, script, import) can store invalid values.
    __table_args__ = (
        CheckConstraint("consequence IS NULL OR consequence BETWEEN 1 AND 5", name="ck_consequence_1_5"),
        CheckConstraint("likelihood IS NULL OR likelihood BETWEEN 1 AND 5", name="ck_likelihood_1_5"),
        CheckConstraint("risk_score IS NULL OR risk_score BETWEEN 1 AND 25", name="ck_risk_1_25"),
        CheckConstraint("status != 'CLOSED' OR closure_action IS NOT NULL", name="ck_closed_has_action"),
        CheckConstraint("status != 'PENDING_VERIFICATION' OR closure_action IS NOT NULL", name="ck_pending_has_action"),
        UniqueConstraint("reporter_id", "idem_key", name="uq_reporter_idem_key"),
        # Indexes match the hot queries: likelihood look-up, dashboard / register filters.
        Index("ix_hazard_area_cat_time", "area_id", "category_code", "created_at"),
        Index("ix_hazard_status", "status"),
        Index("ix_hazard_created", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    # Idempotency key sent by the client: a double-tap or retry on poor site Wi-Fi returns the same report.
    idem_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"))
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.DRAFT)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    photo_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")

    # What the AI suggested, and whether the reporter kept it (traceability)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_suggestions: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    ai_top_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ai_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Confirmed classification and risk
    category_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Routing and closure
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    planned_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    closure_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    closure_photo_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    closed_on_spot: Mapped[bool] = mapped_column(Boolean, default=False)

    # Action plan and independent verification of the closure
    action_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    area: Mapped[Area] = relationship(back_populates="hazards")
    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    closed_by: Mapped[User | None] = relationship(foreign_keys=[closed_by_id])
    action_owner: Mapped[User | None] = relationship(foreign_keys=[action_owner_id])
    verified_by: Mapped[User | None] = relationship(foreign_keys=[verified_by_id])
    events: Mapped[list[HazardEvent]] = relationship(
        back_populates="hazard", order_by="HazardEvent.at", cascade="all, delete-orphan"
    )


class HazardEvent(Base):
    """Append-only audit trail: who did what to a hazard, and when."""

    __tablename__ = "hazard_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    hazard_id: Mapped[int] = mapped_column(ForeignKey("hazards.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))  # reported, confirmed, assigned, planned, closed, verified, ...
    note: Mapped[str] = mapped_column(Text, default="")
    # Set for every status change (state-machine transition); empty for events that do not change status.
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    hazard: Mapped[Hazard] = relationship(back_populates="events")
    actor: Mapped[User] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    hazard_id: Mapped[int] = mapped_column(ForeignKey("hazards.id"))
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    hazard: Mapped[Hazard] = relationship()
