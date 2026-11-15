"""Evaluation metrics (pure Python, unit-tested in tests/test_metrics.py)."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


def binary_counts(y_true: Sequence[bool], y_pred: Sequence[bool]) -> dict[str, int]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t and p)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if not t and p)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t and not p)
    tn = len(y_true) - tp - fp - fn
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def _safe_div(a: float, b: float) -> float | None:
    return a / b if b else None


def prf(c: dict[str, int]) -> dict[str, float | None]:
    p = _safe_div(c["tp"], c["tp"] + c["fp"])
    r = _safe_div(c["tp"], c["tp"] + c["fn"])
    f1 = _safe_div(2 * p * r, p + r) if p is not None and r is not None else None
    acc = _safe_div(c["tp"] + c["tn"], sum(c.values()))
    return {"precision": p, "recall": r, "f1": f1, "accuracy": acc}


def binary_metrics(y_true: Sequence[bool], y_pred: Sequence[bool]) -> dict:
    c = binary_counts(y_true, y_pred)
    return {**c, **prf(c), "support": c["tp"] + c["fn"], "n": len(y_true)}


def bootstrap_ci(
    y_true: Sequence[bool], y_pred: Sequence[bool], metric: str, n_boot: int = 1000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float] | None:
    """Percentile bootstrap confidence interval for precision / recall / f1 (images resampled)."""
    rng = random.Random(seed)
    n = len(y_true)
    if n == 0:
        return None
    values = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        v = prf(binary_counts([y_true[i] for i in idx], [y_pred[i] for i in idx]))[metric]
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    lo = values[int((alpha / 2) * (len(values) - 1))]
    hi = values[int((1 - alpha / 2) * (len(values) - 1))]
    return (lo, hi)


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion k/n."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float | None:
    """Agreement between two raters beyond chance (1 = perfect, 0 = chance level)."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    po = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1:
        return 1.0 if po == 1 else None
    return (po - pe) / (1 - pe)


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def latency_summary(ms: Sequence[float]) -> dict:
    if not ms:
        return {"n": 0}
    return {
        "n": len(ms),
        "mean_ms": sum(ms) / len(ms),
        "p50_ms": percentile(ms, 50),
        "p95_ms": percentile(ms, 95),
        "max_ms": max(ms),
    }
