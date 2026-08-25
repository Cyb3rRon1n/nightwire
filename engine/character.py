from dataclasses import dataclass, field


@dataclass
class CharacterSheet:
    player_id: str
    name: str
    role: str
    lifepath: str
    attributes: dict[str, int] = field(default_factory=dict)
    health: int = 100
    max_health: int = 100
    armor: int = 0
    conditions: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    portrait_path: str | None = None
    skills: dict[str, int] = field(default_factory=dict)
    unspent_skill_points: int = 0
