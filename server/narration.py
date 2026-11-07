import json
import random
import re

import httpx
import ollama

from engine.character import is_tsukumogami
from narrator.ooc import answer_ooc, is_ooc
from narrator.risk import INSTRUCTION as RISK_INSTRUCTION, NO_ROLL, assess
from engine.chrome import change_humanity, usable_overclocks
from engine.debt import repo_target_name, tick_debt
from engine.phone import add_contact, find_contact, phone_of, post
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarrationSegment, NarratorClient, _NoTool
from narrator.image_backend import ImageBackend
from narrator.image_prompt import resolve
from narrator.movement import destination
from narrator.referee import run_referee
from narrator.tools import RequestRoll, execute_tool, roll_check
from narrator.tts_backend import TTSBackend
from narrator.voice_assignment import assign_voice
from narrator.world import kuroshio, select_cards
from ruleset.attributes import Attribute
from ruleset.cyberware import CHROME, humanity_tier, selfhood_tier
from ruleset.difficulty import difficulty_for
from ruleset.skills import SKILLS, roll_attribute


# Verbatim recent narrative gets this fraction of num_ctx (in estimated
# tokens), leaving room for the system prompt (now including the world
# primer), party roster, NPC memory, world cards, the action text, and
# response generation. Lowered from 0.65 by Phase 14 to fund the world
# primer + cards while keeping generation headroom roughly where it was
# (~1,400 vs ~1,550 tokens at num_ctx=8192 - chars/4 ESTIMATES, not
# measurements; Phase 13 measured nearer 3.4-3.8 chars/token, so real
# headroom is lower - see the Phase 14 spec).
# A starting value, not a tuned optimum.
_VERBATIM_BUDGET_FRACTION = 0.55
# No tokenizer dependency - this is a "getting close to budget" trigger,
# not an exact accounting requirement.
_CHARS_PER_TOKEN_ESTIMATE = 4
# Hysteresis: only re-fire compaction once at least this many additional
# lines have been excluded since the last firing, not on every turn that
# excludes anything at all. Without this, steady-state play (each turn
# appending ~2+ lines past the budget threshold) triggers a full LLM
# summarization call on nearly every single turn.
_RECOMPACT_LINE_THRESHOLD = 8
# ponytail: caps the full-rebuild summarization input so its own prompt
# can't silently exceed num_ctx and self-truncate (the same failure class
# this phase exists to fix, just at a higher threshold). 24000 chars is
# Task 4's own live-verified session size, not a tuned ceiling - if a
# session needs to run meaningfully longer than ~2x that, this needs
# either a higher live-verified cap or a switch to incremental (not
# full-rebuild) summarization, which the design spec explicitly deferred.
_MAX_SUMMARIZE_INPUT_CHARS = 24000
# A separate, smaller reserved slice of num_ctx - not renegotiating
# _VERBATIM_BUDGET_FRACTION. 5% at num_ctx=8192 is ~410 tokens (~1,640
# chars), conservative against the ~1,940 tokens of generation headroom
# Phase 11's own final review measured. A starting value, not tuned.
_NPC_MEMORY_BUDGET_FRACTION = 0.05
# World cards (Phase 14): ~490 tokens at num_ctx=8192, enough for the
# 4-card cap at the 400-char card limit. A starting value, not tuned.
_WORLD_BUDGET_FRACTION = 0.06
# A single NPC entry can never exceed 1,110 chars (name<=100 + ": " + up
# to 5 facts<=200 each + 4 "; " separators - see narrator/tools.py's
# _MAX_FACTS_PER_NPC), safely below this budget even at num_ctx=6144's
# documented fallback (1,228 chars) - so one oversized entry can never
# starve the whole selection window. This only holds as long as those
# write-time caps and this read-time budget stay in this relationship;
# don't change one without checking the other.


def _cap_for_summarization(excluded: list[str]) -> list[str]:
    total = 0
    capped: list[str] = []
    for line in reversed(excluded):
        total += len(line) + 1
        if total > _MAX_SUMMARIZE_INPUT_CHARS:
            break
        capped.append(line)
    capped.reverse()
    return capped


