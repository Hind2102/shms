"""Notifications: an in-app message per user, plus a TEST mail backend that writes each message as an .eml
file to a local outbox folder (SHMS_MAIL_OUTBOX, default ./outbox). Nothing is sent over the network."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from datetime import datetime
from email.message import EmailMessage

from sqlalchemy.orm import Session

from .models import Hazard, Notification, User, utcnow
from .settings import get_settings

SENDER = "SHMS <no-reply@shms.example>"
log = logging.getLogger("shms")


def _write_eml(user: User, subject: str, body: str, at: datetime) -> None:
    if not user.email:
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = SENDER, user.email, subject
    msg["Date"] = at.strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg.set_content(body)
    folder = get_settings().mail_outbox
    folder.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", f"{at:%Y%m%dT%H%M%S%f}-{user.id}-{subject}")[:120]
    (folder / f"{stem}.eml").write_text(msg.as_string())


_mail_enabled = True


@contextmanager
def no_mail():
    """Suppress outbox e-mails (in-app notifications are still created), e.g. while seeding synthetic history."""
    global _mail_enabled
    old, _mail_enabled = _mail_enabled, False
    try:
        yield
    finally:
        _mail_enabled = old


def send(
    db: Session, users: list[User], hazard: Hazard, subject: str, body: str = "", at: datetime | None = None
) -> None:
    """One in-app notification and one outbox e-mail per user (users without an address get only the former)."""
    at = at or utcnow()
    for u in users:
        db.add(Notification(user_id=u.id, hazard=hazard, message=subject, created_at=at))
        if not _mail_enabled:
            continue
        try:
            _write_eml(u, subject, body or subject, at)
        except OSError:  # a mail problem must never stop a hazard report or a workflow step
            log.exception("Could not write notification e-mail to the outbox")
