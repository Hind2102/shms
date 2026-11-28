"""v1.7.0: hazard process flow, analysis numbers against the database, register search/CSV/quick actions, role pages."""

import csv
import io
import re
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import select

from shms import analysis, flow, heatmap, services
from shms.models import Hazard, Status, utcnow
from tests.conftest import CLOSE, login
from tests.test_api import OWNER_DIG, REPORTER, SUPERVISOR, create, h

MANAGER = 9


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ---------------------------------------------------------------- flow stage logic


def test_every_status_maps_to_exactly_one_highlighted_stage(client, db):
    # the seeded site has no drafts or planned actions: add one of each through the API
    create(client)
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_gloves", "consequence": 3}
    )
    client.post(f"/api/hazards/{hid}/plan", headers=h(OWNER_DIG), json={"action": "Issue gloves"})
    db.expire_all()
    seen = set()
    for hz in db.scalars(select(Hazard)):
        fl = flow.build(hz)
        current = [s for s in fl.stages if s.state == "current"]
        assert len(current) == 1, hz.id
        assert current[0].key == flow.CURRENT[hz.status]
        assert fl.index == [s.key for s in fl.stages].index(current[0].key) + 1
        assert all(s.state in ("done", "skipped") for s in fl.stages[: fl.index - 1])
        assert all(s.state == "todo" for s in fl.stages[fl.index :])
        assert flow.chip(hz)["n"] == fl.index
        seen.add(hz.status)
    assert seen == set(Status)  # the seeded site covers every status


def test_confirmed_is_never_current_and_drafts_sit_at_reported(client):
    assert "confirmed" not in flow.CURRENT.values()
    assert flow.CURRENT[Status.DRAFT] == "reported"


def test_done_stages_carry_who_and_when_from_the_audit_trail(client, db):
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_gloves", "consequence": 3}
    )
    client.post(f"/api/hazards/{hid}/plan", headers=h(OWNER_DIG), json={"action": "Issue gloves"})
    hz = db.get(Hazard, hid)
    db.refresh(hz)
    fl = flow.build(hz)
    by_key = {s.key: s for s in fl.stages}
    assert by_key["planned"].state == "current" and by_key["planned"].who
    for key in ("reported", "confirmed", "assigned"):
        assert by_key[key].state == "done" and by_key[key].who and by_key[key].when, key
    events = {e.kind: e for e in hz.events}
    assert by_key["planned"].when == events["planned"].at
    assert "Action owner" in fl.next_action and fl.next_owner


def test_fixed_on_the_spot_skips_assignment_and_planning(client, db):
    hid = create(client).json()["id"]
    r = client.post(
        f"/api/hazards/{hid}/confirm",
        headers=h(REPORTER),
        json={
            "category_code": "no_gloves",
            "consequence": 2,
            "fixed_on_spot": True,
            "closure_action": "Gloves on",
            **CLOSE,
        },
    )
    assert r.status_code == 200
    hz = db.get(Hazard, hid)
    db.refresh(hz)
    fl = flow.build(hz)
    states = {s.key: s.state for s in fl.stages}
    assert states["pending"] == "current" and states["assigned"] == "skipped" and states["planned"] == "skipped"
    assert any(p["key"] == "fixed" for p in fl.side)
    assert "verifies the closure" in fl.next_action


def test_rejected_and_reopened_side_paths_and_owners(client, db):
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_gloves", "consequence": 3}
    )
    client.post(f"/api/hazards/{hid}/close", headers=h(OWNER_DIG), json={"action": "Gloves issued", **CLOSE})
    client.post(f"/api/hazards/{hid}/reject", headers=h(SUPERVISOR), json={"reason": "Still bare hands"})
    hz = db.get(Hazard, hid)
    db.refresh(hz)
    fl = flow.build(hz)
    assert fl.current.key == "assigned" and [p["key"] for p in fl.side] == ["rejected"]
    assert fl.next_owner == hz.assignee.name


def test_hazard_page_shows_the_flow_with_text_labels(client, db):
    hz = db.scalar(select(Hazard).where(Hazard.status == Status.OPEN))
    login(client, SUPERVISOR)
    page = client.get(f"/hazards/{hz.id}").text
    assert 'aria-current="step"' in page and "Current stage" in page
    text = _text(page)
    for s in flow.STAGES:
        assert s.label.replace("&", "&amp;") in page or s.label in text
    assert "Next action:" in text and "Owner:" in text


def test_process_help_page_lists_every_stage_and_side_path(client):
    login(client, REPORTER)
    text = _text(client.get("/process").text)
    for s in flow.STAGES:
        assert s.label in text.replace("&amp;", "&")
    for _, label, _ in flow.SIDE_PATHS:
        assert label in text


# ---------------------------------------------------------------- analysis numbers against the database


def test_analysis_matrix_and_totals_match_the_database(db):
    an = analysis.compute(db, heatmap.Filters(window_days=365, status="all"))
    since = an.now - timedelta(days=365)
    rows = [x for x in db.scalars(select(Hazard)) if x.status != Status.DRAFT and x.created_at >= since]
    expect = Counter((x.area.code, x.category_code) for x in rows)
    assert {k: v["count"] for k, v in an.matrix.items()} == dict(expect)
    assert an.total == len(rows)
    for (code, cat), cell in an.matrix.items():
        assert cell["risk"] == sum(x.risk_score or 0 for x in rows if (x.area.code, x.category_code) == (code, cat))


