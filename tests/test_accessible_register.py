"""Regression checks for keyboard navigation and the empty filtered register."""

from tests.conftest import login


def test_register_labels_and_empty_state(client):
    login(client, 9)
    response = client.get("/hazards?area=missing-area")
    assert response.status_code == 200
    html = response.text
    for key in ("status", "area", "level", "category"):
        assert f'for="filter-{key}"' in html
        assert f'id="filter-{key}"' in html
    assert 'href="#main"' in html
    assert '<main id="main" tabindex="-1">' in html
    assert "No hazards match these filters." in html
    assert "Clear filters" in html
