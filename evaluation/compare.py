"""Summarise every run in evaluation/results/ into a comparison table and report figures.

    python -m evaluation.compare                 # all runs
    python -m evaluation.compare --only-subset   # runs on the shared 300-image subset

Writes evaluation/results/summary.md, summary.json, fig_f1.png and fig_pr.png.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sh17 import HAZARDS

RESULTS = Path(__file__).resolve().parent / "results"
LABELS = {"no_hard_hat": "No hard hat", "no_eye_protection": "No eye protection",
          "no_gloves": "No gloves", "no_hi_vis_vest": "No hi-vis vest"}
# Validated categorical palette (fixed order; values are direct-labelled because two slots are < 3:1 contrast)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, MUTED, GRID = "#1d2733", "#5f6b7a", "#e3e6ea"


def load_runs(only_subset: bool) -> list[dict]:
    runs = []
    for f in sorted(RESULTS.glob("*/metrics.json")):
        m = json.loads(f.read_text())
        if only_subset and not m["run"].endswith("_subset"):
            continue
        runs.append(m)
    return runs


def fmt(v, pct=False):
    if v is None:
        return "–"
    return f"{100 * v:.1f}" if pct else f"{v:.3f}"


def ci(v):
    return f" [{v[0]:.2f}–{v[1]:.2f}]" if v else ""


def table(runs: list[dict]) -> str:
    lines = ["| Run | Images | Hazard | Precision [95% CI] | Recall [95% CI] | F1 | Positives |",
             "|---|---:|---|---|---|---:|---:|"]
    for m in runs:
        for h in HAZARDS:
            x = m["hazards"][h]
            lines.append(f"| {m['run']} | {m['scored_images']} | {LABELS[h]} | {fmt(x['precision'])}{ci(x['precision_ci95'])} "
                         f"| {fmt(x['recall'])}{ci(x['recall_ci95'])} | {fmt(x['f1'])} | {x['support']} |")
    lines += ["", "| Run | Macro F1 | Micro P | Micro R | Latency p50 (s) | Latency p95 (s) | Errors |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for m in runs:
        lat = m["latency_steady"]
        mi = m["hazards"]["micro"]
        lines.append(f"| {m['run']} | {fmt(m['hazards']['macro_f1'])} | {fmt(mi['precision'])} | {fmt(mi['recall'])} "
                     f"| {lat.get('p50_ms', 0) / 1000:.2f} | {lat.get('p95_ms', 0) / 1000:.2f} | {m['errors']} |")
    maps = [m for m in runs if "detection_map" in m]
    if maps:
        lines += ["", "| Run | mAP50 | mAP50-95 | Box P | Box R |", "|---|---:|---:|---:|---:|"]
        for m in maps:
            d = m["detection_map"]
            lines.append(f"| {m['run']} | {fmt(d['mAP50'])} | {fmt(d['mAP50_95'])} | {fmt(d['precision'])} | {fmt(d['recall'])} |")
    return "\n".join(lines)


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_f1(runs: list[dict], path: Path) -> None:
    import matplotlib.pyplot as plt

    runs = runs[:4]
    fig, ax = plt.subplots(figsize=(7.5, 3.4), dpi=200)
    width = 0.8 / max(1, len(runs))
    for i, m in enumerate(runs):
        xs = [j + (i - (len(runs) - 1) / 2) * width for j in range(len(HAZARDS))]
        vals = [m["hazards"][h]["f1"] or 0 for h in HAZARDS]
        ax.bar(xs, vals, width * 0.92, color=PALETTE[i], label=m["run"], zorder=2)
        for x, v in zip(xs, vals):
            ax.text(x, v + 0.015, f"{v:.2f}", ha="center", va="bottom", fontsize=7.5, color=INK)
    ax.set_xticks(range(len(HAZARDS)), [LABELS[h] for h in HAZARDS], color=INK)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("F1 on held-out SH17 images", color=MUTED, fontsize=9)
    _style(ax)
    ax.legend(frameon=False, fontsize=8, ncol=min(4, len(runs)), loc="upper center", bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def fig_pr(runs: list[dict], path: Path) -> None:
    """Precision vs recall per hazard: YOLO threshold sweeps as lines, VLMs as single points."""
    import matplotlib.pyplot as plt

    runs = runs[:4]
    fig, axes = plt.subplots(1, len(HAZARDS), figsize=(11, 3.2), dpi=200, sharey=True)
    for ax, h in zip(axes, HAZARDS):
        for i, m in enumerate(runs):
            if "threshold_sweep" in m:
                pts = [(s[h]["recall"], s[h]["precision"]) for s in m["threshold_sweep"]
                       if s[h]["recall"] is not None and s[h]["precision"] is not None]
                ax.plot([p[0] for p in pts], [p[1] for p in pts], color=PALETTE[i], linewidth=2, label=m["run"])
                op = m["hazards"][h]
                ax.scatter([op["recall"] or 0], [op["precision"] or 0], s=40, color=PALETTE[i],
                           edgecolor="white", linewidth=1.5, zorder=3)
            else:
                op = m["hazards"][h]
                ax.scatter([op["recall"] or 0], [op["precision"] or 0], s=60, marker="D", color=PALETTE[i],
                           edgecolor="white", linewidth=1.5, zorder=3, label=m["run"])
        ax.set_title(LABELS[h], fontsize=10, color=INK)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("Recall", color=MUTED, fontsize=9)
        _style(ax)
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    axes[0].set_ylabel("Precision", color=MUTED, fontsize=9)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=8, ncol=min(4, len(labels)), loc="lower center",
               bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only-subset", action="store_true")
    args = ap.parse_args()
    runs = load_runs(args.only_subset)
    if not runs:
        raise SystemExit("No results yet. Run `python -m evaluation.evaluate ...` first.")
    md = table(runs)
    (RESULTS / "summary.md").write_text("# Evaluation summary (held-out SH17 split)\n\n" + md + "\n")
    (RESULTS / "summary.json").write_text(json.dumps(
        [{"run": m["run"], "macro_f1": m["hazards"]["macro_f1"], **{h: m["hazards"][h] for h in HAZARDS},
          "latency": m["latency_steady"]} for m in runs], indent=2))
    fig_f1(runs, RESULTS / "fig_f1.png")
    fig_pr(runs, RESULTS / "fig_pr.png")
    print(md)
    print(f"\nWrote {RESULTS / 'summary.md'}, fig_f1.png, fig_pr.png")


if __name__ == "__main__":
    main()
