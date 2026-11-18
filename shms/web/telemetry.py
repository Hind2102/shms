"""Request telemetry and a Prometheus-format /metrics endpoint (microservices lab: "measure, don't assume").

Kept dependency-free: counters live in memory per process; AI and workflow figures are read from the
database at scrape time, so they survive restarts.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..db import get_session
from ..models import Hazard

router = APIRouter(include_in_schema=False)
_lock = threading.Lock()
_count: dict[tuple[str, str, int], int] = defaultdict(int)
_seconds: dict[tuple[str, str, int], float] = defaultdict(float)


async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")
    if path != "unmatched" and not path.startswith(("/static", "/uploads", "/metrics")):
        key = (request.method, path, response.status_code)
        with _lock:
            _count[key] += 1
            _seconds[key] += time.perf_counter() - start
    return response


def snapshot() -> list[dict]:
    with _lock:
        return [
            {"method": m, "path": p, "status": s, "count": c, "seconds": _seconds[(m, p, s)]}
            for (m, p, s), c in sorted(_count.items())
        ]


def reset() -> None:
    with _lock:
        _count.clear()
        _seconds.clear()


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_session)) -> str:
    lines = [
        "# HELP shms_http_requests_total HTTP requests by route and status",
        "# TYPE shms_http_requests_total counter",
    ]
    rows = snapshot()
    for r in rows:
        lines.append(
            f'shms_http_requests_total{{method="{r["method"]}",path="{r["path"]}",status="{r["status"]}"}} {r["count"]}'
        )
    lines += [
        "# HELP shms_http_request_seconds_sum Total time spent handling requests",
        "# TYPE shms_http_request_seconds_sum counter",
    ]
    for r in rows:
        lines.append(
            f'shms_http_request_seconds_sum{{method="{r["method"]}",path="{r["path"]}",status="{r["status"]}"}} {r["seconds"]:.6f}'
        )
    lines += ["# HELP shms_hazards Hazards by status", "# TYPE shms_hazards gauge"]
    for status, n in db.execute(select(Hazard.status, func.count()).group_by(Hazard.status)):
        lines.append(f'shms_hazards{{status="{status.value}"}} {n}')
    open_high = db.scalar(
        select(func.count()).where(Hazard.status.in_(services.ACTIVE), Hazard.risk_level.in_(["High", "Extreme"]))
    )
    lines += ["# TYPE shms_hazards_open_high gauge", f"shms_hazards_open_high {open_high}"]
    m = services.ai_monitoring(db)
    lines += [
        "# HELP shms_ai_reports AI-analysed reports in the monitoring window",
        "# TYPE shms_ai_reports gauge",
        f"shms_ai_reports {m['reports']}",
        "# TYPE shms_ai_errors gauge",
        f"shms_ai_errors {m['errors']}",
    ]
    if m["acceptance"] is not None:
        lines += [
            "# HELP shms_ai_acceptance_ratio Share of AI suggestions the reporter kept",
            "# TYPE shms_ai_acceptance_ratio gauge",
            f"shms_ai_acceptance_ratio {m['acceptance']:.4f}",
        ]
    for q in ("p50_ms", "p95_ms"):
        if m["latency"][q] is not None:
            lines.append(f'shms_ai_latency_seconds{{quantile="0.{q[1:3]}"}} {m["latency"][q] / 1000:.4f}')
    return "\n".join(lines) + "\n"
