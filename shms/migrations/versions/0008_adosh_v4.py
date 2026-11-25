"""ADOSH-SF v4.0 risk matrix: closure control type + residual risk columns, and re-score every confirmed hazard.

Schema: hazards.control_type, residual_consequence, residual_score, residual_level (all nullable; legacy closures
stay NULL = "not recorded" – nothing is back-filled).

Data: likelihood is recomputed from the area history at each hazard's report time (similar confirmed hazards in the
same area and category in the previous 365 days: 0 -> 1, 1 -> 2, 2 -> 3, 3-5 -> 4, >= 6 -> 5), then score, band and
target date (from the hazard's confirmation – or last reopening – plus the band's project-defined days). Each re-scored
hazard gets an audit event "risk re-scored to ADOSH-SF v4.0 matrix" with old -> new values. No rows are deleted and no
alerts are sent. The matrix is frozen here on purpose: later edits to risk_matrix.json must not change this migration.

Downgrade drops the new columns only; re-scored values stay (the old values remain readable in the audit events).
"""

from datetime import datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "0008_adosh_v4"
down_revision = "0007_photo_capture"
branch_labels = None
depends_on = None

LOOKBACK_DAYS = 365
LIKELIHOOD_CAPS = ((0, 1), (1, 2), (2, 3), (5, 4))  # (max similar count, level); more -> 5
BANDS = ((3, "Low", 30), (7, "Moderate", 14), (14, "High", 7), (25, "Extreme", 1))  # (max score, level, days)
EVENT_KIND = "risk_rescored"
EVENT_TITLE = "risk re-scored to ADOSH-SF v4.0 matrix"
CONTROL_CODES = ("elimination", "substitution", "engineering", "procedural", "ppe")


def likelihood_for(count: int) -> int:
    return next((level for cap, level in LIKELIHOOD_CAPS if count <= cap), 5)


def band_for(score: int) -> tuple[str, int]:
    return next((level, days) for top, level, days in BANDS if score <= top)


def _dt(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _fmt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "none"


def rescore(conn) -> int:
    """Re-score every confirmed hazard; returns how many changed band."""
    hz = sa.table(
        "hazards",
        sa.column("id", sa.Integer),
        sa.column("area_id", sa.Integer),
        sa.column("reporter_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("category_code", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("confirmed_at", sa.DateTime),
        sa.column("consequence", sa.Integer),
        sa.column("likelihood", sa.Integer),
        sa.column("risk_score", sa.Integer),
        sa.column("risk_level", sa.String),
        sa.column("due_at", sa.DateTime),
    )
    ev = sa.table(
        "hazard_events",
        sa.column("hazard_id", sa.Integer),
        sa.column("actor_id", sa.Integer),
        sa.column("kind", sa.String),
        sa.column("note", sa.Text),
        sa.column("at", sa.DateTime),
    )
    rows = [r._asdict() for r in conn.execute(sa.select(hz))]
    for r in rows:
        r["created_at"], r["confirmed_at"], r["due_at"] = map(_dt, (r["created_at"], r["confirmed_at"], r["due_at"]))
    confirmed = [r for r in rows if r["status"] != "DRAFT" and r["consequence"] is not None]
    reopened: dict[int, datetime] = {}
    for hid, at in conn.execute(sa.select(ev.c.hazard_id, ev.c.at).where(ev.c.kind == "reopened")):
        at = _dt(at)
        reopened[hid] = max(at, reopened.get(hid, at))

    now = datetime.utcnow()  # noqa: DTZ003 - the app stores naive UTC
    changed_band = 0
    for r in confirmed:
        t = r["created_at"]
        since = t - timedelta(days=LOOKBACK_DAYS)
        count = sum(
            1
            for o in confirmed
            if o["id"] != r["id"]
            and o["area_id"] == r["area_id"]
            and o["category_code"] == r["category_code"]
            and since <= o["created_at"] <= t
        )
        likelihood = likelihood_for(count)
        score = r["consequence"] * likelihood
        level, days = band_for(score)
        base = reopened.get(r["id"]) or r["confirmed_at"] or t
        due = base + timedelta(days=days)
        changed_band += level != r["risk_level"]
        conn.execute(
            hz.update()
            .where(hz.c.id == r["id"])
            .values(likelihood=likelihood, risk_score=score, risk_level=level, due_at=due)
        )
        note = (
            f"System migration, no user action: {EVENT_TITLE}. "
            f"Likelihood {r['likelihood']} -> {likelihood} ({count} similar in the previous {LOOKBACK_DAYS} days); "
            f"score {r['risk_score']} -> {score}; level {r['risk_level']} -> {level}; "
            f"target date {_fmt(r['due_at'])} -> {_fmt(due)}"
        )
        conn.execute(
            ev.insert().values(hazard_id=r["id"], actor_id=r["reporter_id"], kind=EVENT_KIND, note=note, at=now)
        )
    return changed_band


def upgrade() -> None:
    with op.batch_alter_table("hazards") as batch:
        batch.add_column(sa.Column("control_type", sa.String(20), nullable=True))
        batch.add_column(sa.Column("residual_consequence", sa.Integer, nullable=True))
        batch.add_column(sa.Column("residual_score", sa.Integer, nullable=True))
        batch.add_column(sa.Column("residual_level", sa.String(20), nullable=True))
        batch.create_check_constraint(
            "ck_control_type",
            "control_type IS NULL OR control_type IN (" + ",".join(f"'{c}'" for c in CONTROL_CODES) + ")",
        )
        batch.create_check_constraint(
            "ck_residual_consequence_1_5", "residual_consequence IS NULL OR residual_consequence BETWEEN 1 AND 5"
        )
    rescore(op.get_bind())


def downgrade() -> None:
    with op.batch_alter_table("hazards") as batch:
        batch.drop_constraint("ck_residual_consequence_1_5", type_="check")
        batch.drop_constraint("ck_control_type", type_="check")
        for column in ("residual_level", "residual_score", "residual_consequence", "control_type"):
            batch.drop_column(column)
