"""Load test (non-functional testing, Lecture 4): how does the running service behave when several people
report at the same time, e.g. during a shift change or a site-wide PPE campaign?

Start the app with the detector you want to test, then:
    uvicorn shms.asgi:app --port 8000                       # in one terminal (SHMS_DETECTOR=yolo)
    python -m evaluation.load_test --image data/samples/<photo>.jpg --users 1 4 8 --requests 40

Each virtual user sends photos to POST /api/detect back-to-back. Reports throughput, latency p50/p95 and
errors per concurrency level, and writes evaluation/results/load_test_<detector>.json.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .metrics import latency_summary

RESULTS = Path(__file__).resolve().parent / "results"


def _headers(args) -> dict:
    """API token (normal mode) or, with SHMS_DEMO_HEADER_AUTH=1 on the server, the demo X-User-Id header."""
    return {"Authorization": f"Bearer {args.token}"} if args.token else {"X-User-Id": args.user_id}


def run_level(url: str, image: bytes, users: int, total: int, auth_headers: dict) -> dict:
    lat, errors, model = [], 0, None

    def one(_):
        nonlocal errors, model
        t0 = time.perf_counter()
        try:
            r = httpx.post(
                f"{url}/api/detect",
                headers=auth_headers,
                timeout=300,
                files={"photo": ("load.jpg", image, "image/jpeg")},
            )
            ok = r.status_code == 200 and not r.json().get("error")
            model = model or (r.json().get("model") if r.status_code == 200 else None)
        except httpx.HTTPError:
            ok = False
        dt = (time.perf_counter() - t0) * 1000
        if ok:
            lat.append(dt)
        else:
            errors += 1

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=users) as pool:
        list(pool.map(one, range(total)))
    wall = time.perf_counter() - t0
    return {
        "users": users,
        "requests": total,
        "errors": errors,
        "model": model,
        "throughput_rps": round(len(lat) / wall, 3),
        "wall_s": round(wall, 2),
        **latency_summary(lat),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--users", type=int, nargs="+", default=[1, 4, 8])
    ap.add_argument("--requests", type=int, default=40, help="requests per concurrency level")
    ap.add_argument("--token", default="", help="API token: python -m shms.tokens create <username>")
    ap.add_argument("--user-id", default="1", help="only with SHMS_DEMO_HEADER_AUTH=1 on the server")
    args = ap.parse_args()
    image = args.image.read_bytes()
    httpx.post(
        f"{args.url}/api/detect",
        headers=_headers(args),
        files={"photo": ("warm.jpg", image, "image/jpeg")},
        timeout=300,
    )  # warm-up
    levels = []
    for u in args.users:
        r = run_level(args.url, image, u, args.requests, _headers(args))
        levels.append(r)
        print(
            f"{u:3d} users: {r['throughput_rps']:6.2f} req/s  p50 {r.get('p50_ms', 0):7.0f} ms  "
            f"p95 {r.get('p95_ms', 0):7.0f} ms  errors {r['errors']}",
            flush=True,
        )
    model = next((lv["model"] for lv in levels if lv["model"]), "unknown")
    out = {"model": model, "image": args.image.name, "machine": platform.platform(), "levels": levels}
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"load_test_{model.replace(':', '_').replace('/', '_')}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"-> {path}")


if __name__ == "__main__":
    main()
