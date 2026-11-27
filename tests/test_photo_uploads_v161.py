"""v1.6.1 – ordinary phone photos: HEIC, large JPEGs, screenshots, rotation, WhatsApp copies, report location."""

from io import BytesIO

import pillow_heif
import pytest
from PIL import Image

from shms.detection.mock import MockDetector
from shms.settings import get_settings
from tests.conftest import jpeg_bytes, login
from tests.test_api import REPORTER, h

GPS = {1: "N", 2: (24.0, 46.0, 30.0), 3: "E", 4: (54.0, 42.0, 0.0)}  # 24.775 N, 54.7 E


def _exif(orientation: int = 1, gps: bool = True) -> bytes:
    e = Image.Exif()
    e[0x0112] = orientation
    e.get_ifd(0x8769).update({36867: "2026:11:26 09:12:33", 36881: "+04:00"})
    if gps:
        e.get_ifd(0x8825).update(GPS)
    return e.tobytes()


def _heic(size=(1200, 900), gps: bool = True) -> bytes:
    buf = BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", size, (120, 130, 140))).save(buf, quality=60, exif=_exif(gps=gps))
    return buf.getvalue()


def _api(client, name, data, mime="image/jpeg", **form):
    return client.post(
        "/api/hazards", headers=h(REPORTER), data={"area_code": "DIG", **form}, files={"photo": (name, data, mime)}
    )


def _stored(report) -> Image.Image:
    return Image.open(get_settings().upload_dir / report["photo_path"])


def _area_id(code="DIG") -> int:
    from sqlalchemy import select

    from shms import db as dbmod
    from shms.models import Area

    with dbmod.new_session() as s:
        return s.scalar(select(Area.id).where(Area.code == code))


def _page_report(client, name, data, mime="image/jpeg", **form):
    login(client, REPORTER)
    return client.post(
        "/report", data={"area_id": _area_id(), **form}, files={"photo": (name, data, mime)}, follow_redirects=False
    )


# ------------------------------------------------------------------ formats, size, orientation


def test_iphone_heic_is_accepted_with_capture_time_and_gps(client):
    r = _api(client, "IMG_4821.HEIC", _heic(), "image/heic")
    assert r.status_code == 201, r.text
    report = r.json()
    assert report["photo_path"].endswith(".jpg") and _stored(report).format == "JPEG"
    assert report["photo_captured_at"] == "2026-11-26T09:12:33+04:00"
    assert report["location"] == {"latitude": 24.775, "longitude": 54.7, "accuracy_m": None, "source": "photo"}


def test_heif_with_wrong_mime_type_is_still_recognised_by_content(client):
    assert _api(client, "photo.heif", _heic(gps=False), "application/octet-stream").status_code == 201


def test_48_megapixel_jpeg_is_downscaled_not_rejected(client):
    buf = BytesIO()
    Image.new("RGB", (8064, 6048), (90, 100, 110)).save(buf, "JPEG", quality=70)
    r = _api(client, "IMG_48MP.jpg", buf.getvalue())
    assert r.status_code == 201, r.text
    assert max(_stored(r.json()).size) == 2048


def test_file_between_20_and_30_mb_is_accepted(client):
    data = jpeg_bytes() + b"\0" * (25 * 1024 * 1024)  # trailing bytes after the JPEG end marker are ignored
    assert _api(client, "IMG_25MB.jpg", data).status_code == 201


def test_png_screenshot_with_transparency_is_flattened_on_white(client):
    shot = Image.new("RGBA", (390, 844), (0, 0, 0, 0))
    shot.paste((200, 30, 30, 255), (0, 400, 390, 600))
    buf = BytesIO()
    shot.save(buf, "PNG")
    r = _api(client, "Screenshot 2026-11-26 at 09.14.png", buf.getvalue(), "image/png")
    assert r.status_code == 201
    stored = _stored(r.json())
    assert stored.mode == "RGB" and stored.getpixel((5, 5)) > (240, 240, 240)


def test_exif_orientation_is_applied(client):
    buf = BytesIO()
    Image.new("RGB", (800, 600), "white").save(buf, "JPEG", exif=_exif(orientation=6))
    r = _api(client, "IMG_rotated.jpg", buf.getvalue())
    w, hgt = _stored(r.json()).size
    assert (w, hgt) == (600, 800)  # stored landscape pixels, shown upright (portrait) after rotation


