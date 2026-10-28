"""Phase 18 referee: a small required-field yes/no pass after narration that
decides the state changes qwen3:8b never volunteered as optional tool fields.
See docs/superpowers/specs/2026-10-28-narrator-reliability-18-design.md."""

from engine.character import is_tsukumogami
from engine.chrome import change_humanity
from engine.debt import SHELL, new_shell, pay_installment, repo_target_name, repossess, unthrottle
from engine.session import Session
from ruleset.cyberware import CHROME

_LEVELS = ["none", "small", "big"]
_AMOUNT = {"none": 0, "small": 2, "big": 4}
_LEVEL_FIELDS = ("human_moment", "acted_as_machine")
_HARA_OBJECTIVE = "Owe Old Hara a favor"
_SYSTEM = (
    "You are a strict referee for a tabletop RPG. Read the player's action and the narration, "
    "then answer each question about what actually happened in the narration. "
    "When unsure, answer none or false."
)


def build_questions(session: Session, player_id: str) -> dict[str, str]:
    c = session.characters[player_id]
    name = c.name
    questions = {
        "human_moment": f"none/small/big: did {name} share a genuinely human moment (a kindness, a shared meal, "
                        "being thanked, keeping a promise, choosing restraint)?",
    }
    if is_tsukumogami(c):
        questions["acted_as_machine"] = (f"none/small/big: did {name} act as a pure machine (cold calculation, "
                                         "following an owner's script, treating people as inputs)?")
    if c.pending_repo:
        questions["gave_up_repo_item"] = (f"true/false: did {name} hand over or lose their "
                                          f"{repo_target_name(c.pending_repo)} to the repo crew?")
    if c.installments_owed > 0 and not c.bodiless:
        questions["gig_paid_out"] = f"true/false: did {name} get paid for finished work?"
    if c.bodiless:
        questions["got_new_shell"] = f"true/false: did {name} get a new utsusemi shell?"
    if c.throttled:
        questions["hara_unlocked_chrome"] = (f"true/false: did Old Hara unlock {name}'s throttled "
                                             f"{CHROME[c.throttled].name}?")
    return questions


def build_schema(questions: dict[str, str]) -> dict:
    properties = {
        k: ({"type": "string", "enum": _LEVELS} if k in _LEVEL_FIELDS else {"type": "boolean"})
        for k in questions
    }
    return {"type": "object", "properties": properties, "required": list(questions), "additionalProperties": False}


def validate_verdict(verdict: dict, questions: dict[str, str]) -> None:
    if not isinstance(verdict, dict) or set(verdict) != set(questions):
        raise ValueError(f"referee answered {sorted(verdict) if isinstance(verdict, dict) else verdict!r}, "
                         f"expected {sorted(questions)}")
    for key, value in verdict.items():
        ok = value in _LEVELS if key in _LEVEL_FIELDS else isinstance(value, bool)
        if not ok:
            raise ValueError(f"bad referee value for {key}: {value!r}")


def _state_line(session: Session, player_id: str) -> str:
    c = session.characters[player_id]
    parts = [f"{c.name}: {'tsukumogami' if is_tsukumogami(c) else 'human'}"]
    if c.installments_owed > 0:
        parts.append(f"owes {c.installments_owed}")
    if c.pending_repo:
        parts.append(f"repo pending: {repo_target_name(c.pending_repo)}")
    if c.throttled:
        parts.append(f"throttled: {CHROME[c.throttled].name}")
    if c.bodiless:
        parts.append("bodiless")
    return ", ".join(parts)


def _messages(session, player_id, action_text, narration_text, questions) -> list[dict]:
    lines = "\n".join(f"- {k}: {q}" for k, q in questions.items())
    user = (f"State: {_state_line(session, player_id)}\nAction: {action_text}\n"
            f"Narration: {narration_text}\nQuestions:\n{lines}")
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def apply_verdict(session: Session, player_id: str, verdict: dict) -> None:
    c = session.characters[player_id]
    name = c.name
    delta = _AMOUNT[verdict.get("human_moment", "none")] - _AMOUNT[verdict.get("acted_as_machine", "none")]
    if delta:
        before = c.humanity
        session.pending_world_events.extend(change_humanity(c, delta))
        if is_tsukumogami(c) and c.humanity != before:
            session.log.append(f"[selfhood: {c.humanity - before:+d}]")
    # Same order as 17b's tool path: repo and unthrottle before payment, which clears both.
    if verdict.get("gave_up_repo_item") and c.pending_repo:
        removed = repossess(c)
        if removed == SHELL:
            session.log.append(f"[torite: Saeko's crew took {name}'s shell - {name} drops into the nearest machine]")
        else:
            session.log.append(f"[torite: Saeko's crew took {name}'s {CHROME[removed].name}]")
    if verdict.get("hara_unlocked_chrome") and c.throttled:
        unthrottle(c)
        if _HARA_OBJECTIVE not in session.active_objectives:
            session.active_objectives.append(_HARA_OBJECTIVE)
    if verdict.get("got_new_shell") and c.bodiless:
        new_shell(c)
        session.log.append(f"[utsusemi: {name} wakes in a new shell]")
    if verdict.get("gig_paid_out") and c.installments_owed > 0:
        pay_installment(c, 1)


async def run_referee(session: Session, client, player_id: str, action_text: str, narration_text: str) -> None:
    if player_id not in session.characters:
        return
    questions = build_questions(session, player_id)
    try:
        verdict = await client.judge(_messages(session, player_id, action_text, narration_text, questions),
                                     build_schema(questions))
        validate_verdict(verdict, questions)
    except Exception as e:  # a failed referee must never break the turn
        session.log.append(f"[referee error: {e}]")
        return
    apply_verdict(session, player_id, verdict)
