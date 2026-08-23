from engine.session import Session
from narrator.client import NarratorClient
from narrator.tools import execute_tool


def _build_messages(session: Session, action_text: str) -> list[dict]:
    recent = "\n".join(session.log[-10:])
    context = f"Recent events:\n{recent}\n\n" if recent else ""
    return [{"role": "user", "content": f"{context}Player action: {action_text}"}]


async def handle_action(session: Session, narrator_client: NarratorClient, player_id: str, message: dict) -> None:
    action_text = message.get("text")
    if not action_text:
        raise ValueError("missing 'text' in action message")

    messages = _build_messages(session, action_text)
    response = await narrator_client.respond(messages)

    session.log.append(f"{player_id}: {action_text}")
    session.log.append(response.narration)

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
