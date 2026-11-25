"""Migration 0009 (approved concept map): renames, new zones, proportional pin re-mapping; nothing deleted."""

import importlib
import sqlite3

import sqlalchemy as sa

from shms import db as dbmod
from shms import site_layout
from shms.seed import ZONE_PPE
from tests.test_migrations import _old_db, _snapshot

MIGRATION = importlib.import_module("shms.migrations.versions.0009_ata_site_map")


def _at_0008_with_pins(tmp_path):
    url = _old_db(tmp_path / "old.db")
    dbmod.migrate_to_head(url, "0008_adosh_v4")
    con = sqlite3.connect(tmp_path / "old.db")
    # hazard 1 (DIG) pinned at the centre of the old DIG rectangle (446, 99, 165, 139); hazard 2 at its top-left corner
    con.execute("UPDATE areas SET name = 'Clarification (Red Mud)', code = 'DIG' WHERE id = 1")
    con.execute("UPDATE hazards SET x = 528, y = 168 WHERE id = 1")
    con.execute("UPDATE hazards SET x = 446, y = 99 WHERE id = 2")
    con.commit()
    con.close()
    return url


def test_existing_rows_relationships_and_ids_are_kept(tmp_path):
    url = _at_0008_with_pins(tmp_path)
    before = _snapshot(url)
    dbmod.migrate_to_head(url)
    after = _snapshot(url)
    assert after == before  # every existing row and relationship (the snapshot ignores only the six new zones)
    con = sqlite3.connect(tmp_path / "old.db")
    assert con.execute("SELECT count(*) FROM areas").fetchone()[0] == 1 + 6  # EVP, HYD, ALS, LIM, WKS, WTR
    con.close()


def test_areas_take_map_names_and_new_zones_get_owner_ppe_and_released_checks(tmp_path):
    url = _at_0008_with_pins(tmp_path)
    dbmod.migrate_to_head(url)
    eng = sa.create_engine(url)
    with eng.connect() as c:
        rows = {r.code: r for r in c.execute(sa.text("SELECT * FROM areas"))}
    eng.dispose()
    assert rows["DIG"].name == "Digestion" and rows["DIG"].id == 1
    for code in ("EVP", "HYD", "ALS", "LIM", "WKS", "WTR"):
        z = site_layout.zone(code)
        assert rows[code].name == z.name and (rows[code].x, rows[code].y, rows[code].w, rows[code].h) == (
            z.x,
            z.y,
            z.w,
            z.h,
        )
        assert rows[code].owner_id == 2  # the only Area Owner in the old database
        assert rows[code].ai_checks == "no_hard_hat,no_eye_protection,no_gloves"
    assert rows["WTR"].required_ppe == "Hard hat, Safety glasses, Life jacket (near open water)"
    assert rows["ALS"].required_ppe == "Hard hat, Safety glasses, Gloves, Dust mask"


def test_pins_move_proportionally_into_the_new_polygon(tmp_path):
    url = _at_0008_with_pins(tmp_path)
    dbmod.migrate_to_head(url)
    eng = sa.create_engine(url)
    with eng.connect() as c:
        pins = dict(((i, (x, y)) for i, x, y in c.execute(sa.text("SELECT id, x, y FROM hazards ORDER BY id"))))
    eng.dispose()
    dig = site_layout.zone("DIG")
    assert pins[2] == (dig.x, dig.y)  # corner stays the corner
    assert abs(pins[1][0] - (dig.x + dig.w / 2)) <= 2 and abs(pins[1][1] - (dig.y + dig.h / 2)) <= 3  # centre
    assert all(dig.contains(*p) for p in pins.values())


def test_downgrade_restores_names_and_pins_and_keeps_added_areas(tmp_path):
    from alembic import command

    url = _at_0008_with_pins(tmp_path)
    dbmod.migrate_to_head(url)
    eng = sa.create_engine(url)
    cfg = dbmod._alembic_config()
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0008_adosh_v4")
    with eng.connect() as c:
        assert c.execute(sa.text("SELECT x, y FROM hazards WHERE id = 2")).one() == (446, 99)
        assert c.execute(sa.text("SELECT count(*) FROM areas")).scalar() == 7  # never deletes data
    eng.dispose()


def test_frozen_migration_values_match_the_map_and_the_seed():
    for code, (_, new_name, _, _, rect) in MIGRATION.EXISTING.items():
        z = site_layout.zone(code)
        assert (new_name, rect) == (z.name, (z.x, z.y, z.w, z.h)), code
    ppe = {code: p for code, _, p in ZONE_PPE}
    for code, (name, required, _, rect) in MIGRATION.NEW.items():
        z = site_layout.zone(code)
        assert (name, rect, required) == (z.name, (z.x, z.y, z.w, z.h), ppe[code]), code