def _select_verbatim_narrative(narrative: list[str], num_ctx: int) -> list[str]:
    budget_chars = int(num_ctx * _VERBATIM_BUDGET_FRACTION * _CHARS_PER_TOKEN_ESTIMATE)
    selected: list[str] = []
    total = 0
    for line in reversed(narrative):
        total += len(line) + 1
        if total > budget_chars:
            break
        selected.append(line)
    selected.reverse()
    return selected


_PROSE_TURNS = 3
_SPEECH = re.compile(r"^[^:\n]{1,30}: ")
_ROLL_LINE = re.compile(r" rolls .+ vs .+: ")  # the engine's own dice line (_roll_line): kept whole
_FIRST_SENTENCE = re.compile(r"^.*?[.!?…](?:\s+|$)")


def _trim_prose(lines: list[str], session: Session) -> list[str]:
    """Actions and dialogue stay; the narrator's own prose stays only for the last few turns, minus each
    turn's opening sentence, so it has nothing to copy (soak run 5: 10 repeated openings in 33 turns)."""
    actors = tuple(f"{pid}: " for pid in session.characters)
    starts = [i for i, line in enumerate(lines) if line.startswith(actors)] if actors else []
    keep_from = starts[-_PROSE_TURNS] if len(starts) >= _PROSE_TURNS else 0
    out, opened = [], False
    for i, line in enumerate(lines):
        if actors and line.startswith(actors):
            out.append(line); opened = False
        elif _SPEECH.match(line) or _ROLL_LINE.search(line):
            out.append(line)
        elif i >= keep_from:
            if not opened:
                opened = True
                line = _FIRST_SENTENCE.sub("", line, count=1)
            if line.strip():
                out.append(line)
    return out


_RECENT_OPENINGS = 5


def _opening_key(text: str) -> str:
    return " ".join(text.lower().split())[:40]


def _opening(response) -> str | None:
    """The first 40 characters of the reply's opening narrator prose, or None when it opens with dialogue."""
    first = next(iter(response.narration), None)
    return _opening_key(first.text) if first is not None and first.speaker == "narrator" and first.text.strip() else None


def _recent_openings(session: Session) -> set[str]:
    """The opening prose of the last few turns, as _opening keys (the soak test's repeated_opening, per turn)."""
    actors = tuple(f"{pid}: " for pid in session.characters)
    lines = [line for line in session.log if not line.startswith("[")]
    found: list[str] = []
    for i, line in enumerate(lines):
        if actors and line.startswith(actors):
            prose = next((l for l in lines[i + 1:] if not l.startswith(actors) and not _SPEECH.match(l)
                          and not _ROLL_LINE.search(l)), None)
            if prose:
                found.append(_opening_key(prose))
    return set(found[-_RECENT_OPENINGS:])


# The quote must open after a space and start a sentence, so "Names in Ikebe don't sell" stays whole.
_PROSE_THEN_QUOTE = re.compile(r"^(?P<prose>[^\"‘“]{12,}?[.!?,:;—-])\s+['\"‘“](?P<said>[A-Z…].+?)['\"’”]?\s*$", re.S)


def _split_prose_from_speech(response) -> None:
    """A speech line that opens with stage directions and then a quote: the directions go to the narrator
    (playthrough 2026-11-07: "scarred ganger: The blade is already in his hand... 'You think...'")."""
    out = []
    for seg in response.narration:
        m = _PROSE_THEN_QUOTE.match(seg.text) if seg.speaker != "narrator" else None
        if m and m["said"].strip():
            out.append(NarrationSegment(speaker="narrator", text=m["prose"].strip()))
            seg.text = m["said"].strip()
        out.append(seg)
    response.narration[:] = out


_RECENT_LINES = 40


