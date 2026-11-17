"""Database engine and session handling (SQLAlchemy 2.0, SQLite by default)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine(url: str) -> Engine:
    """(Re)create the engine; called once at app start-up and by tests."""
    global _engine, _SessionLocal
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(_engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce foreign keys in SQLite
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


class SchemaMismatch(RuntimeError):
    pass


def _alembic_config():
    from pathlib import Path

    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    return cfg


def head_revision() -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def schema_status(engine: Engine) -> str:
    """'empty' (no tables), 'current' (at the newest migration) or 'outdated' (anything else)."""
    from alembic.migration import MigrationContext
    from sqlalchemy import inspect

    tables = set(inspect(engine).get_table_names()) - {"alembic_version"}
    if not tables:
        return "empty"
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return "current" if current == head_revision() else "outdated"


def migrate_to_head(url: str) -> None:
    """Apply all migrations (same as `alembic upgrade head`) using a private engine, so the
    foreign-key switch that SQLite migrations need never leaks into the application's connections."""
    from alembic import command

    engine = create_engine(url)
    cfg = _alembic_config()
    try:
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
    finally:
        engine.dispose()


def create_all() -> None:
    """Create a new database at the newest migration, or check that an existing one is up to date."""
    from alembic.script import ScriptDirectory

    from . import models  # noqa: F401  (register tables)

    assert _engine is not None, "call init_engine() first"
    status = schema_status(_engine)
    if status == "empty":
        from alembic.migration import MigrationContext

        Base.metadata.create_all(_engine)
        with _engine.begin() as conn:  # record "at newest migration" without running migration scripts
            MigrationContext.configure(conn).stamp(ScriptDirectory.from_config(_alembic_config()), "head")
    elif status == "outdated":
        raise SchemaMismatch(
            f"The database {_engine.url} was created by an older SHMS version. Back up the file, then run "
            "`alembic upgrade head` (it migrates the database in SHMS_DATABASE_URL and keeps all data)."
        )


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    assert _SessionLocal is not None, "call init_engine() first"
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def new_session() -> Session:
    assert _SessionLocal is not None, "call init_engine() first"
    return _SessionLocal()
