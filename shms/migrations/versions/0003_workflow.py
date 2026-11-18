"""Safety workflow v2: action owner and deadline, independent verification, from/to status on audit events.

Existing rows keep their status. Hazards closed before this migration stay CLOSED with an empty verified_at,
i.e. "closed before the verification step existed"; nothing is invented for them.

Revision ID: 0003_workflow
Revises: 0002_course_upgrade
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_workflow"
down_revision = "0002_course_upgrade"
branch_labels = None
depends_on = None

STATUS = sa.Enum("DRAFT", "OPEN", "PLANNED", "PENDING_VERIFICATION", "CLOSED", name="status")
OLD_STATUS = sa.Enum("DRAFT", "OPEN", "CLOSED", name="status")


def upgrade() -> None:
    with op.batch_alter_table("hazards", recreate="always") as b:
        b.alter_column("status", type_=STATUS, existing_type=sa.String(6), existing_nullable=False)
        b.add_column(sa.Column("action_owner_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("action_due_at", sa.DateTime, nullable=True))
        b.add_column(sa.Column("verified_at", sa.DateTime, nullable=True))
        b.add_column(sa.Column("verified_by_id", sa.Integer, nullable=True))
        b.create_foreign_key("fk_hazards_action_owner", "users", ["action_owner_id"], ["id"])
        b.create_foreign_key("fk_hazards_verified_by", "users", ["verified_by_id"], ["id"])
        b.create_check_constraint(
            "ck_pending_has_action", "status != 'PENDING_VERIFICATION' OR closure_action IS NOT NULL"
        )
    with op.batch_alter_table("hazard_events") as b:
        b.add_column(sa.Column("from_status", sa.String(30), nullable=True))
        b.add_column(sa.Column("to_status", sa.String(30), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hazard_events") as b:
        b.drop_column("to_status")
        b.drop_column("from_status")
    with op.batch_alter_table("hazards", recreate="always") as b:
        b.drop_constraint("ck_pending_has_action", type_="check")
        b.drop_constraint("fk_hazards_verified_by", type_="foreignkey")
        b.drop_constraint("fk_hazards_action_owner", type_="foreignkey")
        for c in ("verified_by_id", "verified_at", "action_due_at", "action_owner_id"):
            b.drop_column(c)
        b.alter_column("status", type_=OLD_STATUS, existing_nullable=False)
