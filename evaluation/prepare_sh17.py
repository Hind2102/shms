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

from .sh17 import (
    HAZARDS,
    SH17_NAMES,
    dhash,
    find_layout,
    gt_hazards,
    label_path,
    near_duplicates,
    read_boxes,
    read_list,
)

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
    ap.add_argument(
        "--dev",
        type=int,
        default=100,
        help="size of the dev set drawn from the TRAIN split, for tuning prompts (never the test set)",
    )
    ap.add_argument("--no-dup-check", action="store_true", help="skip the near-duplicate (train/test leakage) check")
    ap.add_argument(
        "--export-samples", type=int, default=6, help="copy N downscaled test images to data/samples/ for the demo"
    )
    args = ap.parse_args()

    lay = find_layout(args.root)
    if lay.test_list is None:
        raise SystemExit("Could not find val_files.txt or test_files.txt in the SH17 folder")
    images = read_list(lay.test_list)
    train = set(read_list(lay.train_list)) if lay.train_list else set()
    leak = train.intersection(images)
    print(f"Held-out split: {lay.test_list.name} with {len(images)} images; overlap with train list: {len(leak)}")

    # Leakage check (data-engineering lecture): an exact file overlap is not enough; the same photo can be
    # in both splits under different names or sizes. Compare perceptual hashes of test vs train images.
    dups: dict[str, str] = {}
    if not args.no_dup_check and train:
        print("Hashing images for the near-duplicate check ...", flush=True)
        th = {n: dhash(lay.images / n) for n in images if (lay.images / n).is_file()}
        tr = {n: dhash(lay.images / n) for n in train if (lay.images / n).is_file()}
        dups = near_duplicates(th, tr)
        print(f"Near-duplicates of training images inside the test split: {len(dups)}")

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
        row = {
            "image": name,
            "in_subset": int(name in subset),
            "near_dup_train": int(name in dups),
            "n_boxes": len(boxes),
        }
        row.update(
            {
                f"n_{c}": sum(1 for b in boxes if b.label == c)
                for c in ("person", "head", "helmet", "face", "glasses", "face-guard", "hands", "gloves", "safety-vest")
            }
        )
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
        "split_file": lay.test_list.name,
        "images_listed": len(images),
        "images_found": len(rows),
        "images_missing": missing,
        "train_test_overlap": len(leak),
        "subset_size": len(sub_rows),
        "seed": args.seed,
        "near_duplicate_check": "skipped" if args.no_dup_check or not train else "dHash 64-bit, <= 4 bits",
        "near_duplicates_of_train": len(dups),
        "helmets_overlapping_a_head_pct": round(100 * helmet_hits / helmet_total, 1) if helmet_total else None,
        "prevalence_full": {h: round(sum(r[f"gt_{h}"] for r in rows) / len(rows), 3) for h in HAZARDS},
        "prevalence_subset": {
            h: round(sum(r[f"gt_{h}"] for r in sub_rows) / max(1, len(sub_rows)), 3) for h in HAZARDS
        },
        "positives_full": {h: sum(r[f"gt_{h}"] for r in rows) for h in HAZARDS},
        "class_instances": {c: cls_counts.get(c, 0) for c in SH17_NAMES},
    }
    (OUT_DIR / "sh17_test_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    print(f"Manifest written to {out}")

    # Dev set: images from the TRAIN split, used only to tune prompts / thresholds, so the held-out test
    # split is touched once, for the final numbers. (The VLM was never trained on SH17, so train images are
    # unbiased for it; they are NOT suitable for tuning YOLO, which was trained on them.)
    if args.dev and train:
        dev_names = sorted(n for n in train if (lay.images / n).is_file())
        dev_names = random.Random(args.seed).sample(dev_names, min(args.dev, len(dev_names)))
        dev_rows = []
        for name in dev_names:
            gt = gt_hazards(read_boxes(label_path(lay, name)))
            dev_rows.append({"image": name, "in_subset": 0, **{f"gt_{k}": int(v) for k, v in gt.items()}})
        dev_out = OUT_DIR / "sh17_dev_manifest.csv"
        if dev_rows:
            with dev_out.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(dev_rows[0]))
                w.writeheader()
                w.writerows(dev_rows)
            print(f"Dev manifest ({len(dev_rows)} train-split images) written to {dev_out}")
        else:
            print("No training images found on disk; dev manifest not written.")

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
