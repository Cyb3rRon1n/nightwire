from enum import Enum


class Attribute(str, Enum):
    BODY = "body"
    REFLEXES = "reflexes"
    TECH = "tech"
    COOL = "cool"
    INTELLECT = "intellect"
    PRESENCE = "presence"


def modifier(score: int) -> int:
    return (score - 10) // 2
