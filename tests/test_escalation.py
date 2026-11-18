"""Deadlines from the risk band, overdue escalation (supervisor, then manager) and the test mail outbox."""

from datetime import timedelta

from sqlalchemy import select

from shms import escalate, services
from shms.models import Notification, Role, Status, User
from shms.settings import get_settings
from tests.conftest import login
from tests.test_workflow import report, users


def _manager(db):
    m = User(name="Manager", role=Role.MANAGER, email="manager@shms.example")
    db.add(m)
    db.flush()
    return m


def _notified(db, h):
    return {n.user_id for n in db.scalars(select(Notification).where(Notification.hazard_id == h.id))}


def test_overdue_hazard_escalates_to_supervisors_and_writes_outbox_mail(empty_db):
    h = report(empty_db, consequence=2)  # low risk: no alert at creation
    sup = users(empty_db)[Role.SUPERVISOR][0]
    sup.email = "sara@shms.example"
    done = escalate.run(empty_db, now=h.due_at + timedelta(hours=1))
    assert done == [(h.id, 1)] and h.escalation_level == 1
    assert sup.id in _notified(empty_db, h)
    assert "escalated" in [e.kind for e in h.events]
    mails = list(get_settings().mail_outbox.glob("*.eml"))
    assert mails and "sara@shms.example" in mails[0].read_text() and f"#{h.id}" in mails[0].read_text()


def test_second_level_after_seven_days_notifies_managers(empty_db):
    h = report(empty_db, consequence=2)
    m = _manager(empty_db)
    escalate.run(empty_db, now=h.due_at + timedelta(days=1))
    assert m.id not in _notified(empty_db, h)
    assert escalate.run(empty_db, now=h.due_at + timedelta(days=7, hours=1)) == [(h.id, 2)]
    assert m.id in _notified(empty_db, h) and h.escalation_level == 2


def test_escalation_is_not_repeated(empty_db):
    h = report(empty_db, consequence=2)
    later = h.due_at + timedelta(hours=1)
    escalate.run(empty_db, now=later)
    n = len(_notified(empty_db, h))
    assert escalate.run(empty_db, now=later + timedelta(hours=2)) == []
    assert len(_notified(empty_db, h)) == n


def test_not_yet_due_and_awaiting_verification_never_escalate(empty_db):
    h = report(empty_db, consequence=2)
    assert escalate.run(empty_db, now=h.due_at - timedelta(hours=1)) == []
    services.close(empty_db, h, empty_db.get(User, h.area.owner_id), "Done")
    assert h.status == Status.PENDING_VERIFICATION
    assert escalate.run(empty_db, now=h.due_at + timedelta(days=30)) == []


def test_reopen_sets_a_new_deadline_and_resets_escalation(empty_db):
    h = report(empty_db, consequence=2)
    escalate.run(empty_db, now=h.due_at + timedelta(days=1))
    sup = users(empty_db)[Role.SUPERVISOR][0]
    services.close(empty_db, h, empty_db.get(User, h.area.owner_id), "Done")
    services.verify(empty_db, h, sup, "ok")
    old_due = h.due_at
    services.reopen(empty_db, h, sup, "Recurred")
    assert h.escalation_level == 0 and h.due_at > old_due


def test_page_load_runs_escalation_at_most_once_per_minute(empty_db, monkeypatch):
    calls = []
    monkeypatch.setattr(escalate, "run", lambda db, now=None: calls.append(now) or [])
    escalate.reset_throttle()
    t0 = report(empty_db).created_at
    escalate.maybe_run(empty_db, now=t0)
    escalate.maybe_run(empty_db, now=t0 + timedelta(seconds=30))
    escalate.maybe_run(empty_db, now=t0 + timedelta(seconds=61))
    assert len(calls) == 2


def test_high_risk_alert_also_goes_to_the_outbox(empty_db):
    users(empty_db)[Role.SUPERVISOR][0].email = "sara@shms.example"
    for _ in range(4):
        h = report(empty_db, code="no_eye_protection", consequence=5)
    assert h.risk_level == "High"
    assert any("High risk" in p.read_text() for p in get_settings().mail_outbox.glob("*.eml"))


def test_opening_a_page_escalates_overdue_hazards(client, db):
    from shms.models import Hazard
    from tests.test_web_workflow import _open_hazard

    hid = _open_hazard(client)
    h = db.get(Hazard, hid)
    h.due_at = h.created_at - timedelta(days=1)
    db.commit()
    escalate.reset_throttle()
    login(client, 8)
    assert client.get("/").status_code == 200
    db.expire_all()
    assert db.get(Hazard, hid).escalation_level == 1


def test_demo_users_have_non_deliverable_example_addresses(db):
    emails = [u.email for u in db.scalars(select(User))]
    assert emails and all(e and e.endswith("@shms.example") for e in emails)


def test_unwritable_outbox_never_blocks_a_report(empty_db, tmp_path):
    from shms.settings import override_settings

    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the outbox folder should be")
    override_settings(mail_outbox=blocker / "outbox")
    users(empty_db)[Role.SUPERVISOR][0].email = "sara@shms.example"
    for _ in range(4):
        h = report(empty_db, code="no_eye_protection", consequence=5)
    assert h.risk_level == "High" and h.status == Status.OPEN
    assert users(empty_db)[Role.SUPERVISOR][0].id in _notified(empty_db, h)  # in-app notification still created
