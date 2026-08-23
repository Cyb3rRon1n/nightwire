from dataclasses import dataclass, field


@dataclass
class CharacterSheet:
    player_id: str
    name: str
    role: str
    lifepath: str
    attributes: dict[str, int] = field(default_factory=dict)
    health: int = 10
    max_health: int = 10
    armor: int = 0
    conditions: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
