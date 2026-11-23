"""EXPERIMENTAL unsafe-condition suggestions behind SHMS_EXPERIMENTAL_CONDITIONS (off by default)."""

import pytest

from shms import services, taxonomy
from shms.detection import conditions_vlm
from shms.models import Role, Status
from shms.services import Confirmation
from shms.settings import override_settings
from tests.conftest import jpeg_bytes, login
from tests.test_api import REPORTER, h
from tests.test_workflow import area, users

EXP = ("floor_liquid", "walkway_obstruction")


@pytest.fixture()
def flag_on(settings):
    return override_settings(experimental_conditions=True)


def _report_via_form(client, name="site_no_hard_hat.jpg"):
    login(client, REPORTER)
    r = client.post(
        "/report", data={"area_id": 3}, files={"photo": (name, jpeg_bytes(), "image/jpeg")}, follow_redirects=False
    )
    assert r.status_code == 303
    return r.headers["location"]


def test_experimental_categories_are_never_ai_released():
    assert not set(EXP) & set(taxonomy.ai_codes()) and not set(EXP) & set(taxonomy.enabled_codes())
    assert all(taxonomy.get(c).experimental for c in EXP)


def test_flag_off_by_default_allows_manual_reports_and_never_calls_the_model(client, monkeypatch, settings):
    assert settings.experimental_conditions is False
    monkeypatch.setattr(conditions_vlm, "ask", lambda *a, **k: pytest.fail("model must not be called"))
    page = client.get(_report_via_form(client)).text
    assert 'value="floor_liquid"' in page and "Experimental check</strong>" not in page


@pytest.mark.parametrize("code", [*EXP, "open_panel", "floor_opening", "surface_corrosion", "other_condition"])
def test_manual_condition_needs_no_model(empty_db, code):
    rep = users(empty_db)[Role.REPORTER][0]
    d = services.create_draft(empty_db, rep, area(empty_db), None, None)
    hz = services.confirm(empty_db, d, rep, Confirmation(code, 3))
    assert hz.status == Status.OPEN and hz.category_code == code
    assert hz.ai_top_code is None and hz.ai_accepted is None


def test_flag_on_shows_a_fixed_wording_note_never_preselected(client, monkeypatch, flag_on):
    monkeypatch.setattr(
        conditions_vlm,
        "ask",
        lambda *a, **k: {"spill": True, "obstruction": False, "explanation": "hydraulic oil from the press"},
    )
    page = client.get(_report_via_form(client)).text
    assert "Experimental" in page and "Possible liquid on the floor" in page
    assert "hydraulic oil" not in page  # the model's free text (which may name a substance) is not shown
    assert 'value="floor_liquid"' in page and 'value="floor_liquid" selected' not in page
    assert "Object possibly obstructing a walkway" not in page.split("Experimental")[1].split("</div>")[0]


def test_flag_on_failure_of_the_experimental_model_never_blocks_a_report(client, monkeypatch, flag_on):
    def boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(conditions_vlm, "ask", boom)
    page = client.get(_report_via_form(client)).text
    assert "Step 2 of 2" in page  # the confirm form is shown as usual


def test_flag_on_does_not_change_the_ppe_ai_suggestion(client, monkeypatch, flag_on):
    monkeypatch.setattr(conditions_vlm, "ask", lambda *a, **k: {"spill": True, "obstruction": True, "explanation": ""})
    hid = int(_report_via_form(client).split("/")[2])
    hz = client.get(f"/api/hazards/{hid}", headers=h(REPORTER)).json()
    assert hz["ai_top_code"] == "no_hard_hat"
    assert {s["code"] for s in hz["ai_suggestions"] if s.get("experimental")} == set(EXP)


def test_flag_on_reporter_can_confirm_an_experimental_type(empty_db, flag_on):
    rep = users(empty_db)[Role.REPORTER][0]
    d = services.create_draft(empty_db, rep, area(empty_db), None, None)
    hz = services.confirm(empty_db, d, rep, Confirmation("floor_liquid", 3))
    assert hz.status == Status.OPEN and hz.category_code == "floor_liquid"


def test_api_experimental_observation_uses_only_visible_condition_language(client, monkeypatch, flag_on):
    monkeypatch.setattr(conditions_vlm, "ask", lambda *a: {"spill": True, "obstruction": False, "explanation": "acid"})
    report_url = _report_via_form(client)
    result = client.get(f"/api/hazards/{report_url.split('/')[2]}", headers=h(REPORTER)).json()
    observation = next(s for s in result["ai_suggestions"] if s.get("experimental"))
    assert observation["code"] == "floor_liquid"
    assert "acid" not in observation["explanation"]
