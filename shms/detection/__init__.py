"""Hazard detectors. Use :func:`build_detector` to get the configured one."""

from __future__ import annotations

from functools import lru_cache

from .base import Box, DetectorResult, HazardDetector, Suggestion

__all__ = ["Box", "DetectorResult", "HazardDetector", "Suggestion", "build_detector", "get_detector"]


def build_detector(kind: str, **overrides) -> HazardDetector:
    from ..settings import get_settings

    s = get_settings()
    kind = kind.lower()
    if kind == "mock":
        from .mock import MockDetector

        return MockDetector()
    if kind == "yolo":
        from .yolo import YoloDetector

        return YoloDetector(
            overrides.get("weights", s.yolo_weights),
            conf=overrides.get("conf", s.yolo_conf),
            device=overrides.get("device", s.yolo_device),
        )
    if kind == "ollama":
        from .ollama_vlm import OllamaDetector

        return OllamaDetector(overrides.get("model", s.ollama_model), url=s.ollama_url, timeout_s=s.ollama_timeout_s)
    raise ValueError(f"Unknown detector {kind!r}; choose yolo, ollama or mock")


@lru_cache(maxsize=1)
def get_detector() -> HazardDetector:
    """The detector the web app uses (loaded once, on first report)."""
    from ..settings import get_settings

    return build_detector(get_settings().detector)
