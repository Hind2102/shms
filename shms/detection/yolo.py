"""YOLO object detector trained on SH17, followed by the PPE rule engine."""

from __future__ import annotations

from pathlib import Path

from .base import Box, HazardDetector, Suggestion
from .rules import DEFAULT_RULES, RuleConfig, hazards_from_boxes


class YoloDetector(HazardDetector):
    def __init__(
        self,
        weights: str | Path,
        conf: float = 0.35,
        device: str = "",
        rules: RuleConfig = DEFAULT_RULES,
        imgsz: int = 640,
    ):
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("YOLO detector needs the optional dependency: pip install -e '.[yolo]'") from exc
        weights = Path(weights)
        if not weights.is_file():
            raise FileNotFoundError(f"YOLO weights not found at {weights}. Run: python scripts/download_models.py")
        self.model = YOLO(str(weights))
        self.conf = conf
        self.device = device or None
        self.rules = rules
        self.imgsz = imgsz
        self.name = f"yolo:{weights.stem}"

    def boxes(self, image_path: Path) -> list[Box]:
        result = self.model.predict(
            str(image_path), conf=self.conf, imgsz=self.imgsz, device=self.device, verbose=False
        )[0]
        names = result.names
        out = []
        for xyxyn, conf, cls in zip(
            result.boxes.xyxyn.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist(), strict=True
        ):
            out.append(Box(names[int(cls)], float(conf), *map(float, xyxyn)))
        return out

    def _predict(self, image_path: Path) -> tuple[list[Suggestion], list[Box]]:
        boxes = self.boxes(image_path)
        return hazards_from_boxes(boxes, self.rules), boxes
