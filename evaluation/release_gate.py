"""Release gate (MLOps lecture): decide, from held-out results, which hazard types the AI may be used for.

    python -m evaluation.release_gate --run yolo_sh17_yolo9e

Reads evaluation/results/<run>/metrics.json and the thresholds in evaluation/release_gate.json, prints a
pass/fail table, and writes shms/config/ai_release.json. The web app enables only the approved hazard types,
so a change of model or data can never silently enable an unproven check.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .sh17 import HAZARDS

HERE = Path(__file__).resolve().parent
RELEASE_FILE = HERE.parent / "shms" / "config" / "ai_release.json"


def decide(metrics: dict, gate: dict) -> dict:
    lat = metrics.get("latency_steady", {}).get("p95_ms")
    lat_ok = lat is not None and lat <= gate["max_latency_p95_ms"]
    approved, rejected = [], {}
    for h in HAZARDS:
        m = metrics["hazards"][h]
        reasons = []
        for key, label in (("precision", "precision"), ("recall", "recall"), ("specificity", "specificity")):
            v = m.get(key)
            if v is None or v < gate[f"min_{key}"]:
                reasons.append(f"{label} {v if v is None else round(v, 3)} < {gate[f'min_{key}']}")
        if not lat_ok:
            reasons.append(f"latency p95 {lat} ms > {gate['max_latency_p95_ms']} ms")
        if reasons:
            rejected[h] = reasons
        else:
            approved.append(h)
    return {
        "run": metrics["run"],
        "detector": metrics["detector"],
        "images": metrics["scored_images"],
        "approved": approved,
        "rejected": rejected,
        "per_hazard": {
            h: {k: metrics["hazards"][h].get(k) for k in ("precision", "recall", "specificity", "mcc", "f1")}
            for h in HAZARDS
        },
        "latency_p95_ms": lat,
        "gate": {k: v for k, v in gate.items() if not k.startswith("_")},
        "decided_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="yolo_sh17_yolo9e", help="results folder of a full held-out run")
    ap.add_argument("--dry-run", action="store_true", help="print the decision without writing the app config")
    args = ap.parse_args()
    metrics = json.loads((HERE / "results" / args.run / "metrics.json").read_text())
    if metrics.get("split", "test") != "test":
        raise SystemExit("The release gate only accepts results on the held-out test split.")
    gate = json.loads((HERE / "release_gate.json").read_text())
    d = decide(metrics, gate)
    for h in HAZARDS:
        p = d["per_hazard"][h]
        verdict = "APPROVED" if h in d["approved"] else "REJECTED: " + "; ".join(d["rejected"][h])
        print(f"{h:18s} P={p['precision']:.3f} R={p['recall']:.3f} Spec={p['specificity']:.3f}  {verdict}")
    if not args.dry_run:
        RELEASE_FILE.write_text(json.dumps(d, indent=2) + "\n")
        print(f"-> {RELEASE_FILE}")


if __name__ == "__main__":
    main()
