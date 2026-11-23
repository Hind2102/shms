from evaluation.external_floor_liquid import positive_summary


def test_positive_only_result_counts_errors_as_misses_and_withholds_false_alarm_metrics():
    result = positive_summary([{"detected": True}, {"detected": False}, {"error": "timeout"}])
    assert result["detected"] == 1 and result["errors"] == 1
    assert result["recall"] == 1 / 3
    assert result["precision"] is None and result["specificity"] is None
