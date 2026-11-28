"""Area hazard profiles (project assumptions, ``config/area_profiles.json``): typical hazards and required PPE per
reporting zone. They describe the work in each area – not recorded reports – and are shown on the check-before-entering
card. The required PPE in the database (``Area.required_ppe``) is seeded from here and set by migration 0011."""

from __future__ import annotations

import json
from functools import lru_cache

from . import taxonomy
from .settings import PACKAGE_DIR


@lru_cache(maxsize=1)
def _all() -> dict[str, dict]:
    return json.loads((PACKAGE_DIR / "config" / "area_profiles.json").read_text())["areas"]


def get(code: str) -> dict:
    """The profile for an area code: typical_hazards (category codes), summary and required_ppe."""
    return _all()[code]


def typical_hazards(code: str) -> list[taxonomy.Category]:
    profile = _all().get(code)
    return [taxonomy.get(c) for c in profile["typical_hazards"]] if profile else []


def summary(code: str) -> str:
    profile = _all().get(code)
    return profile["summary"] if profile else ""
