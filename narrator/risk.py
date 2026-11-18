"""Before narration: does the player's action need a roll?

Live 2026-11-06: the narrator resolved "I slip behind the counter while she's busy" straight away, with no roll; prompt
wording alone never held on the 8B model (Phase 18). This yes/no check runs first, so the engine can tell the narrator
to set the moment up and ask for the roll. Like the referee, a "yes" counts only if its quote is really in the action,
and any failure answers "no": the turn always goes ahead.
"""

import re
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
# Playthrough 2026-11-07: the set-up said the punch caught the enforcer "square in the jaw", then the roll came.
INSTRUCTION = ("Engine: this action is risky. Narrate only the set-up, up to the moment of risk, and call request_roll. "
               "Stop on the moment before it lands: the punch is thrown, not landed; the lie is told, not believed; the "
               "jump begins, not ends. Do not say how it turns out.")


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


# After a risky set-up: the prompt line above ("stop on the moment before it lands") still let the lie be believed and
# the jump end in the set-up (live probe 2026-11-07). This check catches it; the engine redoes once, then cuts.
# Probe 2026-11-18 on qwen3:8b (think off): framed as "the narrator had to stop before it resolves" the model said
# "undecided" for every leak (6-9/12); framed as plain reading comprehension it got 12/12.
_OUTCOME_SYSTEM = "You check short story passages. Answer only from what the passage says."
_OUTCOME_QUESTION = ("In the passage, did that attempt succeed, fail, or is the result not shown yet? succeeded: the "
                     "passage says it worked. failed: the passage says it went wrong. not_shown: it is still happening "
                     "or about to happen. evidence copies the words that show the result (empty if not_shown).")
OUTCOME_SCHEMA = {"type": "object", "properties": {
    "evidence": {"type": "string"}, "result": {"type": "string", "enum": ["succeeded", "failed", "not_shown"]}},
    "required": ["evidence", "result"], "additionalProperties": False}


def outcome_redo(quote: str) -> str:
    return (f"Engine: the set-up already gave the outcome away (\"{quote}\"). The dice decide that. Narrate the set-up "
            "again and stop on the moment before it resolves.")


async def leaked_outcome(client, action_text: str, setup_text: str) -> str | None:
    """The set-up's own words that already resolve the attempt, or None (clean, an answer whose quote isn't in the
    set-up, or a failed check: the turn always goes ahead)."""
    try:
        answer = await client.judge([{"role": "system", "content": _OUTCOME_SYSTEM}, {"role": "user", "content":
                                     f"Passage: {setup_text}\n\nThe player tried: {action_text}\n{_OUTCOME_QUESTION}"}],
                                    OUTCOME_SCHEMA)
    except Exception:
        return None
    quote = str(answer.get("evidence", "")).strip()
    decided = answer.get("result") in ("succeeded", "failed")
    return quote if decided and quote and _squash(quote) in _squash(setup_text) else None


_SENTENCES = re.compile(r"(?<=[.!?…])\s+")


def cut_at_outcome(response, quote: str) -> bool:
    """Drops the sentence where the outcome starts and everything after it (or, when the quote opens the set-up,
    from its last sentence). False (nothing changed) when the quote isn't found or nothing would be left."""
    want = _squash(quote)
    for i, seg in enumerate(response.narration):
        sentences = _SENTENCES.split(seg.text.strip())
        # the last sentence the quote reaches, then the first one it starts in
        end = next((k for k in range(len(sentences)) if want in _squash(" ".join(sentences[:k + 1]))), None)
        if end is None:
            continue
        start = next(j for j in range(end, -1, -1) if want in _squash(" ".join(sentences[j:end + 1])))
        if start == 0 and i == 0:   # the quote opens the set-up: cut from where it ends (probe 2026-11-18)
            start = end
        kept = " ".join(sentences[:start])
        if not kept and i == 0:
            return False
        response.narration[i + 1:] = []
        if kept:
            seg.text = kept
        else:
            response.narration.pop(i)
        return True
    return False
