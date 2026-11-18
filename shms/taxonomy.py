"""Hazard category list (loaded from ``config/taxonomy.json``)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from .settings import PACKAGE_DIR


@dataclass(frozen=True)
class Category:
    code: str
    name: str
    group: str
    ai: bool
    default_consequence: int
    why: str = ""
    ppe: str = ""
    # EXPERIMENTAL categories (unsafe conditions) are never AI-released and only exist when
    # SHMS_EXPERIMENTAL_CONDITIONS=1 (see docs/unsafe_conditions_plan.md).
    experimental: bool = False


@lru_cache(maxsize=1)
def categories() -> dict[str, Category]:
    data = json.loads((PACKAGE_DIR / "config" / "taxonomy.json").read_text())
    return {c["code"]: Category(**c) for c in data["categories"]}


def get(code: str) -> Category:
    try:
        return categories()[code]
    except KeyError as exc:
        raise ValueError(f"Unknown hazard category: {code!r}") from exc


def ai_codes() -> list[str]:
    """Categories the AI is allowed to suggest (the evaluated subset)."""
    return [c.code for c in categories().values() if c.ai]


def release() -> dict | None:
    """The release-gate decision (written by `python -m evaluation.release_gate`), or None if absent."""
    from .settings import get_settings

    path = get_settings().ai_release_file
    return json.loads(path.read_text()) if path.is_file() else None


def enabled_codes() -> list[str]:
    """Hazard types the app may use: AI categories that passed the release gate on held-out data.
    Without a release file every AI category is enabled (development and tests)."""
    r = release()
    approved = set(r["approved"]) if r else set(ai_codes())
    return [c for c in ai_codes() if c in approved]


def grouped() -> dict[str, list[Category]]:
    out: dict[str, list[Category]] = {}
    for c in categories().values():
        out.setdefault(c.group, []).append(c)
    return out


def experimental_codes() -> list[str]:
    """Experimental hazard types, available only when the feature flag is on."""
    from .settings import get_settings

    if not get_settings().experimental_conditions:
        return []
    return [c.code for c in categories().values() if c.experimental]
