"""v1.6.0 field-first polish: area card, /board, badges, phone bottom action, report pre-selection, seed closure
texts, shift and today summaries, and no page calling missing data "safe"."""

import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from shms import services, site_layout, taxonomy
from shms.models import Area, Hazard, Status
from shms.seed import ACTION_TEXT, PPE_FINDINGS
from shms.settings import PACKAGE_DIR, override_settings
from tests.conftest import jpeg_bytes, login
from tests.test_api import OWNER_DIG, REPORTER, SUPERVISOR, create, h

MANAGER = 9


def _visible(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ---------------------------------------------------------------- "Check before entering" card


def test_area_card_shows_ppe_pictograms_with_labels_hazards_route_and_permit_note(client, db):
    login(client, REPORTER)
    page = client.get("/site?unit=DIG").text
    card = page.split('id="unit-detail"')[1].split("</section>")[0]
    area = db.scalar(select(Area).where(Area.code == "DIG"))
    assert card.count('class="ppe-sign"') == len(area.ppe_list)
    for item in area.ppe_list:
        assert f"<span>{item}</span>" in card  # every pictogram has its text label
    assert '<symbol id="ppe-hat"' in page and "#005eb8" in page  # own drawing, blue mandatory circle
    assert "Open hazards" in card and "Suggested route" in card and "route=1" in card
    assert "Permits and site rules still apply" in card
    assert 'href="/report?area=DIG"' in card


def test_area_card_comes_right_after_the_map_and_pins_are_collapsed(client):
    login(client, REPORTER)
    page = client.get("/site?unit=DIG").text
    assert page.index('id="plan"') < page.index('id="unit-detail"') < page.index("Calculation:")
    assert '<details class="pin-index card">' in page and "Show open hazard pins (" in page


def test_site_map_hides_the_drawings_title_strip_but_keeps_the_concept_note(client):
    login(client, REPORTER)
    page = client.get("/site").text
    assert f'viewBox="0 {site_layout.TITLE_STRIP_H} ' in page
    assert site_layout.FOOTER_NOTE in page


# ---------------------------------------------------------------- /board


def test_board_requires_sign_in(client):
    r = client.get("/board", follow_redirects=False)
    assert r.status_code in (302, 303, 401) and "/login" in r.headers.get("location", "/login")


@pytest.mark.parametrize("user_id", [REPORTER, OWNER_DIG, SUPERVISOR, MANAGER])
def test_board_is_read_only_refreshes_every_minute_and_lists_high_and_extreme(client, db, user_id):
    login(client, user_id)
    page = client.get("/board").text
    assert 'data-seconds="60"' in page and "location.reload()" in page  # 60 s auto-refresh ...
    assert 'id="refresh-toggle"' in page and "Pause auto-refresh" in page  # ... that the viewer can pause
    assert "<form" not in page  # read-only
    urgent = [
        x
        for x in db.scalars(select(Hazard).where(Hazard.status.in_(services.ACTIVE)))
        if x.risk_level in ("High", "Extreme")
    ]
    assert f'<span class="bk-v">{len(urgent)}</span>' in page
    assert all(f">{x.area.code}</strong>" in page for x in urgent[:12])
    assert 'href="/static/ata_concept_map.svg"' in page


def test_board_dark_background_option(client):
    login(client, MANAGER)
    assert 'class="board-page dark"' in client.get("/board?theme=dark").text
    assert 'class="board-page"' in client.get("/board").text


# ---------------------------------------------------------------- badges


def test_risk_badges_always_carry_the_word_and_a_shape_icon():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(PACKAGE_DIR / "templates")))
    macro = env.get_template("_macros.html").module.level
    css = (PACKAGE_DIR / "static" / "style.css").read_text()
    for word in ("Low", "Moderate", "High", "Extreme"):
        assert f">{word}</span>" in str(macro(word))
        assert f'.lvl.{word}::before {{ content: "\\25' in css, word  # a shape icon, not colour alone


# ---------------------------------------------------------------- phone bottom action bar


