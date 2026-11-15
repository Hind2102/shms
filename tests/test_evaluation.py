"""Evaluation code is tested too: metrics against hand-computed values, and the pipeline on a tiny fake SH17."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from evaluation import metrics as M
from evaluation.sh17 import find_layout, gt_hazards, read_boxes, read_list

ROOT = Path(__file__).resolve().parent.parent


def test_binary_metrics_hand_computed():
    y_true = [1, 1, 1, 0, 0, 0, 1, 0]
    y_pred = [1, 1, 0, 1, 0, 0, 1, 0]
    m = M.binary_metrics([bool(x) for x in y_true], [bool(x) for x in y_pred])
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (3, 1, 1, 3)
    assert m["precision"] == 0.75 and m["recall"] == 0.75 and m["f1"] == 0.75 and m["accuracy"] == 0.75


def test_metrics_undefined_when_no_predictions():
    m = M.binary_metrics([True, False], [False, False])
    assert m["precision"] is None and m["recall"] == 0.0 and m["f1"] is None


def test_bootstrap_ci_contains_point_estimate():
    y_true = [True] * 30 + [False] * 30
    y_pred = [True] * 24 + [False] * 6 + [True] * 6 + [False] * 24
    lo, hi = M.bootstrap_ci(y_true, y_pred, "precision")
    assert lo <= 0.8 <= hi and hi - lo < 0.4


def test_wilson_and_kappa():
    lo, hi = M.wilson_ci(90, 100)
    assert 0.82 < lo < 0.84 and 0.94 < hi < 0.95
    assert M.cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert M.cohen_kappa([True, True, False, False], [True, False, True, False]) == 0.0


def test_latency_percentiles():
    s = M.latency_summary([float(x) for x in range(1, 101)])
    assert s["p50_ms"] == pytest.approx(50.5) and s["p95_ms"] == pytest.approx(95.05) and s["max_ms"] == 100


def make_fake_sh17(root: Path, n: int = 12) -> None:
    (root / "data" / "images").mkdir(parents=True)
    (root / "data" / "labels").mkdir(parents=True)
    names = []
    for i in range(n):
        name = f"pexels-photo-{i}.jpeg"
        names.append(name)
        Image.new("RGB", (320, 240), (i * 20 % 255, 80, 80)).save(root / "data" / "images" / name)
        lines = ["0 0.5 0.5 0.4 0.8", "12 0.5 0.2 0.1 0.1"]  # person + head
        if i % 2:
            lines.append("10 0.5 0.17 0.1 0.08")  # helmet on head
        if i % 3 == 0:
            lines.append("16 0.5 0.45 0.25 0.2")  # vest
        (root / "data" / "labels" / f"pexels-photo-{i}.txt").write_text("\n".join(lines))
    (root / "data" / "val_files.txt").write_text("\n".join(f"./images/{n}" for n in names))
    (root / "data" / "train_files.txt").write_text("other.jpeg\n")


def test_sh17_reader_and_derived_labels(tmp_path):
    make_fake_sh17(tmp_path)
    lay = find_layout(tmp_path)
    names = read_list(lay.test_list)
    assert names[0] == "pexels-photo-0.jpeg" and len(names) == 12
    gt0 = gt_hazards(read_boxes(lay.labels / "pexels-photo-0.txt"))
    gt1 = gt_hazards(read_boxes(lay.labels / "pexels-photo-1.txt"))
    assert gt0 == {"no_hard_hat": True, "no_eye_protection": False, "no_hi_vis_vest": False, "no_gloves": False}
    assert gt1 == {"no_hard_hat": False, "no_eye_protection": False, "no_hi_vis_vest": True, "no_gloves": False}


def test_pipeline_end_to_end_with_mock(tmp_path, monkeypatch):
    """prepare -> evaluate -> compare runs and produces consistent files (uses a copy of the evaluation folder)."""
    import shutil

    make_fake_sh17(tmp_path / "sh17")
    work = tmp_path / "repo"
    shutil.copytree(ROOT / "evaluation", work / "evaluation", ignore=shutil.ignore_patterns("data", "results"))
    shutil.copytree(ROOT / "shms", work / "shms")
    env = {"PYTHONPATH": str(work), "PATH": "/usr/bin:/bin", "SHMS_DETECTOR": "mock"}
    run = lambda *a: subprocess.run([sys.executable, "-m", *a], cwd=work, env=env, capture_output=True, text=True)  # noqa: E731
    r = run("evaluation.prepare_sh17", "--root", str(tmp_path / "sh17"), "--subset", "5", "--export-samples", "0")
    assert r.returncode == 0, r.stderr
    stats = json.loads((work / "evaluation" / "data" / "sh17_test_stats.json").read_text())
    assert stats["images_found"] == 12 and stats["subset_size"] == 5 and stats["positives_full"]["no_hard_hat"] == 6
    r = run("evaluation.evaluate", "--root", str(tmp_path / "sh17"), "--detector", "mock")
    assert r.returncode == 0, r.stderr
    m = json.loads((work / "evaluation" / "results" / "mock" / "metrics.json").read_text())
    assert m["scored_images"] == 12 and set(m["hazards"]) >= {"no_hard_hat", "micro", "macro_f1"}
    r = run("evaluation.evaluate", "--root", str(tmp_path / "sh17"), "--detector", "mock")  # resumes from cache
    assert "12 cached, 0 to run" in r.stdout
    pytest.importorskip("matplotlib")
    r = run("evaluation.compare")
    assert r.returncode == 0, r.stderr
    assert (work / "evaluation" / "results" / "fig_f1.png").is_file()


def test_near_duplicate_detection(tmp_path):
    from evaluation.sh17 import dhash, near_duplicates

    base = Image.radial_gradient("L").convert("RGB").resize((400, 300))
    base.save(tmp_path / "train.jpg", quality=95)
    base.resize((200, 150)).save(tmp_path / "test_dup.jpg", quality=40)  # same photo, smaller, recompressed
    Image.linear_gradient("L").convert("RGB").resize((400, 300)).save(tmp_path / "test_new.jpg")
    test = {n: dhash(tmp_path / n) for n in ("test_dup.jpg", "test_new.jpg")}
    dups = near_duplicates(test, {"train.jpg": dhash(tmp_path / "train.jpg")})
    assert dups == {"test_dup.jpg": "train.jpg"}


def test_robustness_perturbations_keep_images_valid():
    from evaluation.robustness import PERTURBATIONS

    im = Image.new("RGB", (640, 480), (120, 130, 140))
    for name, (_, fn) in PERTURBATIONS.items():
        out = fn(im)
        assert out.mode == "RGB" and min(out.size) >= 32, name
