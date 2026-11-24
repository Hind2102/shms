from io import BytesIO

import pytest
from PIL import Image

from tests.conftest import login
from tests.test_api import REPORTER, h


@pytest.mark.parametrize("gps", [True, False])
def test_upload_prefills_metadata_in_api_and_review(client, gps):
    exif = Image.Exif()
    exif[34665] = {36867: "2026:11:24 10:30:12", 36881: "+04:00"}
    if gps:
        exif[34853] = {1: "S", 2: (24.0, 30.0, 0.0), 3: "W", 4: (54.0, 15.0, 0.0)}
    buf = BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "JPEG", exif=exif)
    photo = {"photo": ("phone.jpg", buf.getvalue(), "image/jpeg")}
    response = client.post("/api/hazards", headers=h(REPORTER), data={"area_code": "DIG"}, files=photo)
    report = response.json()
    assert report["photo_captured_at"] == "2026-11-24T10:30:12+04:00"
    assert report["photo_latitude"] == (-24.5 if gps else None)
    assert report["photo_longitude"] == (-54.25 if gps else None)
    assert report["x"] is None and report["y"] is None
    login(client, REPORTER)
    page = client.post("/report", data={"area_id": 3}, files=photo)
    assert "2026-11-24T10:30:12+04:00" in page.text
    assert ("-24.5, -54.25" if gps else "GPS unavailable") in page.text


def test_camera_time_without_offset_and_incomplete_gps():
    from shms.photo_metadata import photo_capture

    im = Image.new("RGB", (10, 10))
    exif = im.getexif()
    exif[36867] = "2026:11:24 14:10:00"
    exif[34853] = {1: "N", 2: (24.0, 0, 0)}
    encoded = BytesIO()
    im.save(encoded, "JPEG", exif=exif)
    with Image.open(encoded) as photo:
        capture = photo_capture(photo)
    assert capture.taken_at == "2026-11-24T14:10:00"
    assert capture.latitude is None and capture.longitude is None
