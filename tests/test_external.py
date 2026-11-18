"""External validation script (evaluation/external_hardhat.py) on a miniature fake dataset."""

import json

from PIL import Image

from evaluation import external_hardhat as ext


def _fake(tmp_path):
    (tmp_path / "data").mkdir()
    samples = []
    specs = {
        "bare.png": [("head", [0.4, 0.1, 0.2, 0.2])],  # head without hard hat -> positive
        "hat.png": [("helmet", [0.4, 0.1, 0.2, 0.2])],  # hard hat only -> negative
        "tiny.png": [("head", [0.5, 0.5, 0.01, 0.01])],  # head below the rule's size threshold
        "empty.png": [],
    }
    for i, (name, dets) in enumerate(specs.items()):
        Image.new("RGB", (416, 416), (i * 40, 90, 160 - i * 30)).save(tmp_path / "data" / name)
        samples.append(
            {
                "filepath": f"data/{name}",
                "metadata": {"width": 416, "height": 416},
                "ground_truth": {"detections": [{"label": lab, "bounding_box": bb} for lab, bb in dets]},
            }
        )
    (tmp_path / "samples.json").write_text(json.dumps({"samples": samples}))
    return tmp_path


def test_labels_use_the_same_rule_engine_and_the_raw_variant(tmp_path):
    rows = {r["image"]: r for r in ext.load_rows(_fake(tmp_path))}
    assert rows["data/bare.png"]["gt"] is True and rows["data/bare.png"]["gt_raw"] is True
    assert rows["data/hat.png"]["gt"] is False and rows["data/hat.png"]["gt_raw"] is False
    assert rows["data/tiny.png"]["gt"] is False and rows["data/tiny.png"]["gt_raw"] is True  # rule's size threshold
    assert rows["data/empty.png"]["gt"] is False


def test_verdict_follows_the_preregistered_thresholds():
    ok = {"precision": 0.9, "recall": 0.8, "specificity": 0.85}
    assert ext.verdict(ok)["pass"] is True
    for k in ok:
        bad = dict(ok, **{k: 0.5})
        assert ext.verdict(bad)["pass"] is False


def test_near_duplicates_are_found_by_dhash(tmp_path):
    root = _fake(tmp_path)
    ref = {"same.png": ext.dhash(root / "data" / "bare.png")}
    found = ext.find_near_duplicates({"data/bare.png": root / "data" / "bare.png"}, ref)
    assert found == {"data/bare.png": "same.png"}
