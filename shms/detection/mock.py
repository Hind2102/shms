"""Deterministic detector for tests, CI and demos without a model download."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .base import Box, HazardDetector, Suggestion


class MockDetector(HazardDetector):
    """Returns a fixed answer derived from the file contents.

    If the file name contains a category code (e.g. ``site_no_hard_hat_1.jpg``)
    that category is returned with confidence 0.9, which makes end-to-end tests
    predictable. Otherwise the result is a stable pseudo-random choice.
    """

    name = "mock"
    _codes = ("no_hard_hat", "no_hi_vis_vest", "no_gloves")

    def _predict(self, image_path: Path) -> tuple[list[Suggestion], list[Box]]:
        stem = image_path.name.lower()
        for code in self._codes:
            if code in stem:
                return [Suggestion(code, 0.9, [], "matched file name (mock detector)")], []
        if "clean" in stem:
            return [], []
        digest = hashlib.sha256(image_path.read_bytes()).digest()
        code = self._codes[digest[0] % len(self._codes)]
        conf = 0.4 + (digest[1] / 255) * 0.5
        return [Suggestion(code, conf, [], "mock detector (no model loaded)")], []