def _drop_repeated_lines(response, session: Session) -> None:
    """Drops reply lines (prose or speech) that copy a recent story line word for word (playthrough 2026-11-07:
    Old Hara's whole speech before and after the roll, a ganger's threat across 4 turns). Keeps at least one line."""
    recent = {_opening_key(line.split(": ", 1)[1] if _SPEECH.match(line) else line)
              for line in [l for l in session.log if not l.startswith("[")][-_RECENT_LINES:]}
    kept = [seg for seg in response.narration if _opening_key(seg.text) not in recent]
    response.narration[:] = kept or response.narration[-1:]


def _drop_opening(response) -> None:
    first = response.narration[0]
    first.text = _FIRST_SENTENCE.sub("", first.text, count=1)
    if not first.text.strip():
        response.narration.pop(0)


def _npc_entry(name: str, facts: list[str]) -> str:
    return f"{name}: {'; '.join(facts)}"


def _select_npc_memory_for_context(session: Session, num_ctx: int) -> dict[str, list[str]]:
    budget_chars = int(num_ctx * _NPC_MEMORY_BUDGET_FRACTION * _CHARS_PER_TOKEN_ESTIMATE)
    selected: list[tuple[str, list[str]]] = []
    total = 0
    for name, facts in reversed(session.npc_memory.items()):
        total += len(_npc_entry(name, facts)) + 1
        if total > budget_chars:
            break
        selected.append((name, facts))
    selected.reverse()
    return dict(selected)


# The Scene line sits outside every num_ctx budget, and location / mood /
# objectives are model-written with no length limit (objectives only
# grow), so cap them on the read side: per-field chars, newest objectives.
_SCENE_FIELD_MAX_CHARS = 120
_SCENE_MAX_OBJECTIVES = 5


_CREW_ENTRY_MAX_CHARS = 200


_SAEKO = (("final notice", "Thursday was yesterday. Don't make me come find you."),
          ("remote-throttled", "We switched off your {chrome}. Pay and it comes back."),
          ("comes for", "My crew is on the way."))


def _saeko_text(session, player_id, character, event) -> None:
    for key, template in _SAEKO:
        if key in event:
            chrome = CHROME[character.throttled].name if character.throttled else ""
            add_contact(session, player_id, "Saeko Kirigaya", "creditor", pace=-1)
            turn = phone_of(session, player_id)["turn"]
            post(session, player_id, "Saeko Kirigaya", "Saeko Kirigaya", template.format(chrome=chrome), turn)
            return


def _crew_line(session: Session) -> str:
    entries = []
    for c in session.characters.values():
        if not c.chrome and c.humanity == 100 and c.installments_owed <= 0 and not is_tsukumogami(c):
            continue
        if is_tsukumogami(c):
            tier = selfhood_tier(c.humanity) + (", gone dark" if c.gone_too_far else "")
            entry = f"{c.name}: selfhood {c.humanity} ({tier})"
        else:
            entry = f"{c.name}: humanity {c.humanity} ({humanity_tier(c.humanity)})"
        if c.bodiless:
            entry += ", bodiless: living in a nearby machine"
        if c.chrome:
            entry += ", chrome: " + ", ".join(CHROME[i].name for i in c.chrome)
        if c.installments_owed > 0:
            entry += f", owes {c.installments_owed}, repo clock {c.repo_clock}/6"
        if c.throttled:
            entry += f", throttled: {CHROME[c.throttled].name}"
        if c.pending_repo:
            entry += f", repo crew coming for: {repo_target_name(c.pending_repo)}"
        entries.append(entry[:_CREW_ENTRY_MAX_CHARS])
    return "Crew: " + "; ".join(entries) if entries else ""


def _scene_line(session: Session) -> str:
    parts = []
    if session.location:
        parts.append(session.location[:_SCENE_FIELD_MAX_CHARS])
    if session.scene_mood:
        parts.append(f"mood: {session.scene_mood[:_SCENE_FIELD_MAX_CHARS]}")
    if session.active_objectives:
        recent = session.active_objectives[-_SCENE_MAX_OBJECTIVES:]
        parts.append("objectives: " + "; ".join(o[:_SCENE_FIELD_MAX_CHARS] for o in recent))
    return "Scene: " + " · ".join(parts) if parts else ""


