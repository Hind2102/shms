"""Risk scoring on the 5x5 consequence x likelihood matrix of the ADOSH-SF Technical Guideline
"Process of Risk Management" v4.0 (Tables 1-3).

Pure functions only (no database access) so every cell of the matrix can be
unit-tested. Level definitions and bands live in ``config/risk_matrix.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from .settings import PACKAGE_DIR

LEVELS = (1, 2, 3, 4, 5)
# Shown wherever SHMS displays a likelihood (v1.4.1). Keep the 365 in step with lookback_days (tested).
LIKELIHOOD_NOTE = (
    "ADOSH-SF likelihood describes how likely harm is; SHMS estimates it from how often similar hazards were "
    "reported in the same area in the last 365 days – a project heuristic, not the guideline's definition."
)


@dataclass(frozen=True)
class Band:
    level: str
    min: int
    max: int
    action: str
    color: str
    target_days: int  # project-defined: the guideline sets no time frames
    guideline_range: str = ""  # the range as printed in Table 3 (min/max also cover non-product scores)


@dataclass(frozen=True)
class RiskResult:
    consequence: int
    likelihood: int
    score: int
    level: str
    color: str
    action: str
    target_days: int


@lru_cache(maxsize=1)
def matrix_config() -> dict:
    return json.loads((PACKAGE_DIR / "config" / "risk_matrix.json").read_text())


def bands() -> list[Band]:
    return [Band(**b) for b in matrix_config()["bands"]]


def lookback_days() -> int:
    return int(matrix_config()["lookback_days"])


def consequence_levels() -> dict[int, dict]:
    return {int(k): v for k, v in matrix_config()["consequence"].items()}


def likelihood_levels() -> dict[int, dict]:
    return {int(k): v for k, v in matrix_config()["likelihood"].items()}


def _check_level(name: str, value: int) -> None:
    if value not in LEVELS:
        raise ValueError(f"{name} must be an integer 1-5, got {value!r}")


def likelihood_from_history(similar_count: int) -> int:
    """Map the number of similar past hazards in an area to a likelihood level 1-5."""
    if similar_count < 0:
        raise ValueError("similar_count cannot be negative")
    for level, spec in sorted(likelihood_levels().items()):
        cap = spec.get("max_count")
        if cap is None or similar_count <= cap:
            return level
    return 5  # pragma: no cover - config always ends with an open-ended level


def band_for(score: int) -> Band:
    for b in bands():
        if b.min <= score <= b.max:
            return b
    raise ValueError(f"No risk band covers score {score}")


def score(consequence: int, likelihood: int) -> RiskResult:
    _check_level("consequence", consequence)
    _check_level("likelihood", likelihood)
    s = consequence * likelihood
    b = band_for(s)
    return RiskResult(consequence, likelihood, s, b.level, b.color, b.action, b.target_days)


def is_alert_level(level: str) -> bool:
    """High and Extreme hazards trigger a supervisor notification."""
    return level in {"High", "Extreme"}


def high_consequence_min() -> int:
    return int(matrix_config()["high_consequence_alert_min"])


def alert_reason(consequence: int, level: str) -> str | None:
    """Why supervisors are alerted, or None. High/Extreme by score band; otherwise a Major or Catastrophic
    consequence, because ADOSH-SF Sec. 5(b) asks for particular attention to risks with a very low likelihood
    but major consequences (project rule: consequence >= 4 alerts whatever the band)."""
    if is_alert_level(level):
        return f"{level} risk"
    if consequence >= high_consequence_min():
        name = consequence_levels()[consequence]["name"]
        return (
            f"consequence {consequence} ({name}) although the score band is {level}: "
            "ADOSH-SF Sec. 5(b) – particular attention to risks with major consequences"
        )
    return None


def control_types() -> dict[str, dict]:
    """Hierarchy of controls, ADOSH-SF Sec. 5.3.4(c), in order from most to least effective."""
    return {c["code"]: c for c in matrix_config()["hierarchy_of_controls"]}


def matrix_table() -> list[list[RiskResult]]:
    """Laid out as ADOSH-SF Table 3: rows = likelihood 1..5 (Rare to Frequent), columns = consequence 1..5."""
    return [[score(c, lk) for c in LEVELS] for lk in LEVELS]


def guideline() -> dict:
    return matrix_config()["guideline"]