def test_every_page_has_the_report_action_in_the_bottom_bar(client):
    login(client, REPORTER)
    for path in ("/", "/site", "/hazards", "/matrix", "/notifications", "/dashboard"):
        bar = client.get(path).text.split('class="bottom-bar"')[1].split("</div>")[0]
        assert 'class="btn primary report-fab" href="/report">Report a hazard<' in bar, path


def test_report_and_confirm_put_their_submit_in_the_bottom_bar(client):
    login(client, REPORTER)
    bar = client.get("/report").text.split('class="bottom-bar"')[1]
    assert 'type="submit" form="hazard-report"' in bar
    hid = create(client).json()["id"]
    bar = client.get(f"/hazards/{hid}/confirm").text.split('class="bottom-bar"')[1]
    assert 'type="submit" form="confirm-form"' in bar


def test_supervisor_verifies_from_the_bottom_bar(client):
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 2}
    )
    body = {"action": "Hard hat issued", "control_type": "ppe", "residual_consequence": 1}
    client.post(f"/api/hazards/{hid}/close", headers=h(OWNER_DIG), json=body)
    login(client, SUPERVISOR)
    bar = client.get(f"/hazards/{hid}").text.split('class="bottom-bar"')[1]
    assert 'type="submit" form="verify-form"' in bar


def test_consequence_is_chosen_on_large_labelled_cards(client):
    login(client, REPORTER)
    hid = create(client).json()["id"]
    page = client.get(f"/hazards/{hid}/confirm").text
    assert page.count('class="cons-card cons-') == 5 and "Insignificant" in page and "Catastrophic" in page


# ---------------------------------------------------------------- minimal typing: area pre-selection


def test_report_form_preselects_the_area_of_the_last_report_or_the_linked_area(client, db):
    login(client, REPORTER)
    client.post("/report", data={"area_id": 7}, files={"photo": ("p.jpg", jpeg_bytes(), "image/jpeg")})
    page = client.get("/report").text
    assert re.search(r'<option value="7" selected', page) and "area of your last report" in page
    als = db.scalar(select(Area).where(Area.code == "ALS"))
    page = client.get("/report?area=ALS").text
    assert re.search(rf'<option value="{als.id}" selected', page) and "Area from the link" in page
    assert page.index('id="photo"') < page.index('id="area"')  # photo first


def test_new_reporter_gets_an_explicit_choose_area_placeholder(client, db):
    from shms import auth
    from shms.models import Role, User

    db.add(
        User(
            name="New contractor",
            role=Role.REPORTER,
            username="newbie",
            password_hash=auth.hash_password("pw-new-1234"),
        )
    )
    db.commit()
    from tests.conftest import login as _login

    uid = db.scalar(select(User.id).where(User.username == "newbie"))
    _login(client, uid, "pw-new-1234")
    assert '<option value="" selected disabled>Choose the area</option>' in client.get("/report").text


# ---------------------------------------------------------------- seed closure texts


def test_seeded_closure_text_matches_the_hazard_type(db):
    closed = [x for x in db.scalars(select(Hazard)) if x.closure_action]
    assert closed
    for x in closed:
        assert x.closure_action in ACTION_TEXT[x.category_code].values(), (x.id, x.category_code, x.closure_action)
        assert x.closure_action == ACTION_TEXT[x.category_code][x.control_type]
    ppe_words = (
        "hard hat",
        "glasses",
        "face shield",
        "glove",
        "ppe",
        "briefing",
        "toolbox",
        "sampl",
        "valve",
        "overhead",
    )
    for x in closed:
        if x.category_code in PPE_FINDINGS:
            assert any(w in x.closure_action.lower() for w in ppe_words), x.closure_action
            assert not any(w in x.closure_action.lower() for w in ("drip tray", "grating", "spill", "corros"))


def test_action_texts_cover_every_seeded_category_and_control():
    from shms import risk

    for code in {c for profile in __import__("shms.seed", fromlist=["PROFILE"]).PROFILE.values() for c in profile}:
        assert set(ACTION_TEXT[code]) == set(risk.control_types()), code
        assert taxonomy.get(code)