def test_analysis_top_overdue_trend_and_common(db):
    an = analysis.compute(db, heatmap.Filters(window_days=365, status="all"))
    active_high = [
        x for x in db.scalars(select(Hazard)) if x.status in analysis.ACTIVE and x.risk_level in ("High", "Extreme")
    ]
    assert len(an.top) == min(15, len(active_high))
    assert [x.risk_score for x in an.top] == sorted((x.risk_score for x in an.top), reverse=True)
    late = [x for x in db.scalars(select(Hazard)) if heatmap.is_overdue(x, an.now)]
    assert sum(r["count"] for r in an.overdue.values()) == len(late)
    y, m, months = an.now.year, an.now.month, set()
    for _ in range(6):
        months.add((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    in_months = [
        x
        for x in db.scalars(select(Hazard))
        if x.status != Status.DRAFT and (x.created_at.year, x.created_at.month) in months
    ]
    assert sum(sum(v) for v in an.trend.values()) == len(in_months)
    for code, cm in an.common.items():
        if cm:
            assert cm[1] == max(v["count"] for (c, _), v in an.matrix.items() if c == code)


def test_analysis_page_and_csv(client):
    login(client, MANAGER)
    page = client.get("/analysis").text
    assert page.count("Calculation:") >= 4 and "not a statement about conditions" in page
    r = client.get("/analysis.csv?status=all&window=365")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[1][:5] == ["area_code", "area", "hazard_code", "hazard", "reports"]
    total = int(re.search(r"(\d+) confirmed reports? in this view", _text(page)).group(1))
    assert sum(int(row[4]) for row in rows[2:]) == total


# ---------------------------------------------------------------- register: search, CSV, counts, quick actions


def test_register_search_and_status_counts(client, db):
    login(client, SUPERVISOR)
    hz = db.scalar(select(Hazard).where(Hazard.status == Status.OPEN))
    page = client.get(f"/hazards?q=%23{hz.id}").text
    assert f'href="/hazards/{hz.id}"' in page
    counts = Counter(x.status.value for x in db.scalars(select(Hazard)) if x.status != Status.DRAFT)
    full = client.get("/hazards").text
    for st in ("open", "pending_verification", "closed"):
        assert re.search(rf'status={st}"[^>]*>[^<]*<span>{counts[st]}</span>', full), st


def test_register_csv_matches_the_filters(client, db):
    login(client, MANAGER)
    r = client.get("/hazards.csv?status=closed")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == sum(1 for x in db.scalars(select(Hazard)) if x.status == Status.CLOSED)
    assert {row["status"] for row in rows} == {"closed"} and {row["stage"] for row in rows} == {"Verified closed"}


def test_quick_actions_follow_permissions(client, db):
    hz = db.scalar(select(Hazard).where(Hazard.status == Status.OPEN, Hazard.assignee_id == OWNER_DIG))
    if hz is None:
        hid = create(client).json()["id"]
        client.post(
            f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_gloves", "consequence": 3}
        )
        hz = db.get(Hazard, hid)
    login(client, OWNER_DIG)
    page = client.get("/hazards?status=open").text
    assert f'href="/hazards/{hz.id}#plan-form"' in page and f'href="/hazards/{hz.id}#close-form"' in page
    login(client, MANAGER)  # read-only role: no action buttons
    page = client.get("/hazards").text
    assert "#plan-form" not in page and "/verify" not in page


def test_verify_in_one_click_from_the_list(client, db):
    hz = db.scalar(select(Hazard).where(Hazard.status == Status.PENDING_VERIFICATION, Hazard.closed_by_id != 8))
    login(client, SUPERVISOR)
    page = client.get("/hazards?status=pending_verification").text
    assert f'action="/hazards/{hz.id}/verify"' in page
    client.post(f"/hazards/{hz.id}/verify", data={"note": "Verified from the list"})
    db.refresh(hz)
    assert hz.status == Status.CLOSED


# ---------------------------------------------------------------- role pages


@pytest.mark.parametrize("user_id", [REPORTER, OWNER_DIG, SUPERVISOR, MANAGER])
def test_every_role_home_opens_with_what_needs_action_now(client, db, user_id):
    from shms.models import User

    login(client, user_id)
    page = client.get("/").text
    cards = services.action_cards(db, db.get(User, user_id), utcnow())
    assert page.index('class="action-cards"') < page.index("</section>")
    for c in cards:
        assert f'<span class="n">{c["n"]}</span><span class="t">{c["title"]}</span>' in page
    assert not re.search(r"\bsafe\b", _text(page), re.I)


@pytest.mark.parametrize("path", ["/analysis", "/process", "/hazards", "/site", "/board", "/queue"])
def test_new_pages_open_for_every_role_that_may_see_them(client, path):
    for uid in (REPORTER, OWNER_DIG, SUPERVISOR, MANAGER):
        login(client, uid)
        code = client.get(path).status_code
        assert code in (200, 403), (path, uid)
        if path in ("/analysis", "/process", "/hazards", "/site"):
            assert code == 200, (path, uid)
