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
    assert report(empty_db, code="caustic_spill", ai_code="no_hard_hat").ai_accepted is False
    assert report(empty_db, code="caustic_spill", ai_code=None).ai_accepted is None


def test_unknown_category_rejected(empty_db):
    with pytest.raises(ValueError):
        report(empty_db, code="alien_invasion")


def test_likelihood_grows_with_similar_history(empty_db):
    now = utcnow()
    first = report(empty_db, code="caustic_spill", at=now - timedelta(days=10))
    assert first.likelihood == 1
    for d in range(9, 4, -1):  # five more in the window
        report(empty_db, code="caustic_spill", at=now - timedelta(days=d))
    latest = report(empty_db, code="caustic_spill", at=now)
    assert latest.likelihood == 4  # 6 similar hazards -> Likely
    other = report(empty_db, code="slip_trip", at=now)
    assert other.likelihood == 1  # different category -> not similar


def test_history_outside_lookback_is_ignored(empty_db):
    now = utcnow()
    for _ in range(5):
        report(empty_db, code="steam_leak", at=now - timedelta(days=200))
    assert report(empty_db, code="steam_leak", at=now).likelihood == 1


def test_high_risk_alerts_supervisor_and_owner(empty_db):
    h = report(empty_db, code="fall_from_height", consequence=5)  # 5 x 1 = 5 Medium -> no alert
    assert empty_db.scalars(select(Notification)).all() == []
    for _ in range(3):
        report(empty_db, code="fall_from_height", consequence=5)
    h = report(empty_db, code="fall_from_height", consequence=5)  # 4 similar -> L3 -> 15 High
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
        services.confirm(empty_db, h, roles[Role.AREA_OWNER][0], Confirmation("slip_trip", 2))


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
        report(empty_db, code="caustic_spill")
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
            results.append(services.dashboard(s, now=utcnow().replace(year=2026, month=11, day=15, hour=12))["by_level"])
    assert results[0] == results[1]
