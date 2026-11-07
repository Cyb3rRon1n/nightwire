"""Phase 18 referee: a small required-field yes/no pass after narration that
decides the state changes qwen3:8b never volunteered as optional tool fields.
See docs/superpowers/specs/2026-10-28-narrator-reliability-18-design.md."""

import re

from engine import phone
from engine.character import is_tsukumogami
from engine.chrome import change_humanity
from engine.debt import SHELL, new_shell, pay_installment, repo_target_name, repossess, unthrottle
from engine.session import Session
from ruleset.cyberware import CHROME

_LEVELS = ["none", "small", "big"]
_AMOUNT = {"none": 0, "small": 2, "big": 4}
_LEVEL_FIELDS = ("human_moment", "acted_as_machine")
_HARA_OBJECTIVE = "Owe Old Hara a favor"
_LOCATION_MAX = 60
_SPEECH = re.compile(r"^[^:\n]{1,30}: ")  # "Mama Sato: ..." lines in the narration text
_SYSTEM = (
    "You are a strict referee for a tabletop RPG. Read the player's action and the narration, "
    "then answer each question about what actually happened in the narration. "
    "When unsure, answer none or false. Before each none/small/big answer, its _quote field copies the exact words "
    "from the action or narration that show it (empty for none)."
)


def build_questions(session: Session, player_id: str) -> dict[str, str]:
    c = session.characters[player_id]
    name = c.name
    questions = {
        "human_moment": f"none/small/big: did {name} share a genuinely human moment (a kindness, a shared meal, "
                        "being thanked, keeping a promise, choosing restraint)? Sneaking, climbing, jumping, fighting, hacking "
                        "or any other skill use on its own is none.",
    }
    questions["moved_to"] = (f"text: if {name} arrived somewhere new this turn, the place's name exactly as the action or "
                             "narration writes it (for example: Mama Sato's izakaya); otherwise empty. Only asking about "
                             "or looking at a place is not arriving.")
    if is_tsukumogami(c):
        questions["acted_as_machine"] = (f"none/small/big: did {name} act as a pure machine (cold calculation, "
                                         "following an owner's script, treating people as inputs)? Sneaking, climbing, "
                                         "jumping, fighting, hacking or any other skill use, and the dice result line, "
                                         "are none on their own.")
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
    # The quote comes first so the model commits to evidence before its answer.
    properties = {}
    for k in questions:
        if k in _LEVEL_FIELDS:
            properties[f"{k}_quote"] = {"type": "string"}
            properties[k] = {"type": "string", "enum": _LEVELS}
        elif k == "moved_to":
            properties[k] = {"type": "string", "maxLength": _LOCATION_MAX}
        else:
            properties[k] = {"type": "boolean"}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def validate_verdict(verdict: dict, questions: dict[str, str]) -> None:
    expected = set(questions) | {f"{k}_quote" for k in questions if k in _LEVEL_FIELDS}
    if isinstance(verdict, dict) and "moved_to" in questions:
        verdict.setdefault("moved_to", "")  # optional: older answers and test fakes leave it out
    if not isinstance(verdict, dict) or set(verdict) != expected:
        raise ValueError(f"referee answered {sorted(verdict) if isinstance(verdict, dict) else verdict!r}, "
                         f"expected {sorted(expected)}")
    for key, value in verdict.items():
        if key.endswith("_quote") or key == "moved_to":
            ok = isinstance(value, str)
        else:
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


def _squash(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s']", " ", text.lower()).split())


def ground(session: Session, verdict: dict, action: str, narration: str) -> dict:
    """A level answer counts only if its quote really is in the text it may come from
    (Phase 18 live: plain stealth and jump turns earned +2 "human moments"). A human
    moment can be in the narration (being thanked); acting as a machine is the
    player's choice, so it must be in their own words (2026-11-06 live: the
    narrator's description of a roof climb was quoted as machine behaviour)."""
    sources = {"human_moment": (_squash(f"{action}\n{narration}"), "the scene"),
               "acted_as_machine": (_squash(action), "the player's action")}
    grounded = {k: v for k, v in verdict.items() if not k.endswith("_quote")}
    for k in _LEVEL_FIELDS:
        text, where = sources[k]
        quote = _squash(verdict.get(f"{k}_quote", ""))
        if grounded.get(k, "none") != "none" and not (quote and quote in text):
            grounded[k] = "none"
            session.log.append(f"[referee: {k} had no quote from {where}, ignored]")
    # A new location counts only if the scene really names it (2026-11-06 live: the narrator never set the izakaya).
    moved = " ".join(str(grounded.get("moved_to", "")).split())[:_LOCATION_MAX]
    # Only the player or the narrator's own prose moves the player: an NPC naming a place isn't arriving there
    # (dry run 2026-11-06: "What brings you to Ikebe?" moved the player out of the izakaya).
    prose = "\n".join(line for line in narration.splitlines() if not _SPEECH.match(line))
    if moved and _squash(moved) not in _squash(f"{action}\n{prose}"):
        session.log.append("[referee: moved_to had no match in the scene, ignored]")
        moved = ""
    grounded["moved_to"] = moved
    return grounded


def apply_verdict(session: Session, player_id: str, verdict: dict) -> None:
    c = session.characters[player_id]
    name = c.name
    if verdict.get("moved_to"):
        session.location = verdict["moved_to"][0].upper() + verdict["moved_to"][1:]
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
        jun = phone.add_contact(session, player_id, "Jun Arakawa", "fixer")
        phone.post(session, player_id, "Jun Arakawa", "Jun Arakawa", "Money's in. Clean work.",
                   phone.phone_of(session, player_id)["turn"])
        phone.change_trust(jun, 0.5)


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
    apply_verdict(session, player_id, ground(session, verdict, action_text, narration_text))