# ---------------------------------------------------------------- shift and today summaries


def test_shift_window_follows_the_project_setting():
    override_settings(shift_start_hour=6, site_utc_offset_h=4)
    # 07:20 local = 03:20 UTC -> day shift since 06:00 local = 02:00 UTC
    assert services.shift_window(datetime(2026, 11, 26, 3, 20)) == ("Day shift", datetime(2026, 11, 26, 2, 0))
    # 19:00 local = 15:00 UTC -> night shift since 18:00 local = 14:00 UTC
    assert services.shift_window(datetime(2026, 11, 26, 15, 0)) == ("Night shift", datetime(2026, 11, 26, 14, 0))
    # 03:00 local = 23:00 UTC previous day -> night shift since 18:00 local the day before
    assert services.shift_window(datetime(2026, 11, 25, 23, 0)) == ("Night shift", datetime(2026, 11, 25, 14, 0))


def test_supervisor_home_shows_counts_since_start_of_shift(client):
    login(client, SUPERVISOR)
    page = _visible(client.get("/").text)
    assert re.search(r"(Day|Night) shift – since \d\d:\d\d", page)
    for label in ("Reported", "High or Extreme", "Alerts sent", "Closures verified", "Waiting for verification"):
        assert label in page


def test_area_owner_home_starts_with_my_areas_today(client):
    login(client, OWNER_DIG)
    page = client.get("/").text
    assert page.index("My areas today") < page.index("Your open hazards")
    for code in ("BXH", "GRD", "DIG"):  # the areas this owner is accountable for
        assert f'href="/site?unit={code}#unit-detail"' in page


# ---------------------------------------------------------------- honesty: never "safe" for missing data


def _clear_history(db):
    from shms.models import HazardEvent, Notification

    for model in (Notification, HazardEvent, Hazard):
        for row in db.scalars(select(model)):
            db.delete(row)
    db.commit()


@pytest.mark.parametrize("user_id", [REPORTER, OWNER_DIG, SUPERVISOR, MANAGER])
def test_no_page_calls_missing_data_safe(client, db, user_id):
    """With no hazards at all every empty state is shown – and none may say the site or an area is safe."""
    _clear_history(db)
    login(client, user_id)
    paths = [
        "/",
        "/site",
        "/site?unit=WTR&route=1",
        "/site?overlay=overdue",
        "/site?overlay=reports",
        "/dashboard",
        "/hazards",
        "/notifications",
        "/areas/DIG",
        "/board",
        "/matrix",
    ]
    if user_id in (OWNER_DIG, SUPERVISOR):
        paths.append("/queue")
    for path in paths:
        text = _visible(client.get(path).text)
        assert not re.search(r"\bsafe\b", text, re.I), (path, re.search(r".{40}\bsafe\b.{40}", text, re.I))


def test_empty_states_say_no_recorded_hazards(client, db):
    _clear_history(db)
    login(client, MANAGER)
    assert "None recorded" in _visible(client.get("/site").text)
    assert "No active High or Extreme hazards are recorded." in _visible(client.get("/board").text)
    assert "No overdue actions are recorded." in _visible(client.get("/").text)


def test_status_of_a_closed_case_uses_a_completed_mark():
    css = (PACKAGE_DIR / "static" / "style.css").read_text()
    assert '.st.closed::before { content: "\\2713"' in css


def test_board_counts_overdue(client, db):
    login(client, MANAGER)
    hz = db.scalar(select(Hazard).where(Hazard.status == Status.OPEN))
    hz.due_at = hz.created_at - timedelta(days=1)
    db.commit()
    now = services.utcnow() if hasattr(services, "utcnow") else datetime.utcnow()
    active = list(db.scalars(select(Hazard).where(Hazard.status.in_(services.ACTIVE))))
    expected = sum(1 for x in active if x.status in services.AWAITING_ACTION and x.due_at and x.due_at < now)
    page = client.get("/board").text
    assert f'<span class="bk-v">{expected}</span><span class="bk-l">Overdue actions</span>' in page
