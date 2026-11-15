"""Download the pre-trained SH17 YOLO weights (published by the dataset authors) and verify them.

    python scripts/download_models.py            # yolo8s (22 MB, default for the app)
    python scripts/download_models.py --all      # also yolo9e (117 MB, most accurate in the SH17 paper)

Source: https://github.com/ahmadmughees/SH17dataset/releases/tag/v1
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/ahmadmughees/SH17dataset/releases/download/v1"
MODELS = {
    "yolo8s": ("yolo8s.pt", "dfaf451bdda3f92fe4012327e337225929ad7af22146b00e0d6989c2f4e40a4b"),
    "yolo9e": ("yolo9e.pt", "5ac6ac236da0f5cee84418f38170de67e314404f7a63a97c74ba5d172e33f39d"),
}
OUT = Path(__file__).resolve().parent.parent / "models"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(key: str) -> Path:
    fname, digest = MODELS[key]
    dest = OUT / f"sh17_{fname}"
    if dest.is_file() and sha256(dest) == digest:
        print(f"{dest.name}: already present, checksum OK")
        return dest
    OUT.mkdir(exist_ok=True)
    print(f"Downloading {BASE}/{fname} ...")
    urllib.request.urlretrieve(f"{BASE}/{fname}", dest)
    if sha256(dest) != digest:
        dest.unlink()
        sys.exit(f"Checksum mismatch for {fname}; download removed. Try again.")
    print(f"{dest.name}: downloaded, checksum OK")
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="also download yolo9e")
    args = ap.parse_args()
    for k in ["yolo8s", "yolo9e"] if args.all else ["yolo8s"]:
        fetch(k)