def _build_messages(session: Session, action_text: str, num_ctx: int) -> list[dict]:
    # apply_character_update's player_id is trusted as-is (it legitimately
    # targets a different character than the actor, e.g. damage to a
    # teammate) - but the model was never told what real player_ids exist,
    # so on an early turn (nothing in the log yet to infer one from) it
    # invents a plausible-looking placeholder like "player" instead of the
    # real "p1", and the update silently fails validation. Grounding every
    # turn in the real roster fixes the root cause without narrowing who a
    # future multi-target tool call can address.
    roster = ", ".join(f"{c.player_id} ({c.name})" for c in session.characters.values())
    party = f"Party (use these exact player_ids): {roster}\n\n" if roster else ""
    # [start_combat: {...}]-style lines are tool-execution annotations for the
    # UI, not narrative fact - feeding them back verbatim let the model read
    # its own acknowledgment ("combat start requires...") as evidence combat
    # was actually ongoing, and re-trigger the tool turn after turn.
    narrative = _trim_prose([line for line in session.log if not line.startswith("[")], session)
    verbatim = _select_verbatim_narrative(narrative, num_ctx)
    parts = []
    if session.narrative_summary:
        parts.append(f"Summary of earlier events: {session.narrative_summary}")
    npc_memory = _select_npc_memory_for_context(session, num_ctx)
    if npc_memory:
        npc_lines = "\n".join(_npc_entry(name, facts) for name, facts in npc_memory.items())
        parts.append(f"Known NPCs:\n{npc_lines}")
    if verbatim:
        parts.append("Recent events:\n" + "\n".join(verbatim))
    # Scene + world notes go last, right before the action - content
    # nearest the end of the prompt carries the most weight (Phase 14
    # spec, SillyTavern World Info insertion-depth precedent).
    scene = _scene_line(session)
    if scene:
        parts.append(scene)
    crew = _crew_line(session)
    if crew:
        parts.append(crew)
    if session.pending_world_events:
        parts.append("World event: " + " ".join(session.pending_world_events))
    world_budget = int(num_ctx * _WORLD_BUDGET_FRACTION * _CHARS_PER_TOKEN_ESTIMATE)
    scan_text = " ".join([action_text, *session.pending_world_events])
    cards = select_cards(kuroshio(), session, scan_text, world_budget)
    if cards:
        parts.append("World notes:\n" + "\n".join(cards))
    context = "\n\n".join(parts) + "\n\n" if parts else ""
    return [{"role": "user", "content": f"{party}{context}Player action: {action_text}"}]


async def _maybe_compact(session: Session, narrator_client: NarratorClient) -> None:
    narrative = [line for line in session.log if not line.startswith("[")]
    verbatim = _select_verbatim_narrative(narrative, narrator_client.num_ctx)
    excluded_count = len(narrative) - len(verbatim)
    if excluded_count < session.narrative_summary_line_count + _RECOMPACT_LINE_THRESHOLD:
        return
    excluded = narrative[:excluded_count]
    try:
        session.narrative_summary = await narrator_client.summarize("\n".join(_cap_for_summarization(excluded)))
        session.narrative_summary_line_count = excluded_count
    except (ValueError, TypeError, httpx.HTTPError, ollama.ResponseError, ConnectionError, KeyError) as e:
        session.log.append(f"[summary error: {e}]")


