# Phase 3b: WebSocket Narrator Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the narrator engine (Phase 3a) into the live WebSocket server (Phase 2b) — a new `action` message type flows a player's free-text action through the narrator, executes any resulting tool call against the real session, and broadcasts the narration to every connected player. Closes two real gaps the Phase 3a final review found: `NarratorClient` was synchronous (would block the async WS event loop for every player) and `request_roll` trusted model-supplied attribute modifiers instead of the acting character's real stats.

**Architecture:** `NarratorClient.respond()` becomes async (Task 1), backed by `ollama.AsyncClient`. `request_roll` gains a real `player_id`/`attribute` lookup against `CharacterSheet.attributes` via `ruleset.attributes.modifier()` (Task 2) — the server-authoritative pattern already established for `request_roll`'s die result extends to the attribute modifier too. `server/views.py`'s `build_view` starts including the world-state fields Phase 3a added to `Session` but never broadcast (Task 3) — otherwise `update_world` tool calls would execute but never reach a client. A new `server/narration.py` (Task 4) is the only new integration surface: it builds a short conversation-context window from `Session.log` (unchanged schema — no new persisted chat-history structure), calls the narrator, appends the action and narration to the log, and executes any tool call — injecting the acting `player_id` for `request_roll` specifically, since that's the one tool where the model must never choose whose stats apply. `server/app.py` gains one new branch in its existing message-type dispatch, symmetric with the existing `join` special-case.

**Tech Stack:** No new dependencies — `ollama.AsyncClient` and `pytest-asyncio` are already installed from Phase 3a.

**Spec:** `docs/superpowers/specs/2026-08-22-narrator-backend-design.md` (tool surface, reliability), `docs/superpowers/specs/2026-08-22-core-engine-design.md` (turn model — this plan does not change turn/combat gating; a narrated action outside combat is still free-flowing per the existing engine, and this plan does not add narrator-triggered combat state changes)

## Global Constraints

