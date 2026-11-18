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


def test_layout_matches_reporting_areas_and_stays_inside_viewbox():
    assert {u.code for u in site_layout.UNITS if u.reporting} == {row[0] for row in AREAS}
    for u in site_layout.UNITS:
        assert 0 <= u.x < u.x + u.w <= 1200
        assert 0 <= u.y < u.y + u.h <= 800
        if u.reporting:
            path = site_layout.walk_route(u.code, set())
            assert path[0] == site_layout.GATE
            assert path[-1] == (u.x + u.w // 2, u.y + u.h)


def test_route_detours_and_refuses_flagged_or_unreachable_destinations():
    direct = site_layout.walk_route("DIG", set())
    detour = site_layout.walk_route("DIG", {"BXH", "GRD"})
    assert detour and detour != direct
    assert site_layout.walk_route("DIG", {"DIG"}) == []
    assert site_layout.walk_route("DIG", {"GRD", "CLR"}) == []
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


def test_lots_do_not_overlap():
    for a, b in combinations(site_layout.UNITS, 2):
        assert a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y, (a.code, b.code)


def test_entry_panel_and_routing_ignore_display_filters(client, db):
    login(client, 9)

    area = db.scalar(select(Area).where(Area.code == "DIG"))
    hazard = db.scalar(select(Hazard).where(Hazard.area_id == area.id, Hazard.status.in_(ACTIVE)))
    hazard.created_at = utcnow() - timedelta(days=800)
    hazard.risk_level = "High"
    db.commit()
    page = client.get("/site?unit=DIG&route=1&window=30&level=Extreme&overlay=reports")
    assert page.status_code == 200
    assert "The destination has active High or Extreme" in page.text
    assert "Recent verified closures" in page.text and "Required PPE" in page.text
    assert 'id="walk-route"' not in page.text


@pytest.mark.parametrize("user_id", [1, 4, 8, 9], ids=["reporter", "owner", "supervisor", "manager"])
def test_every_role_can_check_entry_conditions(client, user_id):
    login(client, user_id)
    page = client.get("/site", params={"unit": "DIG", "route": "1"})
    assert page.status_code == 200
    assert 'id="unit-detail"' in page.text
    assert "Chemical gloves" in page.text
    assert "follow site rules and permits" in page.text
