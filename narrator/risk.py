"""Before narration: does the player's action need a roll?

Live 2026-11-06: the narrator resolved "I slip behind the counter while she's busy" straight away, with no roll; prompt
wording alone never held on the 8B model (Phase 18). This yes/no check runs first, so the engine can tell the narrator
to set the moment up and ask for the roll. Like the referee, a "yes" counts only if its quote is really in the action,
and any failure answers "no": the turn always goes ahead.
"""

from difflib import get_close_matches

from narrator.referee import _squash
from ruleset.skills import SKILLS

_SYSTEM = ("You are a strict referee for a tabletop RPG. Decide whether the player's action needs a dice roll. "
           "Before answering, risky_quote copies the exact words from the action that make it risky (empty if none).")
_QUESTION = ("Does this action try something whose outcome is uncertain and could fail with consequences: sneaking past "
             "or stealing from someone, climbing or jumping somewhere dangerous, hacking, fighting, lying to or pressuring "
             "someone unwilling? Talking, walking somewhere, looking around, eating, asking questions or other plain "
             "actions are false. Words the player rules out ('I am not here to threaten you') don't count.")
_SKILL_QUESTION = ("If risky, the skill it tests: melee (fists, blades, any close attack), ranged_combat (guns, "
                   "throwing), stealth, athletics (climbing, jumping, running), piloting, hacking, engineering, "
                   "demolitions, intimidation, streetwise, perception, deduction, persuasion (including lying), "
                   "performance; otherwise none.")
SCHEMA = {"type": "object", "properties": {"risky_quote": {"type": "string"}, "risky": {"type": "boolean"},
                                           "skill": {"type": "string", "enum": [*SKILLS, "none"]}},
          "required": ["risky_quote", "risky", "skill"], "additionalProperties": False}
INSTRUCTION = ("Engine: this action is risky. Narrate only the set-up, up to the moment of risk, and call request_roll. "
               "Do not say how it turns out.")


NO_ROLL = "Engine: this action is not risky. Narrate it through to what happens, without a roll."


async def assess(client, action_text: str) -> tuple[bool | None, str | None]:
    """(risky, skill). risky is True (with a quote from the action), False (plainly not risky) or None (unknown: the
    check failed or claimed risk without a real quote - the engine then neither forces nor blocks a roll). skill is
    the skill the attempt tests when risky; the narrator sees the scene but kept picking the wrong one (dry run
    2026-11-06: "I kill everyone in the bar" rolled Stealth), so this pick wins."""
    try:
        answer = await client.judge([{"role": "system", "content": _SYSTEM}, {"role": "user", "content":
                                     f"Action: {action_text}\nQuestion: {_QUESTION}\nSkill: {_SKILL_QUESTION}"}], SCHEMA)
    except Exception:  # a failed check must never block the turn
        return None, None
    if answer.get("risky") is False:
        return False, None
    quote = _squash(str(answer.get("risky_quote", "")))
    if not (answer.get("risky") is True and quote and _close(quote, _squash(action_text))):
        return None, None
    skill = answer.get("skill")
    return True, skill if skill in SKILLS else None


async def is_risky(client, action_text: str) -> bool | None:
    return (await assess(client, action_text))[0]


def _close(quote: str, action: str) -> bool:
    """The quote is in the action, allowing for typos: every quoted word closely matches a word the player typed
    (dry run 2026-11-06: the check quoted "sneak past the guard" for "i sneek past teh gaurd")."""
    words = action.split()
    return quote in action or all(get_close_matches(w, words, n=1, cutoff=0.6) for w in quote.split())
