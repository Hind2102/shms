"""Alembic migrations: an old database is upgraded without losing rows or relationships."""

import sqlite3

import pytest
import sqlalchemy as sa

from shms import db as dbmod

# Schema of the original release (commit de90451), as stored in backups/shms_2026-11-17.db.
OLD_DDL = """
CREATE TABLE users (id INTEGER NOT NULL, name VARCHAR(100) NOT NULL, role VARCHAR(10) NOT NULL, PRIMARY KEY (id));
CREATE TABLE areas (id INTEGER NOT NULL, code VARCHAR(20) NOT NULL, name VARCHAR(100) NOT NULL,
  owner_id INTEGER NOT NULL, required_ppe TEXT NOT NULL, ai_checks TEXT NOT NULL, x INTEGER NOT NULL,
  y INTEGER NOT NULL, w INTEGER NOT NULL, h INTEGER NOT NULL, PRIMARY KEY (id), UNIQUE (code),
  FOREIGN KEY(owner_id) REFERENCES users (id));
CREATE TABLE hazards (id INTEGER NOT NULL, area_id INTEGER NOT NULL, reporter_id INTEGER NOT NULL,
  status VARCHAR(6) NOT NULL, created_at DATETIME NOT NULL, confirmed_at DATETIME, photo_path VARCHAR(300),
  description TEXT NOT NULL, ai_model VARCHAR(100), ai_suggestions TEXT NOT NULL, ai_top_code VARCHAR(40),
  ai_latency_ms FLOAT, ai_error TEXT, ai_accepted BOOLEAN, category_code VARCHAR(40), consequence INTEGER,
  likelihood INTEGER, risk_score INTEGER, risk_level VARCHAR(20), due_at DATETIME, assignee_id INTEGER,
  planned_action TEXT, closed_at DATETIME, closed_by_id INTEGER, closure_action TEXT,
  closure_photo_path VARCHAR(300), closed_on_spot BOOLEAN NOT NULL, PRIMARY KEY (id),
  FOREIGN KEY(area_id) REFERENCES areas (id), FOREIGN KEY(reporter_id) REFERENCES users (id),
  FOREIGN KEY(assignee_id) REFERENCES users (id), FOREIGN KEY(closed_by_id) REFERENCES users (id));
CREATE TABLE hazard_events (id INTEGER NOT NULL, hazard_id INTEGER NOT NULL, actor_id INTEGER NOT NULL,
  kind VARCHAR(30) NOT NULL, note TEXT NOT NULL, at DATETIME NOT NULL, PRIMARY KEY (id),
  FOREIGN KEY(hazard_id) REFERENCES hazards (id), FOREIGN KEY(actor_id) REFERENCES users (id));
CREATE TABLE notifications (id INTEGER NOT NULL, user_id INTEGER NOT NULL, hazard_id INTEGER NOT NULL,
  message TEXT NOT NULL, read BOOLEAN NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY (id),
  FOREIGN KEY(user_id) REFERENCES users (id), FOREIGN KEY(hazard_id) REFERENCES hazards (id));
"""

OLD_ROWS = """
INSERT INTO users VALUES (1,'Rep','REPORTER'),(2,'Owner','AREA_OWNER'),(3,'Sup','SUPERVISOR');
INSERT INTO areas VALUES (1,'DIG','Digestion',2,'Hard hat','no_hard_hat',0,0,10,10);
INSERT INTO hazards (id,area_id,reporter_id,status,created_at,description,ai_suggestions,category_code,
  consequence,likelihood,risk_score,risk_level,assignee_id,closed_on_spot)
  VALUES (1,1,1,'OPEN','2026-11-01 08:00:00','','[]','no_hard_hat',3,2,6,'Medium',2,0);
INSERT INTO hazards (id,area_id,reporter_id,status,created_at,description,ai_suggestions,category_code,
  consequence,likelihood,risk_score,risk_level,assignee_id,closed_at,closed_by_id,closure_action,closed_on_spot)
  VALUES (2,1,1,'CLOSED','2026-11-02 08:00:00','','[]','no_gloves',2,1,2,'Low',2,'2026-11-03 08:00:00',2,'Gloves issued',0);
INSERT INTO hazard_events VALUES (1,1,1,'confirmed','x','2026-11-01 08:00:00'),(2,2,2,'closed','y','2026-11-03 08:00:00');
INSERT INTO notifications VALUES (1,3,1,'High risk',0,'2026-11-01 08:00:00');
"""

TABLES = ("users", "areas", "hazards", "hazard_events", "notifications")
# Migration 0008 adds one audit event per re-scored hazard by design; every row that existed before is kept.
NOT_RESCORE = "kind != 'risk_rescored'"
# Migration 0009 adds the six new zones of the approved concept map by design; every area that existed is kept.
NOT_NEW_ZONE = "code NOT IN ('EVP','HYD','ALS','LIM','WKS','WTR')"


def _old_db(path) -> str:
    con = sqlite3.connect(path)
    con.executescript(OLD_DDL + OLD_ROWS)
    con.commit()
    con.close()
    return f"sqlite:///{path}"


def _snapshot(url: str) -> dict:
    eng = sa.create_engine(url)
    with eng.connect() as c:
        counts = {
            t: c.execute(
                sa.text(
                    f"SELECT count(*) FROM {t}"
                    + {"hazard_events": f" WHERE {NOT_RESCORE}", "areas": f" WHERE {NOT_NEW_ZONE}"}.get(t, "")
                )
            ).scalar()
            for t in TABLES
        }
        joins = c.execute(
            sa.text(
                "SELECT h.id, h.status, a.code, u.name, h.closure_action, count(e.id) FROM hazards h "
                "JOIN areas a ON a.id = h.area_id JOIN users u ON u.id = h.reporter_id "
                f"LEFT JOIN hazard_events e ON e.hazard_id = h.id AND e.{NOT_RESCORE} GROUP BY h.id ORDER BY h.id"
            )
        ).all()
    eng.dispose()
    return {"counts": counts, "joins": [tuple(r) for r in joins]}


def test_upgrade_old_schema_preserves_rows_and_relationships(tmp_path):
    url = _old_db(tmp_path / "old.db")
    before = _snapshot(url)
    dbmod.migrate_to_head(url)
    after = _snapshot(url)
    assert after == before
    eng = sa.create_engine(url)
    cols = {c["name"] for c in sa.inspect(eng).get_columns("hazards")}
    assert "idem_key" in cols
    assert dbmod.schema_status(eng) == "current"
    eng.dispose()


def test_outdated_database_tells_user_to_run_alembic(tmp_path):
    url = _old_db(tmp_path / "old.db")
    dbmod.init_engine(url)
    with pytest.raises(dbmod.SchemaMismatch, match="alembic upgrade head"):
        dbmod.create_all()


def test_new_database_is_created_at_head(tmp_path):
    dbmod.init_engine(f"sqlite:///{tmp_path / 'new.db'}")
    dbmod.create_all()
    assert dbmod.schema_status(dbmod._engine) == "current"


def test_migrations_produce_the_same_schema_as_the_models(tmp_path):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    dbmod.migrate_to_head(url)
    eng = sa.create_engine(url)
    with eng.connect() as c:
        diffs = compare_metadata(MigrationContext.configure(c), dbmod.Base.metadata)
    eng.dispose()
    assert diffs == []
