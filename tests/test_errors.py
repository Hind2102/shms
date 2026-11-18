"""Unexpected errors: users get a generic message, the details go to the server log only."""

import logging

from fastapi.testclient import TestClient

from shms import services
from tests.conftest import BrowserClient, login
from tests.test_api import SUPERVISOR, h


def test_unexpected_error_shows_generic_page_and_logs_details(app, monkeypatch, caplog):
    c = BrowserClient(app, raise_server_exceptions=False)
    login(c, SUPERVISOR)

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(services, "dashboard", boom)
    with caplog.at_level(logging.ERROR, logger="shms"):
        r = c.get("/")
    assert r.status_code == 500
    assert "secret internal detail" not in r.text and "Traceback" not in r.text
    assert "Something went wrong" in r.text
    assert "secret internal detail" in caplog.text


def test_unexpected_api_error_is_generic_json(app, monkeypatch):
    c = TestClient(app, raise_server_exceptions=False)
    monkeypatch.setattr(services, "dashboard", lambda *a, **k: 1 / 0)
    r = c.get("/api/dashboard", headers=h(SUPERVISOR))
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error"}
