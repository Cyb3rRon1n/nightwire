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
    # Phone: per-player contacts, threads and timing (engine/phone.py).
    phone: dict[str, dict] = field(default_factory=dict)
    # Suggested actions (spec 2026-11-18): player_id -> the chips shown after their last story turn.
    suggestions: dict[str, list[dict]] = field(default_factory=dict)
    # Who is in the scene (narrator/cast.py): named NPCs, and the location they belong to.
    present: list[str] = field(default_factory=list)
    cast_location: str | None = None
    drop_in_turn: int | None = None  # player turn of a keeper's last drop-in away from their place (narrator/cast.py)
    # NPC voices (narrator/voices.py): each character's last move, each type's line counter, this turn's sample lines.
    last_moves: dict[str, str] = field(default_factory=dict)
    type_turns: dict[str, int] = field(default_factory=dict)
    voice_lines: list[str] = field(default_factory=list)
    # Unfinished business (narrator/promises.py): open promises, and a journal of what is over.
    promises: list[dict] = field(default_factory=list)
    journal: list[dict] = field(default_factory=list)
    # Liked turns (narrator/ratings.py): the newest turn as a rating would save it, its rating, and calm check-ins.
    last_turn: dict | None = None
    last_rating: dict | None = None
    checkin_open: bool = False
    checkin_turn: int | None = None
