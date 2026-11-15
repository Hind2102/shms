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


def grouped() -> dict[str, list[Category]]:
    out: dict[str, list[Category]] = {}
    for c in categories().values():
        out.setdefault(c.group, []).append(c)
    return out
