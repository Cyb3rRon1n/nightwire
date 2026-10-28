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
    pending_initiative: dict[str, int] = field(default_factory=dict)
    last_turn_had_image: bool = False
    narrative_summary: str = ""
    narrative_summary_line_count: int = 0
    npc_memory: dict[str, list[str]] = field(default_factory=dict)
    # Rolls the narrator requested that the player hasn't rolled yet
    # (two-step rolls, Phase 16): player_id -> RequestRoll args + dc + name.
    pending_rolls: dict[str, dict] = field(default_factory=dict)
    # Phase 17a: a chrome-ya's standing offer per player, and engine events
    # (e.g. the confrontation scene) the next prompt build shows once.
    pending_chrome_offers: dict[str, str] = field(default_factory=dict)
    pending_world_events: list[str] = field(default_factory=list)
    # Phase 18: effective stakes of recent rolls, for the "high" cap.
    recent_stakes: list[str] = field(default_factory=list)
