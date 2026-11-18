from datetime import timedelta

import pytest
from sqlalchemy import select

from shms import services
from shms.detection.base import DetectorResult, Suggestion
from shms.models import Area, Notification, Role, Status, User, utcnow
from shms.services import Confirmation, PermissionDenied, WorkflowError


def users(db):
    by_role = {}
    for u in db.scalars(select(User)):
        by_role.setdefault(u.role, []).append(u)
    return by_role


def area(db, code="DIG"):
    return db.scalar(select(Area).where(Area.code == code))


def ai(code, conf=0.8):
    return DetectorResult("mock", [Suggestion(code, conf)], 12.0)


def report(db, code="no_hard_hat", consequence=3, ai_code="no_hard_hat", at=None, **kw):
    u = users(db)[Role.REPORTER][0]
    h = services.create_draft(db, u, area(db), "x.jpg", ai(ai_code) if ai_code else None, at=at)
    return services.confirm(db, h, u, Confirmation(code, consequence, **kw), at=at)


def test_confirmed_report_is_routed_to_area_owner(empty_db):
    h = report(empty_db)
    assert h.status == Status.OPEN
    assert h.assignee_id == area(empty_db).owner_id
    assert [e.kind for e in h.events] == ["reported", "confirmed", "assigned"]


def test_fixed_on_spot_closes_immediately_and_records_how(empty_db):
    h = report(empty_db, fixed_on_spot=True, closure_action="Issued hard hat")
    assert h.status == Status.CLOSED and h.closed_on_spot
    assert h.closure_action == "Issued hard hat" and h.closed_at is not None


def test_fixed_on_spot_requires_action(empty_db):
    with pytest.raises(WorkflowError):
        report(empty_db, fixed_on_spot=True, closure_action="  ")


def test_ai_acceptance_recorded(empty_db):
    assert report(empty_db, code="no_hard_hat", ai_code="no_hard_hat").ai_accepted is True
    assert report(empty_db, code="no_gloves", ai_code="no_hard_hat").ai_accepted is False
    assert report(empty_db, code="no_gloves", ai_code=None).ai_accepted is None


def test_unknown_category_rejected(empty_db):
    with pytest.raises(ValueError):
        report(empty_db, code="alien_invasion")


def test_likelihood_grows_with_similar_history(empty_db):
    now = utcnow()
    first = report(empty_db, code="no_eye_protection", at=now - timedelta(days=10))
    assert first.likelihood == 1
    for d in range(9, 4, -1):  # five more in the window
        report(empty_db, code="no_eye_protection", at=now - timedelta(days=d))
    latest = report(empty_db, code="no_eye_protection", at=now)
    assert latest.likelihood == 4  # 6 similar hazards -> Likely
    other = report(empty_db, code="no_gloves", at=now)
    assert other.likelihood == 1  # different category -> not similar


def test_history_outside_lookback_is_ignored(empty_db):
    now = utcnow()
    for _ in range(5):
        report(empty_db, code="no_hi_vis_vest", at=now - timedelta(days=200))
    assert report(empty_db, code="no_hi_vis_vest", at=now).likelihood == 1


def test_high_risk_alerts_supervisor_and_owner(empty_db):
    h = report(empty_db, code="no_eye_protection", consequence=5)  # 5 x 1 = 5 Medium -> no alert
    assert empty_db.scalars(select(Notification)).all() == []
    for _ in range(3):
        report(empty_db, code="no_eye_protection", consequence=5)
    h = report(empty_db, code="no_eye_protection", consequence=5)  # 4 similar -> L3 -> 15 High
    assert h.risk_level == "High"
    notified = {n.user_id for n in empty_db.scalars(select(Notification).where(Notification.hazard_id == h.id))}
    roles = users(empty_db)
    assert roles[Role.SUPERVISOR][0].id in notified and area(empty_db).owner_id in notified
    assert "alerted" in [e.kind for e in h.events]


def test_owner_closes_with_documented_action(empty_db):
    h = report(empty_db)
    owner = empty_db.get(User, h.area.owner_id)
    services.plan_action(empty_db, h, owner, "Toolbox talk on Monday")
    services.close(empty_db, h, owner, "Hard hat issued; crew briefed")
    assert h.status == Status.CLOSED and h.closed_by_id == owner.id
    assert [e.kind for e in h.events][-2:] == ["planned", "closed"]


def test_close_requires_action_text(empty_db):
    h = report(empty_db)
    with pytest.raises(WorkflowError):
        services.close(empty_db, h, empty_db.get(User, h.area.owner_id), "")


def test_only_owner_or_supervisor_can_close(empty_db):
    h = report(empty_db)
    roles = users(empty_db)
    with pytest.raises(PermissionDenied):
        services.close(empty_db, h, roles[Role.REPORTER][0], "done")
    other_owner = next(u for u in roles[Role.AREA_OWNER] if u.id != h.area.owner_id)
    with pytest.raises(PermissionDenied):
        services.close(empty_db, h, other_owner, "done")
    services.close(empty_db, h, roles[Role.SUPERVISOR][0], "done by supervisor")
    assert h.status == Status.CLOSED


def test_closed_hazard_cannot_be_closed_again(empty_db):
    h = report(empty_db, fixed_on_spot=True, closure_action="fixed")
    with pytest.raises(WorkflowError):
        services.close(empty_db, h, users(empty_db)[Role.SUPERVISOR][0], "again")


