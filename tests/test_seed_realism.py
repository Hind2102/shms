"""v1.4.1: the synthesized demo history is realistic under the v1.4.0 ADOSH-SF rules (seed fixed)."""

from collections import Counter
from datetime import datetime

import pytest
from sqlalchemy import select

from shms import db as dbmod
from shms import risk, taxonomy
from shms.models import Hazard, Status
from shms.seed import PPE_FINDINGS, seed


@pytest.fixture(scope="module")
def history():
    dbmod.init_engine("sqlite://")
    dbmod.create_all()
    with dbmod.new_session() as s:
        seed(s, now=datetime(2026, 11, 25, 12, 0))
        yield [h for h in s.scalars(select(Hazard)) if h.status != Status.DRAFT]


def test_band_distribution_is_realistic(history):
    share = {k: v / len(history) for k, v in Counter(h.risk_level for h in history).items()}
    assert 0.30 <= share.get("Low", 0) <= 0.40
    assert 0.30 <= share.get("Moderate", 0) <= 0.40
    assert 0.15 <= share.get("High", 0) <= 0.25
    assert share.get("Extreme", 0) <= 0.08


def test_scores_follow_the_v140_rules(history):
    for h in history:
        r = risk.score(h.consequence, h.likelihood)
        assert (h.risk_score, h.risk_level) == (r.score, r.level)


def test_most_ppe_findings_are_consequence_2_or_3_and_c4_has_a_stated_context(history):
    ppe = [h for h in history if h.category_code in PPE_FINDINGS]
    assert sum(h.consequence in (2, 3) for h in ppe) / len(ppe) >= 0.9
    assert all(h.consequence <= 4 for h in history)
    assert all(
        len(h.description) > len(f"Synthetic report: {taxonomy.get(h.category_code).name.lower()}.")
        for h in history
        if h.consequence == 4
    )


def test_area_profiles_differ(history):
    """Caustic areas: more eye/face and glove findings; bauxite handling: more hard-hat findings."""

    def share(areas, codes):
        hs = [h for h in history if h.area.code in areas]
        return sum(h.category_code in codes for h in hs) / len(hs)

    caustic, bauxite = {"DIG", "CLR", "FLT", "TNK"}, {"BXH"}
    assert share(caustic, {"no_eye_protection", "no_gloves"}) > share(bauxite, {"no_eye_protection", "no_gloves"})
    assert share(bauxite, {"no_hard_hat"}) > share(caustic, {"no_hard_hat"})


def test_physical_conditions_are_reported_too(history):
    assert {h.category_code for h in history} & set(taxonomy.manual_codes())
    assert sum(h.category_code not in PPE_FINDINGS for h in history) >= len(history) // 5


def test_closure_controls_are_mixed_and_residual_never_exceeds_original(history):
    closed = [h for h in history if h.control_type]
    mix = Counter(h.control_type for h in closed)
    assert set(mix) == set(risk.control_types())
    assert mix["procedural"] > mix["elimination"] and mix["engineering"] > mix["substitution"]
    assert (mix["elimination"] + mix["substitution"]) / len(closed) <= 0.12  # rare
    assert all(h.residual_consequence <= h.consequence for h in closed)
