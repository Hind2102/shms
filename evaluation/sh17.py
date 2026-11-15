"""Reading the SH17 dataset (Kaggle release) and deriving image-level hazard labels.

Expected layout after unzipping the Kaggle download into SH17_ROOT::

    SH17_ROOT/images/*.jpg|jpeg|png
    SH17_ROOT/labels/*.txt            YOLO format: class cx cy w h (normalised)
    SH17_ROOT/val_files.txt           (or test_files.txt) the held-out split
    SH17_ROOT/train_files.txt

Folder names are searched recursively, so an extra top-level folder from unzipping is fine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shms.detection.base import Box
from shms.detection.rules import hazards_from_boxes

# Class order from sh17.yaml in the official repository (used by the released weights).
SH17_NAMES = ["person", "ear", "ear-mufs", "face", "face-guard", "face-mask", "foot", "tool", "glasses",
              "gloves", "helmet", "hands", "head", "medical-suit", "shoes", "safety-suit", "safety-vest"]
HAZARDS = ["no_hard_hat", "no_eye_protection", "no_gloves", "no_hi_vis_vest"]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class Layout:
    root: Path
    images: Path
    labels: Path
    test_list: Path | None
    train_list: Path | None


def _find_dir(root: Path, name: str) -> Path:
    if (root / name).is_dir():
        return root / name
    hits = sorted(p for p in root.rglob(name) if p.is_dir())
    if not hits:
        raise FileNotFoundError(f"No '{name}/' folder under {root}")
    return hits[0]


def _find_file(root: Path, names: list[str]) -> Path | None:
    for n in names:
        hits = sorted(root.rglob(n))
        if hits:
            return hits[0]
    return None


def find_layout(root: str | Path) -> Layout:
    root = Path(root).expanduser().resolve()
    return Layout(
        root=root,
        images=_find_dir(root, "images"),
        labels=_find_dir(root, "labels"),
        test_list=_find_file(root, ["val_files.txt", "test_files.txt"]),
        train_list=_find_file(root, ["train_files.txt"]),
    )


def read_list(path: Path) -> list[str]:
    """Split files hold one image per line, sometimes with a path prefix; keep the file name."""
    return [Path(line.strip().replace("\\", "/")).name for line in path.read_text().splitlines() if line.strip()]


def read_boxes(label_file: Path, names: list[str] = SH17_NAMES) -> list[Box]:
    boxes = []
    if not label_file.is_file():
        return boxes
    for line in label_file.read_text().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls, cx, cy, w, h = int(float(parts[0])), *map(float, parts[1:5])
        boxes.append(Box(names[cls], 1.0, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
    return boxes


def gt_hazards(boxes: list[Box]) -> dict[str, bool]:
    found = {s.code for s in hazards_from_boxes(boxes)}
    return {h: h in found for h in HAZARDS}


def label_path(layout: Layout, image_name: str) -> Path:
    return layout.labels / (Path(image_name).stem + ".txt")
