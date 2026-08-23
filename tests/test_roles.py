from ruleset.attributes import Attribute
from ruleset.roles import ROLES, Role


def test_four_roles_exist():
    assert set(ROLES.keys()) == {"solo", "netrunner", "techie", "fixer"}


def test_each_role_has_a_valid_primary_attribute():
    for role in ROLES.values():
        assert isinstance(role, Role)
        assert isinstance(role.primary_attribute, Attribute)


def test_solo_keys_off_reflexes():
    assert ROLES["solo"].primary_attribute == Attribute.REFLEXES


def test_netrunner_and_techie_both_key_off_tech():
    assert ROLES["netrunner"].primary_attribute == Attribute.TECH
    assert ROLES["techie"].primary_attribute == Attribute.TECH


def test_fixer_keys_off_presence():
    assert ROLES["fixer"].primary_attribute == Attribute.PRESENCE


def test_every_role_has_a_nonempty_description():
    for role in ROLES.values():
        assert role.description.strip() != ""
