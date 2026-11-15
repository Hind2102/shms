from shms.detection.base import Box
from shms.detection.rules import hazards_from_boxes


def codes(boxes):
    return {s.code for s in hazards_from_boxes(boxes)}


def B(label, x1, y1, x2, y2, c=0.9):
    return Box(label, c, x1, y1, x2, y2)


def test_head_without_helmet_is_hazard():
    assert codes([B("head", .40, .10, .50, .22)]) == {"no_hard_hat"}


def test_helmet_on_head_is_safe():
    assert "no_hard_hat" not in codes([B("head", .40, .10, .50, .22), B("helmet", .40, .08, .50, .16)])


def test_helmet_sitting_just_above_head_box_counts():
    # Some annotators box the face/head below the helmet: helmet lies above the head box.
    assert "no_hard_hat" not in codes([B("head", .40, .14, .50, .24), B("helmet", .40, .09, .50, .15)])


def test_helmet_elsewhere_does_not_cover_head():
    assert "no_hard_hat" in codes([B("head", .40, .10, .50, .22), B("helmet", .80, .70, .90, .80)])


def test_two_workers_one_bare_head():
    boxes = [B("head", .1, .1, .2, .2), B("helmet", .1, .08, .2, .15), B("head", .6, .1, .7, .2)]
    s = hazards_from_boxes(boxes)
    assert [x.code for x in s] == ["no_hard_hat"]
    assert len(s[0].evidence) == 1


def test_person_without_vest():
    assert "no_hi_vis_vest" in codes([B("person", .2, .1, .5, .9)])


def test_person_with_vest_or_safety_suit():
    assert "no_hi_vis_vest" not in codes([B("person", .2, .1, .5, .9), B("safety-vest", .25, .3, .45, .55)])
    assert "no_hi_vis_vest" not in codes([B("person", .2, .1, .5, .9), B("safety-suit", .2, .2, .5, .9)])


def test_vest_of_other_person_does_not_count():
    boxes = [B("person", .0, .1, .3, .9), B("person", .6, .1, .9, .9), B("safety-vest", .05, .3, .25, .55)]
    s = hazards_from_boxes(boxes)
    assert s[0].code == "no_hi_vis_vest" and len(s[0].evidence) == 1


def test_bare_hand_and_gloved_hand():
    assert "no_gloves" in codes([B("hands", .3, .5, .35, .56)])
    assert "no_gloves" not in codes([B("hands", .3, .5, .35, .56), B("gloves", .3, .5, .35, .56)])


def test_tiny_background_objects_ignored():
    assert codes([B("person", .1, .1, .12, .12), B("head", .5, .5, .505, .505)]) == set()


def test_confidence_is_max_of_evidence():
    s = hazards_from_boxes([B("head", .1, .1, .2, .2, c=.4), B("head", .5, .1, .6, .2, c=.8)])
    assert s[0].confidence == .8


def test_label_spelling_is_normalised():
    assert codes([B("Safety_Vest", .25, .3, .45, .55), B("Person", .2, .1, .5, .9)]) == set()


def test_no_people_no_hazards():
    assert codes([B("tool", .1, .1, .3, .3)]) == set()
