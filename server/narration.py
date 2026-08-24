from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend
from narrator.tools import execute_tool
from narrator.tts_backend import TTSBackend
from narrator.voice_assignment import assign_voice


def _build_messages(session: Session, action_text: str) -> list[dict]:
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
    recent = "\n".join(narrative[-10:])
    context = f"Recent events:\n{recent}\n\n" if recent else ""
    return [{"role": "user", "content": f"{party}{context}Player action: {action_text}"}]


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

    messages = _build_messages(session, action_text)
    response = await narrator_client.respond(messages)

    session.log.append(f"{player_id}: {action_text}")

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
            # Server-authoritative: never trust the model's own player_id for
            # whose attributes apply to a roll it requested on the actor's behalf.
            tool_args["player_id"] = player_id
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
        try:
            await narrator_client.unload()
            await tts_backend.unload()
            image_bytes = await image_backend.generate_scene(response.image_request.prompt, reference_paths)
            relative_path = f"images/{session.session_id}/{len(session.log)}.png"
            output_path = store.directory / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            session.log.append(f"[image: {relative_path}]")
            generated_image = True
        except (ValueError, TypeError, OSError) as e:
            session.log.append(f"[image error: {e}]")
    session.last_turn_had_image = generated_image
