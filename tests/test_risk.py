from narrator.risk import is_risky


class _Judge:
    def __init__(self, answer):
        self.answer = answer
    async def judge(self, messages, schema):
        return self.answer


async def test_a_typo_in_the_action_still_counts_as_risky():
    # Dry run 2026-11-06: "i sneek past teh gaurd lol" got "unknown" because the quote was spelled correctly.
    assert await is_risky(_Judge({"risky_quote": "sneak past the guard", "risky": True}), "i sneek past teh gaurd lol") is True


async def test_a_quote_about_something_else_is_still_unknown():
    assert await is_risky(_Judge({"risky_quote": "storm the vault", "risky": True}), "i sneek past teh gaurd lol") is None
