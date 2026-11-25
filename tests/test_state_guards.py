"""Every workflow action checks its own expected from-state(s) explicitly – not only the shared transition table.

Security review (Phase 1b): confirm() did not check DRAFT, so a reporter could re-confirm an OPEN, PLANNED,
PENDING_VERIFICATION or CLOSED hazard and bypass close(), reject() and reopen() (risk downgrade, closing without
owner rights, leaving escalation, reopening without a reason). The audit found the same pattern in close() (DRAFT),
reject() (CLOSED) and reopen() (PENDING_VERIFICATION), because those target states are shared in the table.
"""

import pytest
from sqlalchemy import func, select

from shms import services
from shms.models import HazardEvent, Role, Status, User
from shms.services import Confirmation, WorkflowError
from tests.conftest import CLOSE, login
from tests.test_api import OWNER_DIG, REPORTER, SUPERVISOR, create, h
from tests.test_workflow import area, report, users

ALL = (Status.DRAFT, Status.OPEN, Status.PLANNED, Status.PENDING_VERIFICATION, Status.CLOSED)


def _in_state(db, state: Status):
    """A hazard in the requested state, built only through the normal workflow."""
    r = users(db)
    rep, sup = r[Role.REPORTER][0], r[Role.SUPERVISOR][0]
    if state == Status.DRAFT:
        return services.create_draft(db, rep, area(db), "x.jpg", None)
    hz = report(db, consequence=5)
    owner = db.get(User, hz.area.owner_id)
    if state in (Status.PLANNED,):
        services.plan_action(db, hz, owner, "Toolbox talk")
    if state in (Status.PENDING_VERIFICATION, Status.CLOSED):
        services.close(db, hz, owner, "Hard hat issued", **CLOSE)
    if state == Status.CLOSED:
        services.verify(db, hz, sup, "ok")
    assert hz.status == state
    return hz


def _snapshot(db, hz) -> tuple:
    db.flush()
    n_events = db.scalar(select(func.count()).select_from(HazardEvent).where(HazardEvent.hazard_id == hz.id))
    return (
        hz.status,
        hz.category_code,
        hz.consequence,
        hz.likelihood,
        hz.risk_score,
        hz.risk_level,
        hz.due_at,
        hz.closed_at,
        hz.closed_by_id,
        hz.closure_action,
        hz.closed_on_spot,
        hz.verified_at,
        hz.verified_by_id,
        hz.escalation_level,
        n_events,
    )


# ---------------------------------------------------------------- confirm: only a draft


@pytest.mark.parametrize("state", [s for s in ALL if s != Status.DRAFT])
@pytest.mark.parametrize("role", [Role.REPORTER, Role.SUPERVISOR])
@pytest.mark.parametrize("fixed", [False, True])
def test_reconfirming_a_confirmed_hazard_is_refused_and_changes_nothing(empty_db, state, role, fixed):
    hz = _in_state(empty_db, state)
    actor = users(empty_db)[role][0]
    before = _snapshot(empty_db, hz)
    c = Confirmation("no_gloves", 1, "downgrade", fixed_on_spot=fixed, closure_action="done" if fixed else "")
    with pytest.raises(WorkflowError, match="Only a draft"):
        services.confirm(empty_db, hz, actor, c)
    assert _snapshot(empty_db, hz) == before


def _confirmed_via_api(client) -> int:
    hid = create(client).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 5}
    )
    return hid


def _api_state(client, hid):
    j = client.get(f"/api/hazards/{hid}", headers=h(SUPERVISOR)).json()
    keys = ("status", "category_code", "consequence", "risk_score", "risk_level", "due_at", "closed_at")
    return tuple(j[k] for k in keys), len(j["events"])


@pytest.mark.parametrize("uid", [REPORTER, SUPERVISOR])
def test_api_reconfirm_returns_422_and_changes_nothing(client, uid):
    hid = _confirmed_via_api(client)
    before = _api_state(client, hid)
    body = {"category_code": "no_gloves", "consequence": 1, "fixed_on_spot": True, "closure_action": "done"}
    r = client.post(f"/api/hazards/{hid}/confirm", headers=h(uid), json=body)
    assert r.status_code == 422 and "Only a draft" in r.json()["detail"]
    assert _api_state(client, hid) == before


@pytest.mark.parametrize("uid", [REPORTER, SUPERVISOR])
def test_page_reconfirm_redirects_with_message_and_changes_nothing(client, uid):
    hid = _confirmed_via_api(client)
    before = _api_state(client, hid)
    login(client, uid)
    r = client.post(
        f"/hazards/{hid}/confirm",
        data={"category_code": "no_gloves", "consequence": 1, "fixed_on_spot": "true", "closure_action": "done"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"].startswith(f"/hazards/{hid}?error=")
    assert "already been confirmed" in client.get(r.headers["location"]).text
    assert _api_state(client, hid) == before


# ---------------------------------------------------------------- every other action from a wrong state

ACTIONS = {
    "plan": ({Status.OPEN}, lambda db, hz, sup: services.plan_action(db, hz, sup, "Toolbox talk")),
    "close": ({Status.OPEN, Status.PLANNED}, lambda db, hz, sup: services.close(db, hz, sup, "Done", **CLOSE)),
    "verify": ({Status.PENDING_VERIFICATION}, lambda db, hz, sup: services.verify(db, hz, sup, "ok")),
    "reject": ({Status.PENDING_VERIFICATION}, lambda db, hz, sup: services.reject(db, hz, sup, "not done")),
    "reopen": ({Status.CLOSED}, lambda db, hz, sup: services.reopen(db, hz, sup, "recurred")),
}
WRONG = [(name, s) for name, (ok, _) in ACTIONS.items() for s in ALL if s not in ok]


@pytest.mark.parametrize(("action", "state"), WRONG, ids=[f"{a}-from-{s.value}" for a, s in WRONG])
def test_action_from_a_wrong_state_is_refused_and_changes_nothing(empty_db, action, state):
    hz = _in_state(empty_db, state)
    sup = users(empty_db)[Role.SUPERVISOR][0]  # has the rights, so only the state check can refuse
    before = _snapshot(empty_db, hz)
    with pytest.raises(WorkflowError):
        ACTIONS[action][1](empty_db, hz, sup)
    assert _snapshot(empty_db, hz) == before


def test_escalation_only_touches_hazards_awaiting_action(empty_db):
    from datetime import timedelta

    from shms import escalate

    hazards = {s: _in_state(empty_db, s) for s in ALL if s != Status.DRAFT}
    latest = max(hz.due_at for hz in hazards.values())
    changed = {hid for hid, _ in escalate.run(empty_db, now=latest + timedelta(days=30))}
    assert changed == {hazards[Status.OPEN].id, hazards[Status.PLANNED].id}
    assert OWNER_DIG
