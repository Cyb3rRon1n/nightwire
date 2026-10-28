import json
import random

import httpx
import ollama

from engine.chrome import change_humanity, usable_overclocks
from engine.debt import tick_debt
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend
from narrator.tools import RequestRoll, execute_tool, roll_check
from narrator.tts_backend import TTSBackend
from narrator.voice_assignment import assign_voice
from narrator.world import kuroshio, select_cards
from ruleset.cyberware import CHROME, humanity_tier
from ruleset.difficulty import Difficulty


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


def _crew_line(session: Session) -> str:
    entries = []
    for c in session.characters.values():
        if not c.chrome and c.humanity == 100 and c.installments_owed <= 0:
            continue
        entry = f"{c.name}: humanity {c.humanity} ({humanity_tier(c.humanity)})"
        if c.chrome:
            entry += ", chrome: " + ", ".join(CHROME[i].name for i in c.chrome)
        if c.installments_owed > 0:
            entry += f", owes {c.installments_owed}, repo clock {c.repo_clock}/6"
        if c.throttled:
            entry += f", throttled: {CHROME[c.throttled].name}"
        if c.pending_repo:
            entry += f", repo crew coming for: {CHROME[c.pending_repo].name}"
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
    narrative = [line for line in session.log if not line.startswith("[")]
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


def _hold_roll(session: Session, player_id: str, tool_args: dict) -> None:
    # Two-step rolls (Phase 16): don't roll yet - the player rolls next, then
    # the narrator resolves knowing the result. Server-authoritative actor,
    # same as before: never the model's own player_id.
    tool_args["player_id"] = player_id
    try:
        request = RequestRoll(**tool_args)
    except (ValueError, TypeError) as e:
        session.log.append(f"[tool error: {e}]")
        return
    character = session.characters.get(player_id)
    if character is None:
        session.log.append(f"[tool error: unknown player_id: {player_id!r}]")
        return
    pending = request.model_dump()
    pending["dc"] = Difficulty[request.difficulty.upper()].value
    pending["name"] = character.name
    session.pending_rolls[player_id] = pending
    session.log.append(f"[roll pending: {json.dumps(pending)}]")


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
    if player_id in session.pending_rolls:
        raise ValueError("roll first")
    character = session.characters.get(player_id)
    if character is not None:
        for event in tick_debt(character):
            session.pending_world_events.append(event)
            session.log.append(f"[torite: {event}]")
    await _run_turn(
        session, narrator_client, store, image_backend, tts_backend, player_id,
        prompt_text=action_text, actor_line=f"{player_id}: {action_text}", allow_roll=True,
    )


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
) -> None:
    # Events are shown once, but only dropped after the narrator actually
    # responded; events queued during the turn survive to the next one.
    shown_events = len(session.pending_world_events)
    messages = _build_messages(session, prompt_text, narrator_client.num_ctx)
    response = await narrator_client.respond(messages)
    del session.pending_world_events[:shown_events]

    if actor_line is not None:
        session.log.append(actor_line)

    for i, segment in enumerate(response.narration):
        line = segment.text if segment.speaker == "narrator" else f"{segment.speaker}: {segment.text}"
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

    if response.tool is not None:
        tool_args = dict(response.tool_args)
        if response.tool == "request_roll":
            if allow_roll:
                _hold_roll(session, player_id, tool_args)
            else:
                session.log.append("[tool error: no new rolls during a roll resolution]")
        else:
            try:
                result = execute_tool(session, response.tool, tool_args)
                session.log.append(f"[{response.tool}: {result}]")
            except (ValueError, TypeError) as e:
                session.log.append(f"[tool error: {e}]")

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
            image_bytes = await image_backend.generate_scene(response.image_request.prompt, reference_paths)
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


_OUTCOME_TEXT = {
    "clean_success": "a clean success",
    "complication": "success with a complication",
    "failure": "a failure",
}


def _label(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _roll_line(pending: dict, result: dict) -> str:
    # A visible story line (not bracketed), so later turns' prompts keep it -
    # the narrator remembers how the dice actually fell.
    die, attr_mod, skill_mod = result["die_result"], result["attribute_mod"], result["skill_mod"]
    bonus = result.get("overclock_bonus", 0)
    total = die + attr_mod + skill_mod + bonus
    who = pending["name"]
    if "overclock" in result:
        who += f" overclocks {CHROME[result['overclock']].name} (−{result['humanity_loss']} humanity) and"
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
    session.log.append(_roll_line(pending, result))
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
    await _run_turn(
        session, narrator_client, store, image_backend, tts_backend, player_id,
        prompt_text=(
            f"Roll result for {rolled['name']}: {_OUTCOME_TEXT[rolled['outcome']]} on "
            f"{rolled['reason']}. Narrate what happens now, true to that result."
        ),
        actor_line=None, allow_roll=False,
    )


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
