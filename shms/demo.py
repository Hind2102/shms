"""Public demo mode (SHMS_DEMO_MODE=1): start-up checks and a fresh database on every start."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy.engine import make_url

from .settings import Settings

log = logging.getLogger("shms")

BANNER = "Public demo – do not upload confidential, personal or site photos; data resets on restart."


def check_config(settings: Settings) -> None:
    """A public demo must sign sessions with a configured key and must show the real AI, never the mock."""
    if not settings.secret_key:
        raise RuntimeError("Demo mode needs SHMS_SECRET_KEY (set it as a secret of the hosting service).")
    if settings.detector == "mock":
        raise RuntimeError("Demo mode must use a real detector (SHMS_DETECTOR=yolo), not the mock.")


def reset_data(settings: Settings, database_url: str) -> None:
    """Delete the SQLite database file, the uploaded photos and the mail outbox, so the app seeds fresh data."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(url.database + suffix).unlink(missing_ok=True)
    for folder in (settings.upload_dir, settings.mail_outbox):
        shutil.rmtree(folder, ignore_errors=True)
    log.warning("Demo mode: data reset – fresh synthesized data is seeded on this start")
