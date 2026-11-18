"""Sign-in with hashed passwords, signed sessions, CSRF on HTML forms, API tokens."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from shms import auth, tokens
from shms.models import ApiToken, User
from shms.seed import DEMO_PASSWORD
from shms.settings import override_settings


@pytest.fixture()
def raw(app):
    """A client that does NOT add CSRF tokens (like a forged cross-site request)."""
    return TestClient(app)


@pytest.fixture()
def strict(settings):
    """Normal mode: the X-User-Id demo header is not accepted."""
    return override_settings(demo_header_auth=False)


def _csrf(c: TestClient) -> str:
    c.get("/login")
    return c.cookies.get(auth.CSRF_COOKIE)


def _login(c: TestClient, username="sara", password=DEMO_PASSWORD):
    return c.post(
        "/login", data={"username": username, "password": password, "csrf_token": _csrf(c)}, follow_redirects=False
    )


# ---------------------------------------------------------------- passwords


def test_password_hash_is_salted_scrypt_and_verifies():
    a, b = auth.hash_password("correct horse"), auth.hash_password("correct horse")
    assert a != b and a.startswith("scrypt$")
    assert auth.check_password("correct horse", a) and not auth.check_password("wrong", a)
    assert not auth.check_password("x", None)


def test_demo_users_have_hashed_passwords_not_plaintext(db):
    for u in db.scalars(select(User)):
        assert u.username and u.password_hash.startswith("scrypt$") and DEMO_PASSWORD not in u.password_hash


# ---------------------------------------------------------------- sessions


def test_login_with_correct_password_sets_a_signed_session(raw):
    r = _login(raw)
    assert r.status_code == 303 and auth.SESSION_COOKIE in r.cookies
    assert "Sara" in raw.get("/").text


def test_wrong_password_and_unknown_user_get_the_same_generic_message(raw):
    a = _login(raw, password="nope")
    b = _login(raw, username="nobody")
    assert a.status_code == b.status_code == 401
    assert "Wrong username or password." in a.text and "Wrong username or password." in b.text
    assert auth.SESSION_COOKIE not in a.cookies and auth.SESSION_COOKIE not in b.cookies


def test_tampered_session_cookie_signs_the_user_out(raw):
    _login(raw)
    value = raw.cookies.get(auth.SESSION_COOKIE)
    uid, rest = value.split(".", 1)
    raw.cookies.set(auth.SESSION_COOKIE, f"9.{rest}")  # try to become the manager
    assert raw.get("/", follow_redirects=False).headers["location"] == "/login"


def test_old_unsigned_user_cookie_is_ignored(raw):
    raw.cookies.set("shms_uid", "8")
    assert raw.get("/", follow_redirects=False).status_code == 303


def test_expired_session_is_rejected():
    old = auth.sign_session(8, issued=0)
    assert auth.read_session(old) is None
    assert auth.read_session(auth.sign_session(8)) == 8


def test_logout_clears_the_session(raw):
    _login(raw)
    raw.post("/logout", data={"csrf_token": raw.cookies.get(auth.CSRF_COOKIE)})
    assert raw.get("/", follow_redirects=False).status_code == 303


# ---------------------------------------------------------------- CSRF


def test_form_post_without_or_with_wrong_csrf_token_is_refused(raw):
    _login(raw)
    assert raw.post("/report", data={"area_id": 1}).status_code == 403
    assert raw.post("/report", data={"area_id": 1, "csrf_token": "forged"}).status_code == 403


def test_login_form_also_needs_the_csrf_token(raw):
    r = raw.post("/login", data={"username": "sara", "password": DEMO_PASSWORD})
    assert r.status_code == 403


def test_every_post_form_contains_the_csrf_field(client):
    from tests.conftest import login

    login(client, 8)
    for path in ("/report", "/login"):
        page = client.get(path).text
        assert page.count('name="csrf_token"') >= page.count('method="post"') >= 1


# ---------------------------------------------------------------- API tokens


def test_api_requires_a_token_in_normal_mode(client, strict):
    assert client.get("/api/hazards").status_code == 401
    assert client.get("/api/hazards", headers={"X-User-Id": "8"}).status_code == 401


def test_api_accepts_a_valid_token_and_stores_only_its_hash(client, db, strict):
    sara = db.scalar(select(User).where(User.username == "sara"))
    token = tokens.create(db, sara, "test")
    db.commit()
    assert client.get("/api/hazards", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    stored = db.scalar(select(ApiToken).where(ApiToken.user_id == sara.id))
    assert token not in stored.token_hash and stored.token_hash == auth.token_hash(token)
    assert client.get("/api/hazards", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_api_does_not_accept_the_browser_session_for_changes(raw, strict):
    _login(raw)
    assert raw.post("/api/hazards/1/close", json={"action": "x"}).status_code == 401


def test_demo_header_works_only_when_enabled(client, strict):
    assert client.get("/api/hazards", headers={"X-User-Id": "8"}).status_code == 401
    override_settings(demo_header_auth=True)
    assert client.get("/api/hazards", headers={"X-User-Id": "8"}).status_code == 200


def test_read_endpoints_and_metrics_need_sign_in(client, strict):
    for path in ("/api/hazards", "/api/hazards/1", "/api/dashboard", "/api/monitoring", "/metrics"):
        assert client.get(path).status_code == 401, path
    assert client.get("/api/health").status_code == 200
