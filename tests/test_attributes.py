from ruleset.attributes import Attribute, modifier


def test_all_six_attributes_exist():
    assert {a.value for a in Attribute} == {
        "body", "reflexes", "tech", "cool", "intellect", "presence",
    }


def test_modifier_formula():
    assert modifier(10) == 0
    assert modifier(11) == 0
    assert modifier(12) == 1
    assert modifier(8) == -1
    assert modifier(20) == 5
    assert modifier(3) == -4
