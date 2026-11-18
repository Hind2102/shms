"""Add optional map coordinates to hazard reports. Existing reports retain area-only locations."""

import sqlalchemy as sa
from alembic import op

revision = "0006_report_pin"
down_revision = "0005_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("hazards") as batch:
        batch.add_column(sa.Column("x", sa.Integer, nullable=True))
        batch.add_column(sa.Column("y", sa.Integer, nullable=True))
        batch.create_check_constraint("ck_hazard_pin_pair", "(x IS NULL) = (y IS NULL)")


def downgrade() -> None:
    with op.batch_alter_table("hazards") as batch:
        batch.drop_constraint("ck_hazard_pin_pair", type_="check")
        batch.drop_column("y")
        batch.drop_column("x")
