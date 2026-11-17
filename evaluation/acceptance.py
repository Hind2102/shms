"""Simulated reporter acceptance (the proposal's success criterion: >= 80 % of AI classifications accepted
by the reporter without changes).

Real acceptance can only be measured in field use (the app records it, see /monitoring). On the labelled
held-out split we can simulate it: a reporter keeps the AI's suggestion when its top suggestion (among the
released hazard types) is a violation that is really in the photo, and must change it when the suggestion is
wrong or when the AI suggests nothing although a violation is present.

    python -m evaluation.acceptance --run yolo_sh17_yolo9e

Writes evaluation/results/acceptance_<run>.json.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from shms.detection.base import Box
from shms.detection.rules import hazards_from_boxes

from .metrics import wilson_ci

HERE = Path(__file__).resolve().parent


def simulate(manifest_rows: list[dict], preds: dict[str, dict], released: list[str], conf: float) -> dict:
    n = accepted = wrong_type = nothing = 0
    for r in manifest_rows:
        gt = {h for h in released if r[f"gt_{h}"] == "1"}
        if not gt or r["image"] not in preds:
            continue
        n += 1
        p = preds[r["image"]]
        if p.get("boxes"):  # YOLO: re-apply the rules at the operating threshold
            boxes = [Box(**b) for b in p["boxes"] if b["confidence"] >= conf]
            sugg = [(s.code, s.confidence) for s in hazards_from_boxes(boxes) if s.code in released]
        else:  # VLM: stored suggestions
            sugg = [(s["code"], s["confidence"]) for s in p.get("suggestions", []) if s["code"] in released]
        if not sugg:
            nothing += 1
            continue
        top = max(sugg, key=lambda s: s[1])[0]
        if top in gt:
            accepted += 1
        else:
            wrong_type += 1
    return {
        "images_with_violation": n,
        "accepted_unchanged": accepted,
        "acceptance_rate": accepted / n if n else None,
        "acceptance_ci95": wilson_ci(accepted, n),
        "wrong_type_suggested": wrong_type,
        "nothing_suggested": nothing,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="yolo_sh17_yolo9e")
    ap.add_argument("--conf", type=float, default=0.35)
    args = ap.parse_args()
    release = json.loads((HERE.parent / "shms" / "config" / "ai_release.json").read_text())
    released = release["approved"]
    manifest = "sh17_test_manifest.csv"
    with (HERE / "data" / manifest).open() as f:
        rows = list(csv.DictReader(f))
    preds = {}
    for line in (HERE / "results" / args.run / "predictions.jsonl").read_text().splitlines():
        p = json.loads(line)
        preds[p["image"]] = p
    out = {
        "run": args.run,
        "released_hazards": released,
        "operating_threshold": args.conf,
        "target": 0.80,
        **simulate(rows, preds, released, args.conf),
    }
    path = HERE / "results" / f"acceptance_{args.run}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    lo, hi = out["acceptance_ci95"]
    print(
        f"{args.run}: {out['accepted_unchanged']}/{out['images_with_violation']} = {out['acceptance_rate']:.1%} "
        f"[{lo:.1%}–{hi:.1%}] accepted unchanged (target 80 %); wrong type {out['wrong_type_suggested']}, "
        f"nothing suggested {out['nothing_suggested']} -> {path}"
    )


if __name__ == "__main__":
    main()
