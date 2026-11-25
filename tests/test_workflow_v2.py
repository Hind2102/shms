"""Safety workflow v2: plan (owner + deadline) -> close -> verify / reject -> closed -> reopen.

Every status change is a rule in services.ALLOWED_TRANSITIONS, has a server-side permission check, and leaves an
audit event with from/to status, actor, time and note. The original AI suggestion is never changed.
"""

from datetime import timedelta

import pytest

from shms import services
from shms.models import Role, Status, User, utcnow
from shms.services import PermissionDenied, WorkflowError
from tests.conftest import CLOSE
from tests.test_workflow import area, report, users


def _people(db):
    r = users(db)
    h = report(db)
    owner = db.get(User, h.area.owner_id)
    other_owner = next(u for u in r[Role.AREA_OWNER] if u.id != owner.id)
    return h, owner, other_owner, r[Role.REPORTER][0], r[Role.SUPERVISOR][0]


def _manager(db):
    m = User(name="Manager", role=Role.MANAGER)
    db.add(m)
    db.flush()
    return m


def _closed_by_owner(db):
    h, owner, other, rep, sup = _people(db)
    services.close(db, h, owner, "Hard hat issued", **CLOSE)
    return h, owner, other, rep, sup


# ---------------------------------------------------------------- plan


def test_plan_moves_open_to_planned_with_owner_and_deadline(empty_db):
    h, owner, *_ = _people(empty_db)
    due = utcnow() + timedelta(days=3)
    services.plan_action(empty_db, h, owner, "Toolbox talk", owner_id=owner.id, due=due)
    assert h.status == Status.PLANNED
    assert (h.action_owner_id, h.action_due_at, h.planned_action) == (owner.id, due, "Toolbox talk")


def test_plan_defaults_to_area_owner_and_risk_deadline(empty_db):
    h, owner, *_ = _people(empty_db)
    services.plan_action(empty_db, h, owner, "Toolbox talk")
    assert (h.action_owner_id, h.action_due_at) == (owner.id, h.due_at)


def test_plan_rejects_deadline_in_the_past(empty_db):
    h, owner, *_ = _people(empty_db)
    with pytest.raises(WorkflowError):
        services.plan_action(empty_db, h, owner, "x", due=utcnow() - timedelta(days=1))


# ---------------------------------------------------------------- close -> pending verification


def test_close_goes_to_pending_verification_not_closed(empty_db):
    h, *_ = _closed_by_owner(empty_db)
    assert h.status == Status.PENDING_VERIFICATION
    assert h.closure_action == "Hard hat issued" and h.verified_at is None


def test_close_from_planned_is_allowed(empty_db):
    h, owner, *_ = _people(empty_db)
    services.plan_action(empty_db, h, owner, "Toolbox talk")
    services.close(empty_db, h, owner, "Done", **CLOSE)
    assert h.status == Status.PENDING_VERIFICATION


def test_fixed_on_spot_needs_verification_too(empty_db):
    h = report(empty_db, fixed_on_spot=True, closure_action="Issued hard hat", **CLOSE)
    assert h.status == Status.PENDING_VERIFICATION and h.closed_on_spot


# ---------------------------------------------------------------- verify / reject


