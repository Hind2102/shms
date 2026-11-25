"""v1.4.1: wherever SHMS shows a likelihood it says that the history-based value is a project heuristic."""

import html
from pathlib import Path

from shms import risk
from tests.conftest import login
from tests.test_api import REPORTER, create, h

ROOT = Path(__file__).resolve().parents[1]


def _has_note(page: str) -> bool:
    return risk.LIKELIHOOD_NOTE in html.unescape(page)


def test_note_states_the_configured_lookback():
    assert f"last {risk.lookback_days()} days" in risk.LIKELIHOOD_NOTE
    assert "project heuristic, not the guideline's definition" in risk.LIKELIHOOD_NOTE


def test_matrix_confirm_and_hazard_pages_show_the_note(client):
    login(client, REPORTER)
    assert _has_note(client.get("/matrix").text)
    hid = create(client).json()["id"]
    confirm = client.get(f"/hazards/{hid}/confirm").text
    assert _has_note(confirm) and "<abbr title=" in confirm  # tooltip on the word, plus the visible note
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 2}
    )
    assert _has_note(client.get(f"/hazards/{hid}").text)


def test_readme_and_docs_show_the_note():
    for doc in ("README.md", "docs/architecture.md", "docs/risk_matrix_source.md", "docs/requirements.md"):
        assert risk.LIKELIHOOD_NOTE in (ROOT / doc).read_text(), doc
