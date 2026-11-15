"""Rule engine: turn PPE / body-part detections into image-level hazards.

SH17 labels *objects* (head, helmet, hands, gloves, person, safety-vest ...),
not *violations*. A hazard is therefore derived with explicit, testable rules:

* ``no_hard_hat``   - a visible head with no helmet on it
* ``no_gloves``     - a visible hand with no glove on it
* ``no_hi_vis_vest``- a visible person with no safety vest (or safety suit) on the torso

The same function is applied to (a) the YOLO model's detections and (b) the
SH17 ground-truth boxes, so model output and ground truth are compared on
exactly the same definition of "hazard".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import Box, Suggestion


@dataclass(frozen=True)
class RuleConfig:
    # A helmet "covers" a head when this share of the helmet lies inside the head box
    # after the head box is extended upwards by ``head_expand_up`` x its height.
    helmet_cover: float = 0.30
    head_expand_up: float = 0.5
    glove_cover: float = 0.30
    # The centre of the vest must fall inside the person box.
    vest_labels: tuple[str, ...] = ("safety-vest", "safety-suit")
    # Ignore people / heads / hands smaller than this share of the image (far background).
    min_person_area: float = 0.004
    min_head_area: float = 0.0004
    min_hand_area: float = 0.0002
    enabled: tuple[str, ...] = field(default=("no_hard_hat", "no_hi_vis_vest", "no_gloves"))


DEFAULT_RULES = RuleConfig()


def _intersection(a: Box, b: Box) -> float:
    w = min(a.x2, b.x2) - max(a.x1, b.x1)
    h = min(a.y2, b.y2) - max(a.y1, b.y1)
    return max(0.0, w) * max(0.0, h)


def _expand_up(b: Box, frac: float) -> Box:
    dy = (b.y2 - b.y1) * frac
    return Box(b.label, b.confidence, b.x1, max(0.0, b.y1 - dy), b.x2, b.y2)


def _covered(target: Box, covers: list[Box], min_share: float) -> bool:
    """True if any cover box has at least ``min_share`` of its own area inside target."""
    for c in covers:
        if c.area > 0 and _intersection(target, c) / c.area >= min_share:
            return True
        # Also accept the reverse: the target lies mostly inside the cover box.
        if target.area > 0 and _intersection(target, c) / target.area >= min_share:
            return True
    return False


def _norm(label: str) -> str:
    return label.lower().replace("_", "-").replace(" ", "-")


def hazards_from_boxes(boxes: list[Box], cfg: RuleConfig = DEFAULT_RULES) -> list[Suggestion]:
    by: dict[str, list[Box]] = {}
    for b in boxes:
        by.setdefault(_norm(b.label), []).append(b)
    heads, helmets = by.get("head", []), by.get("helmet", [])
    hands, gloves = by.get("hands", []) + by.get("hand", []), by.get("gloves", []) + by.get("glove", [])
    persons = by.get("person", [])
    vests = [b for lbl in cfg.vest_labels for b in by.get(lbl, [])]

    out: list[Suggestion] = []

    if "no_hard_hat" in cfg.enabled:
        bare = [
            h for h in heads
            if h.area >= cfg.min_head_area and not _covered(_expand_up(h, cfg.head_expand_up), helmets, cfg.helmet_cover)
        ]
        if bare:
            out.append(Suggestion("no_hard_hat", max(b.confidence for b in bare), bare,
                                  f"{len(bare)} head(s) detected without a hard hat"))

    if "no_gloves" in cfg.enabled:
        bare = [h for h in hands if h.area >= cfg.min_hand_area and not _covered(h, gloves, cfg.glove_cover)]
        if bare:
            out.append(Suggestion("no_gloves", max(b.confidence for b in bare), bare,
                                  f"{len(bare)} bare hand(s) detected"))

    if "no_hi_vis_vest" in cfg.enabled:
        bare = []
        for p in persons:
            if p.area < cfg.min_person_area:
                continue
            has_vest = any(p.x1 <= v.center[0] <= p.x2 and p.y1 <= v.center[1] <= p.y2 for v in vests)
            if not has_vest:
                bare.append(p)
        if bare:
            out.append(Suggestion("no_hi_vis_vest", max(b.confidence for b in bare), bare,
                                  f"{len(bare)} person(s) detected without a high-visibility vest"))

    return out