def _hold_roll(session: Session, player_id: str, tool_args: dict) -> str | None:
    # Two-step rolls (Phase 16): don't roll yet - the player rolls next, then
    # the narrator resolves knowing the result. Server-authoritative actor,
    # same as before: never the model's own player_id.
    tool_args["player_id"] = player_id
    try:
        request = RequestRoll(**tool_args)
    except (ValueError, TypeError) as e:
        session.log.append(f"[tool error: {e}]")
        return str(e)
    character = session.characters.get(player_id)
    if character is None:
        session.log.append(f"[tool error: unknown player_id: {player_id!r}]")
        return f"unknown player_id: {player_id!r}"
    if character.bodiless and SKILLS[request.skill].governing_attribute in (Attribute.BODY, Attribute.REFLEXES):
        message = f"{character.name} has no body"
        session.log.append(f"[tool error: {message}]")
        return message
    pending = request.model_dump()
    pending["attribute"] = roll_attribute(request.skill, request.attribute).value  # no Stealth (Presence)
    effective, difficulty = difficulty_for(request.stakes, session.recent_stakes)
    session.recent_stakes = (session.recent_stakes + [effective])[-6:]
    pending["difficulty"] = difficulty.name.lower()
    pending["dc"] = difficulty.value
    pending["name"] = character.name
    session.pending_rolls[player_id] = pending
    session.log.append(f"[roll pending: {json.dumps(pending)}]")
    return None


async def handle_action(
    session: Session,
    narrator_client: NarratorClient,
    store: JSONFileSessionStore,
    image_backend: ImageBackend,
    tts_backend: TTSBackend,
    player_id: str,
    message: dict,
) -> None:
    action_text = message.get("text")
    if not isinstance(action_text, str) or not action_text.strip():
        raise ValueError("missing 'text' in action message")
    if len(action_text) > 1000:
        raise ValueError("action text too long")
    character = session.characters.get(player_id)
    if is_ooc(action_text):
        # Out of character (dry run 2026-11-06): a help-desk answer, kept out of the story and the narrator's context.
        who = character.name if character else player_id
        session.log.append(f"[ooc question: {who}: {action_text.strip()}]")
        session.log.append(f"[ooc: {await answer_ooc(narrator_client, action_text)}]")
        return
    if player_id in session.pending_rolls:
        raise ValueError("roll first")
    if character is not None:
        for event in tick_debt(character):
            session.pending_world_events.append(event)
            session.log.append(f"[torite: {event}]")
            _saeko_text(session, player_id, character, event)
    # The engine moves the player before the narrator runs, so a narrator timeout can't lose the move (soak run 5).
    moved_to = destination(action_text)
    if moved_to:
        session.location = moved_to
    risky, roll_skill = await assess(narrator_client, action_text) if character is not None else (None, None)
    must_roll = risky is True
    await _run_turn(
        session, narrator_client, store, image_backend, tts_backend, player_id,
        prompt_text=f"{action_text}\n\n{RISK_INSTRUCTION}" if must_roll else action_text,
        actor_line=f"{player_id}: {action_text}", allow_roll=True, referee_action=action_text, must_roll=must_roll,
        no_roll=risky is False, roll_skill=roll_skill,
    )


def _is_player_voice(session: Session, speaker: str) -> bool:
    s = speaker.strip().lower()
    return any(s in (c.name.strip().lower(), c.player_id.strip().lower()) for c in session.characters.values())


async def _log_narration(session, response, store, tts_backend, player_id) -> str:
    """Logs and voices the response's segments; returns the narration text that was kept."""
    texts: list[str] = []
    for i, segment in enumerate(response.narration):
        if segment.speaker != "narrator" and _is_player_voice(session, segment.speaker):
            session.log.append(f"[voice filtered: {segment.speaker}]")
            continue
        line = segment.text if segment.speaker == "narrator" else f"{segment.speaker}: {segment.text}"
        if segment.speaker != "narrator" and segment.speaker.strip():
            known = phone_of(session, player_id)["contacts"]
            if not find_contact(known, segment.speaker):  # "Saeko" is Saeko Kirigaya, not a stranger
                add_contact(session, player_id, segment.speaker.strip())
        texts.append(line)  # with the speaker, so the referee can tell narration from what NPCs say
        session.log.append(line)
        log_index = len(session.log)
        voice = assign_voice(session, segment.speaker, segment.gender, tts_backend.voices)
        try:
            audio_bytes = await tts_backend.synthesize(segment.text, voice)
            relative_path = f"audio/{session.session_id}/{log_index}-{i}.wav"
            output_path = store.directory / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_bytes)
            session.log.append(f"[audio: {relative_path}]")
        except (ValueError, TypeError, OSError) as e:
            session.log.append(f"[audio error: {e}]")
    return "\n".join(texts)


