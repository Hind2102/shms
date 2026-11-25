"""ADOSH-SF v4.0 features (v1.4.0): hierarchy of controls at closure, residual risk, the high-consequence alert,
the re-scoring migration and the rule that legacy values are never invented."""

import importlib
import sqlite3
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from shms import db as dbmod
from shms import risk, services
from shms.models import Hazard, Notification, Role, Status, User, utcnow
from shms.services import WorkflowError
from tests.conftest import CLOSE, login
from tests.test_api import OWNER_DIG, REPORTER, SUPERVISOR, create, h
from tests.test_authz import MANAGER
from tests.test_migrations import OLD_DDL, OLD_ROWS
from tests.test_workflow import area, report, users

MIGRATION = importlib.import_module("shms.migrations.versions.0008_adosh_v4")


def _owner(db, hz):
    return db.get(User, hz.area.owner_id)


# ---------------------------------------------------------------- a) hierarchy of controls at closure


def test_close_requires_a_control_type_from_the_hierarchy(empty_db):
    hz = report(empty_db)
    with pytest.raises(WorkflowError, match="hierarchy of controls"):
        services.close(empty_db, hz, _owner(empty_db, hz), "Done", residual_consequence=1)
    with pytest.raises(WorkflowError, match="hierarchy of controls"):
        services.close(empty_db, hz, _owner(empty_db, hz), "Done", control_type="hope", residual_consequence=1)
    assert hz.status == Status.OPEN and hz.control_type is None


@pytest.mark.parametrize("code", ["elimination", "substitution", "engineering", "procedural", "ppe"])
def test_each_control_type_is_stored_and_written_to_the_audit_trail(empty_db, code):
    hz = report(empty_db)
    services.close(empty_db, hz, _owner(empty_db, hz), "Done", control_type=code, residual_consequence=1)
    assert hz.control_type == code
    assert f"control: {risk.control_types()[code]['name']}" in hz.events[-1].note


def test_database_rejects_an_unknown_control_type(empty_db):
    hz = report(empty_db)
    hz.control_type = "luck"
    with pytest.raises(sa.exc.IntegrityError):
        empty_db.flush()


def test_reject_clears_the_control_type_and_residual_risk(empty_db):
    hz = report(empty_db)
    services.close(empty_db, hz, _owner(empty_db, hz), "Done", **CLOSE)
    services.reject(empty_db, hz, users(empty_db)[Role.SUPERVISOR][0], "Not good enough")
    assert (hz.control_type, hz.residual_consequence, hz.residual_score, hz.residual_level) == (None,) * 4


# ---------------------------------------------------------------- b) residual risk


def test_residual_risk_is_residual_consequence_times_likelihood(empty_db):
    report(empty_db, code="no_eye_protection")
    hz = report(empty_db, code="no_eye_protection", consequence=4)  # 4 x 2 = 8 High
    assert (hz.risk_score, hz.risk_level) == (8, "High")
    services.close(empty_db, hz, _owner(empty_db, hz), "Barrier", control_type="engineering", residual_consequence=2)
    assert (hz.residual_consequence, hz.residual_score, hz.residual_level) == (2, 4, "Moderate")
    assert "residual risk C2 x L2 = 4 (Moderate), was 8 (High)" in hz.events[-1].note


@pytest.mark.parametrize("bad", [None, 0, 6])
def test_residual_consequence_is_required_and_1_to_5(empty_db, bad):
    hz = report(empty_db)
    with pytest.raises(WorkflowError, match="residual consequence"):
        services.close(empty_db, hz, _owner(empty_db, hz), "Done", control_type="ppe", residual_consequence=bad)


def test_fixed_on_the_spot_also_records_control_and_residual_risk(empty_db):
    with pytest.raises(WorkflowError, match="hierarchy of controls"):
        report(empty_db, fixed_on_spot=True, closure_action="Issued hard hat")
    hz = report(
        empty_db, fixed_on_spot=True, closure_action="Issued hard hat", control_type="ppe", residual_consequence=1
    )
    assert hz.status == Status.PENDING_VERIFICATION and hz.control_type == "ppe" and hz.residual_level == "Low"


def test_api_close_needs_control_type_and_returns_residual_risk(client):
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 3}
    )
    r = client.post(f"/api/hazards/{hid}/close", headers=h(OWNER_DIG), json={"action": "Hard hat issued"})
    assert r.status_code == 422 and "hierarchy of controls" in r.json()["detail"]
    body = {"action": "Hard hat issued", "control_type": "ppe", "residual_consequence": 1}
    j = client.post(f"/api/hazards/{hid}/close", headers=h(OWNER_DIG), json=body).json()
    assert j["control_type"] == "ppe" and j["residual_consequence"] == 1
    assert j["residual_score"] == j["likelihood"] and j["residual_level"] == risk.band_for(j["likelihood"]).level


