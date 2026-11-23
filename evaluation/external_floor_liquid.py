"""Positive-only challenge on the version-pinned Mendeley indoor water series."""

import argparse
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

import httpx

from evaluation.metrics import wilson_ci
from evaluation.sh17 import dhash
from shms.detection.conditions_vlm import FROZEN_PROMPT, ask

ARCHIVE_SHA = "427e336858a996ee967abdbfc94c5582b96f496ed85d3261632183d47dd39f40"
ROOT = "Stagnant Water and Wet Surface Dataset"
MODEL = "qwen2.5vl:7b"
URL = "http://localhost:11434"


def positive_summary(rows: list[dict]) -> dict:
    n = len(rows)
    hits = sum(row.get("detected") is True for row in rows)
    return {
        "eligible_tested": n,
        "detected": hits,
        "errors": sum("error" in row for row in rows),
        "recall": hits / n if n else None,
        "wilson95": wilson_ci(hits, n),
        "precision": None,
        "specificity": None,
    }


def select_images(archive: Path, directory: Path) -> tuple[int, list[tuple[str, Path]]]:
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA:
            raise ValueError("Expected Mendeley v4 December archive (see docs/external_floor_liquid.md)")
    images = []
    with zipfile.ZipFile(archive) as source:
        if source.read(f"{ROOT}/classes.txt").decode().strip().splitlines() != ["water", "wet surface"]:
            raise ValueError("Unexpected label mapping")
        for member in source.namelist():
            filename = Path(member)
            if filename.parent.as_posix() != f"{ROOT}/Indoor/Top View" or filename.suffix.lower() != ".jpeg":
                continue
            labels = source.read(str(filename.with_suffix(".txt"))).decode().splitlines()
            if not labels:
                continue
            for line in labels:
                cls, *box = line.split()
                if cls not in {"0", "1"} or len(box) != 4 or not all(0 <= float(v) <= 1 for v in box):
                    raise ValueError(f"Invalid box in {member}")
            path = directory / filename.name
            data = source.read(member)
            path.write_bytes(data)
            images.append((hashlib.sha256(data).hexdigest(), path))
    selected = []
    hashes = []
    for digest, path in sorted(images):
        fingerprint = dhash(path)
        if all((fingerprint ^ other).bit_count() > 4 for other in hashes):
            hashes.append(fingerprint)
            selected.append((digest, path))
            if len(selected) == 32:
                break
    return len(images), selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path, help="New JSON file (existing evidence is never overwritten)")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output file")
    with tempfile.TemporaryDirectory() as directory:
        eligible, selected = select_images(args.archive, Path(directory))
        if not selected:
            raise ValueError("No eligible labelled indoor images")
        response = httpx.get(f"{URL}/api/tags")
        response.raise_for_status()
        digest = next(m["digest"] for m in response.json()["models"] if m["name"] == MODEL)
        rows = []
        for sha, path in selected:
            row = {"file": path.name, "sha256": sha}
            try:
                row["detected"] = ask(path, FROZEN_PROMPT, MODEL, URL)["spill"]
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                row["error"] = type(exc).__name__
            rows.append(row)
    result = {
        "dataset_doi": "10.17632/y6zyrnxbfm.4",
        "archive_sha256": ARCHIVE_SHA,
        "eligible_before_selection": eligible,
        "model": MODEL,
        "model_digest": digest,
        "prompt": FROZEN_PROMPT,
        "predictions": rows,
        "summary": positive_summary(rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        out.write(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
