"""Course update (commit b2f307b): idempotency key, integrity constraints and query indexes on hazards.

Each change is applied only if it is missing, so databases created by create_all() at b2f307b or later
(already complete, but unstamped) pass through unchanged.

Revision ID: 0002_course_upgrade
Revises: 0001_baseline
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_course_upgrade"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

CHECKS = {
    "ck_consequence_1_5": "consequence IS NULL OR consequence BETWEEN 1 AND 5",
    "ck_likelihood_1_5": "likelihood IS NULL OR likelihood BETWEEN 1 AND 5",
    "ck_risk_1_25": "risk_score IS NULL OR risk_score BETWEEN 1 AND 25",
    "ck_closed_has_action": "status != 'CLOSED' OR closure_action IS NOT NULL",
}
INDEXES = {
    "ix_hazard_area_cat_time": ["area_id", "category_code", "created_at"],
    "ix_hazard_status": ["status"],
    "ix_hazard_created": ["created_at"],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("hazards")}
    checks = {c["name"] for c in insp.get_check_constraints("hazards")}
    uniques = {u["name"] for u in insp.get_unique_constraints("hazards")}
    todo_checks = {n: s for n, s in CHECKS.items() if n not in checks}
    if "idem_key" not in cols or todo_checks or "uq_reporter_idem_key" not in uniques:
        with op.batch_alter_table("hazards", recreate="always") as b:
            if "idem_key" not in cols:
                b.add_column(sa.Column("idem_key", sa.String(64), nullable=True))
            for name, sql in todo_checks.items():
                b.create_check_constraint(name, sql)
            if "uq_reporter_idem_key" not in uniques:
                b.create_unique_constraint("uq_reporter_idem_key", ["reporter_id", "idem_key"])
    have = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("hazards")}
    for name, columns in INDEXES.items():
        if name not in have:
            op.create_index(name, "hazards", columns)


def downgrade() -> None:
    for name in INDEXES:
        op.drop_index(name, table_name="hazards")
    with op.batch_alter_table("hazards", recreate="always") as b:
        b.drop_constraint("uq_reporter_idem_key", type_="unique")
        for name in CHECKS:
            b.drop_constraint(name, type_="check")
        b.drop_column("idem_key")
