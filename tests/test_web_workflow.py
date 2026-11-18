"""Workflow v2 through the JSON API and the HTML pages (plan with owner/deadline, verify, reject, reopen)."""

from datetime import timedelta

from shms.models import utcnow
from tests.conftest import login
from tests.test_api import OWNER_DIG, REPORTER, SUPERVISOR, create, h


def _open_hazard(client) -> int:
    hz = create(client).json()
    r = client.post(
        f"/api/hazards/{hz['id']}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 3}
    )
    assert r.json()["status"] == "open"
    return hz["id"]


def _pending(client) -> int:
    hid = _open_hazard(client)
    r = client.post(f"/api/hazards/{hid}/close", headers=h(OWNER_DIG), json={"action": "Hard hat issued"})
    assert r.json()["status"] == "pending_verification"
    return hid


def test_api_plan_with_owner_and_deadline(client):
    hid = _open_hazard(client)
    due = (utcnow() + timedelta(days=2)).replace(microsecond=0)
    r = client.post(
        f"/api/hazards/{hid}/plan",
        headers=h(OWNER_DIG),
        json={"action": "Toolbox talk", "owner_id": OWNER_DIG, "due": due.isoformat()},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "planned" and body["action_owner_id"] == OWNER_DIG
    assert body["action_due_at"] == due.isoformat()


def test_api_reject_then_reopen_after_verify(client):
    hid = _pending(client)
    r = client.post(f"/api/hazards/{hid}/reject", headers=h(SUPERVISOR), json={"reason": "No photo of the fix"})
    assert r.status_code == 200 and r.json()["status"] == "open"
    client.post(f"/api/hazards/{hid}/close", headers=h(OWNER_DIG), json={"action": "Fixed, photo attached"})
    r = client.post(f"/api/hazards/{hid}/verify", headers=h(REPORTER), json={"note": "Confirmed"})
    assert r.json()["status"] == "closed"
    r = client.post(f"/api/hazards/{hid}/reopen", headers=h(SUPERVISOR), json={"reason": "Recurred"})
    assert r.status_code == 200 and r.json()["status"] == "open"
    moves = [(e["kind"], e["from_status"], e["to_status"]) for e in r.json()["events"] if e["to_status"]]
    assert moves[-1] == ("reopened", "closed", "open")


def test_api_reject_without_reason_is_422(client):
    hid = _pending(client)
    r = client.post(f"/api/hazards/{hid}/reject", headers=h(SUPERVISOR), json={"reason": " "})
    assert r.status_code == 422


def test_api_owner_cannot_verify_own_closure_403(client):
    hid = _pending(client)
    r = client.post(f"/api/hazards/{hid}/verify", headers=h(OWNER_DIG), json={"note": "ok"})
    assert r.status_code == 403


def test_html_pending_page_shows_closure_and_verify_form_for_supervisor(client):
    hid = _pending(client)
    login(client, SUPERVISOR)
    page = client.get(f"/hazards/{hid}").text
    assert "Hard hat issued" in page and "Awaiting verification" in page
    assert f'action="/hazards/{hid}/verify"' in page and f'action="/hazards/{hid}/reject"' in page


def test_html_verify_and_reopen_flow(client):
    hid = _pending(client)
    login(client, SUPERVISOR)
    r = client.post(f"/hazards/{hid}/verify", data={"note": "Checked on site"}, follow_redirects=True)
    assert r.status_code == 200 and "Verified" in r.text
    assert f'action="/hazards/{hid}/reopen"' in r.text
    r = client.post(f"/hazards/{hid}/reopen", data={"reason": "Same crew again"}, follow_redirects=True)
    assert r.status_code == 200 and "Same crew again" in r.text


def test_html_owner_sees_plan_form_with_deadline(client):
    hid = _open_hazard(client)
    login(client, OWNER_DIG)
    page = client.get(f"/hazards/{hid}").text
    assert 'name="due"' in page and 'name="owner_id"' in page


def test_html_plan_with_deadline_date(client):
    hid = _open_hazard(client)
    login(client, OWNER_DIG)
    day = (utcnow() + timedelta(days=5)).strftime("%Y-%m-%d")
    r = client.post(
        f"/hazards/{hid}/plan",
        data={"planned_action": "Hard-hat check at gate", "owner_id": OWNER_DIG, "due": day},
        follow_redirects=True,
    )
    assert r.status_code == 200 and "Hard-hat check at gate" in r.text and "planned" in r.text


def test_queue_keeps_planned_hazards_and_supervisor_sees_pending(client):
    planned = _open_hazard(client)
    client.post(f"/api/hazards/{planned}/plan", headers=h(OWNER_DIG), json={"action": "Toolbox talk"})
    pending = _pending(client)
    login(client, OWNER_DIG)
    page = client.get("/queue").text
    assert f"/hazards/{planned}" in page
    login(client, SUPERVISOR)
    page = client.get("/queue").text
    assert f"/hazards/{pending}" in page and "Awaiting verification" in page


def test_register_filter_offers_all_statuses(client):
    login(client, SUPERVISOR)
    page = client.get("/hazards?status=pending_verification").text
    for s in ("open", "planned", "pending_verification", "closed"):
        assert f">{s}<" in page or f'value="{s}"' in page


def test_register_ignores_unknown_status_filter(client):
    login(client, SUPERVISOR)
    assert client.get("/hazards?status=foo").status_code == 200
