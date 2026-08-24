from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend
from narrator.tools import execute_tool


def _build_messages(session: Session, action_text: str) -> list[dict]:
    # [start_combat: {...}]-style lines are tool-execution annotations for the
    # UI, not narrative fact - feeding them back verbatim let the model read
    # its own acknowledgment ("combat start requires...") as evidence combat
    # was actually ongoing, and re-trigger the tool turn after turn.
    narrative = [line for line in session.log if not line.startswith("[")]
    recent = "\n".join(narrative[-10:])
    context = f"Recent events:\n{recent}\n\n" if recent else ""
    return [{"role": "user", "content": f"{context}Player action: {action_text}"}]


async def handle_action(
    session: Session,
    narrator_client: NarratorClient,
    store: JSONFileSessionStore,
    image_backend: ImageBackend,
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
    for segment in response.narration:
        session.log.append(segment.text)

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

    if response.image_request is not None:
        character = session.characters.get(player_id)
        reference_paths = []
        if character is not None and character.portrait_path is not None:
            reference_paths.append(str(store.directory / character.portrait_path))
        try:
            await narrator_client.unload()
            image_bytes = await image_backend.generate_scene(response.image_request.prompt, reference_paths)
            relative_path = f"images/{session.session_id}/{len(session.log)}.png"
            output_path = store.directory / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            session.log.append(f"[image: {relative_path}]")
        except (ValueError, TypeError, OSError) as e:
            session.log.append(f"[image error: {e}]")