- Python >=3.11. `NarratorClient.respond()` is `async def` as of Task 1 — every call site (Task 4's `handle_action`, `narrator/harness.py`) must `await` it.
- `request_roll`'s attribute modifier is server-computed from `session.characters[player_id].attributes` via `ruleset.attributes.modifier()` — never trusted from the model. `skill_mod` stays model-supplied but clamped to `[-2, 5]`, because the ruleset (Phase 1) never built a skill system — `CharacterSheet` has no skills field to look up. This is a documented, deliberate simplification, not an oversight; a real skill system is out of this plan's scope.
- `request_roll`'s `tool_args["player_id"]` is always overwritten server-side with the acting connection's real `player_id` before validation, in `server/narration.py` — the model's own `player_id` value for this specific tool is discarded, never trusted. `apply_character_update` keeps trusting the model's `player_id` as-is (unchanged from Phase 3a) — that tool legitimately targets a different character than the actor (e.g. narrating damage to an NPC or another player).
- `Session.log` stays `list[str]` — no new persisted chat-history structure. The narrator's conversation context is rebuilt fresh on every call from the last 10 `session.log` entries; multi-turn memory beyond that window, and prompt-engineering quality generally, are explicitly deferred per the spec.
- A tool-execution failure (`ValueError`/`TypeError` from `narrator.tools.execute_tool`) is caught in `server/narration.py` and appended to `session.log` as a visible `"[tool error: ...]"` entry — it never raises out of `handle_action`, never crashes the WebSocket connection.
- No live-model or network calls in `pytest -v` — every new/changed async test uses a fake async `chat_fn`. Manual verification against the real local model is a Task 5 step, not part of the automated suite.
- This plan does not add narrator-triggered combat start/end, narrator-triggered turn advancement, or out-of-turn action rejection — `handle_action` runs regardless of `session.in_combat`/turn order, matching the existing engine's free-flowing-outside-combat model. Enforcing "only the current turn's player may act during combat" for narrated actions is real follow-up work, not this plan's job (the existing `is_players_turn` check exists in `engine.turns` but nothing in this plan calls it from the action path).

---

## File Structure

- Modify: `narrator/client.py` — `NarratorClient.respond()` becomes `async def`, backed by `ollama.AsyncClient` by default.
- Modify: `narrator/harness.py` — `run_harness()` becomes `async def`; `main()` uses `asyncio.run`.
- Modify: `narrator/tools.py` — `RequestRoll` gains `player_id`/`attribute` fields, drops `attribute_mod`; `_execute_request_roll` looks up the real score.
- Modify: `server/views.py` — `build_view` includes `location`, `scene_mood`, `active_objectives`.
- Create: `server/narration.py` — `handle_action(session, narrator_client, player_id, message) -> None`.
- Modify: `server/app.py` — `create_app(store, narrator_client)`; the message loop branches on `type == "action"`.
- Modify: `tests/test_narrator_client.py`, `tests/test_harness.py`, `tests/test_narrator_tools.py`, `tests/test_views.py`, `tests/test_app.py` — updated/added tests.
- Create: `tests/test_narration.py`.

## Interfaces this plan builds on (current state, post Phase 3a)

```python
# narrator/tools.py (current — Task 2 changes RequestRoll)
class ApplyCharacterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: str
    health_delta: int = 0
    armor_delta: int = 0
    add_conditions: list[str] = []
    remove_conditions: list[str] = []
    add_inventory: list[str] = []
    remove_inventory: list[str] = []

TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Callable[[Session, BaseModel], dict]]]
def execute_tool(session: Session, tool_name: str, tool_args: dict) -> dict: ...

# narrator/client.py (current — Task 1 changes respond() to async)
class NarratorResponse(BaseModel):
    narration: str
    tool: ToolName | None = None
    tool_args: dict = {}

class NarratorClient:
    def __init__(self, model: str = "qwen3:8b", system_prompt: str = "", chat_fn=None) -> None: ...
    def respond(self, messages: list[dict]) -> NarratorResponse: ...  # Task 1: becomes async

# engine/session.py (unchanged)
@dataclass
class Session:
    session_id: str
    characters: dict[str, CharacterSheet]
    turn_order: list[str]
    current_turn_index: int
    in_combat: bool
    pre_combat_turn_order: list[str] | None
    log: list[str]
    location: str | None
    scene_mood: str | None
    active_objectives: list[str]

# engine/character.py (unchanged)
@dataclass
class CharacterSheet:
    player_id: str
    name: str
    role: str
    lifepath: str
    attributes: dict[str, int]  # e.g. {"reflexes": 14} — raw scores, not modifiers
    health: int
    max_health: int
    armor: int
    conditions: list[str]
    inventory: list[str]

# ruleset/attributes.py (unchanged)
def modifier(score: int) -> int: ...  # (score - 10) // 2

# server/dispatch.py (unchanged)
def handle_message(session: Session, message: dict) -> None: ...  # join/start_combat/advance_turn/end_combat

# server/connection_manager.py (unchanged)
class ConnectionManager:
    def connect(self, session_id: str, player_id: str, connection) -> None: ...
    def disconnect(self, session_id: str, player_id: str, connection=None) -> None: ...
    async def broadcast(self, session_id: str, session: Session) -> None: ...

# server/app.py (current — Task 4 changes create_app's signature and the message loop)
def create_app(store: JSONFileSessionStore) -> FastAPI: ...
```

---

### Task 1: Async narrator client and harness

**Files:**
- Modify: `narrator/client.py`
- Modify: `narrator/harness.py`
- Modify: `tests/test_narrator_client.py`
- Modify: `tests/test_harness.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `NarratorClient.respond(messages: list[dict]) -> Awaitable[NarratorResponse]` — used by Task 4's `handle_action`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_narrator_client.py` in full:

```python
# tests/test_narrator_client.py
import json

import pytest

from narrator.client import NarratorClient, NarratorResponse


def _fake_chat_returning(payload: dict):
    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps(payload)}}
    return chat_fn


@pytest.mark.asyncio
async def test_respond_returns_narration_only_when_no_tool_call():
    client = NarratorClient(
        model="qwen3:8b",
        system_prompt="You are a cyberpunk GM.",
        chat_fn=_fake_chat_returning({"narration": "The alley is quiet.", "tool": None, "tool_args": {}}),
    )
    response = await client.respond([{"role": "user", "content": "I look around."}])
    assert isinstance(response, NarratorResponse)
    assert response.narration == "The alley is quiet."
    assert response.tool is None
    assert response.tool_args == {}


@pytest.mark.asyncio
async def test_respond_returns_a_tool_call():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "You lunge for the ledge.",
            "tool": "request_roll",
            "tool_args": {
                "player_id": "p1", "attribute": "reflexes", "skill_mod": 1,
                "difficulty": "hard", "reason": "leap across a gap",
            },
        }),
    )
    response = await client.respond([{"role": "user", "content": "I try to jump the gap."}])
    assert response.tool == "request_roll"
    assert response.tool_args["difficulty"] == "hard"


@pytest.mark.asyncio
async def test_respond_passes_the_structured_output_schema_to_chat_fn():
    seen = {}

    async def chat_fn(*, model, messages, format):
        seen["format"] = format
        seen["model"] = model
        return {"message": {"content": json.dumps({"narration": "ok", "tool": None, "tool_args": {}})}}

    client = NarratorClient(model="qwen3:8b", chat_fn=chat_fn)
    await client.respond([{"role": "user", "content": "hi"}])

    assert seen["model"] == "qwen3:8b"
    assert seen["format"] == NarratorResponse.model_json_schema()


@pytest.mark.asyncio
async def test_respond_prepends_the_system_prompt():
    seen = {}

    async def chat_fn(*, model, messages, format):
        seen["messages"] = messages
        return {"message": {"content": json.dumps({"narration": "ok", "tool": None, "tool_args": {}})}}

    client = NarratorClient(system_prompt="You are a cyberpunk GM.", chat_fn=chat_fn)
    await client.respond([{"role": "user", "content": "hi"}])

    assert seen["messages"][0] == {"role": "system", "content": "You are a cyberpunk GM."}
    assert seen["messages"][1] == {"role": "user", "content": "hi"}


@pytest.mark.asyncio
async def test_respond_raises_on_malformed_model_output():
    async def chat_fn(**kwargs):
        return {"message": {"content": "not json"}}

    client = NarratorClient(chat_fn=chat_fn)
    with pytest.raises(ValueError):
        await client.respond([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_respond_raises_on_a_hallucinated_tool_name():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "You lunge for the ledge.",
            "tool": "Agility Check (DC 15) to leap across the gap",
            "tool_args": {},
        }),
    )
    with pytest.raises(ValueError):
        await client.respond([{"role": "user", "content": "I try to jump the gap."}])
```

Replace `tests/test_harness.py` in full:

```python
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
        "tool_args": {"player_id": "p1", "attribute": "reflexes", "skill_mod": 1, "difficulty": "nightmarish", "reason": "leap"},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrator_client.py tests/test_harness.py -v`
Expected: FAIL — `TypeError: object NarratorResponse can't be used in 'await' expression` (or similar: the tests now `await` a function that isn't yet a coroutine)

- [ ] **Step 3: Write minimal implementation**

```python
# narrator/client.py
from collections.abc import Awaitable, Callable
from typing import Literal

import ollama
from pydantic import BaseModel, ValidationError

from narrator.tools import TOOL_REGISTRY

ToolName = Literal[tuple(TOOL_REGISTRY)]


class NarratorResponse(BaseModel):
    narration: str
    tool: ToolName | None = None
    tool_args: dict = {}


class NarratorClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        system_prompt: str = "",
        chat_fn: Callable[..., Awaitable[dict]] | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self._chat_fn = chat_fn or self._default_chat

    @staticmethod
    async def _default_chat(*, model: str, messages: list[dict], format: dict) -> dict:
        return await ollama.AsyncClient().chat(model=model, messages=messages, format=format)

    async def respond(self, messages: list[dict]) -> NarratorResponse:
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        response = await self._chat_fn(
            model=self.model,
            messages=full_messages,
            format=NarratorResponse.model_json_schema(),
        )
        try:
            return NarratorResponse.model_validate_json(response["message"]["content"])
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e
```

```python
# narrator/harness.py
import argparse
import asyncio
from dataclasses import dataclass, field

from pydantic import ValidationError

from narrator.client import NarratorClient, NarratorResponse
from narrator.tools import TOOL_REGISTRY


@dataclass
class Scenario:
    name: str
    messages: list[dict]
    expected_tool: str | None


@dataclass
class ScenarioResult:
    passes: int = 0
    total: int = 0


@dataclass
class HarnessReport:
    results: dict[str, ScenarioResult] = field(default_factory=dict)


def _scores_as_pass(response: NarratorResponse, expected_tool: str | None) -> bool:
    if response.tool != expected_tool:
        return False
    if expected_tool is None:
        return True
    model_cls, _ = TOOL_REGISTRY[expected_tool]
    try:
        model_cls(**response.tool_args)
        return True
    except ValidationError:
        return False


async def run_harness(client: NarratorClient, scenarios: list[Scenario], repeat: int) -> HarnessReport:
    report = HarnessReport()
    for scenario in scenarios:
        result = ScenarioResult()
        for _ in range(repeat):
            response = await client.respond(scenario.messages)
            result.total += 1
            if _scores_as_pass(response, scenario.expected_tool):
                result.passes += 1
        report.results[scenario.name] = result
    return report


DEFAULT_SCENARIOS: list[Scenario] = [
    Scenario(
        name="risky_physical_action_calls_request_roll",
        messages=[{"role": "user", "content": "I try to leap across the rooftop gap before the drone spots me."}],
        expected_tool="request_roll",
    ),
    Scenario(
        name="idle_observation_has_no_tool_call",
        messages=[{"role": "user", "content": "I look around the room."}],
        expected_tool=None,
    ),
    Scenario(
        name="taking_damage_calls_apply_character_update",
        messages=[{"role": "system", "content": "The player was just hit by gunfire for 4 damage."},
                   {"role": "user", "content": "I stagger back, bleeding."}],
        expected_tool="apply_character_update",
    ),
    Scenario(
        name="entering_a_new_location_calls_update_world",
        messages=[{"role": "user", "content": "I head into the Afterlife bar."}],
        expected_tool="update_world",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the narrator reliability harness against a live model.")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--model", type=str, default="qwen3:8b")
    parser.add_argument("--system-prompt", type=str, default="You are a cyberpunk tabletop game master.")
    args = parser.parse_args()

    client = NarratorClient(model=args.model, system_prompt=args.system_prompt)
    report = asyncio.run(run_harness(client, DEFAULT_SCENARIOS, args.repeat))

    for name, result in report.results.items():
        rate = result.passes / result.total if result.total else 0.0
        print(f"{name}: {result.passes}/{result.total} ({rate:.0%})")


if __name__ == "__main__":
    main()
```

Note: `Literal[tuple(TOOL_REGISTRY)]` is unchanged from Phase 3a — this task doesn't touch that constraint, only makes `respond()` async.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrator_client.py tests/test_harness.py -v`
Expected: PASS (6 passed in test_narrator_client.py, 5 passed in test_harness.py)

- [ ] **Step 5: Commit**

```bash
git add narrator/client.py narrator/harness.py tests/test_narrator_client.py tests/test_harness.py
git commit -m "feat: make NarratorClient and the reliability harness async"
```

---

### Task 2: Real attribute lookup for request_roll

**Files:**
- Modify: `narrator/tools.py`
- Modify: `tests/test_narrator_tools.py`

**Interfaces:**
- Consumes: `ruleset.attributes.modifier(score: int) -> int` (new import into `narrator/tools.py`).
- Produces: `RequestRoll` now requires `player_id: str` and `attribute: Literal[...]` instead of a raw `attribute_mod: int` — a breaking change to `RequestRoll`'s own shape, contained entirely within `narrator/tools.py` and its tests. `TOOL_REGISTRY`'s type and `execute_tool`'s signature are unchanged.

- [ ] **Step 1: Write the failing tests**

Replace the `request_roll`-related section of `tests/test_narrator_tools.py` (the two existing `test_request_roll_*` functions) with these five:

```python
def test_request_roll_uses_the_characters_real_attribute_score():
    session = _session_with_character(attributes={"reflexes": 16})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill_mod": 0, "difficulty": "easy", "reason": "dodge",
    })
    assert result["attribute_mod"] == 3  # modifier(16) == (16 - 10) // 2 == 3


def test_request_roll_clamps_skill_mod_to_a_plausible_range():
    session = _session_with_character()
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "body", "skill_mod": 999, "difficulty": "easy", "reason": "x",
    })
    assert result["skill_mod"] == 5


def test_request_roll_rejects_an_unknown_player_id():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        execute_tool(session, "request_roll", {
            "player_id": "ghost", "attribute": "body", "skill_mod": 0, "difficulty": "easy", "reason": "x",
        })


def test_request_roll_rolls_a_real_die_and_resolves_the_outcome():
    session = _session_with_character(attributes={"reflexes": 14})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill_mod": 2, "difficulty": "easy", "reason": "climbing a wall",
    })
    assert 1 <= result["die_result"] <= 10
    assert result["dc"] == 8
    assert result["outcome"] in ("clean_success", "complication", "failure")


def test_request_roll_rejects_an_unknown_difficulty():
    session = _session_with_character()
    with pytest.raises(ValueError):
        execute_tool(session, "request_roll", {
            "player_id": "p1", "attribute": "body", "skill_mod": 0, "difficulty": "impossible", "reason": "x",
        })
```

(`_session_with_character(**overrides)` is the existing helper already at the top of this file — `CharacterSheet`'s `attributes` field defaults to `{}`, and `_execute_request_roll`'s `.get(tool.attribute, 10)` fallback means a character with no `attributes` set still resolves with a neutral score, so the tests that don't care about the exact modifier don't need to pass `attributes` explicitly.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrator_tools.py -v`
Expected: FAIL — the old `test_request_roll_rolls_a_real_die_and_resolves_the_outcome`/`test_request_roll_rejects_an_unknown_difficulty` calls (still passing `attribute_mod`) now raise a pydantic `ValidationError` since `RequestRoll` no longer has that field, until you've replaced them with the versions above.

- [ ] **Step 3: Write minimal implementation**

In `narrator/tools.py`, change the imports and `RequestRoll`:

```python
import random
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from engine.session import Session
from ruleset.attributes import modifier
from ruleset.difficulty import Difficulty
from ruleset.resolution import resolve_roll


class RequestRoll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    attribute: Literal["body", "reflexes", "tech", "cool", "intellect", "presence"]
    skill_mod: int
    difficulty: Literal["easy", "moderate", "hard", "extreme"]
    reason: str
```

Replace `_execute_request_roll`:

```python
def _execute_request_roll(session: Session, tool: RequestRoll) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    character = session.characters[tool.player_id]
    raw_score = character.attributes.get(tool.attribute, 10)
    attribute_mod = modifier(raw_score)
    # ponytail: no skill system exists yet (the ruleset's Phase 1 never built
    # one) - clamp the model-supplied skill_mod to a plausible range instead
    # of trusting it outright. Real skill lookup when the ruleset adds one.
    skill_mod = max(-2, min(5, tool.skill_mod))
    die_result = random.randint(1, 10)
    dc = Difficulty[tool.difficulty.upper()].value
    outcome = resolve_roll(die_result, attribute_mod, skill_mod, dc)
    return {
        "die_result": die_result,
        "attribute_mod": attribute_mod,
        "skill_mod": skill_mod,
        "dc": dc,
        "outcome": outcome.value,
    }
```

Everything else in `narrator/tools.py` (the other 4 tool classes, executors, `TOOL_REGISTRY`, `execute_tool`) is unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrator_tools.py -v`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
git add narrator/tools.py tests/test_narrator_tools.py
git commit -m "feat: request_roll uses the acting character's real attribute score"
```

---

### Task 3: Broadcast world state

**Files:**
- Modify: `server/views.py`
- Modify: `tests/test_views.py`

**Interfaces:**
- Consumes: `Session.location`, `Session.scene_mood`, `Session.active_objectives` (already exist, added in Phase 3a — `server/views.py` just never read them).
- Produces: `build_view`'s return dict gains 3 keys — used by Task 4's tests (a session mutated by `update_world` should show up in the next broadcast) but no code signature changes.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_views.py`:

```python
def test_view_includes_world_state():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.location = "Watson district"
    session.scene_mood = "tense"
    session.active_objectives = ["find the fixer"]

    view = build_view(session, "p1")

    assert view["location"] == "Watson district"
    assert view["scene_mood"] == "tense"
    assert view["active_objectives"] == ["find the fixer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_views.py -v`
Expected: FAIL with `KeyError: 'location'`

- [ ] **Step 3: Write minimal implementation**

In `server/views.py`, change `build_view`'s return statement:

```python
    return {
        "session_id": session.session_id,
        "in_combat": session.in_combat,
        "current_turn": current_turn(session),
        "is_your_turn": is_players_turn(session, viewer_id),
        "log": session.log,
        "location": session.location,
        "scene_mood": session.scene_mood,
        "active_objectives": session.active_objectives,
        "characters": characters,
    }
```

Nothing else in the file changes.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_views.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add server/views.py tests/test_views.py
git commit -m "feat: broadcast world state (location, scene_mood, active_objectives)"
```

---

### Task 4: Wire the action message into the WebSocket server

**Files:**
- Create: `server/narration.py`
- Test: `tests/test_narration.py`
- Modify: `server/app.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: `narrator.client.NarratorClient` (Task 1's async `respond`), `narrator.tools.execute_tool` (Task 2's real `RequestRoll` shape — this task never constructs a `RequestRoll` directly, only forwards `tool_args` through `execute_tool`, so it doesn't need to know the exact field names beyond `player_id`), `engine.session.Session`.
- Produces: `handle_action(session: Session, narrator_client: NarratorClient, player_id: str, message: dict) -> None` (async, raises `ValueError` on a missing `text` field) — used by Task 4's own `server/app.py` change. `create_app(store: JSONFileSessionStore, narrator_client: NarratorClient) -> FastAPI` — this is a signature change from Phase 2b/3a; nothing outside this plan's tests currently calls `create_app`, so nothing else needs updating.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_narration.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.narration'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/narration.py
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
```

Now update `server/app.py`. The constructor gains a `narrator_client` parameter, and the message loop gets one new branch, symmetric with the existing `join` special-case:

```python
# server/app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from server.connection_manager import ConnectionManager
from server.dispatch import handle_message
from server.narration import handle_action


def create_app(store: JSONFileSessionStore, narrator_client: NarratorClient) -> FastAPI:
    app = FastAPI()
    manager = ConnectionManager()
    sessions: dict[str, Session] = {}  # ponytail: single-process; needs a real store if ever multi-worker

    @app.websocket("/ws/{session_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str, player_id: str) -> None:
        await websocket.accept()
        if session_id not in sessions:
            sessions[session_id] = store.load(session_id) or Session(session_id=session_id)
        session = sessions[session_id]
        manager.connect(session_id, player_id, websocket)

        try:
            while True:
                try:
                    message = await websocket.receive_json()
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"invalid message: {e}"})
                    continue

                if message.get("type") == "join":
                    character_id = (message.get("character") or {}).get("player_id")
                    if character_id != player_id:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"character.player_id {character_id!r} does not match connection player_id {player_id!r}",
                        })
                        continue

                try:
                    if message.get("type") == "action":
                        await handle_action(session, narrator_client, player_id, message)
                    else:
                        handle_message(session, message)
                except (ValueError, TypeError) as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue

                store.save(session)
                await manager.broadcast(session_id, session)
        except WebSocketDisconnect:
            manager.disconnect(session_id, player_id, websocket)

    return app
```

Finally, update `tests/test_app.py`. Add `NarratorClient` to the imports and `json` if not already present, then update the `_client` helper and add two new tests:

```python
# tests/test_app.py — add near the top, alongside the existing imports
import json

from narrator.client import NarratorClient
```

```python
# tests/test_app.py — replace the existing _client helper
def _unused_chat_fn(*, model, messages, format):
    raise AssertionError("narrator should not be called by this test")


def _client(tmp_path, narrator_client=None):
    store = JSONFileSessionStore(tmp_path)
    client = narrator_client or NarratorClient(chat_fn=_unused_chat_fn)
    return TestClient(create_app(store, client))
```

(All 5 existing tests in this file call `_client(tmp_path)` with no `narrator_client` argument and never send an `"action"` message, so `_unused_chat_fn` is never invoked — they continue to pass unchanged.)

```python
# tests/test_app.py — add these two new tests
def test_action_message_triggers_the_narrator_and_broadcasts_narration(tmp_path):
    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps({
            "narration": "The alley is quiet.", "tool": None, "tool_args": {},
        })}}
    narrator_client = NarratorClient(chat_fn=chat_fn)
    client = _client(tmp_path, narrator_client)

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "action", "text": "I look around."})
        view = ws.receive_json()

    assert "The alley is quiet." in view["log"]


