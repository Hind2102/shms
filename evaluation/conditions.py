"""Unsafe-conditions experiment runner (pre-registered: docs/unsafe_conditions_plan.md).

    python -m evaluation.conditions --root ~/Desktop/"Final SEP"/datasets/warehouse_hazards --split dev --prompt c1
    python -m evaluation.conditions --root ... --split test --prompt <frozen prompt>     # once

Predictions are cached per run folder; an interrupted run resumes.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import time
from datetime import UTC, datetime
from pathlib import Path

from shms.detection.conditions_vlm import PROMPTS, ask

from .metrics import always_yes_baseline, binary_metrics, bootstrap_ci, latency_summary

HERE = Path(__file__).resolve().parent
HAZARDS = ("spill", "obstruction")
THRESHOLDS = {"precision": 0.80, "recall": 0.75, "specificity": 0.80}


def labels(r: dict) -> dict[str, bool]:
    sub = r.get("subtype", "")
    return {
        "spill": r["category"] == "spill" or "spill + obstacle" in sub,
        "obstruction": r["category"] == "obstacle" or "spill + obstacle" in sub or "with obstacle" in sub,
    }


def ambiguous(r: dict, hazard: str) -> bool:
    """accept_also names the hazard although the label says it is absent."""
    key = "spill" if hazard == "spill" else "obstacle"
    return not labels(r)[hazard] and key in (r.get("accept_also") or "")


def dev_sample(train_rows: list[dict], per_class: int = 20, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for cat in ("spill", "obstacle", "safe"):
        pool = sorted((r for r in train_rows if r["category"] == cat), key=lambda r: r["file_name"])
        out += rng.sample(pool, per_class)
    return out


def _metrics(rows: list[dict], preds: dict, hazard: str) -> dict:
    y_true = [labels(r)[hazard] for r in rows]
    y_pred = [preds[r["file_name"]][hazard] for r in rows]
    m = binary_metrics(y_true, y_pred)
    for k in ("precision", "recall", "specificity", "f1", "mcc"):
        m[f"{k}_ci95"] = bootstrap_ci(y_true, y_pred, k)
    m["baseline_always_yes"] = always_yes_baseline(y_true)
    m["positives"], m["negatives"] = sum(y_true), len(y_true) - sum(y_true)
    m["pass"] = all(m.get(k) is not None and m[k] >= t for k, t in THRESHOLDS.items())
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--prompt", choices=sorted(PROMPTS), required=True)
    ap.add_argument("--model", default="qwen2.5vl:7b")
    args = ap.parse_args()

    folder = "train" if args.split == "dev" else "test"
    rows = list(csv.DictReader((args.root / folder / "metadata.csv").open()))
    if args.split == "dev":
        rows = dev_sample(rows)
    name = f"conditions_{args.model.replace(':', '_')}_{args.prompt}_{args.split}"
    out = HERE / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    pred_file = out / "predictions.jsonl"
    preds = {}
    if pred_file.is_file():
        preds = {p["file_name"]: p for p in map(json.loads, pred_file.read_text().splitlines())}
    todo = [r for r in rows if r["file_name"] not in preds]
    with pred_file.open("a") as f:
        for i, r in enumerate(todo, 1):
            t0 = time.perf_counter()
            try:
                p, err = ask(args.root / folder / r["file_name"], args.prompt, args.model), None
            except Exception as exc:  # noqa: BLE001 - recorded, counted as an error
                p, err = {"spill": False, "obstruction": False, "explanation": ""}, f"{type(exc).__name__}: {exc}"
            p |= {"file_name": r["file_name"], "latency_ms": round((time.perf_counter() - t0) * 1000, 1), "error": err}
            preds[r["file_name"]] = p
            f.write(json.dumps(p) + "\n")
            f.flush()
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)

    ok = [r for r in rows if not preds[r["file_name"]]["error"]]
    metrics = {
        "plan": "docs/unsafe_conditions_plan.md",
        "dataset": "Jsohal174/warehouse-safety-hazard-dataset (CC BY 4.0, synthetic)",
        "split": args.split,
        "prompt": args.prompt,
        "model": args.model,
        "images": len(rows),
        "errors": len(rows) - len(ok),
        "hazards": {h: _metrics(ok, preds, h) for h in HAZARDS},
        "sensitivity_without_ambiguous": {
            h: _metrics([r for r in ok if not ambiguous(r, h)], preds, h) for h in HAZARDS
        },
        "latency": latency_summary([preds[r["file_name"]]["latency_ms"] for r in rows][1:]),
        "environment": {"python": platform.python_version(), "date": datetime.now(UTC).isoformat(timespec="seconds")},
    }
    metrics["mean_mcc"] = sum(metrics["hazards"][h]["mcc"] for h in HAZARDS) / len(HAZARDS)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    for h in HAZARDS:
        m = metrics["hazards"][h]
        print(
            f"{h:12} pos {m['positives']}/{len(ok)} P={m['precision'] or 0:.3f} R={m['recall'] or 0:.3f} "
            f"Spec={m['specificity'] or 0:.3f} MCC={m['mcc']:.3f} -> {'PASS' if m['pass'] else 'FAIL'}"
        )
    lat = metrics["latency"]
    print(
        f"mean MCC {metrics['mean_mcc']:.3f}; latency p50 {lat.get('p50_ms', 0):.0f} ms p95 {lat.get('p95_ms', 0):.0f} ms"
    )
    print(f"-> {out / 'metrics.json'}")


if __name__ == "__main__":
    main()
