"""Phase 17b chrome debt loop: the repo clock and its escalation. Functions
return world-event strings; callers queue them on session.pending_world_events.
See docs/superpowers/specs/2026-10-28-debt-and-the-street-17b-design.md."""

from engine.character import CharacterSheet
from engine.chrome import _apply_stats, remove_chrome
from ruleset.cyberware import CHROME

_ACTIONS_PER_PIP = 10
_PIPS_PER_STRIKE = 6


def active_chrome(character: CharacterSheet) -> list[str]:
    return [c for c in character.chrome if c != character.throttled]


def _strike(character: CharacterSheet) -> str:
    character.repo_strikes += 1
    name = character.name
    if not character.chrome or character.repo_strikes == 1:
        return (f"Hoshikawa sends {name} a polite final notice; Saeko Kirigaya's torite crew "
                f"has been asking about {name}.")
    if character.repo_strikes == 2 and character.throttled is None:
        character.throttled = character.chrome[-1]
        _apply_stats(character, CHROME[character.throttled], -1)
        return f"{name}'s {CHROME[character.throttled].name} locks up: remote-throttled by Hoshikawa for missed payments."
    character.pending_repo = character.throttled or character.chrome[-1]
    return f"Saeko Kirigaya's torite crew comes for {name}'s {CHROME[character.pending_repo].name}."


def tick_debt(character: CharacterSheet) -> list[str]:
    if character.installments_owed <= 0:
        return []
    character.repo_actions += 1
    if character.repo_actions < _ACTIONS_PER_PIP:
        return []
    character.repo_actions = 0
    character.repo_clock += 1
    if character.repo_clock < _PIPS_PER_STRIKE:
        return []
    character.repo_clock = 0
    return [_strike(character)]


def _clear_throttle(character: CharacterSheet) -> None:
    if character.throttled is not None:
        _apply_stats(character, CHROME[character.throttled], +1)
        character.throttled = None


def pay_installment(character: CharacterSheet, amount: int) -> None:
    if amount <= 0:
        return
    character.installments_owed = max(0, character.installments_owed - amount)
    character.repo_clock = character.repo_actions = 0
    _clear_throttle(character)
    character.pending_repo = None
    if character.installments_owed == 0:
        character.repo_strikes = 0


def repossess(character: CharacterSheet) -> str:
    if character.pending_repo is None:
        raise ValueError("no repo pending")
    chrome_id = character.pending_repo
    remove_chrome(character, chrome_id)  # half refund; clears throttled/pending_repo pointers
    return chrome_id


def unthrottle(character: CharacterSheet) -> None:
    if character.throttled is None:
        raise ValueError("nothing is throttled")
    _clear_throttle(character)
