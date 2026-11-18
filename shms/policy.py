"""Who may SEE what (server-side). Who may DO what is enforced by the state machine in services.py.

* Every page and API call needs a signed-in user.
* Confirmed hazards (any status after draft) are visible to every signed-in user: a site hazard board, so people
  can check an area before entering (user story US7).
* Drafts – unconfirmed observations – and their photos are visible only to their reporter and supervisors.
* Photos not attached to a hazard (from POST /api/detect) are visible to supervisors only.
"""

from __future__ import annotations

from .models import Hazard, Role, Status, User


def can_view(user: User, h: Hazard) -> bool:
    if h.status != Status.DRAFT:
        return True
    return user.id == h.reporter_id or user.role == Role.SUPERVISOR


def can_view_photo(user: User, owner: Hazard | None) -> bool:
    if owner is None:
        return user.role == Role.SUPERVISOR
    return can_view(user, owner)
