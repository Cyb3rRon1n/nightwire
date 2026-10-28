from enum import IntEnum


class Difficulty(IntEnum):
    # Retuned in Phase 17a for a d10 game: with ~+2 starting modifiers, Hard
    # succeeds ~30% (the old 16 was beatable only on a natural 10).
    EASY = 6
    MODERATE = 9
    HARD = 12
    EXTREME = 15
