"""API tokens and passwords from the command line.

python -m shms.tokens create <username> [--label ci]      # prints a new API token once
python -m shms.tokens set-password <username>              # prompts for a new password
"""

from __future__ import annotations

import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth
from .models import ApiToken, User, utcnow


def create(db: Session, user: User, label: str = "") -> str:
    """Create a token for this user; returns the token (only its hash is stored)."""
    token = auth.new_api_token()
    db.add(ApiToken(user_id=user.id, token_hash=auth.token_hash(token), label=label, created_at=utcnow()))
    db.flush()
    return token


def user_for(db: Session, token: str) -> User | None:
    row = db.scalar(select(ApiToken).where(ApiToken.token_hash == auth.token_hash(token)))
    if row is None:
        return None
    row.last_used_at = utcnow()
    return row.user


def main() -> None:
    from .db import create_all, init_engine, new_session
    from .settings import get_settings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("username")
    c.add_argument("--label", default="")
    s = sub.add_parser("set-password")
    s.add_argument("username")
    args = ap.parse_args()

    init_engine(get_settings().database_url)
    create_all()
    with new_session() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if user is None:
            raise SystemExit(f"No user {args.username!r}")
        if args.cmd == "create":
            print(create(db, user, args.label))
        else:
            pw = getpass.getpass("New password: ")
            if len(pw) < 8:
                raise SystemExit("Use at least 8 characters")
            user.password_hash = auth.hash_password(pw)
            print(f"Password set for {user.username}")
        db.commit()


if __name__ == "__main__":
    main()
