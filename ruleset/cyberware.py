"""Phase 17a chrome catalog and humanity rules - see
docs/superpowers/specs/2026-10-27-chrome-humanity-17a-design.md."""

from dataclasses import dataclass, field

from ruleset.attributes import modifier

SOCIAL_SKILLS = ("persuasion", "performance")


@dataclass(frozen=True)
class Overclock:
    bonus: int
    second_die: bool
    skill: str | None  # None = usable on any roll


@dataclass(frozen=True)
class Chrome:
    id: str
    name: str
    description: str
    humanity_cost: int
    installments: int
    roll_bonus: dict[str, int] = field(default_factory=dict)
    armor: int = 0
    max_health: int = 0
    overclock: Overclock | None = None


CHROME: dict[str, Chrome] = {c.id: c for c in (
    Chrome("hawkeye_optics", "Hawkeye optics", "Zoom, low-light and threat-tagging eyes.", 3, 2, {"perception": 1}),
    Chrome("reflex_wires", "Reflex wires", "Boosted nerve paths for a faster trigger finger.", 6, 3, {"ranged_combat": 1}),
    Chrome("kagerou", "Kagerou", "A spine-mounted time-dilation rig; the world slows when you push it.", 10, 5,
           overclock=Overclock(bonus=2, second_die=True, skill=None)),
    Chrome("kama_blades", "Kama blades", "Forearm blades that unfold like a sickle.", 8, 4, {"melee": 2}),
    Chrome("oni_arms", "Oni arms", "Heavy cyberarms built for lifting and breaking.", 7, 4, {"melee": 1, "athletics": 1}),
    Chrome("lacquer_skin", "Lacquer skin", "Subdermal plating under a glossy finish.", 6, 3, armor=10),
    Chrome("yomi_jack", "Yomi jack", "A neural port that goes deeper into the net than it should.", 5, 3, {"hacking": 1},
           overclock=Overclock(bonus=3, second_die=False, skill="hacking")),
    Chrome("pain_editor", "Pain editor", "Filters pain signals so you keep moving.", 5, 3, max_health=15),
    Chrome("silk_tongue", "Silk tongue", "A voice modulator tuned to sound trustworthy.", 3, 2, {"persuasion": 1}),
    Chrome("kumo_hand", "Kumo hand", "A multi-tool hand with eight fine manipulators.", 3, 2, {"engineering": 1}),
    Chrome("neon_ink", "Neon ink", "Fashionware: living light under the skin.", 0, 1),
)}


def slot_capacity(attributes: dict) -> int:
    return max(2, 3 + modifier(attributes.get("body", 10)))


def humanity_tier(humanity: int) -> str:
    if humanity >= 70:
        return "Steady"
    if humanity >= 40:
        return "Frayed"
    if humanity >= 20:
        return "Slipping"
    if humanity >= 1:
        return "Edge"
    return "Gone too far"


def social_penalty(humanity: int) -> int:
    return 0 if humanity >= 40 else -1 if humanity >= 20 else -2


def overclock_tier_bonus(humanity: int) -> int:
    return 1 if humanity < 40 else 0


def chrome_roll_bonus(chrome_ids: list[str], skill: str) -> int:
    return sum(CHROME[c].roll_bonus.get(skill, 0) for c in chrome_ids)
