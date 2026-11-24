"""Store camera capture time and GPS separately from report time and illustrative map pins."""

import sqlalchemy as sa
from alembic import op

revision = "0007_photo_capture"
down_revision = "0006_report_pin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hazards", sa.Column("photo_captured_at", sa.String(32), nullable=True))
    op.add_column("hazards", sa.Column("photo_latitude", sa.Float(), nullable=True))
    op.add_column("hazards", sa.Column("photo_longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("hazards") as batch:
        for column in ("photo_longitude", "photo_latitude", "photo_captured_at"):
            batch.drop_column(column)