def test_close_form_shows_hierarchy_and_residual_and_refuses_without_them(client):
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 3}
    )
    login(client, OWNER_DIG)
    page = client.get(f"/hazards/{hid}").text
    assert 'name="control_type" value="elimination"' in page and 'name="residual_consequence"' in page
    assert "PPE (last resort)" in page
    r = client.post(f"/hazards/{hid}/close", data={"action": "Done"}, follow_redirects=False)
    assert r.status_code == 303 and "error=" in r.headers["location"]
    r = client.post(
        f"/hazards/{hid}/close", data={"action": "Done", "control_type": "ppe", "residual_consequence": "1"}
    )
    assert r.status_code == 200 and "PPE (last resort)" in r.text


def test_verifier_sees_original_and_residual_risk(client):
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 3}
    )
    body = {"action": "Hard hat issued", "control_type": "ppe", "residual_consequence": 1}
    client.post(f"/api/hazards/{hid}/close", headers=h(OWNER_DIG), json=body)
    login(client, SUPERVISOR)
    page = client.get(f"/hazards/{hid}").text
    verify_form = page.split("Verify closure")[1].split("</form>")[0]
    assert "Original risk" in verify_form and "residual" in verify_form and "PPE (last resort)" in verify_form
    assert "Control type" in client.get("/queue").text


# ---------------------------------------------------------------- c) high-consequence rule


@pytest.mark.parametrize("consequence", [4, 5])
def test_major_consequence_alerts_even_in_a_low_or_moderate_band(empty_db, consequence):
    hz = report(empty_db, code="no_gloves", consequence=consequence)  # C x L1 = 4 or 5 -> Moderate
    assert hz.risk_level == "Moderate"
    notes = list(empty_db.scalars(select(Notification).where(Notification.hazard_id == hz.id)))
    assert {n.user_id for n in notes} >= {users(empty_db)[Role.SUPERVISOR][0].id, area(empty_db).owner_id}
    assert all("Sec. 5(b)" in n.message and f"consequence {consequence}" in n.message for n in notes)
    assert "Sec. 5(b)" in next(e.note for e in hz.events if e.kind == "alerted")


def test_consequence_3_in_a_moderate_band_does_not_alert(empty_db):
    report(empty_db, code="no_gloves", consequence=3)
    assert empty_db.scalars(select(Notification)).all() == []


def test_high_band_alert_says_why(empty_db):
    report(empty_db, code="no_gloves", consequence=3)
    report(empty_db, code="no_gloves", consequence=3)
    hz = report(empty_db, code="no_gloves", consequence=3)  # 3 x 3 = 9 High
    msg = empty_db.scalars(select(Notification).where(Notification.hazard_id == hz.id)).first().message
    assert "Alerted because: High risk" in msg


# ---------------------------------------------------------------- manager dashboard


def test_manager_sees_closure_share_by_control_type_with_its_denominator(empty_db, client):
    sup = users(empty_db)[Role.SUPERVISOR][0]
    now = utcnow()
    for code in ("engineering", "ppe", "ppe"):
        hz = report(empty_db)
        services.close(empty_db, hz, _owner(empty_db, hz), "Done", control_type=code, residual_consequence=1)
        services.verify(empty_db, hz, sup, "ok")
    legacy = report(empty_db)
    services.close(empty_db, legacy, _owner(empty_db, legacy), "Done", **CLOSE)
    services.verify(empty_db, legacy, sup, "ok")
    legacy.control_type = None  # as a closure recorded before v1.4.0
    empty_db.flush()
    perf = services.closure_performance(empty_db, now + timedelta(minutes=1))
    shares = {r["code"]: r["n"] for r in perf["by_control_type"]}
    assert perf["verified_closures"] == 4 == sum(shares.values())
    assert shares == {"elimination": 0, "substitution": 0, "engineering": 1, "procedural": 0, "ppe": 2, None: 1}


def test_manager_home_panel_states_the_denominator(client):
    login(client, MANAGER)
    page = client.get("/").text
    panel = page.split('id="control-types"')[1].split("</div>")[0]
    assert "Share of closures by control type" in panel and "Denominator:" in panel and "not recorded" in panel


# ---------------------------------------------------------------- /matrix page


