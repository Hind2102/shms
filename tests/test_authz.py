"""Server-side authorisation on routes and objects (filtering in the UI is not access control).

Policy: every page needs a signed-in user. Confirmed hazards are visible to everyone signed in (site hazard board,
user story US7). Unconfirmed drafts – and their photos – are visible only to their reporter and supervisors.
Actions are limited by role in services.py (tested in test_workflow_v2.py); here they are checked through the web.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import jpeg_bytes, login
from tests.test_api import OWNER_DIG, REPORTER, SUPERVISOR, create, h

OTHER_REPORTER, MANAGER = 2, 9


def _draft_by(client, uid=REPORTER):
    r = create(client, uid=uid)
    assert r.status_code == 201
    return r.json()


def _confirmed(client):
    hz = _draft_by(client)
    client.post(
        f"/api/hazards/{hz['id']}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 3}
    )
    return hz


def test_every_page_requires_sign_in(app):
    anon = TestClient(app)
    for path in ("/", "/report", "/hazards", "/queue", "/notifications", "/monitoring", "/matrix", "/areas/DIG"):
        assert anon.get(path, follow_redirects=False).headers.get("location") == "/login", path


def test_photos_are_not_public(client, app):
    hz = _draft_by(client)
    photo = hz["photo_path"]
    anon = TestClient(app)
    assert anon.get(f"/uploads/{photo}").status_code == 404  # the old public folder is gone
    assert anon.get(f"/photos/{photo}", follow_redirects=False).status_code in (303, 401)


def test_other_reporter_cannot_open_a_draft_or_its_photo(client):
    hz = _draft_by(client)
    login(client, OTHER_REPORTER)
    assert client.get(f"/hazards/{hz['id']}/confirm").status_code == 404
    assert client.get(f"/hazards/{hz['id']}", follow_redirects=False).status_code == 404
    assert client.get(f"/photos/{hz['photo_path']}").status_code == 404
    login(client, REPORTER)
    assert client.get(f"/photos/{hz['photo_path']}").status_code == 200


def test_api_hides_other_peoples_drafts(client):
    hz = _draft_by(client)
    assert client.get(f"/api/hazards/{hz['id']}", headers=h(OTHER_REPORTER)).status_code == 404
    assert client.get(f"/api/hazards/{hz['id']}", headers=h(SUPERVISOR)).status_code == 200


def test_other_reporter_cannot_confirm_someone_elses_draft(client):
    hz = _draft_by(client)
    r = client.post(
        f"/api/hazards/{hz['id']}/confirm",
        headers=h(OTHER_REPORTER),
        json={"category_code": "no_hard_hat", "consequence": 3},
    )
    assert r.status_code in (403, 404)


def test_confirmed_hazards_and_their_photos_are_visible_to_everyone_signed_in(client):
    hz = _confirmed(client)
    login(client, OTHER_REPORTER)
    assert client.get(f"/hazards/{hz['id']}").status_code == 200
    assert client.get(f"/photos/{hz['photo_path']}").status_code == 200


@pytest.mark.parametrize("uid", [MANAGER, OTHER_REPORTER])
def test_read_only_roles_cannot_plan_or_close_through_the_web(client, uid):
    hz = _confirmed(client)
    login(client, uid)
    client.post(f"/hazards/{hz['id']}/plan", data={"planned_action": "x"})
    client.post(f"/hazards/{hz['id']}/close", data={"action": "x"})
    assert client.get(f"/api/hazards/{hz['id']}", headers=h(SUPERVISOR)).json()["status"] == "open"


def test_photo_names_cannot_escape_the_upload_folder(client):
    login(client, SUPERVISOR)
    for bad in ("..%2Fshms.db", "%2e%2e%2f%2e%2e%2fetc%2fpasswd", "x/../../shms.db"):
        assert client.get(f"/photos/{bad}").status_code == 404, bad


def test_owner_can_still_work_on_their_hazard(client):
    hz = _confirmed(client)
    r = client.post(f"/api/hazards/{hz['id']}/close", headers=h(OWNER_DIG), json={"action": "Done"})
    assert r.status_code == 200 and jpeg_bytes()
