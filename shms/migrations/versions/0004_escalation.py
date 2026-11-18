"""Overdue escalation level on hazards and an e-mail address on users (for the test mail outbox).

Revision ID: 0004_escalation
Revises: 0003_workflow
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_escalation"
down_revision = "0003_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hazards") as b:
        b.add_column(sa.Column("escalation_level", sa.Integer, nullable=False, server_default="0"))
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("email", sa.String(200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.drop_column("email")
    with op.batch_alter_table("hazards") as b:
        b.drop_column("escalation_level")
