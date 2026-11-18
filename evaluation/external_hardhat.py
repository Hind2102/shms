"""External validation of the released no_hard_hat check on Hard Hat Workers (Make ML, CC0).

Pre-registered in docs/external_validation_plan.md (committed before any image was downloaded or any model run):

    python -m evaluation.external_hardhat --root ~/Desktop/"Final SEP"/datasets/hardhat_workers \\
        --sh17 ~/Desktop/"Final SEP"/datasets/sh17 --device mps

Writes evaluation/results/external_hardhat_yolo_sh17_yolo9e/{predictions.jsonl,metrics.json}. Predictions are
cached, so an interrupted run resumes; nothing is tuned on these results.
"""

from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from shms.detection import build_detector
from shms.detection.base import Box
from shms.detection.rules import hazards_from_boxes

from .metrics import always_yes_baseline, binary_metrics, bootstrap_ci
from .sh17 import dhash, find_layout, read_list

HERE = Path(__file__).resolve().parent
CODE = "no_hard_hat"
OPERATING_CONF = 0.35
SWEEP = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70]
THRESHOLDS = {"precision": 0.80, "recall": 0.75, "specificity": 0.80}  # same as the release gate
PLAN_COMMIT = "22d9a6e"


def _boxes(dets: list[dict]) -> list[Box]:
    out = []
    for d in dets:
        x, y, w, h = d["bounding_box"]  # normalised [x, y, width, height]
        out.append(Box(d["label"].lower(), 1.0, x, y, x + w, y + h))
    return out


def load_rows(root: Path) -> list[dict]:
    """One row per image with the primary (rule engine) and the raw (any head box) ground truth."""
    data = json.loads((Path(root) / "samples.json").read_text())["samples"]
    rows = []
    for s in data:
        boxes = _boxes((s.get("ground_truth") or {}).get("detections", []))
        rows.append(
            {
                "image": s["filepath"],
                "gt": CODE in {h.code for h in hazards_from_boxes(boxes)},
                "gt_raw": any(b.label == "head" for b in boxes),
                "n_head": sum(b.label == "head" for b in boxes),
                "n_helmet": sum(b.label == "helmet" for b in boxes),
            }
        )
    return rows


def verdict(m: dict) -> dict:
    failed = [k for k, t in THRESHOLDS.items() if m.get(k) is None or m[k] < t]
    return {"pass": not failed, "failed": failed, "thresholds": THRESHOLDS}


def find_near_duplicates(images: dict[str, Path], reference: dict[str, int], max_bits: int = 4) -> dict[str, str]:
    out = {}
    for name, path in images.items():
        h = dhash(path)
        for ref_name, ref_h in reference.items():
            if bin(h ^ ref_h).count("1") <= max_bits:
                out[name] = ref_name
                break
    return out


def _metrics(rows: list[dict], preds: dict[str, dict], gt_key: str, conf: float = OPERATING_CONF) -> dict:
    y_true = [r[gt_key] for r in rows]
    y_pred = [_predicted(preds[r["image"]], conf) for r in rows]
    m = binary_metrics(y_true, y_pred)
    for metric in ("precision", "recall", "specificity", "f1", "mcc"):
        m[f"{metric}_ci95"] = bootstrap_ci(y_true, y_pred, metric)
    m["baseline_always_yes"] = always_yes_baseline(y_true)
    m["positives"], m["negatives"] = sum(y_true), len(y_true) - sum(y_true)
    m["prevalence"] = sum(y_true) / len(y_true) if y_true else None
    return m


def _predicted(p: dict, conf: float) -> bool:
    if p.get("boxes"):
        boxes = [Box(**b) for b in p["boxes"] if b["confidence"] >= conf]
        return CODE in {s.code for s in hazards_from_boxes(boxes)}
    return CODE in p.get("codes", [])