def _in_fiction_refusal(session, response, player_id, allow_roll) -> str | None:
    """The engine refusal worth a redo: a bodiless character asked to roll a physical skill."""
    if not allow_roll or response.tool != "request_roll":
        return None
    character = session.characters.get(player_id)
    if character is None or not character.bodiless:
        return None
    try:
        request = RequestRoll(**{**response.tool_args, "player_id": player_id})
    except (ValueError, TypeError):
        return None
    if SKILLS[request.skill].governing_attribute in (Attribute.BODY, Attribute.REFLEXES):
        return f"{character.name} has no body"
    return None


def _apply_tool(session, response, player_id, allow_roll, roll_skill: str | None = None) -> None:
    """Runs the narrator's tool call; an engine refusal is logged as a tool error."""
    if response.tool is None:
        return
    tool_args = dict(response.tool_args)
    if response.tool == "request_roll":
        if allow_roll:
            if roll_skill:
                tool_args["skill"] = roll_skill  # the risk check's pick (narrator/risk.py)
            _hold_roll(session, player_id, tool_args)
        else:
            session.log.append("[roll skipped: another roll asked during a roll result]")
        return
    try:
        result = execute_tool(session, response.tool, tool_args)
        session.log.append(f"[{response.tool}: {result}]")
    except (ValueError, TypeError) as e:
        session.log.append(f"[tool error: {e}]")