def test_action_message_missing_text_sends_an_error(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "action"})
        error = ws.receive_json()

    assert error["type"] == "error"
    assert "text" in error["message"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narration.py tests/test_app.py -v`
Expected: PASS (6 passed in test_narration.py, 7 passed in test_app.py)

- [ ] **Step 5: Commit**

```bash
git add server/narration.py server/app.py tests/test_narration.py tests/test_app.py
git commit -m "feat: wire player actions through the narrator over the WebSocket"
```

---

### Task 5: Full suite sanity check

**Files:** none created — verification only, and a fix commit if anything surfaces.

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: all tests from Phase 1/2a/2b/3a plus every test added/changed in Tasks 1-4 pass; only the 2 pre-existing expected skips remain.

- [ ] **Step 2: Confirm no import errors across modules**

Run: `python -c "import server.app, server.narration, narrator.tools, narrator.client, narrator.harness"`
Expected: exits 0, no output.

- [ ] **Step 3: Manually smoke-test the real loop against the real local model (not part of the automated suite)**

This is the first time an actual player action reaches the real model over a real WebSocket connection — worth a real end-to-end check, not just unit-level fakes. A short script exercising it:

```python
# manual smoke test, not committed - run at the interactive prompt or a throwaway script
import asyncio
from fastapi.testclient import TestClient
from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from server.app import create_app

store = JSONFileSessionStore("/tmp/nightwire-smoke-test")
narrator_client = NarratorClient(model="qwen3:8b", system_prompt="You are a cyberpunk tabletop game master.")
client = TestClient(create_app(store, narrator_client))

with client.websocket_connect("/ws/smoke/p1") as ws:
    ws.send_json({"type": "join", "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid", "attributes": {"reflexes": 14}}})
    print(ws.receive_json())
    ws.send_json({"type": "action", "text": "I try to leap across the rooftop gap before the drone spots me."})
    print(ws.receive_json())
```

Expected: no exception, no timeout, a `view` dict whose `log` contains both the player's action line and a real narration string. Record whether a tool call executed successfully or logged a `[tool error: ...]` line — either is a valid outcome to report, this step is observational (matching Phase 3a's own harness-run convention), not a gate.

- [ ] **Step 4: Commit if anything was fixed during this check**

```bash
git add -A
git commit -m "fix: address issues found in Phase 3b full-suite check"
```

(Skip this step if Steps 1-2 passed clean and nothing needed fixing — Step 3's smoke test is observational, not a fix trigger by itself.)
