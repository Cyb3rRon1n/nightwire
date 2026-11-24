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
    npc_memory: dict[str, list[dict]] = field(default_factory=dict)  # narrator/memory.py; old saves: strings
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
    # The director (narrator/director.py): tension 0-10, breather turns left, quiet turns in a row, event id -> turn.
    tension: int = 0
    breather: int = 0
    quiet_turns: int = 0
    events_used: dict[str, int] = field(default_factory=dict)
    # Emerging characters (narrator/people.py): name -> {who, what, district, place, turn, weight, returned}.
    people: dict[str, dict] = field(default_factory=dict)
    # Places that grow (narrator/places.py): place -> {heat, warmth, marks, last_visit, warmed}.
    places: dict[str, dict] = field(default_factory=dict)
    # Pressure clocks (narrator/clocks.py): clock id -> {filled, night, rest_until}.
    clocks: dict[str, dict] = field(default_factory=dict)
    # Word that spreads (narrator/gossip.py): deeds with who knows them and how strongly.
    deeds: list[dict] = field(default_factory=list)
    gossip_turn: int | None = None
    # The night clock (narrator/clock.py): night number, stretch 0-4, the turn the stretch began, the district last seen.
    night: int = 1
    stretch: int = 0
    stretch_start: int | None = 0  # None: a save from before the clock; set on the first tick
    clock_district: str | None = None
    sleepers: list[str] = field(default_factory=list)  # players asleep, waiting for the rest of the party
