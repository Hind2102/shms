"""Baseline: the original SHMS schema (commits 6f18c27 / de90451), e.g. backups/shms_2026-11-17.db.

Tables are created only if they are missing, so an existing database that was created before migrations
existed (no alembic_version table) can be brought under migration control with `alembic upgrade head`.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _missing(name: str) -> bool:
    return name not in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _missing("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("role", sa.String(10), nullable=False),
        )
    if _missing("areas"):
        op.create_table(
            "areas",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("code", sa.String(20), nullable=False, unique=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("required_ppe", sa.Text, nullable=False),
            sa.Column("ai_checks", sa.Text, nullable=False),
            sa.Column("x", sa.Integer, nullable=False),
            sa.Column("y", sa.Integer, nullable=False),
            sa.Column("w", sa.Integer, nullable=False),
            sa.Column("h", sa.Integer, nullable=False),
        )
    if _missing("hazards"):
        op.create_table(
            "hazards",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("area_id", sa.Integer, sa.ForeignKey("areas.id"), nullable=False),
            sa.Column("reporter_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(6), nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("confirmed_at", sa.DateTime),
            sa.Column("photo_path", sa.String(300)),
            sa.Column("description", sa.Text, nullable=False),
            sa.Column("ai_model", sa.String(100)),
            sa.Column("ai_suggestions", sa.Text, nullable=False),
            sa.Column("ai_top_code", sa.String(40)),
            sa.Column("ai_latency_ms", sa.Float),
            sa.Column("ai_error", sa.Text),
            sa.Column("ai_accepted", sa.Boolean),
            sa.Column("category_code", sa.String(40)),
            sa.Column("consequence", sa.Integer),
            sa.Column("likelihood", sa.Integer),
            sa.Column("risk_score", sa.Integer),
            sa.Column("risk_level", sa.String(20)),
            sa.Column("due_at", sa.DateTime),
            sa.Column("assignee_id", sa.Integer, sa.ForeignKey("users.id")),
            sa.Column("planned_action", sa.Text),
            sa.Column("closed_at", sa.DateTime),
            sa.Column("closed_by_id", sa.Integer, sa.ForeignKey("users.id")),
            sa.Column("closure_action", sa.Text),
            sa.Column("closure_photo_path", sa.String(300)),
            sa.Column("closed_on_spot", sa.Boolean, nullable=False),
        )
    if _missing("hazard_events"):
        op.create_table(
            "hazard_events",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("hazard_id", sa.Integer, sa.ForeignKey("hazards.id"), nullable=False),
            sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("kind", sa.String(30), nullable=False),
            sa.Column("note", sa.Text, nullable=False),
            sa.Column("at", sa.DateTime, nullable=False),
        )
    if _missing("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("hazard_id", sa.Integer, sa.ForeignKey("hazards.id"), nullable=False),
            sa.Column("message", sa.Text, nullable=False),
            sa.Column("read", sa.Boolean, nullable=False),
            sa.Column("created_at", sa.DateTime, nullable=False),
        )


def downgrade() -> None:
    for t in ("notifications", "hazard_events", "hazards", "areas", "users"):
        op.drop_table(t)