def test_whatsapp_copy_without_metadata_falls_back_to_upload_time(client):
    r = _page_report(client, "WhatsApp Image 2026-11-26 at 09.20.11.jpeg", jpeg_bytes(size=(1600, 1200)))
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "upload time, because the photo has no capture time" in page
    assert "GPS unavailable in the photo and no device location was shared" in page


def test_stored_copy_has_no_metadata(client):
    buf = BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "JPEG", exif=_exif())
    stored = _stored(_api(client, "gps.jpg", buf.getvalue()).json())
    assert not stored.getexif()


# ------------------------------------------------------------------ plain-language messages, never JSON on a page


def _is_page(r) -> bool:
    return r.headers["content-type"].startswith("text/html") and '{"detail"' not in r.text


def test_too_large_photo_shows_a_message_on_the_report_page(client):
    r = _page_report(client, "big.jpg", jpeg_bytes() + b"\0" * (31 * 1024 * 1024))
    assert r.status_code == 413 and _is_page(r)
    assert "larger than 30 MB" in r.text and 'id="hazard-report"' in r.text


@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("anim.gif", None, "GIF files are not supported"),
        ("notes.jpg", b"not an image", "could not be read as a photo"),
        ("empty.jpg", b"", "The photo file is empty"),
    ],
)
def test_unusable_files_show_plain_messages(client, name, data, expected):
    if data is None:
        buf = BytesIO()
        Image.new("RGB", (16, 16)).save(buf, "GIF")
        data = buf.getvalue()
    r = _page_report(client, name, data)
    assert r.status_code == 422 and _is_page(r)
    assert expected in r.text