def test_only_reporter_confirms(empty_db):
    roles = users(empty_db)
    h = services.create_draft(empty_db, roles[Role.REPORTER][0], area(empty_db), None, None)
    with pytest.raises(PermissionDenied):
        services.confirm(empty_db, h, roles[Role.AREA_OWNER][0], Confirmation("no_gloves", 2))


def test_transition_table_has_no_way_out_of_closed():
    assert services.ALLOWED_TRANSITIONS[Status.CLOSED] == set()


def test_dashboard_counts_new_report_immediately(empty_db):
    before = services.dashboard(empty_db)["kpis"]["open"]
    report(empty_db)
    d = services.dashboard(empty_db)
    assert d["kpis"]["open"] == before + 1
    dig = next(r for r in d["areas"] if r["area"].code == "DIG")
    assert dig["open"] == 1 and dig["heat"] > 0


def test_repeat_hotspots(empty_db):
    for _ in range(3):
        report(empty_db, code="no_eye_protection")
    hs = services.repeat_hotspots(empty_db)
    assert hs and hs[0]["count"] == 3 and hs[0]["area"].code == "DIG"


def test_seed_is_deterministic(settings):
    from shms import db as dbmod
    from shms.seed import seed

    results = []
    for _ in range(2):
        dbmod.init_engine("sqlite://")
        dbmod.create_all()
        with dbmod.new_session() as s:
            seed(s, now=utcnow().replace(year=2026, month=11, day=15, hour=12, minute=0, second=0, microsecond=0))
            results.append(
                services.dashboard(s, now=utcnow().replace(year=2026, month=11, day=15, hour=12))["by_level"]
            )
    assert results[0] == results[1]


def test_only_ppe_required_in_the_area_can_be_reported(empty_db):
    cal = area(empty_db, "CAL")
    cal.ai_checks = "no_hard_hat,no_eye_protection,no_gloves"  # no hi-vis vest required here
    u = users(empty_db)[Role.REPORTER][0]
    h = services.create_draft(empty_db, u, cal, "x.jpg", ai("no_hi_vis_vest"))
    with pytest.raises(WorkflowError, match="not a PPE requirement"):
        services.confirm(empty_db, h, u, Confirmation("no_hi_vis_vest", 3))


def test_ai_suggestion_filtered_by_area_requirements(empty_db):
    import json

    cal = area(empty_db, "CAL")
    cal.ai_checks = "no_hard_hat,no_eye_protection,no_gloves"
    u = users(empty_db)[Role.REPORTER][0]
    result = DetectorResult("mock", [Suggestion("no_hi_vis_vest", 0.95), Suggestion("no_gloves", 0.6)], 5.0)
    h = services.create_draft(empty_db, u, cal, "x.jpg", result)
    assert h.ai_top_code == "no_gloves"  # vest is more confident but not required in this area
    flags = {s["code"]: s["required"] for s in json.loads(h.ai_suggestions)}
    assert flags == {"no_hi_vis_vest": False, "no_gloves": True}


def test_taxonomy_contains_only_ai_detected_hazards():
    from shms import taxonomy

    assert all(c.ai for c in taxonomy.categories().values())
    assert set(taxonomy.categories()) == {"no_hard_hat", "no_eye_protection", "no_gloves", "no_hi_vis_vest"}


def test_database_rejects_invalid_values(empty_db):
    """Integrity rules are enforced by the database itself (DB lecture), not only by the app."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    h = report(empty_db)
    empty_db.commit()
    for sql in (
        f"UPDATE hazards SET consequence = 7 WHERE id = {h.id}",
        f"UPDATE hazards SET risk_score = 40 WHERE id = {h.id}",
        f"UPDATE hazards SET status = 'CLOSED', closure_action = NULL WHERE id = {h.id}",
        f"UPDATE hazards SET area_id = 999 WHERE id = {h.id}",
    ):
        with pytest.raises(IntegrityError):
            empty_db.execute(text(sql))
            empty_db.flush()
        empty_db.rollback()


def test_ai_monitoring_counts_acceptance_and_misses(empty_db):
    report(empty_db, code="no_hard_hat", ai_code="no_hard_hat")
    report(empty_db, code="no_gloves", ai_code="no_hard_hat")
    u = users(empty_db)[Role.REPORTER][0]
    h = services.create_draft(empty_db, u, area(empty_db), "x.jpg", DetectorResult("mock", [], 3.0))
    services.confirm(empty_db, h, u, Confirmation("no_gloves", 2))
    m = services.ai_monitoring(empty_db)
    assert m["reports"] == 3 and m["acceptance"] == 0.5 and m["missed"] == 1
    assert {"ai": "no_hard_hat", "reporter": "no_gloves", "n": 1} in m["corrections"]
    acc = next(c for c in m["checks"] if c["name"] == "Reporter acceptance")
    assert acc["ok"] is None  # fewer reports than min_reports_for_alert -> no verdict yet


def test_old_database_gives_clear_message(tmp_path):
    import sqlite3

    from shms import db as dbmod

    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE hazards (id INTEGER PRIMARY KEY)")  # an 'old' table without the new columns
    con.commit()
    con.close()
    dbmod.init_engine(f"sqlite:///{path}")
    with pytest.raises(dbmod.SchemaMismatch, match="alembic upgrade head"):
        dbmod.create_all()
