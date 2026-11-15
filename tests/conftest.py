import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from shms import db as dbmod
from shms.detection import get_detector
from shms.main import create_app
from shms.settings import override_settings


def jpeg_bytes(color="gray", size=(640, 480)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture()
def settings(tmp_path):
    s = override_settings(upload_dir=tmp_path / "uploads", detector="mock", database_url="sqlite://")
    get_detector.cache_clear()
    yield s
    get_detector.cache_clear()


@pytest.fixture()
def app(settings):
    return create_app(database_url="sqlite://", seed_demo=True)


@pytest.fixture()
def client(app):
    return TestClient(app)


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
