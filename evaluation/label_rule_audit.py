"""Label-rule audit in code: why do the model and the box-derived labels disagree?

    python -m evaluation.label_rule_audit --root ~/Desktop/"Final SEP"/datasets/sh17 [--run yolo_sh17_yolo9e]

For every false alarm (FP) and miss (FN) of the run at its operating threshold, the ground-truth boxes and the
model's boxes are compared and the disagreement is put in one structural category (no relevant body part labelled,
body part below the rule's size limit, PPE labelled but missed, model saw PPE that is not labelled, ...). This needs
no human judgement; whether a person is *visible* where no person box exists can only be seen in the photo, so a
local gallery (evaluation/data/label_rule_gallery.html, not committed: SH17 images are CC BY-NC-SA) is written for
the project owner to inspect.

Also a separate SENSITIVITY analysis with a stricter label variant: each hazard is scored only on images in which the
relevant body part is labelled (person for the vest, head for the hard hat, face for eye protection, hands for
gloves). The released labels and results are not changed.
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
from collections import Counter
from pathlib import Path

from shms.detection.base import Box
from shms.detection.rules import DEFAULT_RULES

from .metrics import always_yes_baseline, binary_metrics, bootstrap_ci
from .sh17 import HAZARDS, find_layout, label_path, read_boxes

HERE = Path(__file__).resolve().parent
PART = {"no_hi_vis_vest": "person", "no_hard_hat": "head", "no_eye_protection": "face", "no_gloves": "hands"}
PPE = {
    "no_hi_vis_vest": ("safety-vest", "safety-suit"),
    "no_hard_hat": ("helmet",),
    "no_eye_protection": ("glasses", "face-guard"),
    "no_gloves": ("gloves",),
}
MIN_AREA = {
    "no_hi_vis_vest": DEFAULT_RULES.min_person_area,
    "no_hard_hat": DEFAULT_RULES.min_head_area,
    "no_eye_protection": DEFAULT_RULES.min_face_area,
    "no_gloves": DEFAULT_RULES.min_hand_area,
}


def _parts(boxes: list[Box], hazard: str) -> list[Box]:
    return [b for b in boxes if b.label == PART[hazard] or (PART[hazard] == "hands" and b.label == "hand")]


def classify(hazard: str, kind: str, gt: list[Box], pred: list[Box]) -> str:
    """Structural reason for one disagreement. kind = 'FP' (model yes, label no) or 'FN' (model no, label yes)."""
    part, ppe, min_area = PART[hazard], PPE[hazard], MIN_AREA[hazard]
    gt_parts = _parts(gt, hazard)
    if kind == "FP":
        if not gt_parts:
            return f"no {part} box in the labels"
        if all(p.area < min_area for p in gt_parts):
            return f"labelled {part} below the rule's size limit"
        if any(b.label in ppe for b in gt):
            return "PPE labelled, model missed it"
        return f"other: model judges a labelled {part} unprotected"
    pred_parts = [p for p in _parts(pred, hazard) if p.area >= min_area]
    if not pred_parts:
        return f"model found no {part}"
    if any(b.label in ppe for b in pred):
        return "model saw PPE that is not in the labels"
    return "other"


def _thumb(path: Path, gt: list[Box], pred: list[Box]) -> str:
    from PIL import Image, ImageDraw

    with Image.open(path) as im:
        im.draft("RGB", (640, 640))
        im = im.convert("RGB")
        im.thumbnail((480, 480))
        d = ImageDraw.Draw(im)
        w, h = im.size
        for boxes, colour in ((gt, (0, 170, 0)), (pred, (220, 0, 0))):
            for b in boxes:
                d.rectangle([b.x1 * w, b.y1 * h, b.x2 * w, b.y2 * h], outline=colour, width=2)
                d.text((b.x1 * w + 2, b.y1 * h + 1), b.label, fill=colour)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--run", default="yolo_sh17_yolo9e")
    ap.add_argument("--gallery-per-category", type=int, default=6)
    args = ap.parse_args()

    lay = find_layout(args.root)
    run = json.loads((HERE / "results" / args.run / "metrics.json").read_text())
    conf = run["operating_threshold"]
    preds = {
        p["image"]: p
        for p in map(json.loads, (HERE / "results" / args.run / "predictions.jsonl").read_text().splitlines())
    }
    rows = list(csv.DictReader((HERE / "data" / "sh17_test_manifest.csv").open()))

    out = {"run": args.run, "operating_threshold": conf, "images": len(rows), "hazards": {}}
    gallery: list[tuple[str, str, str, str]] = []
    for hz in HAZARDS:
        cats: Counter = Counter()
        examples: dict[str, list[str]] = {}
        y_true, y_pred, strict_true, strict_pred = [], [], [], []
        for r in rows:
            p = preds[r["image"]]
            gt_yes, pred_yes = r[f"gt_{hz}"] == "1", hz in p["codes"]
            y_true.append(gt_yes)
            y_pred.append(pred_yes)
            gt = read_boxes(label_path(lay, r["image"]))
            if any(b.area >= MIN_AREA[hz] for b in _parts(gt, hz)):  # stricter variant: body part labelled
                strict_true.append(gt_yes)
                strict_pred.append(pred_yes)
            if gt_yes == pred_yes:
                continue
            kind = "FP" if pred_yes else "FN"
            pred_boxes = [Box(**b) for b in p["boxes"] if b["confidence"] >= conf]
            cat = f"{kind}: {classify(hz, kind, gt, pred_boxes)}"
            cats[cat] += 1
            examples.setdefault(cat, []).append(r["image"])
            if len(examples[cat]) <= args.gallery_per_category:
                gallery.append((hz, cat, r["image"], _thumb(lay.images / r["image"], gt, pred_boxes)))
        strict = binary_metrics(strict_true, strict_pred)
        for metric in ("precision", "recall", "specificity", "mcc"):
            strict[f"{metric}_ci95"] = bootstrap_ci(strict_true, strict_pred, metric)
        strict["baseline_always_yes"] = always_yes_baseline(strict_true)
        out["hazards"][hz] = {
            "released": binary_metrics(y_true, y_pred),
            "disagreements": dict(cats.most_common()),
            "example_images": {k: v[:10] for k, v in examples.items()},
            "sensitivity_part_labelled": {"images": len(strict_true), **strict},
        }
        print(f"{hz}: " + "; ".join(f"{k} {v}" for k, v in cats.most_common()))
    (HERE / "results" / f"label_rule_audit_{args.run}.json").write_text(json.dumps(out, indent=2))

    html = [
        "<!doctype html><meta charset='utf-8'><title>Label-rule audit gallery</title>",
        "<style>body{font-family:sans-serif;margin:16px}figure{display:inline-block;margin:6px;width:480px;"
        "vertical-align:top}figcaption{font-size:12px}</style>",
        "<h1>Label-rule audit – examples</h1><p>Green = dataset labels, red = model boxes at the operating "
        "threshold. For inspection by the project owner; not a substitute for the label audit.</p>",
    ]
    for hz, cat, name, b64 in gallery:
        html.append(
            f"<figure><img src='data:image/jpeg;base64,{b64}' width='480'><figcaption><b>{hz}</b> – {cat}<br>"
            f"{name}</figcaption></figure>"
        )
    (HERE / "data" / "label_rule_gallery.html").write_text("\n".join(html))
    print(f"-> evaluation/results/label_rule_audit_{args.run}.json and evaluation/data/label_rule_gallery.html")


if __name__ == "__main__":
    main()
