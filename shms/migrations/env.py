"""Alembic environment.

The URL is taken from the SHMS settings (SHMS_DATABASE_URL or .env) unless a connection is passed in by
`shms.db.migrate_to_head` (used for in-memory test databases). Foreign keys are switched off during
migrations because SQLite rebuilds tables for most ALTER operations ("batch mode").
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, text

from shms import models  # noqa: F401  (register tables on Base.metadata)
from shms.db import Base

target_metadata = Base.metadata


def _run(connection) -> None:
    if connection.dialect.name == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=OFF"))
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
    if connection.dialect.name == "sqlite":
        connection.execute(text("PRAGMA foreign_keys=ON"))


connection = context.config.attributes.get("connection")
if connection is not None:
    _run(connection)
else:
    from shms.settings import get_settings

    engine = create_engine(context.config.get_main_option("sqlalchemy.url") or get_settings().database_url)
    with engine.connect() as conn:
        _run(conn)
        conn.commit()
