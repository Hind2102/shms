"""Application factory. The ASGI entry point is ``shms.asgi:app``."""

from __future__ import annotations

import io
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import services
from .db import create_all, init_engine, new_session
from .seed import seed
from .settings import PACKAGE_DIR, get_settings
from .web import api, pages, telemetry

log = logging.getLogger("shms")


def _warm_up() -> None:
    """Load the configured detector and run it once on a blank image."""
    import tempfile

    from PIL import Image

    from .detection import get_detector

    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            buf = io.BytesIO()
            Image.new("RGB", (64, 64), "white").save(buf, "JPEG")
            f.write(buf.getvalue())
            f.flush()
            r = get_detector().detect(f.name)
        log.warning("AI detector %s ready (%s)", r.model, r.error or "ok")
    except Exception as exc:  # noqa: BLE001 - the app still works; reports show the AI error
        log.warning("AI detector failed to load: %s", exc)


def create_app(database_url: str | None = None, seed_demo: bool = True) -> FastAPI:
    settings = get_settings()
    init_engine(database_url or settings.database_url)
    create_all()
    if seed_demo:
        with new_session() as db:
            seed(db)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Load the AI model in the background at start-up so the first report is not slowed down.
        if settings.detector != "mock":
            threading.Thread(target=_warm_up, daemon=True).start()
        yield

    app = FastAPI(title="Site Hazard Management System (SHMS)", version="1.2.0", lifespan=lifespan)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    app.middleware("http")(telemetry.timing_middleware)
    app.include_router(api.router)
    app.include_router(telemetry.router)
    app.include_router(pages.router)

    @app.exception_handler(Exception)
    async def _unexpected(req: Request, exc: Exception):
        # Details go to the server log only; users never see a stack trace or internal message.
        log.error("Unhandled error on %s %s", req.method, req.url.path, exc_info=exc)
        if req.url.path.startswith("/api") or req.url.path == "/metrics":
            return JSONResponse({"detail": "Internal server error"}, status_code=500)
        return HTMLResponse(
            "<!doctype html><title>Error</title><h1>Something went wrong</h1>"
            "<p>The error has been logged. Please go back and try again; if it keeps happening, tell the safety "
            "supervisor.</p><p><a href='/'>Back to the dashboard</a></p>",
            status_code=500,
        )

    @app.exception_handler(pages.CsrfError)
    async def _csrf(_req: Request, _exc: Exception):
        return PlainTextResponse("Form expired or forged (missing CSRF token). Reload the page and try again.", 403)

    @app.exception_handler(pages.LoginRequired)
    async def _login(_req: Request, _exc: Exception):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(services.WorkflowError)
    async def _workflow(_req: Request, exc: Exception):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(services.PermissionDenied)
    async def _denied(_req: Request, exc: Exception):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    return app
