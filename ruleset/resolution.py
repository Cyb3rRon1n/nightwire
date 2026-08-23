from enum import Enum


class Outcome(str, Enum):
    CLEAN_SUCCESS = "clean_success"
    COMPLICATION = "complication"
    FAILURE = "failure"


def resolve_roll(die_result: int, attribute_mod: int, skill_mod: int, dc: int) -> Outcome:
    if die_result == 10:
        return Outcome.CLEAN_SUCCESS
    if die_result == 1:
        return Outcome.FAILURE

    total = die_result + attribute_mod + skill_mod
    if total >= dc + 5:
        return Outcome.CLEAN_SUCCESS
    if total >= dc:
        return Outcome.COMPLICATION
    return Outcome.FAILURE
