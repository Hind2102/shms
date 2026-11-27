"""v1.6.1 – public demo (Hugging Face Space): warning banner, reset on start, required secret, per-IP rate limit."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from shms import db as dbmod
from shms.main import create_app
from shms.models import Hazard
from shms.settings import override_settings
from tests.conftest import BrowserClient, login
from tests.test_api import REPORTER, SUPERVISOR

BANNER = "Public demo – do not upload confidential, personal or site photos; data resets on restart."


@pytest.fixture(autouse=True)
def _restore(settings):
    # override_settings replaces the shared settings: switch demo mode and the limit off again after each test.
    yield
    override_settings(demo_mode=False, rate_limit_per_min=0, detector="mock", secret_key="")


@pytest.fixture()
def demo(settings, tmp_path):
    return override_settings(
        demo_mode=True, detector="yolo", secret_key="test-demo-key", database_url=f"sqlite:///{tmp_path}/demo.db"
    )


def _mark_all_hazards(url: str) -> None:
    with dbmod.new_session() as s:
        s.query(Hazard).update({Hazard.description: "changed by the visitor"})
        s.commit()


def _marked() -> int:
    with dbmod.new_session() as s:
        return s.scalar(select(func.count(Hazard.id)).where(Hazard.description == "changed by the visitor"))


@pytest.fixture()
def demo_client(demo):
    return BrowserClient(create_app(database_url=demo.database_url))


def test_no_banner_outside_demo_mode(client):
    assert "Public demo" not in client.get("/login").text


@pytest.mark.parametrize("path", ["/login", "/", "/report", "/site", "/hazards", "/board"])
def test_banner_on_every_page(demo_client, path):
    login(demo_client, SUPERVISOR if path == "/board" else REPORTER)
    r = demo_client.get(path)
    assert r.status_code == 200, path
    assert BANNER in r.text, path


def test_banner_on_error_pages(demo_client):
    login(demo_client, REPORTER)
    assert BANNER in demo_client.get("/hazards/999999").text


def test_login_page_says_data_resets_and_lists_demo_accounts(demo_client):
    page = demo_client.get("/login").text
    assert "resets" in page and "shms-demo-2026" in page and "ahmed" in page and "sara" in page


def test_demo_start_resets_the_database(demo):
    create_app(database_url=demo.database_url)
    _mark_all_hazards(demo.database_url)
    assert _marked() > 0
    (demo.upload_dir / "leftover.jpg").write_bytes(b"x")
    create_app(database_url=demo.database_url)  # restart
    assert _marked() == 0
    assert not (demo.upload_dir / "leftover.jpg").exists()


def test_normal_start_keeps_the_database(settings, tmp_path):
    url = f"sqlite:///{tmp_path}/keep.db"
    create_app(database_url=url)
    _mark_all_hazards(url)
    create_app(database_url=url)
    assert _marked() > 0


def test_demo_refuses_to_start_without_a_secret_key(demo):
    override_settings(secret_key="")
    with pytest.raises(RuntimeError, match="SHMS_SECRET_KEY"):
        create_app(database_url=demo.database_url)


def test_demo_refuses_the_mock_detector(demo):
    override_settings(detector="mock")
    with pytest.raises(RuntimeError, match="mock"):
        create_app(database_url=demo.database_url)


# ------------------------------------------------------------------ rate limit


def _limited(settings, n):
    override_settings(rate_limit_per_min=n)
    return create_app(database_url="sqlite://")


def _post_login(client):
    return client.post("/login", data={"username": "nobody", "password": "x"})


def test_rate_limit_refuses_with_a_plain_message(settings):
    c = BrowserClient(_limited(settings, 3))
    codes = [_post_login(c).status_code for _ in range(4)]
    assert 429 not in codes[:3] and codes[3] == 429
    r = _post_login(c)
    assert "Too many requests" in r.text and "<html" in r.text and int(r.headers["retry-after"]) >= 1


def test_rate_limit_is_per_ip(settings):
    app = _limited(settings, 2)
    a, b = BrowserClient(app, client=("10.0.0.1", 1)), BrowserClient(app, client=("10.0.0.2", 1))
    for _ in range(2):
        _post_login(a)
    assert _post_login(a).status_code == 429
    assert _post_login(b).status_code != 429


def test_rate_limit_ignores_page_views(settings):
    c = TestClient(_limited(settings, 1))
    assert all(c.get("/login").status_code == 200 for _ in range(5))


def test_rate_limit_api_answer_is_json(settings):
    c = TestClient(_limited(settings, 1))
    c.post("/api/hazards")
    r = c.post("/api/hazards")
    assert r.status_code == 429 and r.json()["detail"].startswith("Too many requests")


def test_rate_limit_off_by_default(client):
    assert all(_post_login(client).status_code != 429 for _ in range(40))


def _fingerprint(path):
    return (path.stat().st_size, path.stat().st_mtime_ns) if path.exists() else None


def test_demo_refuses_the_project_database_and_leaves_it_untouched(demo):
    from shms.settings import PROJECT_DIR

    real = PROJECT_DIR / "shms.db"
    before = _fingerprint(real)
    with pytest.raises(RuntimeError, match="demo-only locations"):
        create_app(database_url=f"sqlite:///{real}")
    assert _fingerprint(real) == before


def test_demo_refuses_the_project_upload_folder(demo):
    from shms.settings import PROJECT_DIR

    uploads = PROJECT_DIR / "uploads"
    before = sorted(p.name for p in uploads.iterdir()) if uploads.exists() else None
    override_settings(upload_dir=uploads)
    with pytest.raises(RuntimeError, match="demo-only locations"):
        create_app(database_url=demo.database_url)
    assert (sorted(p.name for p in uploads.iterdir()) if uploads.exists() else None) == before


def test_demo_refuses_the_project_outbox(demo):
    from shms.settings import PROJECT_DIR

    override_settings(mail_outbox=PROJECT_DIR / "outbox")
    with pytest.raises(RuntimeError, match="demo-only locations"):
        create_app(database_url=demo.database_url)
