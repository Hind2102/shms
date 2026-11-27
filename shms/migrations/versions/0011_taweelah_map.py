"""Al Taweelah illustrative site map and area profiles (v1.7.0).

- The site plan's base layer becomes the owner-supplied illustrative image (1672 × 941 px). Every area's legacy
  rectangle columns take the bounding box of its new zone polygon, and report pins move with the same relative position
  from the area's v1.5 zone rectangle into the new zone, then are nudged inside the polygon if needed.
- Display names follow the image: FLT "CCL wash (550)", PWR "Cooling water & utilities (4664)". Codes are unchanged.
- New reporting zone LAB "Laboratory & offices": owner = owner of WKS (fallback: any Area Owner); AI checks are the
  released eye-protection and glove checks only (a laboratory does not require a hard hat).
- Required PPE per area follows the project's area profiles (shms/config/area_profiles.json; project assumptions).

No rows are deleted and no events are added. Downgrade restores names, PPE, rectangles and pins and keeps LAB (data is
never deleted). Geometry and PPE are frozen here on purpose: later edits of the config must not change this migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_taweelah_map"
down_revision = "0010_report_location"
branch_labels = None
depends_on = None

# v1.5 zone rectangles on the 1920 × 1080 concept map (x, y, w, h)
OLD_RECT = {
    "BXH": (175, 160, 1570, 132),
    "DIG": (175, 320, 215, 502),
    "GRD": (414, 320, 246, 180),
    "CLR": (414, 512, 246, 250),
    "FLT": (414, 772, 246, 50),
    "PRC": (684, 320, 486, 320),
    "EVP": (1194, 320, 246, 160),
    "CAL": (1194, 492, 246, 148),
    "HYD": (684, 664, 276, 158),
    "ALS": (972, 664, 468, 158),
    "TNK": (1476, 320, 269, 106),
    "LIM": (1476, 446, 269, 86),
    "PWR": (1476, 551, 269, 96),
    "WKS": (1476, 666, 269, 100),
    "WTR": (175, 858, 1265, 108),
}
# v1.7 zone polygons in image pixels (approved 2026-11-27)
NEW_POLY = {
    "BXH": [(122, 148), (1545, 148), (1580, 178), (1580, 280), (122, 280)],
    "DIG": [(90, 305), (405, 305), (405, 792), (90, 792)],
    "GRD": [(432, 305), (748, 305), (748, 435), (432, 435)],
    "EVP": [(763, 305), (1305, 305), (1305, 478), (690, 478), (690, 450), (763, 450)],
    "CLR": [(432, 452), (680, 452), (680, 706), (432, 706)],
    "PRC": [(688, 485), (1095, 485), (1095, 682), (688, 682)],
    "CAL": [(1102, 485), (1305, 485), (1305, 682), (1102, 682)],
    "HYD": [(438, 707), (935, 707), (935, 792), (438, 792)],
    "FLT": [(945, 698), (1090, 698), (1090, 792), (945, 792)],
    "ALS": [(1100, 698), (1305, 698), (1305, 792), (1100, 792)],
    "TNK": [(1335, 305), (1575, 305), (1575, 396), (1335, 396)],
    "LIM": [(1335, 405), (1575, 405), (1575, 478), (1335, 478)],
    "PWR": [(1335, 488), (1575, 488), (1575, 626), (1335, 626)],
    "WKS": [(1335, 632), (1575, 632), (1575, 692), (1335, 692)],
    "LAB": [(1335, 700), (1575, 700), (1575, 858), (1335, 858)],
    "WTR": [(105, 812), (1300, 812), (1300, 860), (105, 860)],
}
NAMES = {
    "FLT": ("Security filtration", "CCL wash (550)"),
    "PWR": ("Water & utilities", "Cooling water & utilities (4664)"),
}
OLD_PPE = {
    "BXH": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Dust mask, Hearing protection",
    "GRD": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Hearing protection",
    "DIG": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Chemical gloves",
    "CLR": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Chemical gloves",
    "FLT": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Chemical gloves",
    "PRC": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Chemical gloves",
    "CAL": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Heat-resistant gloves, Dust mask",
    "TNK": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield (caustic "
    "transfers), Chemical suit",
    "PWR": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Hearing protection, Arc-rated "
    "clothing (switchrooms)",
    "EVP": "Hard hat, Face shield, Chemical gloves",
    "HYD": "Hard hat, Face shield, Chemical gloves",
    "ALS": "Hard hat, Safety glasses, Gloves, Dust mask",
    "LIM": "Hard hat, Goggles, Gloves, Dust mask",
    "WKS": "Hard hat, Safety glasses, Gloves, Hearing protection",
    "WTR": "Hard hat, Safety glasses, Life jacket (near open water)",
}
NEW_PPE = {
    "BXH": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Dust mask, Hearing protection, "
    "Hi-vis vest (where vehicles operate)",
    "GRD": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Hearing protection",
    "DIG": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Heat-resistant gloves, Chemical gloves, Chemical suit (at line breaking)",
    "CLR": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Chemical gloves",
    "FLT": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Chemical gloves",
    "PRC": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Goggles, Chemical gloves, "
    "Harness (where required)",
    "EVP": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Heat-resistant gloves, Chemical gloves",
    "HYD": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Hearing protection, Face shield "
    "over glasses (caustic)",
    "CAL": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Heat-resistant gloves, "
    "Heat-protective clothing (near kilns), Dust mask",
    "ALS": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Dust mask, Hi-vis vest (where "
    "vehicles operate)",
    "TNK": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Face shield over glasses "
    "(caustic), Chemical gloves, Chemical suit (during transfers)",
    "LIM": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Goggles, Dust mask, Chemical "
    "gloves",
    "PWR": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Hearing protection, Arc-rated "
    "clothing (switchrooms), Life jacket (near open water)",
    "WKS": "Hard hat, Safety glasses, Gloves, Safety boots, Flame-resistant coverall, Hearing protection, Welding "
    "face shield (hot work)",
    "LAB": "Safety glasses (laboratory), Lab coat (laboratory), Chemical gloves (laboratory)",
    "WTR": "Hard hat, Safety glasses, Life jacket (near open water)",
}
LAB = ("LAB", "Laboratory & offices", "WKS", "no_eye_protection,no_gloves")

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


def bbox(poly: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def inside(poly: list[tuple[int, int]], px: float, py: float) -> bool:
    hit = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def remap(x: int, y: int, old: tuple[int, int, int, int], new: tuple[int, int, int, int]) -> tuple[int, int]:
    """Same relative position inside the old rectangle and the new one, kept inside the new rectangle."""
    ox, oy, ow, oh = old
    nx, ny, nw, nh = new
    fx = min(1.0, max(0.0, (x - ox) / ow))
    fy = min(1.0, max(0.0, (y - oy) / oh))
    return round(nx + fx * nw), round(ny + fy * nh)


def into_polygon(x: int, y: int, poly: list[tuple[int, int]]) -> tuple[int, int]:
    """Move a point toward the polygon's box centre in small steps until it is strictly inside."""
    bx, by, bw, bh = bbox(poly)
    cx, cy = bx + bw / 2, by + bh / 2
    for step in range(21):
        t = step / 20
        px, py = round(x + (cx - x) * t), round(y + (cy - y) * t)
        if inside(poly, px, py):
            return px, py
    return round(cx), round(cy)


