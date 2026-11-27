"""Application factory. The ASGI entry point is ``shms.asgi:app``."""

from __future__ import annotations

import io
import logging
import threading
from contextlib import asynccontextmanager
from html import escape

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import demo, services
from .db import create_all, init_engine, new_session
from .seed import seed
from .settings import PACKAGE_DIR, get_settings
from .web import api, pages, ratelimit, telemetry

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


def _banner() -> str:
    return f'<div class="demo-banner" role="note">{escape(demo.BANNER)}</div>' if get_settings().demo_mode else ""


def message_page(title: str, message: str, status: int) -> HTMLResponse:
    """Pages never show raw JSON: a plain-language message, readable on a phone, with a way back."""
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, '
        f'initial-scale=1"><title>{escape(title)}</title><link rel="stylesheet" href="/static/style.css">'
        f'{_banner()}<main id="main" class="container"><h1>{escape(title)}</h1><div class="alert err" role="alert">'
        f'{escape(message)}</div><p><a class="btn primary" href="javascript:history.back()">Go back</a> '
        '<a class="btn secondary" href="/">Home</a></p></main></html>',
        status_code=status,
    )


def create_app(database_url: str | None = None, seed_demo: bool = True) -> FastAPI:
    settings = get_settings()
    if settings.demo_mode:
        demo.check_config(settings)
        demo.check_not_project_data(settings, database_url or settings.database_url)
        demo.reset_data(settings, database_url or settings.database_url)
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

    app = FastAPI(title="Site Hazard Management System (SHMS)", version="1.3.0", lifespan=lifespan)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    app.middleware("http")(telemetry.timing_middleware)
    if settings.rate_limit_per_min > 0:
        app.middleware("http")(ratelimit.middleware(ratelimit.RateLimiter(settings.rate_limit_per_min), message_page))
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
            f"<!doctype html><title>Error</title>{_banner()}<h1>Something went wrong</h1>"
            "<p>The error has been logged. Please go back and try again; if it keeps happening, tell the safety "
            "supervisor.</p><p><a href='/'>Back to the dashboard</a></p>",
            status_code=500,
        )

    def _machine(req: Request) -> bool:
        return req.url.path.startswith("/api") or req.url.path == "/metrics"

    @app.exception_handler(StarletteHTTPException)
    async def _http(req: Request, exc: StarletteHTTPException):
        if _machine(req) or exc.status_code in (401, 405) or exc.headers:
            return await http_exception_handler(req, exc)
        titles = {404: "Not found", 403: "Not allowed", 413: "Photo too large", 422: "Cannot use this input"}
        return message_page(titles.get(exc.status_code, "Cannot complete this"), str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _invalid(req: Request, exc: RequestValidationError):
        if _machine(req):
            return await request_validation_exception_handler(req, exc)
        return message_page(
            "Form incomplete", "Some required information was missing or not valid. Go back and check the form.", 422
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
