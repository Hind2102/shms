"""Risk matrix = ADOSH-SF Technical Guideline 'Process of Risk Management' v4.0 (15 July 2024), Tables 1-3.

The expected grid below was transcribed cell by cell from the coloured Table 3 on p. 10 of the PDF
(SHA-256 f271e33d…, see docs/risk_matrix_source.md): green = Low, yellow = Moderate, orange = High, red = Extreme.
It is written out literally on purpose, so a change to the config cannot silently change the test.
"""

import pytest

from shms import risk

L, M, H, E = "Low", "Moderate", "High", "Extreme"
# Rows: likelihood 1 Rare .. 5 Frequent/Almost certain; columns: consequence 1 Insignificant .. 5 Catastrophic.
TABLE_3 = [
    [L, L, L, M, M],  # Rare (1):      1  2  3  4  5
    [L, M, M, H, H],  # Possible (2):  2  4  6  8 10
    [L, M, H, H, E],  # Likely (3):    3  6  9 12 15
    [M, H, H, E, E],  # Often (4):     4  8 12 16 20
    [M, H, E, E, E],  # Frequent (5):  5 10 15 20 25
]


@pytest.mark.parametrize("c", risk.LEVELS)
@pytest.mark.parametrize("lk", risk.LEVELS)
def test_every_matrix_cell_matches_the_guideline_table(c, lk):
    r = risk.score(c, lk)
    assert r.score == c * lk
    assert r.level == TABLE_3[lk - 1][c - 1]
    assert r.target_days > 0


def test_unassigned_scores_take_the_band_of_their_cell_colour():
    """Table 3's printed ranges (1-3, 4-6, 8-12, 15-25) skip 5, 9, 10 and 16; the cell colours assign them."""
    assert [risk.band_for(s).level for s in (5, 9, 10, 16)] == [M, H, H, E]


def test_bands_cover_1_to_25_without_gaps_or_overlaps():
    covered = [s for b in risk.bands() for s in range(b.min, b.max + 1)]
    assert sorted(covered) == list(range(1, 26))


def test_bands_use_the_guideline_names_ranges_and_action_text():
    bands = {b.level: b for b in risk.bands()}
    assert list(bands) == [L, M, H, E]
    assert {k: b.guideline_range for k, b in bands.items()} == {L: "1 - 3", M: "4 - 6", H: "8 - 12", E: "15 - 25"}
    assert bands[E].action == "Activity or industry should not proceed in current form."
    assert bands[L].action == "No immediate action required, unless escalation of risk is possible."
    assert bands[M].action == "Activity or industry can operate subject to management and /or modification."
    assert bands[H].action.startswith("Activity or industry should be modified to include remedial planning")


def test_level_names_follow_tables_1_and_2():
    assert [v["name"] for v in risk.consequence_levels().values()] == [
        "Insignificant",
        "Minor",
        "Moderate",
        "Major",
        "Catastrophic",
    ]
    assert [v["name"] for v in risk.likelihood_levels().values()] == [
        "Rare",
        "Possible",
        "Likely",
        "Often",
        "Frequent / Almost certain",
    ]
    assert [v["definition"] for v in risk.likelihood_levels().values()] == [
        "Never occurred",
        "Has occurred",
        "Has occurred more than once",
        "Occurs several times per year",
        "Occurs frequently",
    ]
    assert risk.consequence_levels()[4]["definition"] == "Single fatality."
    assert all(v["production_loss"] and v["cost"] for v in risk.consequence_levels().values())


@pytest.mark.parametrize("count,level", [(0, 1), (1, 2), (2, 3), (3, 4), (5, 4), (6, 5), (500, 5)])
def test_likelihood_from_history(count, level):
    """Project interpretation: similar hazards in the same area in the last 365 days."""
    assert risk.likelihood_from_history(count) == level
    assert risk.lookback_days() == 365


@pytest.mark.parametrize("bad", [0, 6, -1, 2.5, None])
def test_invalid_levels_rejected(bad):
    with pytest.raises(ValueError):
        risk.score(bad, 3)
    with pytest.raises(ValueError):
        risk.score(3, bad)


def test_negative_history_rejected():
    with pytest.raises(ValueError):
        risk.likelihood_from_history(-1)


def test_alert_levels():
    assert risk.is_alert_level(H) and risk.is_alert_level(E)
    assert not risk.is_alert_level(M) and not risk.is_alert_level(L)


@pytest.mark.parametrize("c", risk.LEVELS)
@pytest.mark.parametrize("lk", risk.LEVELS)
def test_alert_reason_for_every_cell(c, lk):
    r = risk.score(c, lk)
    reason = risk.alert_reason(c, r.level)
    if r.level in (H, E):
        assert reason == f"{r.level} risk"
    elif c >= 4:  # Major / Catastrophic consequence in a Low or Moderate cell (ADOSH-SF Sec. 5(b))
        assert reason and "Sec. 5(b)" in reason and f"consequence {c}" in reason
    else:
        assert reason is None


def test_hierarchy_of_controls_in_guideline_order():
    assert list(risk.control_types()) == ["elimination", "substitution", "engineering", "procedural", "ppe"]
    assert "last resort" in risk.control_types()["ppe"]["name"]


def test_guideline_reference():
    g = risk.guideline()
    assert g["version"] == "4.0" and g["date"] == "15 July 2024" and len(g["pdf_sha256"]) == 64
