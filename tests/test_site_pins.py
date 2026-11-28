"""Report coordinates must lie inside the selected zone's polygon on the concept map and remain optional."""

import pytest
from sqlalchemy import select

from shms import risk, services, site_layout
from shms.models import Area, Hazard, Status
from shms.site_layout import REPORTING
from tests.conftest import jpeg_bytes, login
from tests.test_api import REPORTER, h


def digestion():
    return REPORTING["DIG"]


def submit(client, data, key="pin"):
    return client.post(
        "/api/hazards",
        data={"area_code": "DIG", **data},
        headers={**h(REPORTER), "Idempotency-Key": key},
        files={"photo": ("photo.jpg", jpeg_bytes(), "image/jpeg")},
    )


def test_pin_persistence_and_retry(client):
    unit = digestion()
    point = {"x": unit.x, "y": unit.y + unit.h}
    first = submit(client, point)
    assert first.status_code == 201
    assert (first.json()["x"], first.json()["y"]) == (point["x"], point["y"])
    assert submit(client, point).json()["id"] == first.json()["id"]
    assert submit(client, {**point, "x": point["x"] + 1}).status_code == 409
    assert submit(client, {}).status_code == 409
    legacy = submit(client, {}, "without-pin")
    assert legacy.status_code == 201
    assert legacy.json()["x"] is None and legacy.json()["y"] is None


@pytest.mark.parametrize("point", [{"x": 1}, {"y": 1}, {"x": -1, "y": 2}, {"x": "NaN", "y": "4"}])
def test_invalid_pin_is_rejected_before_upload(client, db, settings, point):
    old_count = db.query(Hazard).count()
    assert submit(client, point).status_code == 422
    assert db.query(Hazard).count() == old_count
    assert not list(settings.upload_dir.glob("*"))


def test_page_creates_pin_and_map_clusters_only_active_confirmed_reports(client, db):
    for x in db.scalars(select(Hazard)):  # v1.7.0 seeds pins too: start from a map without pins
        x.x = x.y = None
    db.commit()
    login(client, REPORTER)
    unit = digestion()
    area = db.scalar(select(Area).where(Area.code == unit.code))
    point = {"x": unit.x + 10, "y": unit.y + 10}
    page = client.post(
        "/report",
        data={"area_id": area.id, **point},
        files={"photo": ("p.jpg", jpeg_bytes(), "image/jpeg")},
        follow_redirects=False,
    )
    assert page.status_code == 303
    draft_id = int(page.headers["location"].split("/")[2])
    draft = db.get(Hazard, draft_id)
    assert (draft.x, draft.y) == (point["x"], point["y"])
    assert services.site_overview(db)["pin_groups"] == []
    other = submit(client, {**point, "x": point["x"] + 2}).json()["id"]
    for hid in (other, draft_id):
        result = client.post(
            f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 3}
        )
        assert result.status_code == 200
    db.expire_all()
    peak = max(db.get(Hazard, hid).risk_score for hid in (other, draft_id))
    page = client.get("/site").text
    assert 'data-pin-count="2"' in page
    marker = page.split('data-pin-count="2"', 1)[1].split("</g>", 1)[0]  # v1.7.0: markers are <g>, not links
    assert f'fill="{risk.band_for(peak).color}"' in marker
    assert set(marker.split('data-hazards="', 1)[1].split('"', 1)[0].split()) == {str(other), str(draft_id)}
    assert f'href="/hazards/{other}"' in page and f'href="/hazards/{draft_id}"' in page  # linked in the pin list
    db.refresh(draft)
    draft.status, draft.closure_action = Status.CLOSED, "Gloves issued"
    db.commit()
    groups = services.site_overview(db, overlay="reports")["pin_groups"]
    assert [h.id for g in groups for h in g] == [other]


def test_migrated_hazards_keep_area_only_location_and_enforce_complete_pair(tmp_path):
    import sqlite3

    from shms.db import migrate_to_head
    from tests.test_migrations import _old_db

    path = tmp_path / "historical.db"
    migrate_to_head(_old_db(path))
    with sqlite3.connect(path) as database:
        assert database.execute("SELECT area_id, x, y FROM hazards ORDER BY id").fetchall() == [
            (1, None, None),
            (1, None, None),
        ]
        with pytest.raises(sqlite3.IntegrityError, match="ck_hazard_pin_pair"):
            database.execute("UPDATE hazards SET x = 500 WHERE id = 1")


@pytest.mark.parametrize(
    "point,ok",
    # v1.7.0 DIG polygon on the Al Taweelah image: (90, 305) – (405, 792)
    [((90, 305), True), ((247, 548), True), ((405, 792), True), ((406, 548), False), ((500, 400), False)],
    ids=["corner", "inside", "far-corner", "just-outside", "in-another-zone"],
)
def test_pin_must_lie_inside_the_zone_polygon(empty_db, point, ok):
    from tests.test_workflow import area

    dig = area(empty_db)
    assert dig.code == "DIG" and REPORTING["DIG"].contains(*point) is ok
    if ok:
        services.validate_pin(dig, *point)
    else:
        with pytest.raises(services.WorkflowError, match="inside Digestion"):
            services.validate_pin(dig, *point)


def test_report_form_offers_the_zone_polygon_for_pin_selection(client):
    login(client, REPORTER)
    page = client.get("/report").text
    assert 'id="report-map"' in page and f'href="{site_layout.MAP_URL}"' in page
    assert f'data-points="{REPORTING["DIG"].points_attr}"' in page
    assert 'polygon id="pin-bounds"' in page