def test_matrix_page_cites_the_guideline_and_separates_project_choices(client):
    login(client, REPORTER)
    page = client.get("/matrix").text
    official, project = page.split("Defined by this project")
    assert "Process of Risk Management" in official and "version 4.0" in official and "Table 3" in official
    assert "Sec. 5.3.4(c)" in official and "15 - 25" in official and "Extreme Risk" in official
    assert "5 Moderate, 9 and 10 High, 16 Extreme" in official
    assert "sets no time frames" in project and "365 days" in project and "Sec. 5(b)" in project
    assert "Medium" not in page


# ---------------------------------------------------------------- migration 0008


def _old_db(path, extra_sql: str = "") -> str:
    con = sqlite3.connect(path)
    con.executescript(OLD_DDL + OLD_ROWS + extra_sql)
    con.commit()
    con.close()
    return f"sqlite:///{path}"


def _rows(url, sql):
    eng = sa.create_engine(url)
    with eng.connect() as c:
        out = [tuple(r) for r in c.execute(sa.text(sql))]
    eng.dispose()
    return out


def test_migration_rescores_from_history_at_report_time_and_audits_old_to_new(tmp_path):
    # Three earlier no_hard_hat reports in DIG: two within 365 days of hazard 1's report time, one older.
    extra = """
    INSERT INTO hazards (id,area_id,reporter_id,status,created_at,description,ai_suggestions,category_code,
      consequence,likelihood,risk_score,risk_level,assignee_id,closed_on_spot) VALUES
      (3,1,1,'OPEN','2026-03-01 08:00:00','','[]','no_hard_hat',2,1,2,'Low',2,0),
      (4,1,1,'OPEN','2026-06-01 08:00:00','','[]','no_hard_hat',2,1,2,'Low',2,0),
      (5,1,1,'OPEN','2025-06-01 08:00:00','','[]','no_hard_hat',2,1,2,'Low',2,0),
      (6,1,1,'DRAFT','2026-10-01 08:00:00','','[]',NULL,NULL,NULL,NULL,NULL,NULL,0);
    """
    url = _old_db(tmp_path / "old.db", extra)
    dbmod.migrate_to_head(url)
    got = {r[0]: r[1:] for r in _rows(url, "SELECT id, likelihood, risk_score, risk_level, due_at FROM hazards")}
    assert got[1][:3] == (3, 9, "High")  # C3, 2 similar in 365 days -> L3 -> 9 High (was 6 Medium)
    assert got[1][3].startswith("2026-11-08")  # report time (no confirmed_at stored) + 7 days for High
    assert got[2][:3] == (1, 2, "Low")  # different category -> no history
    assert got[6] == (None, None, None, None)  # drafts are not scored
    notes = dict(_rows(url, "SELECT hazard_id, note FROM hazard_events WHERE kind = 'risk_rescored'"))
    assert set(notes) == {1, 2, 3, 4, 5}
    assert "risk re-scored to ADOSH-SF v4.0 matrix" in notes[1]
    assert "Likelihood 2 -> 3" in notes[1] and "score 6 -> 9" in notes[1] and "level Medium -> High" in notes[1]


def test_migration_never_invents_legacy_closure_values(tmp_path):
    url = _old_db(tmp_path / "old.db")
    dbmod.migrate_to_head(url)
    rows = _rows(url, "SELECT control_type, residual_consequence, residual_score, residual_level FROM hazards")
    assert rows and all(r == (None, None, None, None) for r in rows)
    assert _rows(url, "SELECT count(*) FROM notifications") == [(1,)]  # no alerts are sent by a migration


def test_migration_uses_the_frozen_v4_matrix_which_equals_the_current_config():
    for score in range(1, 26):
        level, days = MIGRATION.band_for(score)
        assert (level, days) == (risk.band_for(score).level, risk.band_for(score).target_days)
    for count in range(0, 20):
        assert MIGRATION.likelihood_for(count) == risk.likelihood_from_history(count)
    assert risk.lookback_days() == MIGRATION.LOOKBACK_DAYS
    assert set(MIGRATION.CONTROL_CODES) == set(risk.control_types())


def test_legacy_closure_shows_not_recorded_on_the_hazard_page(client, db):
    hz = db.scalars(select(Hazard).where(Hazard.status == Status.CLOSED)).first()
    hz.control_type = hz.residual_consequence = hz.residual_score = hz.residual_level = None
    db.commit()
    login(client, SUPERVISOR)
    page = client.get(f"/hazards/{hz.id}").text
    assert "not recorded" in page and "residual risk not recorded" in page


def test_migration_handles_datetimes_stored_as_text():
    assert MIGRATION._dt("2026-11-01 08:00:00.123456") == datetime(2026, 11, 1, 8, 0, 0, 123456)
    assert MIGRATION._dt(None) is None