def test_supervisor_verifies_closure(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    services.verify(empty_db, h, sup, "Checked on site")
    assert h.status == Status.CLOSED and h.verified_by_id == sup.id and h.verified_at is not None


def test_reporter_can_verify_closure(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    services.verify(empty_db, h, rep, "Saw the hard hat")
    assert h.status == Status.CLOSED


def test_closer_cannot_verify_own_closure(empty_db):
    h, owner, other, rep, sup = _people(empty_db)
    services.close(empty_db, h, sup, "Supervisor fixed it", **CLOSE)
    with pytest.raises(PermissionDenied):
        services.verify(empty_db, h, sup, "self-check")


def test_area_owner_and_manager_cannot_verify(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    for who in (owner, other, _manager(empty_db)):
        with pytest.raises(PermissionDenied):
            services.verify(empty_db, h, who, "ok")


def test_reject_returns_to_open_with_reason(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    services.reject(empty_db, h, sup, "No hard hat seen on the closing photo")
    assert h.status == Status.OPEN
    assert h.events[-1].note == "No hard hat seen on the closing photo"


def test_reject_requires_reason(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    with pytest.raises(WorkflowError):
        services.reject(empty_db, h, sup, "  ")


# ---------------------------------------------------------------- reopen


def test_reopen_closed_hazard_requires_reason(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    services.verify(empty_db, h, sup, "ok")
    with pytest.raises(WorkflowError):
        services.reopen(empty_db, h, rep, "")
    services.reopen(empty_db, h, rep, "Same crew without hard hats again")
    assert h.status == Status.OPEN and h.verified_at is None


def test_only_reporter_or_supervisor_can_reopen(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    services.verify(empty_db, h, sup, "ok")
    for who in (owner, other, _manager(empty_db)):
        with pytest.raises(PermissionDenied):
            services.reopen(empty_db, h, who, "why")


# ---------------------------------------------------------------- illegal moves and permissions


@pytest.mark.parametrize(
    "action",
    [
        lambda db, h, sup: services.verify(db, h, sup, "x"),  # OPEN -> CLOSED skips verification
        lambda db, h, sup: services.reject(db, h, sup, "x"),  # nothing to reject
        lambda db, h, sup: services.reopen(db, h, sup, "x"),  # already open
    ],
)
def test_illegal_transitions_from_open(empty_db, action):
    h, owner, other, rep, sup = _people(empty_db)
    with pytest.raises(WorkflowError):
        action(empty_db, h, sup)


def test_cannot_plan_or_close_pending_or_closed(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    with pytest.raises(WorkflowError):
        services.plan_action(empty_db, h, owner, "x")
    with pytest.raises(WorkflowError):
        services.close(empty_db, h, owner, "again", **CLOSE)
    services.verify(empty_db, h, sup, "ok")
    with pytest.raises(WorkflowError):
        services.close(empty_db, h, owner, "again", **CLOSE)


def test_manager_is_read_only(empty_db):
    h, *_ = _people(empty_db)
    m = _manager(empty_db)
    with pytest.raises(PermissionDenied):
        services.plan_action(empty_db, h, m, "x")
    with pytest.raises(PermissionDenied):
        services.close(empty_db, h, m, "x", **CLOSE)


def test_every_transition_rule_is_declared():
    t = services.ALLOWED_TRANSITIONS
    assert t[Status.DRAFT] == {Status.OPEN, Status.PENDING_VERIFICATION}
    assert t[Status.OPEN] == {Status.PLANNED, Status.PENDING_VERIFICATION}
    assert t[Status.PLANNED] == {Status.PENDING_VERIFICATION}
    assert t[Status.PENDING_VERIFICATION] == {Status.CLOSED, Status.OPEN}
    assert t[Status.CLOSED] == {Status.OPEN}
    assert {Status.OPEN, Status.PLANNED, Status.PENDING_VERIFICATION} == services.ACTIVE


# ---------------------------------------------------------------- audit trail and AI preservation


def test_events_record_from_and_to_for_every_transition(empty_db):
    h, owner, other, rep, sup = _people(empty_db)
    services.plan_action(empty_db, h, owner, "Toolbox talk")
    services.close(empty_db, h, owner, "Done", **CLOSE)
    services.reject(empty_db, h, sup, "Not done")
    services.close(empty_db, h, owner, "Done properly", **CLOSE)
    services.verify(empty_db, h, rep, "ok")
    services.reopen(empty_db, h, sup, "Recurred")
    moves = [(e.kind, e.from_status, e.to_status, e.actor_id) for e in h.events if e.to_status]
    assert moves == [
        ("assigned", "draft", "open", rep.id),
        ("planned", "open", "planned", owner.id),
        ("closed", "planned", "pending_verification", owner.id),
        ("rejected", "pending_verification", "open", sup.id),
        ("closed", "open", "pending_verification", owner.id),
        ("verified", "pending_verification", "closed", rep.id),
        ("reopened", "closed", "open", sup.id),
    ]


def test_ai_suggestion_is_preserved_through_the_lifecycle(empty_db):
    h, owner, other, rep, sup = _people(empty_db)
    before = (h.ai_model, h.ai_suggestions, h.ai_top_code, h.ai_latency_ms, h.ai_error)
    services.close(empty_db, h, owner, "Done", **CLOSE)
    services.verify(empty_db, h, sup, "ok")
    services.reopen(empty_db, h, rep, "again")
    assert (h.ai_model, h.ai_suggestions, h.ai_top_code, h.ai_latency_ms, h.ai_error) == before


def test_dashboard_counts_pending_as_active_and_only_verified_as_closed(empty_db):
    h, owner, other, rep, sup = _closed_by_owner(empty_db)
    k = services.dashboard(empty_db)["kpis"]
    assert k["open"] == 1
    services.verify(empty_db, h, sup, "ok")
    assert services.dashboard(empty_db)["kpis"]["open"] == 0
    assert area(empty_db) is not None


def test_seeded_history_has_verified_closures_and_few_pending(db):
    from sqlalchemy import select

    from shms.models import Hazard

    hz = list(db.scalars(select(Hazard)))
    closed = [h for h in hz if h.status == Status.CLOSED]
    pending = [h for h in hz if h.status == Status.PENDING_VERIFICATION]
    assert closed and all(h.verified_by_id and h.verified_by_id != h.closed_by_id for h in closed)
    assert len(pending) < len(closed) / 10
