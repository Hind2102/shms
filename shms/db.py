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


def create_all() -> None:
    from sqlalchemy import inspect

    from . import models  # noqa: F401  (register tables)

    assert _engine is not None, "call init_engine() first"
    Base.metadata.create_all(_engine)
    # An existing database file from an older version may lack new columns; say so clearly instead of
    # failing later with an obscure SQL error. (A production system would use migrations, e.g. Alembic.)
    insp = inspect(_engine)
    for table in Base.metadata.sorted_tables:
        have = {c["name"] for c in insp.get_columns(table.name)}
        missing = {c.name for c in table.columns} - have
        if missing:
            raise SchemaMismatch(
                f"The database {_engine.url} was created by an older SHMS version (table {table.name!r} lacks "
                f"{sorted(missing)}). It only holds demo data: delete the file (e.g. shms.db) and start again."
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
