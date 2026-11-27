"""Site analysis (v1.7.0): area × hazard-type matrix, top open High/Extreme, overdue by area, monthly trend per area,
most common hazard per area, and CSV export. Every block carries the sentence that states its calculation."""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import heatmap, taxonomy
from .models import Area, Hazard, Status, utcnow

WINDOWS = (30, 90, 180, 365, 0)
TREND_MONTHS = 6
ACTIVE = (Status.OPEN, Status.PLANNED, Status.PENDING_VERIFICATION)

BASIS = {
    "matrix": "Confirmed reports (drafts excluded) per area and hazard type in the selected window and status; risk "
    "= sum of their risk scores (consequence × likelihood).",
    "top": "Active hazards (open, planned or awaiting verification) rated High or Extreme, any report date, highest risk "
    "score first.",
    "overdue": "Open or planned hazards past their target close date, any report date, per area; the oldest is the "
    "longest time past its target.",
    "trend": "Confirmed reports per calendar month for the last six months (current month to date), per area, any "
    "status.",
    "common": "Hazard type with the most confirmed reports per area in the selected window and status (ties: "
    "alphabetical).",
}


@dataclass
class Analysis:
    filters: heatmap.Filters
    areas: list[Area]
    categories: list[str]
    matrix: dict[tuple[str, str], dict]
    area_totals: dict[str, dict]
    top: list[Hazard]
    overdue: dict[str, dict]
    months: list[str]
    trend: dict[str, list[int]]
    common: dict[str, tuple[str, int] | None]
    total: int
    now: datetime


def _months(now: datetime) -> list[tuple[int, int]]:
    y, m = now.year, now.month
    out = []
    for _ in range(TREND_MONTHS):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def compute(db: Session, f: heatmap.Filters, now: datetime | None = None) -> Analysis:
    now = now or utcnow()
    areas = list(db.scalars(select(Area).order_by(Area.name)))
    by_id = {a.id: a for a in areas}
    confirmed = [h for h in db.scalars(select(Hazard).where(Hazard.status != Status.DRAFT))]
    pool = [h for h in confirmed if heatmap.matches(h, f, now)]

    matrix: dict[tuple[str, str], dict] = defaultdict(lambda: {"count": 0, "risk": 0, "active": 0})
    totals: dict[str, dict] = {a.code: {"count": 0, "risk": 0} for a in areas}
    for h in pool:
        code = by_id[h.area_id].code
        cell = matrix[(code, h.category_code)]
        cell["count"] += 1
        cell["risk"] += h.risk_score or 0
        cell["active"] += h.status in ACTIVE
        totals[code]["count"] += 1
        totals[code]["risk"] += h.risk_score or 0
    used = {c for _, c in matrix}
    categories = [c for c in taxonomy.categories() if c in used]

    top = sorted(
        (h for h in confirmed if h.status in ACTIVE and h.risk_level in heatmap.HIGH_LEVELS),
        key=lambda h: (-(h.risk_score or 0), h.created_at),
    )[:15]

    overdue: dict[str, dict] = {}
    for h in confirmed:
        if heatmap.is_overdue(h, now):
            code = by_id[h.area_id].code
            row = overdue.setdefault(code, {"count": 0, "oldest_days": 0, "high": 0})
            row["count"] += 1
            row["high"] += h.risk_level in heatmap.HIGH_LEVELS
            row["oldest_days"] = max(row["oldest_days"], (now - h.due_at).days)

    months = _months(now)
    trend = {a.code: [0] * TREND_MONTHS for a in areas}
    for h in confirmed:
        key = (h.created_at.year, h.created_at.month)
        if key in months:
            trend[by_id[h.area_id].code][months.index(key)] += 1

    common: dict[str, tuple[str, int] | None] = {}
    for a in areas:
        counts = Counter(h.category_code for h in pool if h.area_id == a.id)
        common[a.code] = min(counts.items(), key=lambda kv: (-kv[1], kv[0])) if counts else None

    labels = [datetime(y, m, 1).strftime("%b %Y") for y, m in months]
    return Analysis(f, areas, categories, dict(matrix), totals, top, overdue, labels, trend, common, len(pool), now)


def csv_text(a: Analysis) -> str:
    """One row per area × hazard type with records, plus the area's overdue count and most common type."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# " + a.filters.describe() + " · generated " + a.now.strftime("%Y-%m-%d %H:%M") + " UTC"])
    w.writerow(["area_code", "area", "hazard_code", "hazard", "reports", "risk_sum", "active", "area_overdue"])
    for area in a.areas:
        for cat in a.categories:
            cell = a.matrix.get((area.code, cat))
            if cell:
                w.writerow(
                    [
                        area.code,
                        area.name,
                        cat,
                        taxonomy.get(cat).name,
                        cell["count"],
                        cell["risk"],
                        cell["active"],
                        a.overdue.get(area.code, {}).get("count", 0),
                    ]
                )
    return buf.getvalue()


def heat_class(value: int, peak: int) -> str:
    """Matrix cell shading class (0 = none … 4 = highest), relative to the highest cell in this view."""
    if not value or not peak:
        return "h0"
    return f"h{min(4, 1 + int(3 * value / peak))}"
