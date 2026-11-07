from narrator.phone_reply import write_reply

CONTACT = {"name": "Mika", "role": "creditor", "trust": 0, "pace": 0, "close": False,
           "knows": ["a", "b"], "cold_until": 0}
THREAD = [{"sender": "me", "text": "hi", "turn": 1, "deliver_at": 1, "read": True},
          {"sender": "Mika", "text": None, "turn": 1, "deliver_at": 2, "read": False}]


class Judge:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    async def judge(self, messages, schema):
        self.calls.append((messages, schema))
        if self.exc:
            raise self.exc
        return self.result


async def test_reply_is_returned_trimmed():
    j = Judge({"reply": "  Pay up.  "})
    assert await write_reply(j, CONTACT, "curt", THREAD, "Kai") == "Pay up."


async def test_prompt_has_tone_role_knowledge_and_thread():
    j = Judge({"reply": "ok"})
    await write_reply(j, CONTACT, "curt", THREAD, "Kai")
    msgs, schema = j.calls[0]
    system = msgs[0]["content"]
    assert "curt" in system and "creditor" in system and "Mika" in system and "'a', 'b'" in system
    assert msgs[1]["content"] == "Kai: hi"  # placeholder without text skipped, "me" shown by name
    assert schema["properties"]["reply"]["maxLength"] == 240


async def test_empty_thread_asks_for_first_text():
    j = Judge({"reply": "yo"})
    await write_reply(j, CONTACT, "warm", [], "Kai")
    assert j.calls[0][0][1]["content"]


async def test_failure_or_blank_gives_role_fallback():
    assert await write_reply(Judge(exc=RuntimeError("x")), CONTACT, "t", THREAD, "Kai") == "Payment's due."
    fixer = {**CONTACT, "role": "fixer"}
    assert await write_reply(Judge({"reply": "  "}), fixer, "t", THREAD, "Kai") == "Busy. Later."
    other = {**CONTACT, "role": "friend"}
    assert await write_reply(Judge({}), other, "t", THREAD, "Kai") == "Can't talk now."


async def test_echoed_name_prefix_is_stripped():
    c = {**CONTACT, "name": "Saeko Kirigaya"}
    assert await write_reply(Judge({"reply": "Saeko Kirigaya: Not surprising."}), c, "t", THREAD, "Kai") == "Not surprising."
    assert await write_reply(Judge({"reply": "saeko:   Not surprising."}), c, "t", THREAD, "Kai") == "Not surprising."
    assert await write_reply(Judge({"reply": "Saeko:"}), c, "t", THREAD, "Kai") == "Payment's due."