def _sh17_hashes(sh17_root: Path, cache: Path) -> dict[str, int]:
    if cache.is_file():
        return {k: int(v) for k, v in json.loads(cache.read_text()).items()}
    lay = find_layout(sh17_root)
    names = read_list(lay.train_list) + read_list(lay.test_list)
    hashes = {n: dhash(lay.images / n) for n in names if (lay.images / n).is_file()}
    cache.write_text(json.dumps({k: str(v) for k, v in hashes.items()}))
    return hashes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, type=Path, help="folder with samples.json and data/")
    ap.add_argument("--sh17", required=True, type=Path, help="SH17 folder (for the near-duplicate check)")
    ap.add_argument("--weights", default="models/sh17_yolo9e.pt")
    ap.add_argument("--device", default="")
    ap.add_argument("--detector", default="yolo", choices=["yolo", "mock"])
    args = ap.parse_args()

    rows = load_rows(args.root)
    name = f"external_hardhat_{args.detector}_{Path(args.weights).stem}"
    out = HERE / "results" / name
    out.mkdir(parents=True, exist_ok=True)

    # 1) leakage check against SH17 train + test (before scoring)
    sh17 = _sh17_hashes(args.sh17, out / "sh17_dhash_cache.json")
    near = find_near_duplicates({r["image"]: args.root / r["image"] for r in rows}, sh17)
    print(f"{len(rows)} images; near-duplicates of SH17 images: {len(near)}")

    # 2) predictions (cached; resumes if interrupted)
    pred_file = out / "predictions.jsonl"
    preds = {}
    if pred_file.is_file():
        preds = {p["image"]: p for p in map(json.loads, pred_file.read_text().splitlines())}
    todo = [r for r in rows if r["image"] not in preds]
    if todo:
        det = build_detector(args.detector, weights=args.weights, conf=0.10, device=args.device)
        with pred_file.open("a") as f:
            for i, r in enumerate(todo, 1):
                res = det.detect(args.root / r["image"])
                p = {
                    "image": r["image"],
                    "codes": sorted(res.codes()),
                    "latency_ms": round(res.latency_ms, 1),
                    "error": res.error,
                    "boxes": [asdict(b) for b in res.boxes],
                }
                preds[r["image"]] = p
                f.write(json.dumps(p) + "\n")
                if i % 250 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
    errors = [r["image"] for r in rows if preds[r["image"]]["error"]]
    ok = [r for r in rows if not preds[r["image"]]["error"]]

    # 3) metrics as pre-registered
    primary = _metrics(ok, preds, "gt")
    metrics = {
        "plan": f"docs/external_validation_plan.md (commit {PLAN_COMMIT})",
        "dataset": "Hard Hat Workers (Make ML), huggingface.co/datasets/Voxel51/hard-hat-detection, CC0",
        "model": args.weights,
        "operating_threshold": OPERATING_CONF,
        "images": len(rows),
        "errors": len(errors),
        "near_duplicates_of_sh17": len(near),
        "near_duplicate_examples": dict(list(near.items())[:20]),
        "primary": primary,
        "verdict": verdict(primary),
        "sensitivity_any_head_box": _metrics(ok, preds, "gt_raw"),
        "secondary_without_near_duplicates": _metrics([r for r in ok if r["image"] not in near], preds, "gt"),
        "threshold_sweep_report_only": [
            {
                "threshold": t,
                **{
                    k: v
                    for k, v in binary_metrics(
                        [r["gt"] for r in ok], [_predicted(preds[r["image"]], t) for r in ok]
                    ).items()
                    if k in ("precision", "recall", "specificity", "f1", "mcc")
                },
            }
            for t in SWEEP
        ],
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    m, v = primary, metrics["verdict"]
    print(
        f"no_hard_hat: P={m['precision']:.3f} R={m['recall']:.3f} Spec={m['specificity']:.3f} MCC={m['mcc']:.3f} "
        f"F1={m['f1']:.3f} (always-yes F1 {m['baseline_always_yes']['f1']:.3f}); "
        f"positives {m['positives']}/{len(ok)} -> {'PASS' if v['pass'] else 'FAIL ' + str(v['failed'])}"
    )
    print(f"-> {out / 'metrics.json'}")


if __name__ == "__main__":
    main()
