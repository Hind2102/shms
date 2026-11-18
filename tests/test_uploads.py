"""Upload safety: content sniffing, size and pixel limits, safe file names."""

import io

from PIL import Image

from shms.settings import get_settings
from tests.conftest import jpeg_bytes
from tests.test_api import REPORTER, h


def _upload(client, name, data, mime="image/jpeg"):
    return client.post(
        "/api/hazards", headers=h(REPORTER), data={"area_code": "DIG"}, files={"photo": (name, data, mime)}
    )


def test_text_file_renamed_to_jpg_is_refused(client):
    r = _upload(client, "photo.jpg", b"this is not an image at all")
    assert r.status_code == 422


def test_unsupported_image_type_is_refused(client):
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(buf, "GIF")
    assert _upload(client, "anim.gif", buf.getvalue(), "image/gif").status_code == 422


def test_png_and_webp_are_accepted(client):
    for fmt in ("PNG", "WEBP"):
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), "blue").save(buf, fmt)
        assert _upload(client, f"p.{fmt.lower()}", buf.getvalue(), f"image/{fmt.lower()}").status_code == 201, fmt


def test_file_over_20_mb_is_refused(client):
    big = jpeg_bytes() + b"\0" * (20 * 1024 * 1024)
    assert _upload(client, "big.jpg", big).status_code == 413


def test_decompression_bomb_is_refused(client):
    buf = io.BytesIO()
    Image.new("L", (9000, 9000), 0).save(buf, "PNG")  # 81 megapixels, but only ~80 KB on disk
    assert len(buf.getvalue()) < 1_000_000
    assert _upload(client, "bomb.png", buf.getvalue(), "image/png").status_code == 422


def test_file_name_cannot_traverse_and_is_stored_as_jpeg(client):
    r = _upload(client, "../../../etc/evil name.jpg", jpeg_bytes())
    assert r.status_code == 201
    name = r.json()["photo_path"]
    assert "/" not in name and ".." not in name and name.endswith(".jpg")
    assert (get_settings().upload_dir / name).is_file()
