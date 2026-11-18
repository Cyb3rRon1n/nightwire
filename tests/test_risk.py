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


# The set-up must stop before the outcome (playthrough 2026-11-07: the lie and the jump resolved in the set-up).
from narrator.client import NarrationSegment, NarratorResponse  # noqa: E402
from narrator.risk import cut_at_outcome, leaked_outcome  # noqa: E402

_SETUP = "You meet his eyes and tell him the Arakawa sent you. He believes every word and waves you through."


class _Broken:
    async def judge(self, messages, schema):
        raise RuntimeError("model down")


async def test_a_set_up_that_gives_the_outcome_away_is_caught_with_its_words():
    judge = _Judge({"evidence": "He believes every word", "result": "succeeded"})
    assert await leaked_outcome(judge, "I lie to the guard.", _SETUP) == "He believes every word"


async def test_a_clean_set_up_an_ungrounded_claim_or_a_failed_check_all_pass():
    assert await leaked_outcome(_Judge({"evidence": "", "result": "not_shown"}), "I lie.", _SETUP) is None
    assert await leaked_outcome(_Judge({"evidence": "the lock clicks open", "result": "succeeded"}), "I lie.", _SETUP) is None
    assert await leaked_outcome(_Broken(), "I lie.", _SETUP) is None


def _response(*texts, speakers=None):
    speakers = speakers or ["narrator"] * len(texts)
    return NarratorResponse.model_validate({"narration": [{"speaker": s, "text": t} for s, t in zip(speakers, texts)],
                                            "tool_call": {"tool": None}})


def test_the_cut_drops_the_outcome_sentence_and_everything_after():
    r = _response(_SETUP, "Guard: Go on.", speakers=["narrator", "Guard"])
    assert cut_at_outcome(r, "believes every word") is True
    assert [s.text for s in r.narration] == ["You meet his eyes and tell him the Arakawa sent you."]


def test_the_cut_keeps_earlier_segments_when_the_outcome_opens_a_later_one():
    r = _response("You gather yourself at the edge.", "You leap. You land hard on the far roof.")
    assert cut_at_outcome(r, "You land hard on the far roof") is True
    assert [s.text for s in r.narration] == ["You gather yourself at the edge.", "You leap."]


def test_no_cut_when_nothing_would_be_left_or_the_quote_is_not_there():
    r = _response("He believes you.")
    assert cut_at_outcome(r, "He believes you") is False and r.narration[0].text == "He believes you."
    assert cut_at_outcome(_response(_SETUP), "the lock clicks") is False


def test_a_cut_reaches_across_a_sentence_break_in_the_quote():
    r = _response("You throw the punch. It lands. He drops.")
    assert cut_at_outcome(r, "It lands. He drops") is True
    assert r.narration[0].text == "You throw the punch."


def test_a_quote_from_the_first_sentence_cuts_from_where_it_ends():
    # Probe 2026-11-18: the evidence for the sneak began at the set-up's first sentence.
    r = _response("You keep low behind the crates. The guard never looks up as you slip by.")
    assert cut_at_outcome(r, "You keep low behind the crates. The guard never looks up as you slip by.") is True
    assert r.narration[0].text == "You keep low behind the crates."
