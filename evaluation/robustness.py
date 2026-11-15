"""Robustness test (non-functional testing, Lecture 4): does the detector still work on poor site photos?

Phone photos in a refinery are often dark, blurred, heavily compressed or taken from far away. We apply
those corruptions to the shared held-out subset and measure how much F1 drops versus the clean images.

    python -m evaluation.robustness --root ~/datasets/sh17 --weights models/sh17_yolo8s.pt --device mps

Writes evaluation/results/robustness_<model>.json and prints a table.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

from shms.detection import build_detector
from shms.detection.rules import hazards_from_boxes

from .evaluate import MANIFEST, load_manifest, score
from .sh17 import HAZARDS, find_layout

RESULTS = Path(__file__).resolve().parent / "results"


def _jpeg(im: Image.Image, q: int) -> Image.Image:
    import io

    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _small(im: Image.Image, f: float) -> Image.Image:
    w, h = im.size
    return im.resize((max(32, int(w * f)), max(32, int(h * f))), Image.BILINEAR)


# name -> (description, function). Images are first downscaled to 1280 px like an uploaded phone photo.
PERTURBATIONS = {
    "clean": ("original image", lambda im: im),
    "dark": ("brightness x0.4 (indoor / night)", lambda im: ImageEnhance.Brightness(im).enhance(0.4)),
    "blur": ("Gaussian blur r=3 (motion / focus)", lambda im: im.filter(ImageFilter.GaussianBlur(3))),
    "jpeg": ("JPEG quality 15 (messaging-app compression)", lambda im: _jpeg(im, 15)),
    "far": ("downscale to 30% (worker far away)", lambda im: _small(im, 0.3)),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True)
    ap.add_argument("--weights", default="models/sh17_yolo8s.pt")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--device", default="")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    rows = load_manifest(MANIFEST, subset=True, limit=args.limit)
    lay = find_layout(args.root)
    det = build_detector("yolo", weights=args.weights, conf=args.conf, device=args.device)
    out: dict = {"model": det.name, "images": len(rows), "conf": args.conf, "perturbations": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for name, (desc, fn) in PERTURBATIONS.items():
            preds = {}
            for r in rows:
                with Image.open(lay.images / r["image"]) as im:
                    im = im.convert("RGB")
                    im.thumbnail((1280, 1280))
                    p = Path(tmp) / f"{name}.jpg"
                    fn(im).save(p, "JPEG", quality=95)
                res = det.detect(p)
                preds[r["image"]] = {"codes": sorted({s.code for s in hazards_from_boxes(res.boxes)})}
            m = score(rows, preds)
            out["perturbations"][name] = {
                "description": desc,
                "macro_f1": m["macro_f1"],
                **{h: {k: m[h][k] for k in ("precision", "recall", "f1")} for h in HAZARDS},
            }
            print(f"{name:6s} macro-F1 {m['macro_f1']:.3f}  ({desc})", flush=True)
    clean = out["perturbations"]["clean"]["macro_f1"] or 0
    for v in out["perturbations"].values():
        v["f1_drop_vs_clean"] = round(clean - (v["macro_f1"] or 0), 4)
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"robustness_{Path(args.weights).stem}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
