"""Read optional capture information from a report photo, before its EXIF is stripped."""

import struct
from dataclasses import dataclass
from datetime import datetime

from PIL import Image


@dataclass(frozen=True)
class PhotoCapture:
    taken_at: str | None = None
    latitude: float | None = None
    longitude: float | None = None


def _coordinate(value: tuple, ref: str, positive: str, negative: str, limit: int) -> float:
    degrees, minutes, seconds = map(float, value)
    if ref not in (positive, negative) or not (0 <= degrees <= limit and 0 <= minutes < 60 and 0 <= seconds < 60):
        raise ValueError("Invalid EXIF GPS coordinate")
    decimal = degrees + minutes / 60 + seconds / 3600
    if decimal > limit:
        raise ValueError("GPS coordinate out of range")
    return round(decimal if ref == positive else -decimal, 6)


def photo_capture(im: Image.Image) -> PhotoCapture:
    # Malformed or partial metadata must not prevent reporting an otherwise readable photo.
    invalid = (TypeError, ValueError, KeyError, IndexError, ArithmeticError, OSError, SyntaxError, struct.error)
    taken_at = None
    latitude = longitude = None
    try:
        exif = im.getexif()
        camera = exif.get_ifd(34665)
        original = camera.get(36867, exif.get(36867))
        if original:
            local_time = datetime.strptime(original, "%Y:%m:%d %H:%M:%S")
            taken_at = local_time.isoformat()
            offset = camera.get(36881, exif.get(36881))
            if offset and len(offset) == 6 and offset[0] in "+-" and offset[3] == ":":
                taken_at = datetime.strptime(original + offset, "%Y:%m:%d %H:%M:%S%z").isoformat()
    except invalid:
        pass
    try:
        gps = im.getexif().get_ifd(34853)
        latitude, longitude = (
            _coordinate(gps[2], gps[1], "N", "S", 90),
            _coordinate(gps[4], gps[3], "E", "W", 180),
        )
    except invalid:
        pass
    return PhotoCapture(taken_at, latitude, longitude)
