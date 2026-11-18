"""Authentication primitives (standard library only).

* Passwords: scrypt (n=2**14, r=8, p=1, 16-byte random salt), compared in constant time.
* Sessions: cookie "<user id>.<issued unix time>.<HMAC-SHA256>" signed with the app secret; valid for 12 hours.
* CSRF: double-submit token – a signed random value in a cookie that every HTML form must echo in a hidden field.
* API tokens: random 32-byte strings; only their SHA-256 is stored.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from functools import lru_cache

from .settings import get_settings

log = logging.getLogger("shms")

SESSION_COOKIE = "shms_session"
CSRF_COOKIE = "shms_csrf"
SESSION_SECONDS = 12 * 3600
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


@lru_cache(maxsize=4)
def _file_secret(folder) -> bytes:
    path = folder / "secret_key"
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_hex(32))
            path.chmod(0o600)
        return path.read_text().strip().encode()
    except OSError:
        log.warning("No SHMS_SECRET_KEY and %s is not writable: using a per-process key", path)
        return secrets.token_bytes(32)


def _secret() -> bytes:
    key = get_settings().secret_key
    return key.encode() if key else _file_secret(get_settings().instance_dir)


def _sign(message: str) -> str:
    mac = hmac.new(_secret(), message.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, n, r, p, salt, digest = stored.split("$")
    test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=32, n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(test.hex(), digest)


# ---------------------------------------------------------------- sessions


def sign_session(user_id: int, issued: int | None = None) -> str:
    issued = int(time.time()) if issued is None else issued
    body = f"{user_id}.{issued}"
    return f"{body}.{_sign('session:' + body)}"


def read_session(cookie: str | None) -> int | None:
    """The user id in a valid, unexpired session cookie, else None."""
    try:
        uid, issued, mac = (cookie or "").split(".")
        if not hmac.compare_digest(mac, _sign(f"session:{uid}.{issued}")):
            return None
        if time.time() - int(issued) > SESSION_SECONDS:
            return None
        return int(uid)
    except ValueError:
        return None


# ---------------------------------------------------------------- CSRF


def new_csrf_token() -> str:
    raw = secrets.token_urlsafe(24)
    return f"{raw}.{_sign('csrf:' + raw)}"


def csrf_valid(cookie: str | None, submitted: str | None) -> bool:
    if not cookie or not submitted or not hmac.compare_digest(cookie, submitted):
        return False
    raw, _, mac = cookie.partition(".")
    return hmac.compare_digest(mac, _sign("csrf:" + raw))


# ---------------------------------------------------------------- API tokens


def new_api_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
