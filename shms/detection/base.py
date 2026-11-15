"""Common types for every hazard detector.

The web application only depends on :class:`HazardDetector`; concrete
detectors (YOLO, Ollama vision-language model, mock) are interchangeable and
selected by configuration. This keeps the AI swappable and lets the full test
suite run without a GPU or a model download.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Box:
    """An object detection, with coordinates normalised to [0, 1] (x1, y1, x2, y2)."""

    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


@dataclass
class Suggestion:
    """A hazard category suggested for the whole photo."""

    code: str
    confidence: float
    evidence: list[Box] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "confidence": round(self.confidence, 4),
            "explanation": self.explanation,
            "evidence": [asdict(b) for b in self.evidence],
        }


@dataclass
class DetectorResult:
    model: str
    suggestions: list[Suggestion]
    latency_ms: float
    boxes: list[Box] = field(default_factory=list)
    error: str | None = None

    @property
    def top(self) -> Suggestion | None:
        return max(self.suggestions, key=lambda s: s.confidence, default=None)

    def codes(self, threshold: float = 0.0) -> set[str]:
        return {s.code for s in self.suggestions if s.confidence >= threshold}


class HazardDetector(ABC):
    """Interface: photo in, hazard suggestions out."""

    name: str = "base"

    @abstractmethod
    def _predict(self, image_path: Path) -> tuple[list[Suggestion], list[Box]]:
        """Return (suggestions, raw boxes). May raise on failure."""

    def detect(self, image_path: str | Path) -> DetectorResult:
        """Run the model, time it, and never raise: errors are returned in the result
        so a failed AI call cannot block a hazard report."""
        start = time.perf_counter()
        try:
            suggestions, boxes = self._predict(Path(image_path))
            error = None
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, logged in DB
            suggestions, boxes, error = [], [], f"{type(exc).__name__}: {exc}"
        latency = (time.perf_counter() - start) * 1000
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return DetectorResult(self.name, suggestions, latency, boxes, error)
