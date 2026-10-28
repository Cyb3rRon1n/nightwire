"""Stateful chrome + humanity operations on a CharacterSheet (Phase 17a).
Functions return world-event strings; callers queue them on
session.pending_world_events for the next prompt."""

from engine.character import CharacterSheet, is_tsukumogami
from ruleset.cyberware import CHROME, Chrome, overclock_tier_bonus, slot_capacity

_CONFRONTATION = (
    "{name} is slipping - someone close to them has noticed what the chrome is doing "
    "and confronts them about it."
)
SHELL_INSTALLMENTS = 4
STARTING_SELFHOOD = 20

_AWAKE = "{name} feels it settle: they're someone now, not something."


def change_humanity(character: CharacterSheet, delta: int) -> list[str]:
    character.humanity = max(0, min(100, character.humanity + delta))
    if character.humanity == 0:
        character.gone_too_far = True
    elif character.humanity > 20:
        character.gone_too_far = False
    if is_tsukumogami(character):
        # Selfhood climbs; the 17a slipping confrontation is for humans.
        if character.humanity >= 80 and not character.awake_reached:
            character.awake_reached = True
            return [_AWAKE.format(name=character.name)]
        return []
    if character.humanity < 40 and not character.slipping_warned:
        character.slipping_warned = True
        return [_CONFRONTATION.format(name=character.name)]
    return []


def _apply_stats(character: CharacterSheet, chrome: Chrome, sign: int) -> None:
    # ponytail: throttle->unthrottle/pay can restore armor that was damaged below the chrome's
    # contribution (clamp at 0 loses the exact amount); upgrade = store the actually-removed amount.
    character.armor = max(0, character.armor + sign * chrome.armor)
    character.max_health += sign * chrome.max_health
    character.health = min(character.health, character.max_health)


def install_chrome(character: CharacterSheet, chrome_id: str) -> list[str]:
    chrome = CHROME.get(chrome_id)
    if chrome is None:
        raise ValueError(f"unknown chrome: {chrome_id!r}")
    if chrome_id in character.chrome:
        raise ValueError(f"{chrome.name} is already installed")
    if len(character.chrome) >= slot_capacity(character.attributes):
        raise ValueError("no free chrome slot")
    if character.bodiless:
        raise ValueError("no shell to install chrome in")
    if character.gone_too_far:
        raise ValueError("humanity too low for new chrome")
    character.chrome.append(chrome_id)
    _apply_stats(character, chrome, +1)
    character.installments_owed += chrome.installments
    cost = 0 if is_tsukumogami(character) else chrome.humanity_cost
    return change_humanity(character, -cost)


def remove_chrome(character: CharacterSheet, chrome_id: str) -> list[str]:
    if chrome_id not in character.chrome:
        raise ValueError(f"{chrome_id!r} is not installed")
    chrome = CHROME[chrome_id]
    character.chrome.remove(chrome_id)
    if character.throttled != chrome_id:
        _apply_stats(character, chrome, -1)
    if character.throttled == chrome_id:
        character.throttled = None
    if character.pending_repo == chrome_id:
        character.pending_repo = None
    refund = 0 if is_tsukumogami(character) else chrome.humanity_cost // 2
    return change_humanity(character, refund)


def usable_overclocks(character: CharacterSheet, skill: str) -> list[dict]:
    if character.gone_too_far:
        return []
    bonus_tier = overclock_tier_bonus(character.humanity)
    usable = []
    for chrome_id in character.chrome:
        oc = CHROME[chrome_id].overclock
        if chrome_id == character.throttled or oc is None or (oc.skill is not None and oc.skill != skill):
            continue
        text = f"+{oc.bonus + bonus_tier}" + (", roll twice keep higher" if oc.second_die else "")
        usable.append({"id": chrome_id, "name": CHROME[chrome_id].name, "bonus_text": text})
    return usable
