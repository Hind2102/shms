"""Approved concept site map (v1.5.0): rename areas, add six zones, re-map report pins.

- The nine existing areas keep their codes, ids, hazards and pins. They take the zone names of the approved map
  (shms/static/ata_concept_map.svg), and their legacy rectangle columns now hold the zone's bounding box in map units.
- New reporting zones EVP, HYD, ALS, LIM, WKS and WTR are added with project-assumed PPE lists. AI checks are the same
  released-PPE list as every other area. Each new zone's owner is the owner of a neighbouring process area, falling
  back to any Area Owner. A database without users gets no new areas, because an area needs an owner.
- Report pins are moved proportionally from the area's rectangle on the old 1200 × 800 plan into its zone on the
  1920 × 1080 map. The relative position inside the area is kept.

No rows are deleted and no events are added. Downgrade restores names, rectangles and pins and keeps the added areas
(data is never deleted). Geometry is frozen here on purpose: later map edits must not change this migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_ata_site_map"
down_revision = "0008_adosh_v4"
branch_labels = None
depends_on = None

# code: (old name, new name, old plan rect on 1200 x 800, old legacy area rect, new zone rect on 1920 x 1080)
EXISTING = {
    "BXH": (
        "Bauxite Handling",
        "Bauxite storage & handling",
        (92, 110, 159, 128),
        (20, 40, 200, 230),
        (175, 160, 1570, 132),
    ),
    "GRD": (
        "Grinding & Desilication",
        "Grinding & slurry preparation",
        (276, 124, 145, 114),
        (240, 40, 180, 230),
        (414, 320, 246, 180),
    ),
    "DIG": ("Digestion", "Digestion", (446, 99, 165, 139), (440, 40, 200, 230), (175, 320, 215, 502)),
    "CLR": (
        "Clarification (Red Mud)",
        "Clarification",
        (638, 111, 143, 127),
        (660, 40, 150, 230),
        (414, 512, 246, 250),
    ),
    "FLT": (
        "Security Filtration",
        "Security filtration",
        (822, 327, 142, 111),
        (830, 40, 150, 230),
        (414, 772, 246, 50),
    ),
    "PRC": ("Precipitation", "Precipitation", (634, 299, 152, 139), (660, 300, 320, 250), (684, 320, 486, 320)),
    "CAL": ("Calcination", "Calcination", (270, 329, 156, 109), (380, 300, 260, 250), (1194, 492, 246, 148)),
    "TNK": (
        "Caustic Tank Farm",
        "Caustic & reagents",
        (98, 511, 154, 127),
        (240, 300, 120, 250),
        (1476, 320, 269, 106),
    ),
    "PWR": (
        "Powerhouse & Utilities",
        "Water & utilities",
        (275, 523, 155, 115),
        (20, 300, 200, 250),
        (1476, 551, 269, 96),
    ),
}
CHECKS = "no_hard_hat,no_eye_protection,no_gloves"
# code: (name, required PPE – project assumption, owner taken from this area, zone rect)
NEW = {
    "EVP": ("Evaporation", "Hard hat, Face shield, Chemical gloves", "PRC", (1194, 320, 246, 160)),
    "HYD": ("Hydrate filtration", "Hard hat, Face shield, Chemical gloves", "PRC", (684, 664, 276, 158)),
    "ALS": ("Alumina storage", "Hard hat, Safety glasses, Gloves, Dust mask", "CAL", (972, 664, 468, 158)),
    "LIM": ("Lime handling", "Hard hat, Goggles, Gloves, Dust mask", "TNK", (1476, 446, 269, 86)),
    "WKS": ("Workshops & stores", "Hard hat, Safety glasses, Gloves, Hearing protection", "PWR", (1476, 666, 269, 100)),
    "WTR": ("Water basins", "Hard hat, Safety glasses, Life jacket (near open water)", "PWR", (175, 858, 1265, 108)),
}

areas = sa.table(
    "areas",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("owner_id", sa.Integer),
    sa.column("required_ppe", sa.Text),
    sa.column("ai_checks", sa.Text),
    sa.column("x", sa.Integer),
    sa.column("y", sa.Integer),
    sa.column("w", sa.Integer),
    sa.column("h", sa.Integer),
)
hazards = sa.table(
    "hazards",
    sa.column("id", sa.Integer),
    sa.column("area_id", sa.Integer),
    sa.column("x", sa.Integer),
    sa.column("y", sa.Integer),
)
users = sa.table("users", sa.column("id", sa.Integer), sa.column("role", sa.String))


def remap(x: int, y: int, old: tuple[int, int, int, int], new: tuple[int, int, int, int]) -> tuple[int, int]:
    """Same relative position inside the old rectangle and the new one, kept inside the new rectangle."""
    ox, oy, ow, oh = old
    nx, ny, nw, nh = new
    fx = min(1.0, max(0.0, (x - ox) / ow))
    fy = min(1.0, max(0.0, (y - oy) / oh))
    return round(nx + fx * nw), round(ny + fy * nh)


def _move_pins(conn, ids: dict[str, int], forward: bool) -> int:
    moved = 0
    for code, (_, _, old_plan, _, new_zone) in EXISTING.items():
        if code not in ids:
            continue
        src, dst = (old_plan, new_zone) if forward else (new_zone, old_plan)
        rows = conn.execute(
            sa.select(hazards.c.id, hazards.c.x, hazards.c.y).where(
                hazards.c.area_id == ids[code], hazards.c.x.is_not(None)
            )
        ).all()
        for hid, x, y in rows:
            nx, ny = remap(x, y, src, dst)
            conn.execute(hazards.update().where(hazards.c.id == hid).values(x=nx, y=ny))
            moved += 1
    return moved


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.select(areas.c.id, areas.c.code, areas.c.owner_id)).all()
    ids = {code: aid for aid, code, _ in rows}
    owners = {code: owner for _, code, owner in rows}
    for code, (_, name, _, _, (x, y, w, h)) in EXISTING.items():
        if code in ids:
            conn.execute(areas.update().where(areas.c.id == ids[code]).values(name=name, x=x, y=y, w=w, h=h))
    _move_pins(conn, ids, forward=True)

    fallback = conn.execute(sa.select(users.c.id).where(users.c.role == "AREA_OWNER").order_by(users.c.id)).first()
    fallback = fallback or conn.execute(sa.select(users.c.id).order_by(users.c.id)).first()
    for code, (name, ppe, like, (x, y, w, h)) in NEW.items():
        owner = owners.get(like) or (fallback[0] if fallback else None)
        if code in ids or owner is None:
            continue
        conn.execute(
            areas.insert().values(
                code=code, name=name, owner_id=owner, required_ppe=ppe, ai_checks=CHECKS, x=x, y=y, w=w, h=h
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    ids = {code: aid for aid, code in conn.execute(sa.select(areas.c.id, areas.c.code)).all()}
    _move_pins(conn, ids, forward=False)
    for code, (old_name, _, _, (x, y, w, h), _) in EXISTING.items():
        if code in ids:
            conn.execute(areas.update().where(areas.c.id == ids[code]).values(name=old_name, x=x, y=y, w=w, h=h))
