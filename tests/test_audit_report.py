import pytest

from evaluation.audit_report import read_verdicts, result_row


def test_original_verdicts_and_unanswered_are_distinct():
    raw = b"image,hazard,derived,verdict\na.jpg,no_gloves,1,disagree\nb.jpg,no_gloves,0,\n"
    expected = {("a.jpg", "no_gloves"): "1", ("b.jpg", "no_gloves"): "0"}
    rows = read_verdicts(raw, expected)
    assert result_row("no_gloves", rows) == "| Gloves | 1 | 1 | 0/1 | 0% (0%–79%) | 0.00 | 1 | 0 |"
    with pytest.raises(ValueError):
        read_verdicts(raw.replace(b"1,disagree", b"0,disagree"), expected)
    with pytest.raises(ValueError):
        read_verdicts(raw + b"b.jpg,no_gloves,0,agree\n", expected)
