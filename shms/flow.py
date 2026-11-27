"""Hazard process flow (v1.7.0): the lifecycle stages, where a hazard is now, who did what and when, and who acts next.

Main path:  Reported → Confirmed & risk-scored → Assigned to Area Owner → Action planned
            → Closed, awaiting verification → Verified closed
Side paths: Fixed on the spot (confirm goes straight to verification), Rejected (closure sent back to open),
            Reopened (verified closure reopened), Escalated (overdue: supervisors, then managers notified).

Every status maps to exactly one highlighted stage. "Confirmed & risk-scored" is never current: confirming routes the
hazard in the same step. Stages before the current one are done (with who/when from the audit trail) or skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .models import Hazard, HazardEvent, Status, utcnow


@dataclass(frozen=True)
class StageDef:
    key: str
    label: str
    what: str
    event: str  # audit-event kind that completes this stage


STAGES: tuple[StageDef, ...] = (
    StageDef("reported", "Reported", "Photo uploaded; the AI suggests missing PPE.", "reported"),
    StageDef("confirmed", "Confirmed & risk-scored", "The reporter confirms the type and consequence.", "confirmed"),
    StageDef("assigned", "Assigned to Area Owner", "Routed to the owner of the area.", "assigned"),
    StageDef("planned", "Action planned", "Corrective action, action owner and deadline set.", "planned"),
    StageDef(
        "pending", "Closed, awaiting verification", "Closure documented with control and residual risk.", "closed"
    ),
    StageDef("verified", "Verified closed", "Someone other than the closer checked it.", "verified"),
)
CURRENT: dict[Status, str] = {
    Status.DRAFT: "reported",
    Status.OPEN: "assigned",
    Status.PLANNED: "planned",
    Status.PENDING_VERIFICATION: "pending",
    Status.CLOSED: "verified",
}
SIDE_PATHS = (
    ("fixed", "Fixed on the spot", "The reporter fixed it while reporting: it goes straight to verification."),
    ("rejected", "Rejected", "The verifier sends the closure back: the hazard is open again with the Area Owner."),
    ("reopened", "Reopened", "A verified closure turned out not to hold: back to open, with a new target date."),
    ("escalated", "Escalated (overdue)", "Past its target date: supervisors, then managers, are notified."),
)


@dataclass
class Stage:
    key: str
    label: str
    what: str
    state: str  # done | current | todo | skipped
    who: str | None = None
    when: datetime | None = None


@dataclass
class Flow:
    stages: list[Stage]
    current: Stage
    index: int  # 1-based position of the current stage
    next_action: str
    next_owner: str | None
    side: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.stages)


def _last(events: list[HazardEvent], kind: str) -> HazardEvent | None:
    found = [e for e in events if e.kind == kind]
    return found[-1] if found else None


def next_step(h: Hazard) -> tuple[str, str | None]:
    """What has to happen next, and who owns it."""
    if h.status == Status.DRAFT:
        return "Reporter confirms the hazard type and consequence.", h.reporter.name if h.reporter else None
    if h.status == Status.OPEN:
        owner = h.assignee or h.area.owner
        return "Area Owner plans the corrective action, or closes it if already fixed.", owner.name if owner else None
    if h.status == Status.PLANNED:
        owner = h.action_owner or h.assignee or h.area.owner
        due = f" by {h.action_due_at:%d %b %Y}" if h.action_due_at else ""
        return f"Action owner carries out the action and closes it{due}.", owner.name if owner else None
    if h.status == Status.PENDING_VERIFICATION:
        closer = h.closed_by.name if h.closed_by else "the closer"
        return (
            f"Safety supervisor or the reporter verifies the closure (not {closer}).",
            "Safety supervisor or reporter",
        )
    return "None – closed and verified. A supervisor or the reporter can reopen it.", None


def build(h: Hazard, now: datetime | None = None) -> Flow:
    now = now or utcnow()
    events = list(h.events)
    current_key = CURRENT[h.status]
    cur_i = next(i for i, s in enumerate(STAGES) if s.key == current_key)
    stages = []
    for i, d in enumerate(STAGES):
        ev = _last(events, d.event)
        if i < cur_i:
            state = "done" if ev else "skipped"
        elif i == cur_i:
            state = "current"
        else:
            state = "todo"
        if h.closed_on_spot and d.key in ("assigned", "planned") and i < cur_i:
            state = "skipped"
        show = ev if state in ("done", "current") else None
        stages.append(
            Stage(
                d.key,
                d.label,
                d.what,
                state,
                who=show.actor.name if show and show.actor else None,
                when=show.at if show else None,
            )
        )
    side = []
    if h.closed_on_spot:
        side.append({"key": "fixed", "label": "Fixed on the spot", "count": 1, "when": h.confirmed_at})
    for key, label in (("rejected", "Rejected"), ("reopened", "Reopened"), ("escalated", "Escalated")):
        found = [e for e in events if e.kind == key]
        if found:
            side.append({"key": key, "label": label, "count": len(found), "when": found[-1].at})
    if h.status in (Status.OPEN, Status.PLANNED) and h.due_at and h.due_at < now:
        side.append({"key": "overdue", "label": "Overdue", "count": 1, "when": h.due_at})
    action, owner = next_step(h)
    return Flow(stages, stages[cur_i], cur_i + 1, action, owner, side)


def chip(h: Hazard, now: datetime | None = None) -> dict:
    """Compact progress for lists and queues (no audit-trail query): stage n of 6, its label, and flags."""
    now = now or utcnow()
    i = next(i for i, s in enumerate(STAGES) if s.key == CURRENT[h.status])
    flags = []
    if h.status in (Status.OPEN, Status.PLANNED) and h.due_at and h.due_at < now:
        flags.append("overdue")
    if (h.escalation_level or 0) > 0:
        flags.append("escalated")
    if h.closed_on_spot:
        flags.append("fixed on the spot")
    return {"n": i + 1, "total": len(STAGES), "label": STAGES[i].label, "key": STAGES[i].key, "flags": flags}
