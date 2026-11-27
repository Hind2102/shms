"""Migration 0011 (v1.7.0, Al Taweelah illustrative image): renames FLT/PWR, adds LAB, area-profile PPE, pins move
into the new zone polygons; nothing deleted; frozen values match the config, the profiles and the seed."""

import importlib
import sqlite3

import sqlalchemy as sa

from shms import area_profiles, site_layout
from shms import db as dbmod
from shms.seed import LAB_CHECKS, ZONE_PPE
from tests.test_migrations import _old_db, _snapshot

MIGRATION = importlib.import_module("shms.migrations.versions.0011_taweelah_map")


def _at_0010_with_pins(tmp_path):
    url = _old_db(tmp_path / "old.db")
    dbmod.migrate_to_head(url, "0010_report_location")
    con = sqlite3.connect(tmp_path / "old.db")
    con.execute(
        "INSERT INTO areas (id, code, name, owner_id, required_ppe, ai_checks, x, y, w, h) "
        "VALUES (20, 'FLT', 'Security filtration', 2, 'Hard hat', 'no_hard_hat', 414, 772, 246, 50)"
    )
    # hazard 1 (DIG) at the centre of the v1.5 DIG rectangle (175, 320, 215, 502); hazard 2 at its top-left corner
    con.execute("UPDATE hazards SET x = 282, y = 571 WHERE id = 1")
    con.execute("UPDATE hazards SET x = 175, y = 320 WHERE id = 2")
    con.commit()
    con.close()
    return url


def _rows(url):
    eng = sa.create_engine(url)
    with eng.connect() as c:
        areas = {r.code: r for r in c.execute(sa.text("SELECT * FROM areas"))}
        pins = {i: (x, y) for i, x, y in c.execute(sa.text("SELECT id, x, y FROM hazards ORDER BY id"))}
    eng.dispose()
    return areas, pins


def test_existing_rows_and_relationships_are_kept(tmp_path):
    url = _at_0010_with_pins(tmp_path)
    before = _snapshot(url)
    dbmod.migrate_to_head(url)
    assert _snapshot(url) == before  # the snapshot ignores only zones added by design (LAB)


def test_names_follow_the_image_and_lab_is_added_with_owner_ppe_and_checks(tmp_path):
    url = _at_0010_with_pins(tmp_path)
    dbmod.migrate_to_head(url)
    areas, _ = _rows(url)
    assert areas["FLT"].name == "CCL wash (550)" and areas["FLT"].id == 20  # code and id unchanged
    lab = areas["LAB"]
    assert lab.name == "Laboratory & offices" and lab.owner_id == 2  # no WKS here: the only Area Owner
    assert lab.ai_checks == "no_eye_protection,no_gloves"
    assert lab.required_ppe == "Safety glasses (laboratory), Lab coat (laboratory), Chemical gloves (laboratory)"
    assert "Chemical suit (at line breaking)" in areas["DIG"].required_ppe
    z = site_layout.zone("DIG")
    assert (areas["DIG"].x, areas["DIG"].y, areas["DIG"].w, areas["DIG"].h) == (z.x, z.y, z.w, z.h)


def test_pins_move_into_the_new_zone_polygon(tmp_path):
    url = _at_0010_with_pins(tmp_path)
    dbmod.migrate_to_head(url)
    _, pins = _rows(url)
    dig = site_layout.zone("DIG")
    assert all(dig.contains(*p) for p in pins.values())
    assert abs(pins[1][0] - (dig.x + dig.w / 2)) <= 2 and abs(pins[1][1] - (dig.y + dig.h / 2)) <= 2  # centre
    assert abs(pins[2][0] - dig.x) <= 2 and abs(pins[2][1] - dig.y) <= 2  # corner stays (near) the corner


def test_pin_outside_a_bevelled_polygon_is_moved_inside():
    poly = MIGRATION.NEW_POLY["BXH"]  # top-right corner is bevelled
    x, y = MIGRATION.remap(1745, 160, MIGRATION.OLD_RECT["BXH"], MIGRATION.bbox(poly))
    assert not MIGRATION.inside(poly, x, y)
    assert MIGRATION.inside(poly, *MIGRATION.into_polygon(x, y, poly))


def test_downgrade_restores_names_ppe_and_pins_and_keeps_lab(tmp_path):
    from alembic import command

    url = _at_0010_with_pins(tmp_path)
    dbmod.migrate_to_head(url)
    eng = sa.create_engine(url)
    cfg = dbmod._alembic_config()
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "0010_report_location")
    eng.dispose()
    areas, pins = _rows(url)
    assert areas["FLT"].name == "Security filtration" and "LAB" in areas  # never deletes data
    assert areas["DIG"].required_ppe == MIGRATION.OLD_PPE["DIG"]
    assert abs(pins[1][0] - 282) <= 2 and abs(pins[1][1] - 571) <= 2


def test_frozen_values_match_the_config_the_profiles_and_the_seed():
    for code, z in site_layout.REPORTING.items():
        assert [tuple(p) for p in MIGRATION.NEW_POLY[code]] == list(z.points), code
        assert MIGRATION.NEW_PPE[code] == ", ".join(area_profiles.get(code)["required_ppe"]), code
    assert {code: new for code, (_, new) in MIGRATION.NAMES.items()} == {
        c: site_layout.zone(c).name for c in MIGRATION.NAMES
    }
    seeded = {code: ppe for code, _, ppe in ZONE_PPE}
    assert seeded == MIGRATION.NEW_PPE
    assert MIGRATION.LAB[3] == LAB_CHECKS
