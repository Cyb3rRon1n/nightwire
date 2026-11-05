from tools.image_gate import judge

CLEAN = {"heads": 1, "hands": 2, "text_regions": 0, "age_hits": {}}


def test_clean_image_has_no_flags():
    assert judge(**CLEAN) == []


def test_age_tag_always_flags():
    assert judge(**{**CLEAN, "age_hits": {"child": 0.25}}) == ["age: child 0.25"]


def test_person_in_empty_shot_flags_even_when_only_a_body_is_found():
    assert judge(**{**CLEAN, "heads": 0, "hands": 0}, empty=True, persons=1) == ["people in an empty shot: 1"]


def test_wrong_head_count_flags():
    assert judge(**CLEAN, expected_people=2) == ["people: 1 heads, expected 2"]


def test_too_many_hands_flags():
    assert judge(**{**CLEAN, "hands": 3}) == ["hands: 3 for 1 heads"]


def test_lettering_flags():
    assert judge(**{**CLEAN, "text_regions": 2}) == ["lettering: 2 regions, check for gibberish"]


def test_likeness_flags_only_when_another_character_is_closer():
    assert judge(**CLEAN, rank=1, closest="kaede-mori") == []
    assert judge(**CLEAN, rank=3, closest="mitsu") == ["likeness: ranks 3 in the cast, closest is mitsu"]


def test_missing_required_detail_flags():
    assert judge(**CLEAN, missing=("green eyes",)) == ["missing: green eyes"]
