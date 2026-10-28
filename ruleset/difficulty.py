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
