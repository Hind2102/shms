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
from ..settings import get_settings

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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


async def save_photo(upload: UploadFile | None, prefix: str = "") -> str | None:
    """Validate an uploaded image, fix phone orientation, downscale to 2048 px, store as JPEG.
    Returns the file name inside the upload directory, or None if no file was sent."""
    if upload is None or not upload.filename:
        return None
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Photo is larger than 20 MB")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((2048, 2048))
            stem = re.sub(r"[^A-Za-z0-9_-]", "", Path(upload.filename).stem)[:40]
            name = f"{prefix}{uuid.uuid4().hex[:12]}_{stem}.jpg"
            folder = get_settings().upload_dir
            folder.mkdir(parents=True, exist_ok=True)
            im.save(folder / name, format="JPEG", quality=90)
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=422, detail="File is not a readable image") from exc
    return name


def photo_file(name: str) -> Path:
    return get_settings().upload_dir / name
