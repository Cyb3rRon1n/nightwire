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
    unspent_attribute_points: int = 0
    # Phase 17a chrome + humanity
    humanity: int = 100
    chrome: list[str] = field(default_factory=list)
    installments_owed: int = 0
    slipping_warned: bool = False
    gone_too_far: bool = False
    # Phase 17b debt loop
    repo_clock: int = 0
    repo_actions: int = 0
    repo_strikes: int = 0
    throttled: str | None = None
    pending_repo: str | None = None
    # Phase 17c utsusemi origin
    bodiless: bool = False
    awake_reached: bool = False
    # Phase 19a: optional, drives the portrait subject tag (1girl / 1boy / 1other).
    presentation: str | None = None


def is_tsukumogami(character: CharacterSheet) -> bool:
    return character.lifepath == "tsukumogami"
