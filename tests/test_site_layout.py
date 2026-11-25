"""Approved concept map (v1.5.0): zone geometry, road graph routing and the entry check."""

from datetime import timedelta
from itertools import combinations

import pytest
from sqlalchemy import select

from shms import site_layout
from shms.models import Area, Hazard, Status, utcnow
from shms.seed import AREAS
from shms.services import ACTIVE
from tests.conftest import login
from tests.test_workflow import report

REPORTING_CODES = {
    "BXH",
    "DIG",
    "GRD",
    "CLR",
    "FLT",
    "PRC",
    "EVP",
    "CAL",
    "HYD",
    "ALS",
    "TNK",
    "LIM",
    "PWR",
    "WKS",
    "WTR",
}


def test_every_reporting_code_has_geometry_inside_the_map():
    assert set(site_layout.REPORTING) == REPORTING_CODES == {row[0] for row in AREAS}
    assert [z.code for z in site_layout.ZONES if not z.reporting] == ["LAB"]  # support area, no hazard totals
    for z in site_layout.ZONES:
        assert len(z.points) >= 3 and z.name
        assert 0 <= z.x < z.x + z.w <= site_layout.VIEW_W and 0 <= z.y < z.y + z.h <= site_layout.VIEW_H


def test_seed_names_come_from_the_map():
    assert {row[0]: row[1] for row in AREAS} == {code: z.name for code, z in site_layout.REPORTING.items()}


def test_zones_do_not_overlap():
    for a, b in combinations(site_layout.ZONES, 2):
        apart = a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
        assert apart, (a.code, b.code)
        assert not any(b.contains(*p) and b.distance(p) == 0 and not _on_outline(b, p) for p in a.points)


def _on_outline(z, p):
    return any(site_layout._dist_point_segment(p, e) < 1e-9 for e in z.edges())


@pytest.mark.parametrize("code", sorted(REPORTING_CODES))
def test_every_zone_is_reachable_from_the_south_gate_along_the_roads(code):
    path = site_layout.walk_route(code, set())
    assert path[0] == site_layout.GATE
    assert site_layout.zone(code).distance(path[-1]) == 0  # ends on the zone outline
    for p in _legs(path):  # every leg except the last step into the zone runs along a road centre-line
        assert any(site_layout._on(seg, p) for seg in site_layout.ROADS), p


def test_gate_is_on_the_main_access_road():
    assert any(site_layout._on(seg, site_layout.GATE) for seg in site_layout.ROADS)


def _legs(path):
    for a, b in zip(path[:-2], path[1:-1], strict=True):
        n = max(abs(a[0] - b[0]), abs(a[1] - b[1])) // 5 or 1
        yield from (((a[0] + (b[0] - a[0]) * k / n), (a[1] + (b[1] - a[1]) * k / n)) for k in range(n + 1))


def _graph_edges_on(path):
    """The road-graph edges a route uses (a drawn leg may span several edges)."""
    legs = [(min(a, b), max(a, b)) for a, b in zip(path[:-2], path[1:-1], strict=True)]
    return [
        e for e in site_layout.EDGES if any(site_layout._on(leg, e[0]) and site_layout._on(leg, e[1]) for leg in legs)
    ]


@pytest.mark.parametrize(
    "dest,flagged",
    [("HYD", {"WTR"}), ("DIG", {"GRD", "CLR"}), ("CLR", {"PRC", "HYD"}), ("TNK", {"EVP"}), ("WKS", {"ALS", "PWR"})],
)
def test_route_avoids_every_road_beside_a_flagged_zone(dest, flagged):
    path = site_layout.walk_route(dest, flagged)
    assert path, "a detour exists for these cases"
    used = _graph_edges_on(path)
    assert used and not set(used) & site_layout.blocked_edges(flagged)
    zones = [site_layout.zone(c) for c in flagged]
    for a, b in used:  # no stretch of road used runs beside a flagged zone (the gate junction itself is never closed)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        assert all(z.distance(mid) >= site_layout.ADJACENT for z in zones), (a, b)


