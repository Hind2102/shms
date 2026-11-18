"""Unsafe-conditions experiment (evaluation/conditions.py, shms/detection/conditions_vlm.py)."""

import json

from evaluation import conditions as cond
from shms.detection.conditions_vlm import parse_answer


def _row(cat, subtype="", accept=""):
    return {"file_name": f"{cat}/x.jpg", "category": cat, "subtype": subtype, "accept_also": accept}


def test_labels_follow_the_preregistered_rules():
    assert cond.labels(_row("spill")) == {"spill": True, "obstruction": False}
    assert cond.labels(_row("obstacle")) == {"spill": False, "obstruction": True}
    both = _row("spill", "dark fluid with tipped container (spill + obstacle)")
    assert cond.labels(both) == {"spill": True, "obstruction": True}
    assert cond.labels(_row("spill", "oil/dark liquid with obstacle"))["obstruction"] is True
    assert cond.labels(_row("forklift_violation")) == {"spill": False, "obstruction": False}


def test_ambiguous_means_accept_also_names_an_absent_hazard():
    assert cond.ambiguous(_row("safe", accept="spill"), "spill") is True
    assert cond.ambiguous(_row("spill", accept="spill"), "spill") is False  # present anyway
    assert cond.ambiguous(_row("safe"), "obstruction") is False


def test_dev_sample_is_deterministic_and_stratified():
    rows = [
        _row(c) | {"file_name": f"{c}/{i}.jpg"}
        for c in ("spill", "obstacle", "safe", "improper_stacking")
        for i in range(30)
    ]
    a, b = cond.dev_sample(rows), cond.dev_sample(rows)
    assert a == b and len(a) == 60
    assert {c: sum(r["category"] == c for r in a) for c in ("spill", "obstacle", "safe")} == {
        "spill": 20,
        "obstacle": 20,
        "safe": 20,
    }


def test_blocked_walkway_requires_a_visible_walkway():
    ans = {"floor_liquid_visible": False, "walkway_visible": False, "walkway_obstructed": True, "explanation": "x"}
    assert parse_answer(json.dumps(ans)) == {"spill": False, "obstruction": False, "explanation": "x"}
    ans |= {"walkway_visible": True, "floor_liquid_visible": True}
    assert parse_answer(json.dumps(ans)) == {"spill": True, "obstruction": True, "explanation": "x"}
