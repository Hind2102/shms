"""Simple per-IP rate limit for submissions (public demo). Page views (GET/HEAD) are never limited.

The client IP is ``request.client.host``. Behind a reverse proxy, uvicorn must run with ``--proxy-headers`` so that
this is the visitor's address and not the proxy's. In-memory and per process: enough for a one-container demo."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

MESSAGE = "Too many requests from your connection. Wait a minute, then try again."
WINDOW_S = 60.0
MAX_TRACKED = 10_000  # bound memory: forget the oldest IPs beyond this


class RateLimiter:
    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def retry_after(self, ip: str) -> int:
        """0 if this request is allowed (and counts it), else the seconds until the next one is."""
        now = self.clock()
        with self._lock:
            hits = self._hits.pop(ip, deque())
            while hits and now - hits[0] >= WINDOW_S:
                hits.popleft()
            allowed = len(hits) < self.per_minute
            if allowed:
                hits.append(now)
            self._hits[ip] = hits  # re-insert: most recently seen IPs stay at the end
            while len(self._hits) > MAX_TRACKED:
                self._hits.pop(next(iter(self._hits)))
            return 0 if allowed else max(1, math.ceil(WINDOW_S - (now - hits[0])))


def middleware(limiter: RateLimiter, page: Callable[[str, str, int], HTMLResponse]):
    async def limit(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        wait = limiter.retry_after(request.client.host if request.client else "unknown")
        if not wait:
            return await call_next(request)
        headers = {"Retry-After": str(wait)}
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": MESSAGE}, status_code=429, headers=headers)
        resp = page("Too many requests", MESSAGE, 429)
        resp.headers.update(headers)
        return resp

    return limit
