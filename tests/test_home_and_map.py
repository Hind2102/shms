"""Role-specific home pages and the refinery plan view (Phase 3)."""

import re
from datetime import timedelta

import pytest

from shms import services
from shms.models import Area, Hazard, Role, Status, User, utcnow
from tests.conftest import CLOSE, login
from tests.test_api import OWNER_DIG, REPORTER, SUPERVISOR
from tests.test_workflow import area, report, users

MANAGER = 9


def _visible(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


# ---------------------------------------------------------------- role home data


def test_supervisor_home_lists_verifications_urgent_items_and_escalations(empty_db):
    r = users(empty_db)
    sup = r[Role.SUPERVISOR][0]
    pending = report(empty_db, consequence=2)
    services.close(empty_db, pending, empty_db.get(User, pending.area.owner_id), "Done", **CLOSE)
    urgent = report(empty_db, code="no_eye_protection", consequence=5)
    for _ in range(3):
        urgent = report(empty_db, code="no_eye_protection", consequence=5)
    escalated = report(empty_db, consequence=2)
    escalated.escalation_level = 1
    home = services.role_home(empty_db, sup)
    assert pending in home["to_verify"] and urgent in home["urgent"] and escalated in home["escalated"]


def test_area_owner_home_lists_my_open_work_sorted_by_deadline(empty_db):
    owner = area(empty_db).owner
    a = report(empty_db, consequence=4)
    b = report(empty_db, consequence=1)
    home = services.role_home(empty_db, owner)
    assert home["my_work"] == sorted([a, b], key=lambda h: h.due_at)
    other = area(empty_db, "CAL").owner
    assert services.role_home(empty_db, other)["my_work"] == []


def test_reporter_home_shows_my_reports_with_status(empty_db):
    rep = users(empty_db)[Role.REPORTER][0]
    h = report(empty_db)
    home = services.role_home(empty_db, rep)
    assert h in home["my_reports"]


def test_manager_home_has_closure_performance_with_its_denominator(empty_db):
    sup = users(empty_db)[Role.SUPERVISOR][0]
    now = utcnow()
    on_time = report(empty_db, consequence=2, at=now - timedelta(days=20))
    services.close(
        empty_db, on_time, empty_db.get(User, on_time.area.owner_id), "Done", at=now - timedelta(days=19), **CLOSE
    )
    services.verify(empty_db, on_time, sup, "ok", at=now - timedelta(days=18))
    late = report(empty_db, consequence=2, at=now - timedelta(days=40))  # Low band: 30-day target
    services.close(empty_db, late, empty_db.get(User, late.area.owner_id), "Done", at=now - timedelta(days=5), **CLOSE)
    services.verify(empty_db, late, sup, "ok", at=now - timedelta(days=4))
    assert late.closed_at > late.due_at
    m = User(name="Manager", role=Role.MANAGER)
    empty_db.add(m)
    empty_db.flush()
    perf = services.role_home(empty_db, m, now=now)["closure"]
    assert perf["verified_closures"] == 2 and perf["on_time"] == 1 and perf["window_days"] == 90


# ---------------------------------------------------------------- plan view (overlay calculations)


def test_open_risk_overlay_sums_active_risk_in_the_window_and_states_its_basis(empty_db):
    h1 = report(empty_db, consequence=3)
    h2 = report(empty_db, consequence=2)
    view = services.site_overview(empty_db, overlay="open_risk", window_days=90)
    dig = next(a for a in view["areas"] if a["code"] == "DIG")
    assert dig["value"] == h1.risk_score + h2.risk_score
    assert "sum of risk scores" in view["basis"].lower() and "90 days" in view["basis"]
    assert view["site_total"] == h1.risk_score + h2.risk_score


def test_areas_without_hazards_are_labelled_no_records_never_safe(empty_db):
    view = services.site_overview(empty_db, overlay="open_risk", window_days=30)
    cal = next(a for a in view["areas"] if a["code"] == "CAL")
    assert cal["value"] == 0 and cal["label"] == "No recorded hazards in this window"
    assert "safe" not in cal["label"].lower()


def test_report_volume_overlay_is_neutral_and_says_it_is_not_danger(empty_db):
    report(empty_db)
    view = services.site_overview(empty_db, overlay="reports", window_days=30)
    assert view["scale"] == "neutral" and "not a measure of danger" in view["basis"]


def test_overdue_overlay_counts_only_hazards_awaiting_action(empty_db):
    h = report(empty_db, consequence=2)
    h.due_at = utcnow() - timedelta(days=1)
    done = report(empty_db, consequence=2)
    done.due_at = utcnow() - timedelta(days=1)
    services.close(empty_db, done, empty_db.get(User, done.area.owner_id), "Done", **CLOSE)
    view = services.site_overview(empty_db, overlay="overdue", window_days=30)
    assert next(a for a in view["areas"] if a["code"] == "DIG")["value"] == 1


def test_level_filter_restricts_to_high_and_extreme(empty_db):
    report(empty_db, consequence=1)
    view = services.site_overview(empty_db, overlay="open_risk", window_days=90, min_level="High")
    assert view["site_total"] == 0


# ---------------------------------------------------------------- pages


@pytest.mark.parametrize(
    ("uid", "heading"),
    [
        (REPORTER, "Your reports"),
        (OWNER_DIG, "Your open hazards"),
        (SUPERVISOR, "Waiting for your verification"),
        (MANAGER, "Site priorities"),
    ],
)
def test_each_role_gets_its_own_home_page(client, uid, heading):
    login(client, uid)
    page = client.get("/").text
    assert heading in page


def test_plan_view_page_is_labelled_illustrative_and_explains_the_overlay(client):
    login(client, MANAGER)
    for overlay in ("open_risk", "overdue", "reports"):
        page = _visible(client.get(f"/site?overlay={overlay}&window=30").text)
        assert "Concept layout only" in page and "require a verified site plot plan" in page  # v1.5.0 map note
        assert "Calculation:" in page
        assert not re.search(r"\bsafe\b", page, re.I)


def test_plan_view_ignores_unknown_filter_values(client):
    login(client, MANAGER)
    assert client.get("/site?overlay=boom&window=-5&level=xyz").status_code == 200


def test_risk_matrix_page_separates_guidance_from_project_choices(client):
    login(client, REPORTER)
    page = _visible(client.get("/matrix").text)
    assert "From the ADOSH-SF guideline" in page and "Defined by this project" in page
    assert "project heuristic" in page.lower()


def test_dashboard_stays_available_for_everyone(client, db):
    login(client, REPORTER)
    assert client.get("/dashboard").status_code == 200
    assert db.query(Area).count() and db.query(Hazard).filter(Hazard.status != Status.DRAFT).count()