def _move_pins(conn, ids: dict[str, int], forward: bool) -> int:
    moved = 0
    for code, old in OLD_RECT.items():
        if code not in ids:
            continue
        poly = NEW_POLY[code]
        rows = conn.execute(
            sa.select(hazards.c.id, hazards.c.x, hazards.c.y).where(
                hazards.c.area_id == ids[code], hazards.c.x.is_not(None)
            )
        ).all()
        for hid, x, y in rows:
            if forward:
                nx, ny = into_polygon(*remap(x, y, old, bbox(poly)), poly)
            else:
                nx, ny = remap(x, y, bbox(poly), old)
            conn.execute(hazards.update().where(hazards.c.id == hid).values(x=nx, y=ny))
            moved += 1
    return moved


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.select(areas.c.id, areas.c.code, areas.c.owner_id)).all()
    ids = {code: aid for aid, code, _ in rows}
    owners = {code: owner for _, code, owner in rows}
    _move_pins(conn, ids, forward=True)
    for code, poly in NEW_POLY.items():
        if code not in ids:
            continue
        x, y, w, h = bbox(poly)
        values = {"x": x, "y": y, "w": w, "h": h, "required_ppe": NEW_PPE[code]}
        if code in NAMES:
            values["name"] = NAMES[code][1]
        conn.execute(areas.update().where(areas.c.id == ids[code]).values(**values))
    code, name, like, checks = LAB
    fallback = conn.execute(sa.select(users.c.id).where(users.c.role == "AREA_OWNER").order_by(users.c.id)).first()
    owner = owners.get(like) or (fallback[0] if fallback else None)
    if code not in ids and owner is not None:
        x, y, w, h = bbox(NEW_POLY[code])
        conn.execute(
            areas.insert().values(
                code=code, name=name, owner_id=owner, required_ppe=NEW_PPE[code], ai_checks=checks, x=x, y=y, w=w, h=h
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    ids = {code: aid for aid, code in conn.execute(sa.select(areas.c.id, areas.c.code)).all()}
    _move_pins(conn, ids, forward=False)
    for code, (x, y, w, h) in OLD_RECT.items():
        if code not in ids:
            continue
        values = {"x": x, "y": y, "w": w, "h": h, "required_ppe": OLD_PPE[code]}
        if code in NAMES:
            values["name"] = NAMES[code][0]
        conn.execute(areas.update().where(areas.c.id == ids[code]).values(**values))
