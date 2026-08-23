import json

import pytest

from engine.character import CharacterSheet
from engine.session import Session
from narrator.client import NarratorClient
from server.narration import handle_action


def _fake_client(narration: str, tool: str | None = None, tool_args: dict | None = None) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        payload = {"narration": narration, "tool": tool, "tool_args": tool_args or {}}
        return {"message": {"content": json.dumps(payload)}}
    return NarratorClient(chat_fn=chat_fn)


def _session_with_character() -> Session:
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(
        player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"reflexes": 14},
    )
    return session


@pytest.mark.asyncio
async def test_handle_action_appends_the_players_action_and_the_narration_to_the_log():
    session = _session_with_character()
    client = _fake_client("The alley is quiet.")

    await handle_action(session, client, "p1", {"text": "I look around."})

    assert session.log == ["p1: I look around.", "The alley is quiet."]


@pytest.mark.asyncio
async def test_handle_action_raises_on_missing_text():
    session = _session_with_character()
    client = _fake_client("ok")
    with pytest.raises(ValueError, match="missing 'text'"):
        await handle_action(session, client, "p1", {})


@pytest.mark.asyncio
async def test_handle_action_executes_a_tool_call_and_logs_the_result():
    session = _session_with_character()
    client = _fake_client(
        "You lunge for the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill_mod": 1,
            "difficulty": "easy", "reason": "leap",
        },
    )

    await handle_action(session, client, "p1", {"text": "I leap the gap."})

    assert any("request_roll" in line for line in session.log)


@pytest.mark.asyncio
async def test_handle_action_overrides_the_models_player_id_for_request_roll():
    # Server-authoritative: the acting player_id always wins for request_roll,
    # regardless of what the model put in tool_args.
    session = _session_with_character()
    client = _fake_client(
        "You lunge for the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill_mod": 1,
            "difficulty": "easy", "reason": "leap",
        },
    )

    await handle_action(session, client, "p1", {"text": "I leap the gap."})

    assert "unknown player_id" not in "".join(session.log)


@pytest.mark.asyncio
async def test_handle_action_logs_a_tool_error_without_raising():
    session = _session_with_character()
    client = _fake_client(
        "You reach for your gear.", tool="apply_character_update",
        tool_args={"player_id": "ghost"},
    )

    await handle_action(session, client, "p1", {"text": "I check my gear."})

    assert any("tool error" in line for line in session.log)


@pytest.mark.asyncio
async def test_handle_action_with_no_tool_call_only_logs_narration():
    session = _session_with_character()
    client = _fake_client("The street is empty.")

    await handle_action(session, client, "p1", {"text": "I look around."})

    assert session.log == ["p1: I look around.", "The street is empty."]
