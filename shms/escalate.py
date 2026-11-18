"""Overdue escalation (project rule, not a regulation):

* level 1 – an OPEN or PLANNED hazard is past its target close date (from the risk band): notify supervisors;
* level 2 – still not closed 7 days after that date: notify managers.

Each level is raised once. Run from a scheduler (e.g. cron every 15 minutes):

    python -m shms.escalate

The web app also calls `maybe_run` on page loads, at most once per minute, so a demo without a scheduler still
escalates.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import notify, services
from .models import Hazard, Role, User, utcnow

SECOND_LEVEL_AFTER = timedelta(days=7)
THROTTLE = timedelta(seconds=60)
_last_run: datetime | None = None


def _system_actor(db: Session) -> User:
    # Escalations are recorded in the audit trail under the first supervisor (the app has no system user).
    return db.scalar(select(User).where(User.role == Role.SUPERVISOR).order_by(User.id))


def run(db: Session, now: datetime | None = None) -> list[tuple[int, int]]:
    """Raise escalation levels that are due; returns (hazard id, new level) for each change."""
    now = now or utcnow()
    actor = _system_actor(db)
    changed: list[tuple[int, int]] = []
    q = select(Hazard).where(Hazard.status.in_(services.AWAITING_ACTION), Hazard.due_at < now)
    for h in db.scalars(q):
        target = 2 if now >= h.due_at + SECOND_LEVEL_AFTER else 1
        if target <= (h.escalation_level or 0):
            continue
        role = Role.MANAGER if target == 2 else Role.SUPERVISOR
        recipients = list(db.scalars(select(User).where(User.role == role)))
        days = (now - h.due_at).days
        subject = f"Overdue hazard #{h.id} ({h.risk_level}) in {h.area.name} – escalation level {target}"
        body = (
            f"Hazard #{h.id} ({h.category_code}, risk {h.risk_score} {h.risk_level}) in {h.area.name} was due "
            f"{h.due_at:%Y-%m-%d %H:%M} UTC and is {days} day(s) overdue. Status: {h.status.value}."
        )
        notify.send(db, recipients, h, subject, body, at=now)
        h.escalation_level = target
        if actor is not None:
            services._event(
                db, h, actor, "escalated", f"Level {target}: notified {', '.join(u.name for u in recipients)}", at=now
            )
        changed.append((h.id, target))
    db.flush()
    return changed


def reset_throttle() -> None:
    global _last_run
    _last_run = None


def maybe_run(db: Session, now: datetime | None = None) -> None:
    """Called on page loads: runs the escalation check at most once per minute."""
    global _last_run
    now = now or utcnow()
    if _last_run is not None and now - _last_run < THROTTLE:
        return
    _last_run = now
    run(db, now=now)


def main() -> None:
    from .db import create_all, init_engine, new_session
    from .settings import get_settings

    init_engine(get_settings().database_url)
    create_all()
    with new_session() as db:
        changed = run(db)
        db.commit()
    print(f"{len(changed)} escalation(s): {changed}")


if __name__ == "__main__":
    main()
