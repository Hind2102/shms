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


# ---------------------------------------------------------------- prompt v2
# v1 (above) framed the photo as a refinery; on SH17's everyday scenes the model then often decided "no worker
# here" and answered no hazard (recall ~0.33). v2 removes that framing and asks about EACH visible person
# separately, mirroring the YOLO rule engine; the hazards are derived in code, not by the model.
PROMPT_V2 = """This is an automated PPE compliance check. The photo may show any setting: factory, workshop,
kitchen, street, office or home. Do NOT decide whether protective equipment is needed there. Treat every
visible person as if they were on an industrial site, and only report what each person is wearing.

List every clearly visible person (ignore tiny people far in the background). For each person:
- head_visible: can you see the person's head?
- hard_hat: is the head covered by a hard hat or safety helmet?
- face_visible: can you see the person's face?
- eye_protection: are the eyes covered by safety glasses, goggles or a face shield? (ordinary sunglasses or
  prescription glasses count as glasses)
- hands_visible: can you see at least one hand?
- all_visible_hands_gloved: is every visible hand wearing a glove?
- torso_visible: can you see the person's upper body?
- hi_vis_or_safety_suit: is the torso covered by a high-visibility vest, a reflective vest or a safety suit?

Answer false when an item is not worn. Then give one short sentence describing what you saw."""

_PERSON = {
    "type": "object",
    "properties": {
        k: {"type": "boolean"}
        for k in (
            "head_visible",
            "hard_hat",
            "face_visible",
            "eye_protection",
            "hands_visible",
            "all_visible_hands_gloved",
            "torso_visible",
            "hi_vis_or_safety_suit",
        )
    },
    "required": [
        "head_visible",
        "hard_hat",
        "face_visible",
        "eye_protection",
        "hands_visible",
        "all_visible_hands_gloved",
        "torso_visible",
        "hi_vis_or_safety_suit",
    ],
}
SCHEMA_V2 = {
    "type": "object",
    "properties": {"people": {"type": "array", "items": _PERSON}, "explanation": {"type": "string"}},
    "required": ["people", "explanation"],
}
# hazard code -> (body part must be visible, PPE item that must be worn)
V2_RULES = {
    "no_hard_hat": ("head_visible", "hard_hat"),
    "no_eye_protection": ("face_visible", "eye_protection"),
    "no_gloves": ("hands_visible", "all_visible_hands_gloved"),
    "no_hi_vis_vest": ("torso_visible", "hi_vis_or_safety_suit"),
}


def parse_answer_v2(content: str) -> list[Suggestion]:
    data = json.loads(content)
    people = [p for p in data.get("people", []) if isinstance(p, dict)]
    expl = str(data.get("explanation", ""))[:300]
    out = []
    for code, (visible, worn) in V2_RULES.items():
        bare = sum(1 for p in people if p.get(visible) is True and p.get(worn) is not True)
        if bare:
            # A VLM gives no calibrated score; confidence = share of visible people missing the item.
            seen = sum(1 for p in people if p.get(visible) is True)
            out.append(Suggestion(code, round(0.5 + 0.5 * bare / max(seen, 1), 3), [], f"{bare} of {seen}: {expl}"))
    return out


PROMPTS = {"v1": (PROMPT, SCHEMA, parse_answer), "v2": (PROMPT_V2, SCHEMA_V2, parse_answer_v2)}


class OllamaDetector(HazardDetector):
    def __init__(
        self,
        model: str,
        url: str = "http://localhost:11434",
        timeout_s: float = 120,
        max_side: int = 1024,
        client: httpx.Client | None = None,
        prompt: str = "v2",
    ):
        if prompt not in PROMPTS:
            raise ValueError(f"Unknown prompt version {prompt!r}; choose from {sorted(PROMPTS)}")
        self.model = model
        self.url = url.rstrip("/")
        self.max_side = max_side
        self.client = client or httpx.Client(timeout=timeout_s)
        self.prompt_version = prompt
        self.prompt, self.schema, self.parse = PROMPTS[prompt]
        self.name = f"ollama:{model}:prompt-{prompt}"

    def _predict(self, image_path: Path) -> tuple[list[Suggestion], list[Box]]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": self.schema,
            "options": {"temperature": 0, "seed": 42},
            "messages": [{"role": "user", "content": self.prompt, "images": [encode_image(image_path, self.max_side)]}],
        }
        resp = self.client.post(f"{self.url}/api/chat", json=payload)
        resp.raise_for_status()
        return self.parse(resp.json()["message"]["content"]), []