async def _run_turn(
    session: Session,
    narrator_client: NarratorClient,
    store: JSONFileSessionStore,
    image_backend: ImageBackend,
    tts_backend: TTSBackend,
    player_id: str,
    prompt_text: str,
    actor_line: str | None,
    allow_roll: bool,
    referee_action: str | None = None,
    must_roll: bool = False,
    no_roll: bool = False,
    roll_skill: str | None = None,
) -> None:
    # Events are shown once, but only dropped after the narrator actually
    # responded; events queued during the turn survive to the next one.
    shown_events = list(session.pending_world_events)
    messages = _build_messages(session, prompt_text, narrator_client.num_ctx)
    response = await narrator_client.respond(messages)
    del session.pending_world_events[:len(shown_events)]

    refusal = _in_fiction_refusal(session, response, player_id, allow_roll)
    if refusal is None and must_roll and response.tool != "request_roll":
        # Risky (narrator/risk.py) but resolved without a roll: redo once, nothing logged yet. A second miss stands.
        session.pending_world_events[:0] = shown_events
        retry_prompt = f"{prompt_text}\n\nEngine: you resolved it without a roll. Narrate only the set-up and call request_roll."
        messages = _build_messages(session, retry_prompt, narrator_client.num_ctx)
        response = await narrator_client.respond(messages)
        del session.pending_world_events[:len(shown_events)]
    elif refusal is None and no_roll and response.tool == "request_roll":
        # Plainly not risky but the narrator asked for a roll (live: "what's good tonight?" -> Persuasion): redo once.
        session.pending_world_events[:0] = shown_events
        messages = _build_messages(session, f"{prompt_text}\n\n{NO_ROLL}", narrator_client.num_ctx)
        response = await narrator_client.respond(messages)
        del session.pending_world_events[:len(shown_events)]
        if response.tool == "request_roll":  # the check said plain: no roll, whatever the narrator wants (playthrough)
            response.tool_call = _NoTool()
    if refusal is not None:
        # Redo once (Phase 18), decided before anything is logged or voiced: the
        # refused narration is never shown; narrate again with the refusal as fact.
        session.pending_world_events[:0] = shown_events
        retry_prompt = f"{prompt_text}\n\nEngine: {refusal}. That does not happen - narrate the attempt failing or not being possible."
        messages = _build_messages(session, retry_prompt, narrator_client.num_ctx)
        response = await narrator_client.respond(messages)
        del session.pending_world_events[:len(shown_events)]

    opening = _opening(response)
    if opening and opening in _recent_openings(session):
        # Soak run 5: 10 of 33 turns reused an earlier opening. Redo once; a second repeat loses that sentence.
        session.pending_world_events[:0] = shown_events
        redo = (f"{prompt_text}\n\nEngine: don't open with \"{opening}...\" - that opening was already used. "
                "Start with what the action causes.")
        response = await narrator_client.respond(_build_messages(session, redo, narrator_client.num_ctx))
        del session.pending_world_events[:len(shown_events)]
        if _opening(response) in _recent_openings(session):
            _drop_opening(response)

    _split_prose_from_speech(response)
    _drop_repeated_lines(response, session)

    if actor_line is not None:
        session.log.append(actor_line)
    if refusal is not None:
        session.log.append(f"[redo: {refusal}]")
    narration_text = await _log_narration(session, response, store, tts_backend, player_id)
    _apply_tool(session, response, player_id, allow_roll, roll_skill)  # a refusal on the redo is only logged

    # Referee (Phase 18): not on the setup turn that opened a roll - the outcome
    # isn't known yet - nor when every segment was voice-filtered.
    if player_id not in session.pending_rolls and narration_text:
        await run_referee(session, narrator_client, player_id, referee_action or prompt_text, narration_text)

    generated_image = False
    # The model is told "never two turns in a row" but has no way to enforce
    # its own rule across separate calls - live probing found it violated
    # this on 3/3 consecutive turns in one run. Server-side cooldown backs
    # the rule structurally instead of trusting prompt compliance alone,
    # same pattern as request_roll's forced player_id / apply_character_update's
    # roster grounding.
    if response.image_request is not None and not session.last_turn_had_image:
        character = session.characters.get(player_id)
        reference_paths = []
        if character is not None and character.portrait_path is not None:
            reference_paths.append(str(store.directory / character.portrait_path))
        image_prompt, image_negative = response.image_request.prompt, None
        if getattr(image_backend, "wants_tags", False):
            # Phase 19a: tag while the narrator model is still loaded; unload comes next.
            image_prompt, image_negative, source = await resolve(
                narrator_client, "scene", response.image_request.prompt)
            session.log.append(f"[image prompt ({source}): {image_prompt}]")
        # Best-effort VRAM headroom before generating - freeing the narrator/TTS
        # backends' own resident weights matters most on small cards, but a dead
        # TTS/narrator backend must never block the actual image generation it
        # has nothing to do with.
        try:
            await narrator_client.unload()
        except (ValueError, TypeError, OSError, httpx.HTTPError, RuntimeError):
            pass
        try:
            await tts_backend.unload()
        except (ValueError, TypeError, OSError, httpx.HTTPError, RuntimeError):
            pass
        try:
            if image_negative is None:
                image_bytes = await image_backend.generate_scene(image_prompt, reference_paths)
            else:
                image_bytes = await image_backend.generate_scene(image_prompt, reference_paths, negative=image_negative)
            relative_path = f"images/{session.session_id}/{len(session.log)}.png"
            output_path = store.directory / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            session.log.append(f"[image: {relative_path}]")
            generated_image = True
        except (ValueError, TypeError, OSError, httpx.HTTPError, RuntimeError) as e:
            session.log.append(f"[image error: {e}]")
    session.last_turn_had_image = generated_image
    if not generated_image:
        await _maybe_compact(session, narrator_client)


# Playthrough 2026-11-07: a natural-10 punch read as "he's not down, just shaken".
_OUTCOME_GUIDE = {
    "clean_success": "It works, fully and visibly: show what the character gets.",
    "complication": "It works, but at a cost: show both.",
    "failure": "It fails, and something changes for the worse.",
}
_OUTCOME_TEXT = {
    "clean_success": "a clean success",
    "complication": "success with a complication",
    "failure": "a failure",
}


