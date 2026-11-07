from narrator.ooc import answer_ooc, is_ooc


def test_out_of_character_markers_and_undo_are_recognised():
    for text in ("(ooc) how do I check my inventory?", "OOC: what does Cool do?", "((brb))", "// how do rolls work", "undo that, I didn't mean to", "Undo"):
        assert is_ooc(text), text
    for text in ("I ask Mama Sato what's good tonight.", "I undo the knot on the bag.", "(I whisper) stay back"):
        assert not is_ooc(text), text


class _Judge:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []
    async def judge(self, messages, schema):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.answer


async def test_the_help_desk_answers_from_the_game_guide():
    judge = _Judge({"answer": "Your inventory is in the Status panel on the left."})
    assert await answer_ooc(judge, "(ooc) how do I check my inventory?") == "Your inventory is in the Status panel on the left."
    assert "Status panel" in judge.calls[0][0]["content"]  # the guide is in the system prompt


async def test_a_failed_help_desk_still_answers():
    assert "Status panel" in await answer_ooc(_Judge(error=RuntimeError("down")), "(ooc) where is my sheet?")
