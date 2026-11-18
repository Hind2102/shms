"""Owner decision 2026-11-18: the hard-hat check stays enabled but is labelled everywhere as an unverified suggestion
(validated on SH17 only; failed external validation). The label comes from shms/config/ai_release.json → notes."""

import json
import re
from pathlib import Path

import pytest

from shms import taxonomy
from shms.settings import override_settings
from tests.conftest import jpeg_bytes, login
from tests.test_api import REPORTER

LABEL = "validated on SH17 only – failed external validation (Hard Hat Workers): unverified suggestion"
SHIPPED = Path(__file__).resolve().parent.parent / "shms" / "config" / "ai_release.json"


@pytest.fixture()
def shipped_release(settings):
    return override_settings(ai_release_file=SHIPPED)


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_shipped_release_keeps_hard_hat_enabled_with_the_note():
    rel = json.loads(SHIPPED.read_text())
    assert "no_hard_hat" in rel["approved"]
    assert rel["notes"]["no_hard_hat"]["label"] == LABEL


def test_note_only_for_hard_hat(shipped_release):
    assert taxonomy.release_note("no_hard_hat") == LABEL
    assert taxonomy.release_note("no_gloves") is None and taxonomy.release_note("no_eye_protection") is None


def test_confirm_page_labels_the_hard_hat_suggestion(client, shipped_release):
    login(client, REPORTER)
    r = client.post(
        "/report",
        data={"area_id": 3},
        files={"photo": ("site_no_hard_hat.jpg", jpeg_bytes(), "image/jpeg")},
        follow_redirects=True,
    )
    text = _text(r.text)
    assert "Worker without hard hat" in text and LABEL in text


def test_area_page_labels_the_hard_hat_check(client, shipped_release):
    login(client, REPORTER)
    assert LABEL in _text(client.get("/areas/DIG").text)
