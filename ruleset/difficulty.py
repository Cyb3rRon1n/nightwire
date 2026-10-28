from enum import IntEnum


class Difficulty(IntEnum):
    # Retuned in Phase 17a for a d10 game. Success incl. complication at +2
    # total: Easy 70%, Moderate 40%, Hard 10% (natural 10 only), Extreme 10%;
    # at +4 (trained primary skill): 90/60/30/10. Values unchanged (owner-approved);
    # untrained Hard is natural-10-only.
    EASY = 6
    MODERATE = 9
    HARD = 12
    EXTREME = 15


STAKES: dict[str, Difficulty] = {
    "low": Difficulty.EASY,
    "normal": Difficulty.MODERATE,
    "high": Difficulty.HARD,
    "extreme": Difficulty.EXTREME,
}
_CAP_WINDOW = 6
_CAP_HIGH = 2
_HOT = ("high", "extreme")


def difficulty_for(stakes: str, recent: list[str]) -> tuple[str, Difficulty]:
    # Phase 18: the model rates stakes; the engine caps how often they run hot,
    # because qwen3:8b picked Hard on 13/13 risky rolls whatever the prompt said.
    # Once 2 of the last 6 effective stakes were high/extreme, both high and
    # extreme drop to normal - so a run of hot requests is at most half Hard+.
    window = recent[-_CAP_WINDOW:]
    if stakes in _HOT and sum(s in _HOT for s in window) >= _CAP_HIGH:
        stakes = "normal"
    return stakes, STAKES[stakes]
