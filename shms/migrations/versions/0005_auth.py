"""Sign-in: username and password hash on users; per-user API tokens (hashed).

Existing users get a username derived from the first word of their name (lower case, made unique with the id if
needed) and NO password: they cannot sign in until one is set with `python -m shms.tokens set-password <username>`.

Revision ID: 0005_auth
Revises: 0004_escalation
Create Date: 2026-11-18
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "0005_auth"
down_revision = "0004_escalation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("username", sa.String(50), nullable=True))
        b.add_column(sa.Column("password_hash", sa.String(200), nullable=True))
    conn = op.get_bind()
    taken: set[str] = set()
    for uid, name in conn.execute(sa.text("SELECT id, name FROM users ORDER BY id")).all():
        base = re.sub(r"[^a-z0-9]", "", (name or "").split(" ")[0].lower()) or "user"
        username = base if base not in taken else f"{base}{uid}"
        taken.add(username)
        conn.execute(sa.text("UPDATE users SET username = :u WHERE id = :i"), {"u": username, "i": uid})
    with op.batch_alter_table("users") as b:
        b.create_unique_constraint("uq_users_username", ["username"])
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("api_tokens")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_username", type_="unique")
        b.drop_column("password_hash")
        b.drop_column("username")
