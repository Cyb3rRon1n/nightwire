"""Before narration: does the player's action need a roll?

Live 2026-11-06: the narrator resolved "I slip behind the counter while she's busy" straight away, with no roll; prompt
wording alone never held on the 8B model (Phase 18). This yes/no check runs first, so the engine can tell the narrator
to set the moment up and ask for the roll. Like the referee, a "yes" counts only if its quote is really in the action,
and any failure answers "no": the turn always goes ahead.
"""

from narrator.referee import _squash

_SYSTEM = ("You are a strict referee for a tabletop RPG. Decide whether the player's action needs a dice roll. "
           "Before answering, risky_quote copies the exact words from the action that make it risky (empty if none).")
_QUESTION = ("Does this action try something whose outcome is uncertain and could fail with consequences: sneaking past "
             "or stealing from someone, climbing or jumping somewhere dangerous, hacking, fighting, lying to or pressuring "
             "someone unwilling? Talking, walking somewhere, looking around, eating, asking questions or other plain "
             "actions are false.")
SCHEMA = {"type": "object", "properties": {"risky_quote": {"type": "string"}, "risky": {"type": "boolean"}},
          "required": ["risky_quote", "risky"], "additionalProperties": False}
INSTRUCTION = ("Engine: this action is risky. Narrate only the set-up, up to the moment of risk, and call request_roll. "
               "Do not say how it turns out.")


async def is_risky(client, action_text: str) -> bool:
    try:
        answer = await client.judge([{"role": "system", "content": _SYSTEM},
                                     {"role": "user", "content": f"Action: {action_text}\nQuestion: {_QUESTION}"}], SCHEMA)
        quote = _squash(str(answer.get("risky_quote", "")))
        return answer.get("risky") is True and bool(quote) and quote in _squash(action_text)
    except Exception:  # a failed check must never block the turn
        return False
