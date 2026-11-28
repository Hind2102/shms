"""v1.7.0 weather-style heat map: weights, filters, no-data zones, scale, live updates."""

import re
from datetime import timedelta

import numpy as np
import pytest
from sqlalchemy import select

from shms import heatmap, services
from shms.heatmap import Filters
from shms.models import Area, Hazard, Status, utcnow
from tests.conftest import login
from tests.test_api import REPORTER, SUPERVISOR
from tests.test_workflow import report

MANAGER = 9


def _hz(status=Status.OPEN, level="High", score=12, due_days=5, created_days=1, **kw):
    now = utcnow()
    return Hazard(
        status=status,
        risk_level=level,
        risk_score=score,
        due_at=now + timedelta(days=due_days),
        created_at=now - timedelta(days=created_days),
        category_code=kw.get("category", "no_gloves"),
    )


def test_weights_follow_the_documented_rule():
    now = utcnow()
    assert heatmap.weight(_hz(level="High", score=12), now) == 24  # open High: × 2
    assert heatmap.weight(_hz(level="Moderate", score=6), now) == 6
    assert heatmap.weight(_hz(level="Extreme", score=20, due_days=-1), now) == 60  # × 2 × 1.5 overdue
    assert heatmap.weight(_hz(status=Status.PLANNED, level="Low", score=3, due_days=-1), now) == 4.5
    assert heatmap.weight(_hz(status=Status.PENDING_VERIFICATION, score=12), now) == 12
    assert heatmap.weight(_hz(status=Status.CLOSED, score=12), now) == 3
    assert heatmap.weight(_hz(status=Status.DRAFT, score=12), now) == 0


@pytest.mark.parametrize(
    "status,expected",
    [
        ("active", {Status.OPEN, Status.PLANNED, Status.PENDING_VERIFICATION}),
        ("closed", {Status.PENDING_VERIFICATION, Status.CLOSED}),
        ("all", {Status.OPEN, Status.PLANNED, Status.PENDING_VERIFICATION, Status.CLOSED}),
    ],
)
def test_status_filter(status, expected):
    now = utcnow()
    for s in Status:
        assert heatmap.matches(_hz(status=s), Filters(status=status), now) == (s in expected), (status, s)


def test_overdue_category_and_window_filters():
    now = utcnow()
    assert heatmap.matches(_hz(due_days=-1), Filters(status="overdue"), now)
    assert not heatmap.matches(_hz(due_days=1), Filters(status="overdue"), now)
    assert not heatmap.matches(_hz(category="no_gloves"), Filters(category="steam_leak"), now)
    assert heatmap.matches(_hz(category="steam_leak"), Filters(category="steam_leak"), now)
    assert not heatmap.matches(_hz(created_days=40), Filters(window_days=30), now)
    assert heatmap.matches(_hz(created_days=40), Filters(window_days=0), now)


def test_unknown_filter_values_fall_back_safely():
    f = Filters.parse("-5", "boom", "xyz")
    assert (f.window_days, f.category, f.status) == (0, "", "active")


def test_zone_totals_match_the_database(db):
    heat = heatmap.compute(db, Filters(status="all"))
    confirmed = [h for h in db.scalars(select(Hazard)) if h.status != Status.DRAFT]
    assert len(heat.hazards) == len(confirmed)
    for code, z in heat.zones.items():
        mine = [h for h in confirmed if h.area.code == code]
        assert z.count == len(mine) and z.pinned == sum(h.x is not None for h in mine)
        assert z.weight == pytest.approx(sum(heatmap.weight(h, heat.now) for h in mine))


def test_no_data_zones_stay_uncoloured_and_zones_with_data_are_at_least_pale_yellow(db):
    heat = heatmap.compute(db, Filters())
    d = heatmap.density(heat)
    masks = heatmap.zone_masks()
    empty = [c for c, z in heat.zones.items() if not z.count]
    full = [c for c, z in heat.zones.items() if z.count]
    assert empty and full  # the seeded site has both
    for c in empty:
        assert d[masks[c]].max() == 0, c
    for c in full:
        assert d[masks[c]].min() >= heatmap.FLOOR - 1e-9, c
    outside = ~np.logical_or.reduce([masks[c] for c in masks])
    assert d[outside].max() == 0  # roads, sea and land outside the zones are never coloured


def test_one_open_extreme_pinned_hazard_is_full_red(empty_db):
    h = report(empty_db)
    h.status, h.risk_level, h.risk_score, h.x, h.y = Status.OPEN, "Extreme", 25, 247, 548
    h.due_at = utcnow() + timedelta(days=1)
    empty_db.commit()
    d = heatmap.density(heatmap.compute(empty_db, Filters()))
    assert d.max() == pytest.approx(1.0, abs=0.02)
    h.risk_level, h.risk_score = "Low", 2  # a single low hazard is pale, not red
    empty_db.commit()
    d = heatmap.density(heatmap.compute(empty_db, Filters()))
    assert d.max() < 0.1


def test_closing_a_hazard_changes_the_map_immediately(client, db):
    login(client, SUPERVISOR)
    hz = db.scalar(
        select(Hazard).where(Hazard.status == Status.OPEN, Hazard.risk_level.in_(("High", "Extreme"))).limit(1)
    )
    code = hz.area.code
    before = heatmap.compute(db, Filters()).zones[code].weight
    png_before = client.get("/site/heat.png").content
    services.close(db, hz, hz.area.owner, "Barrier fitted", control_type="engineering", residual_consequence=1)
    db.commit()
    after = heatmap.compute(db, Filters()).zones[code].weight
    assert after < before
    assert client.get("/site/heat.png").content != png_before


def test_heat_layer_needs_sign_in_and_is_never_cached(client):
    assert client.get("/site/heat.png", follow_redirects=False).status_code in (303, 401)
    login(client, MANAGER)
    r = client.get("/site/heat.png?status=all&category=no_gloves&window=90")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store" and r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_legend_states_scale_calculation_window_and_denominator(client):
    login(client, REPORTER)
    page = client.get("/site?status=all&window=90&category=no_gloves").text
    text = re.sub(r"<[^>]+>", " ", page)
    assert "Low but recorded" in text and "one open Extreme hazard at a spot" in text
    assert "Calculation:" in text and "Weight = risk score" in text
    assert "reported in the last 90 days" in text and "Worker without gloves" in text
    assert "Denominator:" in text and "with a map pin" in text
    assert not re.search(r"\bsafe\b", text, re.I)


def test_board_shows_the_same_heat_layer(client):
    login(client, SUPERVISOR)
    page = client.get("/board").text
    assert 'href="/site/heat.png?window=0&amp;category=&amp;status=active"' in page
    assert "not a statement about conditions" in page


def test_lab_is_a_reporting_zone_with_its_profile(client, db):
    lab = db.scalar(select(Area).where(Area.code == "LAB"))
    assert lab and "Lab coat (laboratory)" in lab.required_ppe and lab.ai_checks == "no_eye_protection,no_gloves"
    login(client, REPORTER)
    page = client.get("/site?unit=LAB").text
    assert "Laboratory: chemical samples. Offices: no PPE required." in page and "#ppe-coat" in page


def test_no_data_hatching_is_not_overridden_by_css():
    """Regression: a transparent fill rule for zone hit areas hid the hatching on zones without records."""
    from shms.settings import PACKAGE_DIR

    css = (PACKAGE_DIR / "static" / "site-plan.css").read_text()
    assert ".unit-link.no-data .lot-target { fill: url(#no-records); }" in css
    assert css.index(".unit-link .lot-target { fill: transparent") < css.index(".unit-link.no-data .lot-target {")
