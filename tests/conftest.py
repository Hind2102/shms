import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from shms import db as dbmod
from shms.detection import get_detector
from shms.main import create_app
from shms.settings import override_settings

# Every new closure must record the ADOSH-SF control type and the residual consequence (v1.4.0). Tests that are
# about something else close hazards with these neutral values.
CLOSE = {"control_type": "procedural", "residual_consequence": 1}


def jpeg_bytes(color="gray", size=(640, 480)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture()
def settings(tmp_path):
    # No release file: all four AI hazard types enabled, so workflow tests are independent of evaluation results.
    s = override_settings(
        upload_dir=tmp_path / "uploads",
        detector="mock",
        database_url="sqlite://",
        ai_release_file=tmp_path / "none.json",
        mail_outbox=tmp_path / "outbox",
        # API tests identify users with the X-User-Id header; only allowed when explicitly enabled (tests/demo).
        demo_header_auth=True,
    )
    get_detector.cache_clear()
    yield s
    get_detector.cache_clear()


@pytest.fixture()
def app(settings):
    return create_app(database_url="sqlite://", seed_demo=True)


class BrowserClient(TestClient):
    """Behaves like a browser submitting the app's own forms: every non-API POST carries the CSRF token that the
    page's hidden field would contain. CSRF rejection itself is tested with a plain TestClient (tests/test_auth.py)."""

    def post(self, url, *args, **kwargs):
        from shms import auth

        if not str(url).startswith("/api") and "json" not in kwargs:
            if not self.cookies.get(auth.CSRF_COOKIE):
                self.get("/login")
            data = dict(kwargs.get("data") or {})
            data.setdefault("csrf_token", self.cookies.get(auth.CSRF_COOKIE))
            kwargs["data"] = data
        return super().post(url, *args, **kwargs)


def login(client, user_id: int, password: str | None = None):
    """Sign in through the real login form as the seeded user with this id."""
    from shms import db as dbmod
    from shms.models import User
    from shms.seed import DEMO_PASSWORD

    with dbmod.new_session() as s:
        username = s.get(User, user_id).username
    return client.post("/login", data={"username": username, "password": password or DEMO_PASSWORD})


@pytest.fixture()
def client(app):
    return BrowserClient(app)


@pytest.fixture()
def db(app):
    s = dbmod.new_session()
    yield s
    s.close()


@pytest.fixture()
def empty_db(settings):
    """Fresh schema with only users and areas (no synthetic history)."""
    from shms.models import Area, Role, User

    dbmod.init_engine("sqlite://")
    dbmod.create_all()
    s = dbmod.new_session()
    rep = User(name="Rep", role=Role.REPORTER)
    owner = User(name="Owner", role=Role.AREA_OWNER)
    other = User(name="Other owner", role=Role.AREA_OWNER)
    sup = User(name="Sup", role=Role.SUPERVISOR)
    s.add_all([rep, owner, other, sup])
    s.flush()
    s.add_all(
        [
            Area(code="DIG", name="Digestion", owner_id=owner.id, required_ppe="Hard hat"),
            Area(code="CAL", name="Calcination", owner_id=other.id),
        ]
    )
    s.commit()
    yield s
    s.close()
