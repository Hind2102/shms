"""The release gate decides which hazard types the app may use, from held-out evaluation results."""

import json

import pytest
from sqlalchemy import select

from evaluation.release_gate import decide
from shms import services, taxonomy
from shms.models import Area, Role, User
from shms.settings import override_settings

GATE = {"min_precision": 0.8, "min_recall": 0.75, "min_specificity": 0.8, "max_latency_p95_ms": 20000}


def metrics(spec_vest=0.58, p95=150.0):
    good = {"precision": 0.96, "recall": 0.96, "specificity": 0.9, "mcc": 0.85, "f1": 0.96}
    hz = {h: dict(good) for h in ("no_hard_hat", "no_eye_protection", "no_gloves", "no_hi_vis_vest")}
    hz["no_hi_vis_vest"]["specificity"] = spec_vest
    return {"run": "r", "detector": "yolo:x", "scored_images": 1620, "hazards": hz, "latency_steady": {"p95_ms": p95}}


def test_gate_rejects_low_specificity():
    d = decide(metrics(), GATE)
    assert d["approved"] == ["no_hard_hat", "no_eye_protection", "no_gloves"]
    assert "specificity" in d["rejected"]["no_hi_vis_vest"][0]


def test_gate_rejects_everything_when_too_slow():
    d = decide(metrics(spec_vest=0.9, p95=25000), GATE)
    assert d["approved"] == [] and all("latency" in r[-1] for r in d["rejected"].values())


def test_app_only_uses_released_hazards(settings, empty_db, tmp_path):
    release = tmp_path / "ai_release.json"
    release.write_text(json.dumps({"approved": ["no_hard_hat", "no_eye_protection", "no_gloves"]}))
    override_settings(ai_release_file=release)
    assert taxonomy.enabled_codes() == ["no_hard_hat", "no_eye_protection", "no_gloves"]
    dig = empty_db.scalar(select(Area).where(Area.code == "DIG"))
    assert "no_hi_vis_vest" not in dig.check_codes  # area requires it, but the AI check is not released
    rep = empty_db.scalar(select(User).where(User.role == Role.REPORTER))
    h = services.create_draft(empty_db, rep, dig, "x.jpg", None)
    with pytest.raises(services.WorkflowError):
        services.confirm(empty_db, h, rep, services.Confirmation("no_hi_vis_vest", 3))


def test_shipped_release_matches_shipped_results():
    """The committed app config must be exactly what the gate decides from the committed results."""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    shipped = root / "shms" / "config" / "ai_release.json"
    results = root / "evaluation" / "results"
    if not shipped.is_file():
        pytest.skip("no release file shipped")
    rel = json.loads(shipped.read_text())
    m_file = results / rel["run"] / "metrics.json"
    if not m_file.is_file():
        pytest.skip("evaluation results not present")
    gate = json.loads((root / "evaluation" / "release_gate.json").read_text())
    assert decide(json.loads(m_file.read_text()), gate)["approved"] == rel["approved"]
