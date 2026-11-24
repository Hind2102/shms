"""Render a Markdown evidence summary of Hind's 100-photo SH17 audit without modifying the export."""

import argparse
import csv
import hashlib
import io
import random
from pathlib import Path

from .label_audit import DATA
from .metrics import cohen_kappa, wilson_ci
from .sh17 import HAZARDS

NAMES = {
    "no_hard_hat": "Hard hat",
    "no_eye_protection": "Eye or face protection",
    "no_gloves": "Gloves",
}


def read_verdicts(raw: bytes, expected: dict) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames != ["image", "hazard", "derived", "verdict"]:
        raise ValueError("Expected an original SH17 audit CSV export")
    seen = set()
    rows = []
    for row in reader:
        key = (row["image"], row["hazard"])
        if key in seen or key not in expected or row["derived"] != expected[key]:
            raise ValueError(f"Duplicate, unexpected or altered label: {key}")
        if None in row or row["verdict"] not in ("", "agree", "disagree"):
            raise ValueError(f"Invalid response: {key}")
        seen.add(key)
        rows.append(row)
    if seen != expected.keys():
        raise ValueError("Export is missing rows. Download the CSV again; unanswered items may be blank.")
    return rows


def result_row(hazard: str, rows: list[dict]) -> str:
    group = [row for row in rows if row["hazard"] == hazard]
    answered = [row for row in group if row["verdict"]]
    n = len(answered)
    agreed = sum(row["verdict"] == "agree" for row in answered)
    derived = [row["derived"] == "1" for row in answered]
    reviewer = [d if row["verdict"] == "agree" else not d for d, row in zip(derived, answered, strict=True)]
    interval = wilson_ci(agreed, n)
    rate = f"{agreed / n:.0%} ({interval[0]:.0%}–{interval[1]:.0%})" if interval else "—"
    kappa = cohen_kappa(derived, reviewer) if len(set(derived + reviewer)) > 1 else None
    kappa_text = f"{kappa:.2f}" if kappa is not None else "—"
    extra = sum(d and not r for d, r in zip(derived, reviewer, strict=True))
    missed = n - agreed - extra
    return f"| {NAMES[hazard]} | {n} | {len(group) - n} | {agreed}/{n} | {rate} | {kappa_text} | {extra} | {missed} |"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    raw = args.csv.read_bytes()
    with (DATA / "sh17_test_manifest.csv").open() as source:
        sample = random.Random(7).sample(list(csv.DictReader(source)), 100)
    expected = {(row["image"], h): row[f"gt_{h}"] for row in sample for h in HAZARDS}
    rows = [r for r in read_verdicts(raw, expected) if r["hazard"] in NAMES]
    print("# SH17 photo audit\n")
    print("Reviewer: Hind Alhmoudi · Single-reviewer assessment · 100 held-out photographs · Sampling seed 7\n")
    reviewed = sum(bool(row["verdict"]) for row in rows)
    print(f"**{reviewed} of {len(rows)} decisions recorded.** Blank responses are excluded from agreement.\n")
    print(
        "| PPE item | Answered | Blank | Matches | Agreement (95% Wilson CI) | Cohen’s κ | Extra flags | Missed flags |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for hazard in NAMES:
        print(result_row(hazard, rows))
    print(
        "\nAn extra flag means the derived label indicated missing PPE and the reviewer disagreed. "
        "A missed flag means the reviewer identified missing PPE where the derived label indicated none. "
        "A dash indicates an undefined statistic.\n"
    )
    print(
        "**Interpretation.** Agreement compares the reviewer’s visible-PPE judgement with labels derived "
        "from SH17 object boxes. Holding a glove differs from wearing it, and eyewear certification may be "
        "unreadable. The export records choices only; it cannot identify the reason for a particular decision. "
        "Earlier audit screens displayed the derived label. These figures measure single-reviewer agreement "
        "and cannot establish detector accuracy or agreement among three independent human annotators.\n"
    )
    print(f"**Source CSV SHA-256** `{hashlib.sha256(raw).hexdigest()}`")


if __name__ == "__main__":
    main()
