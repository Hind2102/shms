"""Classification of disagreements between model and derived labels (evaluation/label_rule_audit.py)."""

from evaluation.label_rule_audit import classify
from shms.detection.base import Box


def b(label, x1, y1, x2, y2):
    return Box(label, 0.9, x1, y1, x2, y2)


PERSON = b("person", 0.2, 0.1, 0.6, 0.9)
VEST = b("safety-vest", 0.3, 0.3, 0.5, 0.6)


def test_vest_false_alarm_without_any_labelled_person():
    assert classify("no_hi_vis_vest", "FP", gt=[], pred=[PERSON]) == "no person box in the labels"


def test_vest_false_alarm_with_a_too_small_labelled_person():
    tiny = b("person", 0.1, 0.1, 0.12, 0.12)
    assert classify("no_hi_vis_vest", "FP", gt=[tiny], pred=[PERSON]) == "labelled person below the rule's size limit"


def test_vest_false_alarm_where_the_model_missed_a_labelled_vest():
    assert classify("no_hi_vis_vest", "FP", gt=[PERSON, VEST], pred=[PERSON]) == "PPE labelled, model missed it"


def test_hard_hat_miss_where_the_model_found_no_head():
    head = b("head", 0.3, 0.1, 0.4, 0.2)
    assert classify("no_hard_hat", "FN", gt=[head], pred=[]) == "model found no head"


def test_hard_hat_miss_where_a_predicted_helmet_covers_the_bare_head():
    head = b("head", 0.3, 0.1, 0.4, 0.2)
    helmet = b("helmet", 0.3, 0.05, 0.4, 0.15)
    assert classify("no_hard_hat", "FN", gt=[head], pred=[head, helmet]) == "model saw PPE that is not in the labels"
