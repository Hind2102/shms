"""EXPERIMENTAL: unsafe-condition check (liquid on the floor, object obstructing a walkway) with a local VLM.

Not part of the release gate. Evaluated only on synthetic warehouse images (docs/unsafe_conditions_plan.md). The
model is never asked what a liquid is, and "obstructed" only counts when a walkway is visible in the photo.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from .ollama_vlm import encode_image

PROMPTS = {
    "c1": """You are checking one photo of an industrial site for two housekeeping conditions. Look at the floor.

- floor_liquid_visible: is there liquid, a puddle, a wet patch or a fluid trail on the floor (any colour)?
- walkway_visible: can you see a walkway, aisle or passage that people or vehicles use?
- walkway_obstructed: is an object (boxes, pallet, equipment, debris) lying in that walkway so that it blocks or
  narrows the way through? Objects stored properly on racks or beside the walkway do not count.

Do not guess what the liquid is. Answer each question with true or false, then one short sentence about what you saw.""",
    # c2 (after dev run of c1: fallen boxes and debris were called "clear walkway"): ask about anything lying on the
    # walkway floor that should not be there, whether or not people could still get past.
    "c2": """You are checking one photo of an industrial site for two housekeeping conditions. Look carefully at the
whole floor area, including the far end of aisles.

- floor_liquid_visible: is there liquid, a puddle, a wet patch or a fluid trail on the floor (any colour)?
- walkway_visible: can you see a walkway, aisle or passage that people or vehicles use?
- walkway_obstructed: is anything lying on the floor of that walkway that should not be there – fallen or dropped
  boxes, a broken pallet, scattered debris or packaging, tools, or equipment left standing in the aisle? Count it even
  if people could still walk around it. Goods stored neatly on racks or in marked storage spaces beside the walkway do
  not count.

Do not guess what the liquid is. Answer each question with true or false, then one short sentence about what you saw.""",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "floor_liquid_visible": {"type": "boolean"},
        "walkway_visible": {"type": "boolean"},
        "walkway_obstructed": {"type": "boolean"},
        "explanation": {"type": "string"},
    },
    "required": ["floor_liquid_visible", "walkway_visible", "walkway_obstructed", "explanation"],
}


def parse_answer(content: str) -> dict:
    d = json.loads(content)
    return {
        "spill": d.get("floor_liquid_visible") is True,
        "obstruction": d.get("walkway_visible") is True and d.get("walkway_obstructed") is True,
        "explanation": str(d.get("explanation", ""))[:300],
    }


def ask(image: Path, prompt: str = "c1", model: str = "qwen2.5vl:7b", url: str = "http://localhost:11434") -> dict:
    payload = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0, "seed": 42},
        "messages": [{"role": "user", "content": PROMPTS[prompt], "images": [encode_image(image, 1024)]}],
    }
    r = httpx.post(f"{url}/api/chat", json=payload, timeout=180)
    r.raise_for_status()
    return parse_answer(r.json()["message"]["content"])


FROZEN_PROMPT = "c2"  # frozen after dev tuning, evaluated once on the test split (docs/unsafe_conditions_plan.md)


def observe(image: Path) -> list[dict]:
    """Experimental observations for a report, as suggestion records marked experimental. Never raises: a failed
    or unreachable model gives no observation and never blocks a report. The model's free-text explanation is kept
    for traceability only and is not shown to the reporter (it could name a substance)."""
    import logging

    from ..settings import get_settings

    s = get_settings()
    try:
        a = ask(image, FROZEN_PROMPT, s.ollama_model, s.ollama_url)
    except Exception:  # noqa: BLE001
        logging.getLogger("shms").warning("Experimental conditions check failed", exc_info=True)
        return []
    out = []
    for code, key in (("floor_liquid", "spill"), ("walkway_obstruction", "obstruction")):
        if a.get(key):
            out.append(
                {
                    "code": code,
                    "confidence": 0.0,
                    "evidence": [],
                    "explanation": a.get("explanation", ""),
                    "required": False,
                    "experimental": True,
                }
            )
    return out
