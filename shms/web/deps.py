"""Shared request dependencies: database session, current user, photo storage."""

from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

from fastapi import Depends, HTTPException, Request, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import User
from ..photo_metadata import PhotoCapture, photo_capture
from ..settings import get_settings


def current_user_optional(request: Request, db: Session = Depends(get_session)) -> User | None:
    """HTML pages: the user in a valid signed session cookie (see shms/auth.py)."""
    from .. import auth

    uid = auth.read_session(request.cookies.get(auth.SESSION_COOKIE))
    return db.get(User, uid) if uid is not None else None


def api_user_optional(request: Request, db: Session = Depends(get_session)) -> User | None:
    """JSON API: a per-user token (Authorization: Bearer ...). The browser session is deliberately not accepted, so
    the API needs no CSRF protection. The X-User-Id header only works with SHMS_DEMO_HEADER_AUTH=1 (tests, scripts)."""
    from .. import tokens

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        return tokens.user_for(db, token.strip())
    raw = request.headers.get("X-User-Id")
    if get_settings().demo_header_auth and raw and raw.isdigit():
        return db.get(User, int(raw))
    return None


def current_user(user: User | None = Depends(api_user_optional)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in", headers={"WWW-Authenticate": "Bearer"})
    return user


try:  # iPhone / Mac photos (HEIC/HEIF). Optional so the app still starts without it; the message below says so.
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORT = True
except ImportError:  # pragma: no cover - pillow-heif is a declared dependency
    HEIF_SUPPORT = False

# Formats are recognised from the file content; the file name and the browser's MIME type are not trusted.
ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "HEIF"}  # MPO = multi-picture JPEG from some phones
MAX_UPLOAD_MB = 30
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_PIXELS = 120_000_000  # hard cap; a 48 or 108 MP phone photo is downscaled, not rejected
# Decompression-bomb guard for formats decoded at full size (PNG, WebP, HEIC): above 40 MP a real photo still needs
# at least ~0.01 bytes per pixel on disk (48 MP phone HEIC: ~0.06). A tiny file that claims tens of megapixels is
# refused before decoding. JPEG is exempt because it is decoded at reduced size (draft mode).
BOMB_PIXELS = 40_000_000
MIN_BYTES_PER_PIXEL = 0.01
MAX_SIDE = 2048  # stored photos are downscaled to this longest side (enough for the detector and the report)
PHOTO_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}\.jpg$")


class PhotoRejected(HTTPException):
    """An upload the app cannot use. The detail is a plain-language message shown on the page."""


def _reject(status: int, message: str) -> PhotoRejected:
    return PhotoRejected(status_code=status, detail=message)


async def save_photo(upload: UploadFile | None, prefix: str = "") -> str | None:
    name, _ = await store_photo(upload, prefix)
    return name


async def store_photo(
    upload: UploadFile | None, prefix: str = "", *, capture: bool = False
) -> tuple[str | None, PhotoCapture]:
    """Validate an uploaded image and store a re-encoded JPEG under a generated name.

    * size: at most 30 MB, checked while reading (never more than 30 MB + 1 byte in memory);
    * type: the content must decode as JPEG, PNG, WebP or HEIC/HEIF;
    * large photos are downscaled to 2048 px on the longest side (JPEG decoding uses draft mode, so a
      48 MP photo is never fully decoded); only absurd pixel counts (> 120 MP) are refused;
    * EXIF orientation is applied, then all metadata is dropped from the stored copy;
    * name: random prefix + sanitised stem, ".jpg"; no path from the client is used.
    Returns the stored name and requested capture metadata. Raises PhotoRejected with a plain message."""
    if upload is None or not upload.filename:
        return None, PhotoCapture()
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise _reject(
            413,
            f"This photo is larger than {MAX_UPLOAD_MB} MB. Send a smaller copy: on iPhone choose a smaller size "
            "when sharing, or take a screenshot of the photo and upload that.",
        )
    if not data:
        raise _reject(422, "The photo file is empty. Choose the photo again.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ALLOWED_FORMATS:
                raise _reject(
                    422, f"{im.format or 'This'} files are not supported. Upload a JPEG, HEIC, PNG or WebP photo."
                )
            pixels = im.width * im.height
            if pixels > MAX_PIXELS:
                raise _reject(422, "This image is too large to process (over 120 megapixels). Upload a normal photo.")
            compact = len(data) / pixels < MIN_BYTES_PER_PIXEL
            if pixels > BOMB_PIXELS and compact and im.format not in ("JPEG", "MPO"):
                raise _reject(
                    422,
                    "This image cannot be processed safely (too many pixels for its file size). Upload a normal photo.",
                )
            metadata = photo_capture(im) if capture else PhotoCapture()
            if im.format in ("JPEG", "MPO"):
                im.draft("RGB", (MAX_SIDE, MAX_SIDE))  # decode at reduced size: fast and low-memory for 48 MP photos
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):  # screenshots with transparency: flatten on white, not black
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, (255, 255, 255))
                flat.paste(im, mask=im.getchannel("A"))
                im = flat
            im = im.convert("RGB")
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            stem = re.sub(r"[^A-Za-z0-9_-]", "", Path(upload.filename).stem)[:40]
            name = f"{prefix}{uuid.uuid4().hex[:12]}_{stem}.jpg"
            folder = get_settings().upload_dir
            folder.mkdir(parents=True, exist_ok=True)
            im.save(folder / name, format="JPEG", quality=90)
    except Image.DecompressionBombError as exc:
        raise _reject(422, "This image is too large to process (over 120 megapixels). Upload a normal photo.") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        heic = Path(upload.filename).suffix.lower() in (".heic", ".heif")
        hint = " HEIC photos need the pillow-heif package on the server." if heic and not HEIF_SUPPORT else ""
        raise _reject(
            422, "This file could not be read as a photo. Upload a JPEG, HEIC, PNG or WebP photo." + hint
        ) from exc
    return name, metadata


def photo_file(name: str) -> Path:
    return get_settings().upload_dir / name