def test_missing_area_shows_a_message_not_a_validation_dump(client):
    login(client, REPORTER)
    r = client.post("/report", data={}, files={"photo": ("p.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 422 and _is_page(r)
    assert "Choose the area where you saw the hazard." in r.text


def test_other_page_errors_are_html_but_the_api_stays_json(client):
    login(client, REPORTER)
    page = client.get("/hazards/999999")
    assert page.status_code == 404 and _is_page(page) and "Hazard not found" in page.text
    api = client.get("/api/hazards/999999", headers=h(REPORTER))
    assert api.status_code == 404 and api.json()["detail"]


def test_api_rejection_keeps_the_plain_message(client):
    r = _api(client, "big.jpg", jpeg_bytes() + b"\0" * (31 * 1024 * 1024))
    assert r.status_code == 413 and "larger than 30 MB" in r.json()["detail"]


# ------------------------------------------------------------------ analysis always visible


def test_photo_with_no_people_says_none_found_and_offers_manual_choice(client):
    r = _page_report(client, "IMG_pipes_clean.jpg", jpeg_bytes())
    page = client.get(r.headers["location"]).text
    assert "The AI found none of the checked items missing" in page
    assert "This is not a confirmation that the scene is in order" in page
    assert 'name="category_code"' in page  # manual hazard selection


def test_detector_crash_still_creates_a_draft_with_a_visible_message(client, monkeypatch):
    class Broken(MockDetector):
        def detect(self, image_path):
            raise RuntimeError("model file missing")

    monkeypatch.setattr("shms.web.pages.get_detector", lambda: Broken())
    r = _page_report(client, "site.jpg", jpeg_bytes())
    assert r.status_code == 303
    page = client.get(r.headers["location"]).text
    assert "could not analyse this photo" in page and 'name="category_code"' in page


def test_report_form_offers_library_heic_location_and_analysing_state(client):
    login(client, REPORTER)
    page = client.get("/report").text
    assert 'capture="environment"' not in page  # the camera-only attribute blocked choosing existing photos
    assert 'accept="image/*,.heic,.heif"' in page
    assert 'id="use-location"' in page and "Use my current location" in page
    assert 'id="analysing"' in page and "Analysing your photo" in page
    assert "/static/report-upload.js" in page


# ------------------------------------------------------------------ report location sources


def test_device_location_is_stored_when_the_photo_has_no_gps(client):
    r = _api(client, "p.jpg", jpeg_bytes(), device_lat="24.7801", device_lon="54.6912", device_accuracy="12.4")
    assert r.json()["location"] == {"latitude": 24.7801, "longitude": 54.6912, "accuracy_m": 12.4, "source": "device"}


def test_photo_gps_wins_over_the_device_location(client):
    buf = BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "JPEG", exif=_exif())
    r = _api(client, "p.jpg", buf.getvalue(), device_lat="25.0", device_lon="55.0")
    assert r.json()["location"]["source"] == "photo" and r.json()["location"]["latitude"] == 24.775


def test_no_location_is_recorded_as_none(client):
    assert _api(client, "p.jpg", jpeg_bytes()).json()["location"]["source"] == "none"


def test_device_location_on_the_page_is_shown_with_its_source(client):
    r = _page_report(client, "p.jpg", jpeg_bytes(), device_lat="24.78", device_lon="54.69", device_accuracy="8")
    page = client.get(r.headers["location"]).text
    assert "24.78, 54.69" in page and "from the reporter's device when uploading" in page and "± 8 m" in page


@pytest.mark.parametrize(("lat", "lon"), [("91", "54"), ("24", "181"), ("abc", "54"), ("24", "")])
def test_invalid_device_location_is_refused_with_a_message(client, lat, lon):
    r = _page_report(client, "p.jpg", jpeg_bytes(), device_lat=lat, device_lon=lon)
    assert r.status_code == 422 and _is_page(r)
    assert "Use my current location" in r.text


def test_parse_device_location_rules():
    from shms.services import DeviceLocation, parse_device_location

    assert parse_device_location("", "") is None
    assert parse_device_location("24.1234567", "54.7654321", "") == DeviceLocation(24.123457, 54.765432, None)


# ------------------------------------------------------------------ migration 0010


def test_migration_0010_copies_existing_photo_gps_as_report_location(tmp_path):
    import sqlite3

    from shms import db as dbmod
    from tests.test_migrations import _old_db

    url = _old_db(tmp_path / "old.db")
    dbmod.migrate_to_head(url, "0009_ata_site_map")
    con = sqlite3.connect(tmp_path / "old.db")
    con.execute("UPDATE hazards SET photo_latitude = 24.775, photo_longitude = 54.7 WHERE id = 1")
    con.commit()
    count = con.execute("SELECT count(*) FROM hazards").fetchone()[0]
    con.close()
    dbmod.migrate_to_head(url)
    con = sqlite3.connect(tmp_path / "old.db")
    rows = dict(con.execute("SELECT id, location_source FROM hazards").fetchall())
    loc = con.execute("SELECT location_latitude, location_longitude FROM hazards WHERE id = 1").fetchone()
    con.close()
    assert len(rows) == count  # nothing deleted
    assert rows[1] == "photo" and loc == (24.775, 54.7)
    assert all(source == "none" for hid, source in rows.items() if hid != 1)


# ------------------------------------------------------------------ closure photos (confirm "fixed on the spot", close)


def test_closure_photo_inputs_allow_the_photo_library(client):
    from pathlib import Path

    for t in ("confirm.html", "hazard.html"):
        assert 'capture="environment"' not in (Path("shms/templates") / t).read_text(), t


def test_rejected_fixed_on_spot_photo_reshows_the_confirm_form(client):
    hid = _api(client, "a.jpg", jpeg_bytes()).json()["id"]
    login(client, REPORTER)
    r = client.post(
        f"/hazards/{hid}/confirm",
        data={
            "category_code": "no_hard_hat",
            "consequence": 2,
            "fixed_on_spot": "true",
            "closure_action": "Issued",
            "control_type": "ppe",
            "residual_consequence": "1",
        },
        files={"closure_photo": ("fixed.jpg", b"not an image", "image/jpeg")},
    )
    assert r.status_code == 422 and _is_page(r)
    assert "could not be read as a photo" in r.text and 'id="confirm-form"' in r.text


def test_rejected_close_photo_shows_the_message_on_the_hazard_page(client):
    from tests.test_api import OWNER_DIG

    hid = _api(client, "a.jpg", jpeg_bytes()).json()["id"]
    client.post(
        f"/api/hazards/{hid}/confirm", headers=h(REPORTER), json={"category_code": "no_hard_hat", "consequence": 3}
    )
    login(client, OWNER_DIG)
    r = client.post(
        f"/hazards/{hid}/close",
        data={"action": "Done", "control_type": "ppe", "residual_consequence": "1"},
        files={"photo": ("done.jpg", b"not an image", "image/jpeg")},
    )
    assert r.status_code == 200 and "could not be read as a photo" in r.text