def test_every_road_stretch_beside_a_flagged_zone_is_closed():
    for code in site_layout.REPORTING:
        z = site_layout.zone(code)
        closed = site_layout.blocked_edges({code})
        for a, b in site_layout.EDGES:
            beside = z.distance(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)) < site_layout.ADJACENT
            assert ((a, b) in closed) == beside


def test_route_detours_and_refuses_honestly():
    direct = site_layout.walk_route("HYD", set())
    detour = site_layout.walk_route("HYD", {"WTR"})
    assert detour and detour != direct
    assert site_layout.walk_route("DIG", {"DIG"}) == []  # destination flagged
    assert site_layout.walk_route("DIG", {"BXH", "GRD", "CLR", "FLT", "WTR"}) == []  # every approach blocked
    assert site_layout.walk_route("LAB", set()) == []  # support area
    assert site_layout.walk_route("UNKNOWN", set()) == []


def test_flagged_areas_consider_old_pending_cases(empty_db):
    h = report(empty_db)
    h.risk_level = "High"
    h.created_at = utcnow() - timedelta(days=400)
    h.closure_action = "Repair recorded"
    h.status = Status.PENDING_VERIFICATION
    assert site_layout.flagged_areas(empty_db) == {"DIG"}
    h.status = Status.CLOSED
    h.closure_action = "verified"
    assert site_layout.flagged_areas(empty_db) == set()


def test_entry_panel_and_routing_ignore_display_filters(client, db):
    login(client, 9)
    area = db.scalar(select(Area).where(Area.code == "DIG"))
    hazard = db.scalar(select(Hazard).where(Hazard.area_id == area.id, Hazard.status.in_(ACTIVE)))
    if hazard is None:  # make sure DIG has an active case to flag
        hazard = report(db)
    hazard.created_at = utcnow() - timedelta(days=800)
    hazard.risk_level = "High"
    db.commit()
    page = client.get("/site?unit=DIG&route=1&window=30&level=Extreme&overlay=reports")
    assert page.status_code == 200
    assert "The destination has active High or Extreme" in page.text
    assert "Recent verified closures" in page.text and "Required PPE" in page.text
    assert 'id="walk-route"' not in page.text


def test_blocked_route_names_the_flagged_zones(client, db):
    login(client, 9)
    for h in db.scalars(select(Hazard).where(Hazard.status.in_(ACTIVE))):
        h.risk_level = "Low"  # start from no flagged zones
    for code in ("BXH", "GRD", "CLR", "FLT", "WTR"):
        area = db.scalar(select(Area).where(Area.code == code))
        h = report(db, code="no_gloves")
        h.area_id, h.risk_level = area.id, "High"
    db.commit()
    page = client.get("/site?unit=DIG&route=1").text
    assert "block every road approach" in page and "BXH, CLR, FLT, GRD, WTR" in page
    assert 'id="walk-route"' not in page


@pytest.mark.parametrize("user_id", [1, 4, 8, 9], ids=["reporter", "owner", "supervisor", "manager"])
def test_every_role_can_check_entry_conditions(client, user_id):
    login(client, user_id)
    page = client.get("/site", params={"unit": "ALS", "route": "1"})
    assert page.status_code == 200
    assert 'id="unit-detail"' in page.text and "Alumina storage" in page.text
    assert "Dust mask" in page.text and "project assumption" in page.text
    assert "follow site rules and permits" in page.text
    assert site_layout.FOOTER_NOTE in page.text
    assert "Muster" not in page.text  # the approved map shows no muster points, so none are claimed
    assert 'id="walk-route"' in page.text or "Route unavailable" in page.text


@pytest.mark.parametrize("overlay", ["open_risk", "overdue", "reports"])
def test_site_page_shows_every_reporting_zone_with_its_overlay(client, overlay):
    login(client, 9)
    page = client.get("/site", params={"overlay": overlay}).text
    assert 'href="/static/ata_concept_map.svg"' in page
    for code in REPORTING_CODES:
        assert f"unit={code}" in page
    assert "Calculation:" in page and "No matching records" in page
