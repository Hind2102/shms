from shms.detection.base import Box
from shms.detection.rules import hazards_from_boxes


def codes(boxes):
    return {s.code for s in hazards_from_boxes(boxes)}


def B(label, x1, y1, x2, y2, c=0.9):
    return Box(label, c, x1, y1, x2, y2)


def test_head_without_helmet_is_hazard():
    assert codes([B("head", 0.40, 0.10, 0.50, 0.22)]) == {"no_hard_hat"}


def test_helmet_on_head_is_safe():
    assert "no_hard_hat" not in codes([B("head", 0.40, 0.10, 0.50, 0.22), B("helmet", 0.40, 0.08, 0.50, 0.16)])


def test_helmet_sitting_just_above_head_box_counts():
    # Some annotators box the face/head below the helmet: helmet lies above the head box.
    assert "no_hard_hat" not in codes([B("head", 0.40, 0.14, 0.50, 0.24), B("helmet", 0.40, 0.09, 0.50, 0.15)])


def test_helmet_elsewhere_does_not_cover_head():
    assert "no_hard_hat" in codes([B("head", 0.40, 0.10, 0.50, 0.22), B("helmet", 0.80, 0.70, 0.90, 0.80)])


def test_two_workers_one_bare_head():
    boxes = [B("head", 0.1, 0.1, 0.2, 0.2), B("helmet", 0.1, 0.08, 0.2, 0.15), B("head", 0.6, 0.1, 0.7, 0.2)]
    s = hazards_from_boxes(boxes)
    assert [x.code for x in s] == ["no_hard_hat"]
    assert len(s[0].evidence) == 1


def test_person_without_vest():
    assert "no_hi_vis_vest" in codes([B("person", 0.2, 0.1, 0.5, 0.9)])


def test_person_with_vest_or_safety_suit():
    assert "no_hi_vis_vest" not in codes([B("person", 0.2, 0.1, 0.5, 0.9), B("safety-vest", 0.25, 0.3, 0.45, 0.55)])
    assert "no_hi_vis_vest" not in codes([B("person", 0.2, 0.1, 0.5, 0.9), B("safety-suit", 0.2, 0.2, 0.5, 0.9)])


def test_vest_of_other_person_does_not_count():
    boxes = [B("person", 0.0, 0.1, 0.3, 0.9), B("person", 0.6, 0.1, 0.9, 0.9), B("safety-vest", 0.05, 0.3, 0.25, 0.55)]
    s = hazards_from_boxes(boxes)
    assert s[0].code == "no_hi_vis_vest" and len(s[0].evidence) == 1


def test_bare_hand_and_gloved_hand():
    assert "no_gloves" in codes([B("hands", 0.3, 0.5, 0.35, 0.56)])
    assert "no_gloves" not in codes([B("hands", 0.3, 0.5, 0.35, 0.56), B("gloves", 0.3, 0.5, 0.35, 0.56)])


def test_tiny_background_objects_ignored():
    assert codes([B("person", 0.1, 0.1, 0.12, 0.12), B("head", 0.5, 0.5, 0.505, 0.505)]) == set()


def test_confidence_is_max_of_evidence():
    s = hazards_from_boxes([B("head", 0.1, 0.1, 0.2, 0.2, c=0.4), B("head", 0.5, 0.1, 0.6, 0.2, c=0.8)])
    assert s[0].confidence == 0.8


def test_label_spelling_is_normalised():
    assert codes([B("Safety_Vest", 0.25, 0.3, 0.45, 0.55), B("Person", 0.2, 0.1, 0.5, 0.9)]) == set()


def test_no_people_no_hazards():
    assert codes([B("tool", 0.1, 0.1, 0.3, 0.3)]) == set()


def test_face_without_eye_protection():
    assert "no_eye_protection" in codes([B("face", 0.40, 0.12, 0.48, 0.22)])


def test_glasses_or_face_guard_protect_face():
    face = B("face", 0.40, 0.12, 0.48, 0.22)
    assert "no_eye_protection" not in codes([face, B("glasses", 0.41, 0.14, 0.47, 0.17)])
    assert "no_eye_protection" not in codes([face, B("face-guard", 0.39, 0.10, 0.49, 0.23)])


def test_medical_mask_is_not_eye_protection():
    assert "no_eye_protection" in codes([B("face", 0.40, 0.12, 0.48, 0.22), B("face-mask", 0.41, 0.17, 0.47, 0.22)])
