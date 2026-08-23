# tests/test_harness.py
import json

import pytest

from narrator.client import NarratorClient
from narrator.harness import Scenario, run_harness


def _fake_chat_always_returning(payload: dict):
    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps(payload)}}
    return chat_fn


@pytest.mark.asyncio
async def test_run_harness_scores_a_correct_tool_call_as_a_pass():
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "You reach for your pistol.",
        "tool": "request_roll",
        "tool_args": {
            "player_id": "p1", "attribute": "reflexes", "skill_mod": 2,
            "difficulty": "moderate", "reason": "quickdraw",
        },
    }))
    scenarios = [
        Scenario(
            name="risky_action_calls_request_roll",
            messages=[{"role": "user", "content": "I try to quickdraw on the ganger."}],
            expected_tool="request_roll",
        ),
    ]

    report = await run_harness(client, scenarios, repeat=3)

    assert report.results["risky_action_calls_request_roll"].passes == 3
    assert report.results["risky_action_calls_request_roll"].total == 3


@pytest.mark.asyncio
async def test_run_harness_scores_a_wrong_tool_call_as_a_fail():
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "You wander off.", "tool": None, "tool_args": {},
    }))
    scenarios = [
        Scenario(
            name="risky_action_calls_request_roll",
            messages=[{"role": "user", "content": "I try to quickdraw on the ganger."}],
            expected_tool="request_roll",
        ),
    ]

    report = await run_harness(client, scenarios, repeat=2)

    assert report.results["risky_action_calls_request_roll"].passes == 0
    assert report.results["risky_action_calls_request_roll"].total == 2


@pytest.mark.asyncio
async def test_run_harness_scores_narration_only_scenarios_correctly():
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "The street is quiet tonight.", "tool": None, "tool_args": {},
    }))
    scenarios = [
        Scenario(
            name="idle_description_has_no_tool_call",
            messages=[{"role": "user", "content": "I look around."}],
            expected_tool=None,
        ),
    ]

    report = await run_harness(client, scenarios, repeat=1)

    assert report.results["idle_description_has_no_tool_call"].passes == 1


@pytest.mark.asyncio
async def test_run_harness_covers_every_scenario_in_the_report():
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "ok", "tool": None, "tool_args": {},
    }))
    scenarios = [
        Scenario(name="a", messages=[{"role": "user", "content": "x"}], expected_tool=None),
        Scenario(name="b", messages=[{"role": "user", "content": "y"}], expected_tool=None),
    ]

    report = await run_harness(client, scenarios, repeat=1)

    assert set(report.results.keys()) == {"a", "b"}


@pytest.mark.asyncio
async def test_run_harness_fails_a_scenario_whose_tool_args_dont_validate():
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "You lunge for the ledge.",
        "tool": "request_roll",
        "tool_args": {"player_id": "p1", "attribute": "body", "skill_mod": 1, "difficulty": "nightmarish", "reason": "leap"},
    }))
    scenarios = [
        Scenario(
            name="risky_action_calls_request_roll",
            messages=[{"role": "user", "content": "I try to leap the gap."}],
            expected_tool="request_roll",
        ),
    ]

    report = await run_harness(client, scenarios, repeat=1)

    assert report.results["risky_action_calls_request_roll"].passes == 0
