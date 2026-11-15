"""Vision-language model served locally by Ollama (e.g. qwen2.5vl:7b, gemma3:12b, llama3.2-vision).

The photo never leaves the machine, there is no paid API, and the model needs
no training: it is asked fixed yes/no questions that mirror the rule engine's
hazard definitions, and must answer in a JSON schema enforced by Ollama.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import httpx
from PIL import Image

from .base import Box, HazardDetector, Suggestion

PROMPT = """You are a safety inspector at an alumina refinery, where every person on site must wear a
hard hat, safety glasses (or goggles / face shield), gloves and a high-visibility vest (or safety suit).
Look carefully at the photo and answer each question about the people that are clearly visible.

- worker_without_hard_hat: is any visible person's head NOT covered by a hard hat / safety helmet?
- worker_without_eye_protection: is any visible person's face NOT protected by safety glasses, goggles or a face shield?
- bare_hands_visible: is any visible hand NOT wearing a glove?
- worker_without_hi_vis_vest: is any visible person's torso NOT covered by a high-visibility vest or safety suit?

If no person is visible, answer false to all four. Give a confidence between 0 and 1 for your
overall answer and one short sentence explaining what you saw."""

SCHEMA = {
    "type": "object",
    "properties": {
        "people_visible": {"type": "boolean"},
        "worker_without_hard_hat": {"type": "boolean"},
        "worker_without_eye_protection": {"type": "boolean"},
        "bare_hands_visible": {"type": "boolean"},
        "worker_without_hi_vis_vest": {"type": "boolean"},
        "confidence": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": [
        "people_visible",
        "worker_without_hard_hat",
        "worker_without_eye_protection",
        "bare_hands_visible",
        "worker_without_hi_vis_vest",
        "confidence",
        "explanation",
    ],
}

FIELD_TO_CODE = {
    "worker_without_hard_hat": "no_hard_hat",
    "worker_without_eye_protection": "no_eye_protection",
    "worker_without_hi_vis_vest": "no_hi_vis_vest",
    "bare_hands_visible": "no_gloves",
}


def encode_image(path: Path, max_side: int = 1024) -> str:
    """Downscale (SH17 photos reach 8192 px) and return base64 JPEG."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def parse_answer(content: str) -> list[Suggestion]:
    data = json.loads(content)
    conf = data.get("confidence", 0.7)
    try:
        conf = min(1.0, max(0.0, float(conf)))
    except (TypeError, ValueError):
        conf = 0.7
    expl = str(data.get("explanation", ""))[:300]
    return [Suggestion(code, conf, [], expl) for field_, code in FIELD_TO_CODE.items() if data.get(field_) is True]


class OllamaDetector(HazardDetector):
    def __init__(
        self,
        model: str,
        url: str = "http://localhost:11434",
        timeout_s: float = 120,
        max_side: int = 1024,
        client: httpx.Client | None = None,
    ):
        self.model = model
        self.url = url.rstrip("/")
        self.max_side = max_side
        self.client = client or httpx.Client(timeout=timeout_s)
        self.name = f"ollama:{model}"

    def _predict(self, image_path: Path) -> tuple[list[Suggestion], list[Box]]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": SCHEMA,
            "options": {"temperature": 0, "seed": 42},
            "messages": [{"role": "user", "content": PROMPT, "images": [encode_image(image_path, self.max_side)]}],
        }
        resp = self.client.post(f"{self.url}/api/chat", json=payload)
        resp.raise_for_status()
        return parse_answer(resp.json()["message"]["content"]), []
