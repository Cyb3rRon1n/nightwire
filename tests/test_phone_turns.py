import pytest

from engine import phone
from engine.character import CharacterSheet as Character
from engine.session import Session
from server.phone_turns import deliver_due, handle_text


class Judge:
    def __init__(self, exc=None):
        self.exc, self.calls = exc, 0

    async def judge(self, messages, schema):
        self.calls += 1
        if self.exc:
            raise self.exc
        return {"reply": "ok then"}


def _session(role, trust=None):
    s = Session(session_id="s")
    s.characters["p1"] = Character(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    c = phone.add_contact(s, "p1", "Mika", role)
    if trust is not None:
        c["trust"] = trust
    return s


def _texts(s):
    return s.phone["p1"]["threads"]["Mika"]


async def test_partner_at_trust_5_answers_at_once():
    s = _session("partner", 5)
    await handle_text(s, Judge(), "p1", {"to": "Mika", "text": "hi"})
    assert [m["text"] for m in _texts(s)] == ["hi", "ok then"]


async def test_creditor_reply_arrives_on_the_third_later_turn():
    s = _session("creditor", 3)  # delay 1+2 = 3
    j = Judge()
    await handle_text(s, j, "p1", {"to": "Mika", "text": "hi"})
    assert _texts(s)[1]["text"] is None
    await deliver_due(s, j, "p1")
    await deliver_due(s, j, "p1")
    assert _texts(s)[1]["text"] is None
    await deliver_due(s, j, "p1")
    assert _texts(s)[1]["text"] == "ok then"


async def test_words_stay_out_of_the_log_and_the_world_event_is_queued():
    s = _session("partner", 5)
    await handle_text(s, Judge(), "p1", {"to": "Mika", "text": "secret words"})
    assert not any("secret" in line for line in s.log)
    assert s.pending_world_events == ["Rook quietly texts someone on their phone."]
    assert s.phone["p1"]["contacts"]["Mika"]["knows"] == ["secret words"]


async def test_knows_keeps_the_last_20():
    s = _session("partner", 5)
    for i in range(25):
        await handle_text(s, Judge(), "p1", {"to": "Mika", "text": f"t{i}"})
    assert s.phone["p1"]["contacts"]["Mika"]["knows"][0] == "t5"
    assert len(s.phone["p1"]["contacts"]["Mika"]["knows"]) == 20


@pytest.mark.parametrize("to,text", [("Nobody", "hi"), ("Mika", "  "), ("Mika", "x" * 501)])
async def test_bad_texts_are_refused(to, text):
    s = _session("partner", 5)
    with pytest.raises(ValueError):
        await handle_text(s, Judge(), "p1", {"to": to, "text": text})
    assert _texts(s) == []


async def test_hostile_enemy_gets_no_reply():
    s = _session("enemy")
    await handle_text(s, Judge(), "p1", {"to": "Mika", "text": "hi"})
    assert len(_texts(s)) == 1


async def test_failing_writer_still_posts_the_fallback():
    s = _session("creditor", 5)  # delay 1
    j = Judge(RuntimeError("down"))
    await handle_text(s, j, "p1", {"to": "Mika", "text": "hi"})
    await deliver_due(s, j, "p1")
    assert _texts(s)[1]["text"] == "Payment's due."
