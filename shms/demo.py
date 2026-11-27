"""Public demo mode (SHMS_DEMO_MODE=1): start-up checks and a fresh database on every start."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy.engine import make_url

from .settings import PROJECT_DIR, Settings

log = logging.getLogger("shms")

BANNER = "Public demo – do not upload confidential, personal or site photos; data resets on restart."


def check_config(settings: Settings) -> None:
    """A public demo must sign sessions with a configured key and must show the real AI, never the mock."""
    if not settings.secret_key:
        raise RuntimeError("Demo mode needs SHMS_SECRET_KEY (set it as a secret of the hosting service).")
    if settings.detector == "mock":
        raise RuntimeError("Demo mode must use a real detector (SHMS_DETECTOR=yolo), not the mock.")


def check_not_project_data(settings: Settings, database_url: str) -> None:
    """Demo mode wipes its database and photos on every start, so it must never point at the project's own."""
    url = make_url(database_url)
    db = Path(url.database).resolve() if url.get_backend_name() == "sqlite" and url.database else None
    if (
        db == (PROJECT_DIR / "shms.db").resolve()
        or settings.upload_dir.resolve() == (PROJECT_DIR / "uploads").resolve()
        or settings.mail_outbox.resolve() == (PROJECT_DIR / "outbox").resolve()
    ):
        raise RuntimeError(
            "Demo mode deletes its data on every start. Point SHMS_DATABASE_URL, SHMS_UPLOAD_DIR and "
            "SHMS_MAIL_OUTBOX at demo-only locations (e.g. under demo/), not shms.db, uploads/ or outbox/."
        )


def reset_data(settings: Settings, database_url: str) -> None:
    """Delete the SQLite database file, the uploaded photos and the mail outbox, so the app seeds fresh data."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(url.database + suffix).unlink(missing_ok=True)
    for folder in (settings.upload_dir, settings.mail_outbox):
        shutil.rmtree(folder, ignore_errors=True)
    log.warning("Demo mode: data reset – fresh synthesized data is seeded on this start")
