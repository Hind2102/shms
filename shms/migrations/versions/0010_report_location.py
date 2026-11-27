"""Report location with its source: photo EXIF GPS, the reporter's device (browser geolocation) or none."""

import sqlalchemy as sa
from alembic import op

revision = "0010_report_location"
down_revision = "0009_ata_site_map"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hazards", sa.Column("location_latitude", sa.Float(), nullable=True))
    op.add_column("hazards", sa.Column("location_longitude", sa.Float(), nullable=True))
    op.add_column("hazards", sa.Column("location_accuracy_m", sa.Float(), nullable=True))
    op.add_column("hazards", sa.Column("location_source", sa.String(8), nullable=False, server_default="none"))
    # Existing reports: the only location they can have is the photo's EXIF GPS.
    op.execute(
        "UPDATE hazards SET location_latitude = photo_latitude, location_longitude = photo_longitude, "
        "location_source = 'photo' WHERE photo_latitude IS NOT NULL AND photo_longitude IS NOT NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("hazards") as batch:
        for column in ("location_source", "location_accuracy_m", "location_longitude", "location_latitude"):
            batch.drop_column(column)
