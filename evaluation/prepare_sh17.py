"""Build the held-out evaluation manifest from SH17.

    python -m evaluation.prepare_sh17 --root ~/datasets/sh17

Writes evaluation/data/sh17_test_manifest.csv: one row per image in SH17's held-out
split (never used to train the released weights), with object counts and the
ground-truth hazards derived by the same rule engine the app uses. A fixed
random subset (seed 42) is flagged for the slower vision-language models.
Also prints dataset statistics used in the report.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

from PIL import Image

from .sh17 import HAZARDS, SH17_NAMES, find_layout, gt_hazards, label_path, read_boxes, read_list

OUT_DIR = Path(__file__).resolve().parent / "data"


def helmet_head_overlap_share(boxes) -> tuple[int, int]:
    """How many helmets overlap a labelled head (checks whether SH17 labels heads under helmets)."""
    heads = [b for b in boxes if b.label == "head"]
    helmets = [b for b in boxes if b.label == "helmet"]
    hit = 0
    for hm in helmets:
        for hd in heads:
            w = min(hm.x2, hd.x2) - max(hm.x1, hd.x1)
            h = min(hm.y2, hd.y2) - max(hm.y1, hd.y1)
            if w > 0 and h > 0 and (w * h) / max(hm.area, 1e-9) >= 0.3:
                hit += 1
                break
    return hit, len(helmets)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="folder where the SH17 Kaggle zip was extracted")
    ap.add_argument("--subset", type=int, default=300, help="size of the fixed random subset for VLMs")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--export-samples", type=int, default=6,
                    help="copy N downscaled test images to data/samples/ for the demo")
    args = ap.parse_args()

    lay = find_layout(args.root)
    if lay.test_list is None:
        raise SystemExit("Could not find val_files.txt or test_files.txt in the SH17 folder")
    images = read_list(lay.test_list)
    train = set(read_list(lay.train_list)) if lay.train_list else set()
    leak = train.intersection(images)
    print(f"Held-out split: {lay.test_list.name} with {len(images)} images; overlap with train list: {len(leak)}")

    rng = random.Random(args.seed)
    subset = set(rng.sample(images, min(args.subset, len(images))))

    rows, cls_counts, helmet_hits, helmet_total, missing = [], Counter(), 0, 0, 0
    for name in images:
        img = lay.images / name
        if not img.is_file():
            missing += 1
            continue
        boxes = read_boxes(label_path(lay, name))
        cls_counts.update(b.label for b in boxes)
        h, t = helmet_head_overlap_share(boxes)
        helmet_hits, helmet_total = helmet_hits + h, helmet_total + t
        gt = gt_hazards(boxes)
        row = {"image": name, "in_subset": int(name in subset), "n_boxes": len(boxes)}
        row.update({f"n_{c}": sum(1 for b in boxes if b.label == c) for c in ("person", "head", "helmet", "hands", "gloves", "safety-vest")})
        row.update({f"gt_{k}": int(v) for k, v in gt.items()})
        rows.append(row)

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "sh17_test_manifest.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    sub_rows = [r for r in rows if r["in_subset"]]
    stats = {
        "split_file": lay.test_list.name, "images_listed": len(images), "images_found": len(rows),
        "images_missing": missing, "train_test_overlap": len(leak), "subset_size": len(sub_rows), "seed": args.seed,
        "helmets_overlapping_a_head_pct": round(100 * helmet_hits / helmet_total, 1) if helmet_total else None,
        "prevalence_full": {h: round(sum(r[f"gt_{h}"] for r in rows) / len(rows), 3) for h in HAZARDS},
        "prevalence_subset": {h: round(sum(r[f"gt_{h}"] for r in sub_rows) / max(1, len(sub_rows)), 3) for h in HAZARDS},
        "positives_full": {h: sum(r[f"gt_{h}"] for r in rows) for h in HAZARDS},
        "class_instances": {c: cls_counts.get(c, 0) for c in SH17_NAMES},
    }
    (OUT_DIR / "sh17_test_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    print(f"Manifest written to {out}")

    if args.export_samples:
        sample_dir = Path(__file__).resolve().parent.parent / "data" / "samples"
        sample_dir.mkdir(parents=True, exist_ok=True)
        picks = []
        for h in HAZARDS:  # one positive per hazard + negatives
            picks += [r for r in sub_rows if r[f"gt_{h}"]][:1]
        picks += [r for r in sub_rows if not any(r[f"gt_{h}"] for h in HAZARDS) and r["n_person"]][:3]
        for r in picks[: args.export_samples]:
            tag = "_".join(h for h in HAZARDS if r[f"gt_{h}"]) or "compliant"
            with Image.open(lay.images / r["image"]) as im:
                im = im.convert("RGB")
                im.thumbnail((1280, 1280))
                im.save(sample_dir / f"sh17_{Path(r['image']).stem}__{tag}.jpg", quality=88)
        print(f"Exported {min(len(picks), args.export_samples)} sample images to {sample_dir}")


if __name__ == "__main__":
    main()
