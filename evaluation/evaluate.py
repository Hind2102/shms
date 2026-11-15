"""Evaluate a hazard detector on the held-out SH17 test manifest.

    python -m evaluation.evaluate --root ~/datasets/sh17 --detector yolo --weights models/sh17_yolo8s.pt
    python -m evaluation.evaluate --root ~/datasets/sh17 --detector ollama --model qwen2.5vl:7b --subset
    python -m evaluation.evaluate --root ~/datasets/sh17 --detector yolo --map      # + detection mAP (reproduces SH17 paper)

Outputs go to evaluation/results/<run-name>/:
    predictions.jsonl   one line per image (cached: re-running resumes where it stopped)
    metrics.json        precision / recall / F1 with 95% bootstrap CIs per hazard, latency summary,
                        and (YOLO only) a confidence-threshold sweep
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from shms.detection import build_detector
from shms.detection.base import Box
from shms.detection.rules import hazards_from_boxes

from .metrics import binary_metrics, bootstrap_ci, latency_summary
from .sh17 import HAZARDS, SH17_NAMES, find_layout

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "data" / "sh17_test_manifest.csv"
SWEEP = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]


def load_manifest(path: Path, subset: bool, limit: int | None, drop_near_dups: bool = False) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    if drop_near_dups:
        rows = [r for r in rows if r.get("near_dup_train", "0") != "1"]
    if subset:
        rows = [r for r in rows if r["in_subset"] == "1"]
    return rows[:limit] if limit else rows


def score(rows: list[dict], preds: dict[str, dict], key=lambda p: set(p["codes"])) -> dict:
    out = {}
    for h in HAZARDS:
        y_true = [r[f"gt_{h}"] == "1" for r in rows]
        y_pred = [h in key(preds[r["image"]]) for r in rows]
        m = binary_metrics(y_true, y_pred)
        for metric in ("precision", "recall", "f1"):
            m[f"{metric}_ci95"] = bootstrap_ci(y_true, y_pred, metric)
        out[h] = m
    # micro-average over the three hazards
    tp = sum(out[h]["tp"] for h in HAZARDS)
    fp = sum(out[h]["fp"] for h in HAZARDS)
    fn = sum(out[h]["fn"] for h in HAZARDS)
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    out["micro"] = {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if p and r else None,
    }
    out["macro_f1"] = sum(out[h]["f1"] or 0 for h in HAZARDS) / len(HAZARDS)
    return out


def yolo_sweep(rows: list[dict], preds: dict[str, dict]) -> list[dict]:
    """Re-apply the rule engine with boxes filtered at each confidence threshold."""
    res = []
    for t in SWEEP:

        def codes_at(p, t=t):
            boxes = [Box(**b) for b in p["boxes"] if b["confidence"] >= t]
            return {s.code for s in hazards_from_boxes(boxes)}

        m = score(rows, preds, key=codes_at)
        res.append(
            {
                "threshold": t,
                **{h: {k: m[h][k] for k in ("precision", "recall", "f1")} for h in HAZARDS},
                "macro_f1": m["macro_f1"],
            }
        )
    return res


def detection_map(weights: str, root: Path, device: str) -> dict:
    """Standard object-detection mAP on the same split, to compare with the SH17 paper's table."""
    from ultralytics import YOLO

    lay = find_layout(root)
    lst = HERE / "data" / "sh17_test_abs.txt"
    lst.write_text("\n".join(str(lay.images / r["image"]) for r in load_manifest(MANIFEST, False, None)))
    yaml = HERE / "data" / "sh17_eval.yaml"
    yaml.write_text(
        f"path: {lay.root}\ntrain: {lst}\nval: {lst}\nnames:\n"
        + "".join(f"  {i}: {n}\n" for i, n in enumerate(SH17_NAMES))
    )
    m = YOLO(weights).val(data=str(yaml), imgsz=640, batch=8, device=device or None, verbose=False, plots=False)
    return {
        "mAP50": float(m.box.map50),
        "mAP50_95": float(m.box.map),
        "precision": float(m.box.mp),
        "recall": float(m.box.mr),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="SH17 folder (images/ and labels/)")
    ap.add_argument("--detector", choices=["yolo", "ollama", "mock"], required=True)
    ap.add_argument("--weights", default="models/sh17_yolo8s.pt")
    ap.add_argument("--model", default="qwen2.5vl:7b", help="Ollama model tag")
    ap.add_argument("--conf", type=float, default=0.35, help="YOLO operating threshold")
    ap.add_argument("--device", default="", help="YOLO device: '', cpu, mps, cuda:0")
    ap.add_argument("--subset", action="store_true", help="only the fixed 300-image subset")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--name", default=None, help="run name (results folder)")
    ap.add_argument("--map", action="store_true", help="also compute YOLO detection mAP")
    ap.add_argument(
        "--drop-near-dups", action="store_true", help="exclude test images that are near-duplicates of training images"
    )
    args = ap.parse_args()

    if not MANIFEST.is_file():
        sys.exit("Run `python -m evaluation.prepare_sh17 --root ...` first.")
    rows = load_manifest(MANIFEST, args.subset, args.limit, args.drop_near_dups)
    lay = find_layout(args.root)

    if args.detector == "yolo":
        # Run at a low threshold and keep every box, so the sweep can be computed offline.
        det = build_detector("yolo", weights=args.weights, conf=0.10, device=args.device)
        default_name = f"yolo_{Path(args.weights).stem}"
    elif args.detector == "ollama":
        det = build_detector("ollama", model=args.model)
        default_name = f"ollama_{args.model.replace(':', '_').replace('/', '_')}"
    else:
        det = build_detector("mock")
        default_name = "mock"
    name = (args.name or default_name) + ("_nodup" if args.drop_near_dups else "") + ("_subset" if args.subset else "")
    out = HERE / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    pred_file = out / "predictions.jsonl"

    preds: dict[str, dict] = {}
    if pred_file.is_file():
        for line in pred_file.read_text().splitlines():
            p = json.loads(line)
            preds[p["image"]] = p
    todo = [r for r in rows if r["image"] not in preds]
    print(f"{name}: {len(rows)} images, {len(preds)} cached, {len(todo)} to run")

    with pred_file.open("a") as f:
        for i, r in enumerate(todo, 1):
            res = det.detect(lay.images / r["image"])
            if args.detector == "yolo":
                boxes = [b for b in res.boxes if b.confidence >= args.conf]
                codes = sorted({s.code for s in hazards_from_boxes(boxes)})
            else:
                codes = sorted(res.codes())
            p = {
                "image": r["image"],
                "codes": codes,
                "latency_ms": round(res.latency_ms, 1),
                "error": res.error,
                "suggestions": [s.to_dict() for s in res.suggestions],
                "boxes": [asdict(b) for b in res.boxes],
            }
            preds[r["image"]] = p
            f.write(json.dumps(p) + "\n")
            f.flush()
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  last {res.latency_ms:.0f} ms", flush=True)

    errors = [p for p in (preds[r["image"]] for r in rows) if p["error"]]
    ok_rows = [r for r in rows if not preds[r["image"]]["error"]]
    metrics = {
        "run": name,
        "detector": det.name,
        "operating_threshold": args.conf if args.detector == "yolo" else None,
        "images": len(rows),
        "errors": len(errors),
        "scored_images": len(ok_rows),
        "hazards": score(ok_rows, preds),
        # first image includes model loading; report steady-state latency separately
        "latency_all": latency_summary([preds[r["image"]]["latency_ms"] for r in rows]),
        "latency_steady": latency_summary([preds[r["image"]]["latency_ms"] for r in rows][1:]),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    }
    if args.detector == "yolo":
        metrics["threshold_sweep"] = yolo_sweep(ok_rows, preds)
    if args.map and args.detector == "yolo":
        t0 = time.time()
        metrics["detection_map"] = detection_map(args.weights, lay.root, args.device)
        metrics["detection_map"]["seconds"] = round(time.time() - t0)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print(f"\nResults ({len(ok_rows)} images scored, {len(errors)} errors) -> {out / 'metrics.json'}")
    for h in HAZARDS:
        m = metrics["hazards"][h]
        fmt = lambda v: "  n/a" if v is None else f"{v:.3f}"  # noqa: E731
        print(f"  {h:16s} P={fmt(m['precision'])} R={fmt(m['recall'])} F1={fmt(m['f1'])} (positives {m['support']})")
    lat = metrics["latency_steady"]
    if lat.get("n"):
        print(f"  latency p50={lat['p50_ms']:.0f} ms  p95={lat['p95_ms']:.0f} ms")


if __name__ == "__main__":
    main()
