"""Weather-style risk heat map over the site image (v1.7.0).

Every confirmed hazard that matches the filters contributes a weight:

    weight = risk score (1–25) × 2   if it is an open or planned High/Extreme hazard
                               × 1.5 more if it is past its target close date (overdue)
                               × 1   if it is closed and awaiting verification
                               × 0.25 if its closure was verified (history; only with status "closed" or "all")

A hazard with a map pin adds a smooth kernel (Gaussian, σ = 30 image px) at its pin; a hazard without a pin spreads
its weight evenly over its zone ("zone total"). The sum is the risk-weighted density. The colour scale is absolute:
pale yellow = low but recorded, yellow → orange → red = more, full red = at least the density at the pin of one open
Extreme hazard (risk score 25, weight 50). Zones with matching records are never left blank (pale yellow minimum);
zones with no matching records are hatched "no records – not a statement about conditions" by the page, never green.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import site_layout, taxonomy
from .models import Area, Hazard, Status, utcnow

HIGH_LEVELS = ("High", "Extreme")
WINDOWS = (0, 30, 90, 180, 365)  # 0 = any report date
STATUSES = {
    "active": "Active (open, planned, awaiting verification)",
    "overdue": "Overdue (open or planned, past target date)",
    "closed": "Closed (awaiting verification or verified)",
    "all": "All confirmed",
}
SCALE = 4  # one heat cell = 4 × 4 image pixels
SIGMA_PX = 30  # pin kernel width in image pixels
REF_WEIGHT = 50  # one open Extreme hazard: risk score 25 × 2
CLOSED_FACTOR = 0.25
FLOOR = 0.08  # minimum colour inside a zone that has matching records (pale yellow)
CALCULATION = (
    "Weight = risk score × 2 for open or planned High/Extreme hazards, × 1.5 more when overdue; × 1 when awaiting "
    "verification; × 0.25 when verified closed. Pinned hazards add a smooth kernel at the pin (σ 30 px); hazards "
    "without a pin spread evenly over their zone. Full red = the density at one open Extreme hazard's pin or more."
)


@dataclass(frozen=True)
class Filters:
    window_days: int = 0
    category: str = ""
    status: str = "active"

    @classmethod
    def parse(cls, window: str = "", category: str = "", status: str = "") -> Filters:
        days = next((d for d in WINDOWS if str(d) == window), 0)
        cat = category if category in taxonomy.categories() else ""
        return cls(days, cat, status if status in STATUSES else "active")

    def query(self) -> str:
        return f"window={self.window_days}&category={self.category}&status={self.status}"

    def describe(self) -> str:
        when = f"reported in the last {self.window_days} days" if self.window_days else "any report date"
        what = taxonomy.get(self.category).name if self.category else "all hazard types"
        return f"{STATUSES[self.status]}; {what}; {when}"


def is_overdue(h: Hazard, now: datetime) -> bool:
    return h.status in (Status.OPEN, Status.PLANNED) and h.due_at is not None and h.due_at < now


def weight(h: Hazard, now: datetime) -> float:
    base = float(h.risk_score or 0)
    if h.status in (Status.OPEN, Status.PLANNED):
        w = base * (2 if h.risk_level in HIGH_LEVELS else 1)
        return w * (1.5 if is_overdue(h, now) else 1)
    if h.status == Status.PENDING_VERIFICATION:
        return base
    if h.status == Status.CLOSED:
        return base * CLOSED_FACTOR
    return 0.0  # drafts are not confirmed reports


def matches(h: Hazard, f: Filters, now: datetime) -> bool:
    if h.status == Status.DRAFT or (f.category and h.category_code != f.category):
        return False
    if f.window_days and h.created_at < now - timedelta(days=f.window_days):
        return False
    return {
        "active": h.status in (Status.OPEN, Status.PLANNED, Status.PENDING_VERIFICATION),
        "overdue": is_overdue(h, now),
        "closed": h.status in (Status.PENDING_VERIFICATION, Status.CLOSED),
        "all": True,
    }[f.status]


@dataclass
class ZoneHeat:
    code: str
    name: str
    count: int = 0
    pinned: int = 0
    weight: float = 0.0
    top_level: str | None = None
    hazards: list[Hazard] = field(default_factory=list)


@dataclass
class Heat:
    filters: Filters
    zones: dict[str, ZoneHeat]
    hazards: list[Hazard]
    now: datetime

    @property
    def total_weight(self) -> float:
        return sum(z.weight for z in self.zones.values())

    @property
    def pinned(self) -> int:
        return sum(1 for h in self.hazards if h.x is not None)


LEVEL_RANK = {"Low": 1, "Moderate": 2, "High": 3, "Extreme": 4}


def compute(db: Session, f: Filters, now: datetime | None = None) -> Heat:
    now = now or utcnow()
    areas = {a.id: a for a in db.scalars(select(Area))}
    zones = {code: ZoneHeat(code, z.name) for code, z in site_layout.REPORTING.items()}
    for a in areas.values():  # display names come from the database (migrations may rename)
        if a.code in zones:
            zones[a.code].name = a.name
    hazards = [h for h in db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT)) if matches(h, f, now)]
    kept = []
    for h in hazards:
        z = zones.get(areas[h.area_id].code)
        if z is None:
            continue
        kept.append(h)
        z.count += 1
        z.pinned += h.x is not None
        z.weight += weight(h, now)
        z.hazards.append(h)
        if LEVEL_RANK.get(h.risk_level or "", 0) > LEVEL_RANK.get(z.top_level or "", 0):
            z.top_level = h.risk_level
    return Heat(f, zones, kept, now)


# ---------------------------------------------------------------- raster


def _grid() -> tuple[int, int]:
    return -(-site_layout.VIEW_H // SCALE), -(-site_layout.VIEW_W // SCALE)


@lru_cache(maxsize=1)
def zone_masks() -> dict[str, np.ndarray]:
    """One boolean mask per zone on the heat grid. Each cell belongs to at most one zone (a label raster), so a zone
    with records can never colour the edge cells of a neighbouring zone without records."""
    rows, cols = _grid()
    codes = list(site_layout.REPORTING)
    label = Image.new("L", (cols, rows), 0)
    draw = ImageDraw.Draw(label)
    for i, code in enumerate(codes, start=1):
        draw.polygon([(x / SCALE, y / SCALE) for x, y in site_layout.REPORTING[code].points], fill=i)
    lab = np.asarray(label)
    return {code: lab == i for i, code in enumerate(codes, start=1)}


def _gauss(sigma: float) -> np.ndarray:
    r = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    return k / k.sum()


def _blur(a: np.ndarray, sigma: float) -> np.ndarray:
    k = _gauss(sigma)
    a = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, a)
    return np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, a)


@lru_cache(maxsize=1)
def _reference_peak() -> float:
    """Density at the pin of a single hazard of weight REF_WEIGHT (the colour scale's full red)."""
    sigma = SIGMA_PX / SCALE
    k = _gauss(sigma)
    return float(REF_WEIGHT * k.max() * k.max())


def density(heat: Heat) -> np.ndarray:
    """Risk-weighted density on the heat grid, scaled so 1.0 = full red (values above 1 are clipped)."""
    rows, cols = _grid()
    impulses = np.zeros((rows, cols))
    spread = np.zeros((rows, cols))
    masks = zone_masks()
    for code, z in heat.zones.items():
        for h in z.hazards:
            w = weight(h, heat.now)
            if h.x is not None and h.y is not None:
                r, c = min(rows - 1, max(0, h.y // SCALE)), min(cols - 1, max(0, h.x // SCALE))
                impulses[r, c] += w
            else:
                m = masks[code]
                spread[m] += w / max(1, int(m.sum()))
    d = _blur(impulses + spread, SIGMA_PX / SCALE) / _reference_peak()
    union = np.zeros((rows, cols), dtype=bool)
    for code, z in heat.zones.items():
        if z.count:
            union |= masks[code]
            d[masks[code]] = np.maximum(d[masks[code]], FLOOR)
    d[~union] = 0.0  # colour only inside zones with matching records
    return np.clip(d, 0.0, 1.0)


# pale yellow → yellow → orange → red
STOPS = ((0.0, (255, 243, 176)), (0.35, (255, 210, 40)), (0.65, (250, 130, 20)), (1.0, (196, 18, 28)))


def colour(t: np.ndarray) -> np.ndarray:
    out = np.zeros((*t.shape, 3))
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:], strict=False):
        sel = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[sel][:, None]
        out[sel] = np.array(c0) * (1 - f) + np.array(c1) * f
    return out


def png(heat: Heat) -> bytes:
    d = density(heat)
    rgba = np.zeros((*d.shape, 4), dtype=np.uint8)
    rgba[..., :3] = colour(d).astype(np.uint8)
    rgba[..., 3] = np.where(d > 0, (110 + 120 * d).clip(0, 230), 0).astype(np.uint8)
    im = Image.fromarray(rgba, "RGBA").resize((site_layout.VIEW_W // 2, site_layout.VIEW_H // 2), Image.BILINEAR)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()