def _label(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _roll_line(pending: dict, result: dict, stat: str = "humanity") -> str:
    # A visible story line (not bracketed), so later turns' prompts keep it -
    # the narrator remembers how the dice actually fell.
    die, attr_mod, skill_mod = result["die_result"], result["attribute_mod"], result["skill_mod"]
    bonus = result.get("overclock_bonus", 0)
    total = die + attr_mod + skill_mod + bonus
    who = pending["name"]
    if "overclock" in result:
        who += f" overclocks {CHROME[result['overclock']].name} (−{result['humanity_loss']} {stat}) and"
    formula = f"{die} {attr_mod:+d} {skill_mod:+d}" + (f" {bonus:+d}" if bonus else "")
    line = (
        f"{who} rolls {_label(pending['skill'])} ({_label(pending['attribute'])}) "
        f"vs {_label(pending['difficulty'])}: {_OUTCOME_TEXT[result['outcome']]} "
        f"({formula} = {total} vs {result['dc']})"
    )
    if die in (1, 10):
        line += f" — a natural {die}"
    return line + "."


def resolve_roll(session: Session, player_id: str, overclock: str | None = None) -> dict:
    pending = session.pending_rolls.get(player_id)
    if pending is None:
        raise ValueError("no roll pending")
    character = session.characters.get(player_id)
    if character is None:
        raise ValueError(f"unknown player_id: {player_id!r}")
    if overclock is not None and overclock not in {o["id"] for o in usable_overclocks(character, pending["skill"])}:
        raise ValueError(f"can't overclock {overclock!r} on this roll")
    result = roll_check(character, pending["attribute"], pending["skill"], pending["difficulty"], overclock)
    session.pending_rolls.pop(player_id, None)  # only after a successful roll
    if overclock is not None:
        before = character.humanity
        session.pending_world_events.extend(change_humanity(character, -random.randint(1, 6)))
        result["humanity_loss"] = before - character.humanity
    session.log.append(_roll_line(pending, result, "selfhood" if is_tsukumogami(character) else "humanity"))
    rolled = {**result, **pending}
    session.log.append(f"[roll: {json.dumps(rolled)}]")
    return rolled


async def narrate_roll(
    session: Session,
    narrator_client: NarratorClient,
    store: JSONFileSessionStore,
    image_backend: ImageBackend,
    tts_backend: TTSBackend,
    player_id: str,
    rolled: dict,
) -> None:
    # Soak run 5: resolutions re-described the place instead of resolving the punch, then asked for another roll.
    action = _last_action(session, player_id)
    tried = f" They tried: {action}." if action else ""
    await _run_turn(
        session, narrator_client, store, image_backend, tts_backend, player_id,
        prompt_text=(
            f"Roll result for {rolled['name']}: {_OUTCOME_TEXT[rolled['outcome']]} on "
            f"{rolled['reason']}.{tried} Narrate what happens now, true to that result: start with the "
            f"outcome itself. {_OUTCOME_GUIDE[rolled['outcome']]} No new roll this turn."
        ),
        actor_line=None, allow_roll=False,
        # The prompt is the engine's instruction; the referee judges what the player chose to do.
        referee_action=action or rolled["reason"],
    )


def _last_action(session: Session, player_id: str) -> str | None:
    prefix = f"{player_id}: "
    return next((line[len(prefix):] for line in reversed(session.log) if line.startswith(prefix)), None)


async def handle_roll(
    session: Session,
    narrator_client: NarratorClient,
    store: JSONFileSessionStore,
    image_backend: ImageBackend,
    tts_backend: TTSBackend,
    player_id: str,
    overclock: str | None = None,
) -> None:
    rolled = resolve_roll(session, player_id, overclock)
    await narrate_roll(session, narrator_client, store, image_backend, tts_backend, player_id, rolled)
