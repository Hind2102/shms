import pytest

from shms import risk

EXPECTED_LEVEL = {range(1, 5): "Low", range(5, 10): "Medium", range(10, 17): "High", range(17, 26): "Extreme"}


def expected(score):
    return next(v for r, v in EXPECTED_LEVEL.items() if score in r)


@pytest.mark.parametrize("c", risk.LEVELS)
@pytest.mark.parametrize("lk", risk.LEVELS)
def test_every_matrix_cell(c, lk):
    r = risk.score(c, lk)
    assert r.score == c * lk
    assert r.level == expected(c * lk)
    assert r.target_days > 0


def test_bands_cover_every_possible_score_without_gaps():
    covered = set()
    for b in risk.bands():
        covered |= set(range(b.min, b.max + 1))
    assert {c * lk for c in risk.LEVELS for lk in risk.LEVELS} <= covered


@pytest.mark.parametrize("count,level", [(0, 1), (1, 2), (2, 2), (3, 3), (5, 3), (6, 4), (10, 4), (11, 5), (500, 5)])
def test_likelihood_from_history(count, level):
    assert risk.likelihood_from_history(count) == level


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
    assert risk.is_alert_level("High") and risk.is_alert_level("Extreme")
    assert not risk.is_alert_level("Medium") and not risk.is_alert_level("Low")


def test_every_level_has_a_definition():
    assert set(risk.consequence_levels()) == set(risk.LEVELS)
    assert set(risk.likelihood_levels()) == set(risk.LEVELS)
    assert all(v["definition"] for v in risk.consequence_levels().values())
