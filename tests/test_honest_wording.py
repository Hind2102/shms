"""When the AI finds nothing or fails, reporters can still report manually, and the page never implies "safe"."""

import re

from shms.detection.mock import MockDetector
from tests.conftest import jpeg_bytes, login
from tests.test_api import REPORTER, h

SAFE_WORDS = re.compile(r"\bsafe\b|no violation|no missing ppe detected|all clear|compliant", re.I)


def _draft(client, name: str, area: str = "DIG") -> int:
    r = client.post(
        "/api/hazards",
        headers=h(REPORTER),
        data={"area_code": area},
        files={"photo": (name, jpeg_bytes(), "image/jpeg")},
    )
    assert r.status_code == 201
    return r.json()["id"]


def _visible_text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def test_ai_found_nothing_is_not_presented_as_safe(client):
    hid = _draft(client, "site_clean.jpg")
    login(client, REPORTER)
    text = _visible_text(client.get(f"/hazards/{hid}/confirm").text)
    assert not SAFE_WORDS.search(text), SAFE_WORDS.search(text)
    assert "The AI found none of the checked items" in text
    assert "Not checked by the AI" in text and "Safety boots" in text


def test_ai_failure_lets_reporter_choose_every_checked_type(client, monkeypatch):
    class Broken(MockDetector):
        def _predict(self, image_path):
            raise RuntimeError("model offline")

    monkeypatch.setattr("shms.web.api.get_detector", lambda: Broken())
    monkeypatch.setattr("shms.web.pages.get_detector", lambda: Broken())
    hid = _draft(client, "site.jpg")
    login(client, REPORTER)
    page = client.get(f"/hazards/{hid}/confirm").text
    assert "could not analyse this photo" in page
    for code in ("no_hard_hat", "no_eye_protection", "no_gloves"):
        assert f'value="{code}"' in page
    assert not SAFE_WORDS.search(_visible_text(page))


def test_hazard_page_does_not_call_an_empty_ai_result_no_hazard(client):
    hid = _draft(client, "site_clean.jpg")
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_gloves", "consequence": 2}
    )
    login(client, REPORTER)
    text = _visible_text(client.get(f"/hazards/{hid}").text)
    assert "no PPE hazard" not in text and "found none of the checked items" in text
