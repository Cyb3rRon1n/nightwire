from dataclasses import dataclass, field

from engine.character import CharacterSheet


@dataclass
class Session:
    session_id: str
    characters: dict[str, CharacterSheet] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)
    current_turn_index: int = 0
    in_combat: bool = False
    pre_combat_turn_order: list[str] | None = None
    log: list[str] = field(default_factory=list)
    location: str | None = None
    scene_mood: str | None = None
    active_objectives: list[str] = field(default_factory=list)
    speaker_voices: dict[str, str] = field(default_factory=dict)
