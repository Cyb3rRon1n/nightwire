# Phase 3a: Narrator Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the narrator (AI GM) engine as a standalone `narrator/` package: an Ollama structured-output client, the 4-tool surface wired to the existing `engine`/`ruleset` packages, and a repeatable reliability measurement harness against a live local model. No WebSocket wiring — that's Phase 3b.

**Architecture:** `narrator/tools.py` is pure (pydantic schemas + functions mutating `engine.session.Session`/`engine.character.CharacterSheet`, no LLM dependency). `narrator/client.py` wraps `ollama.chat` with a structured-output schema (`format=<json schema>`), validated back into a pydantic model — the same "structured JSON over native tool-calling" approach the spec establishes for local models. The client accepts an injectable `chat_fn`, so `narrator/tools.py` and `narrator/client.py` are both unit-testable with zero network access; only `narrator/harness.py`'s CLI entrypoint touches the real Ollama server. Two existing `engine/` files gain additive fields/round-tripping (Session world-state) — nothing else in `engine/`, `ruleset/`, or `server/` changes.

**Tech Stack:** `ollama` (official Python client) for the local model connection; `pydantic` (already installed transitively via fastapi, made an explicit dependency here since `narrator/` imports it directly) for schema definition, JSON-schema generation, and response validation.

**Spec:** `docs/superpowers/specs/2026-08-23-narrator-backend-design.md` (model choice, content policy, structured-output rationale, tool surface, reliability measurement)

## Global Constraints

- Python >=3.11. No back-compat/versioning shims for saved session files — this is pre-release, no real save data exists yet (matches this project's existing persistence code, which has no migration path either).
- Never trust the model for a die result — `request_roll`'s tool executor always rolls a real `random.randint(1, 10)`; the model only supplies modifiers and difficulty.
- `start_combat`/`end_combat` tools are narration-only in this phase — they never mutate `session.in_combat` or `turn_order`. The spec is explicit that "the narrator doesn't unilaterally decide combat has started; a player action does" — the only mechanical trigger remains the player-sent WebSocket `start_combat`/`end_combat` message already built in Phase 2b (`server/dispatch.py`). Wiring the narrator's tool call into that path is Phase 3b's job, not this plan's.
- The tool executor is a trust boundary (LLM output, not a human's): an unknown `tool_name` or unknown `player_id` raises `ValueError` (matches `server/dispatch.py`'s existing error convention); removing a condition/inventory item that isn't present is a no-op, not an error, since the model's view of state can be stale.
- `health` clamps to `[0, max_health]`; `armor` clamps to a minimum of `0` (no upper bound is modeled on `CharacterSheet`).
- No test in `pytest -v` may call a live model or the network — `narrator/tools.py` and `narrator/client.py` tests use fake/injected callables exclusively. `narrator/harness.py`'s scoring logic gets one such fake-backed unit test; its CLI entrypoint (which does call the real local Ollama server) is exercised manually, not by the automated suite.
- This plan does not add a cyberware/gear subsystem — `CharacterSheet` only has a generic `inventory: list[str]` (the ruleset's Phase 1 never built a richer cyberware model). The spec's "cyberware install/removal" maps onto `apply_character_update`'s existing `add_inventory`/`remove_inventory` fields; a dedicated cyberware system is out of this plan's scope.

---

## File Structure

- `narrator/__init__.py` — empty, makes `narrator` a package.
- `narrator/tools.py` — pydantic tool schemas (`RequestRoll`, `ApplyCharacterUpdate`, `UpdateWorld`, `StartCombat`, `EndCombat`), `TOOL_REGISTRY`, `execute_tool(session, tool_name, tool_args) -> dict`. No I/O, no LLM import.
- `narrator/client.py` — `NarratorResponse` pydantic model, `NarratorClient` class wrapping structured-output Ollama calls.
- `narrator/harness.py` — fixed test scenarios, `run_harness(client, scenarios, repeat) -> HarnessReport`, `python -m narrator.harness --repeat N` CLI entrypoint against the real local model.
- Modify `engine/session.py` — add `location: str | None`, `scene_mood: str | None`, `active_objectives: list[str]` fields.
- Modify `engine/persistence.py` — round-trip the 3 new `Session` fields in `load()`.
- `tests/test_narrator_tools.py`, `tests/test_narrator_client.py`, `tests/test_harness.py` — new test files.
- `tests/test_session.py`, `tests/test_persistence.py` — additive test functions for the new `Session` fields.

## Interfaces this plan builds on (already implemented, unchanged except where noted)

```python
# engine/character.py (unchanged)
@dataclass
class CharacterSheet:
    player_id: str
    name: str
    role: str
    lifepath: str
    attributes: dict[str, int] = field(default_factory=dict)
    health: int = 10
    max_health: int = 10
    armor: int = 0
    conditions: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)

# engine/session.py (Task 1 adds 3 fields, everything else unchanged)
@dataclass
class Session:
    session_id: str
    characters: dict[str, CharacterSheet] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)
    current_turn_index: int = 0
    in_combat: bool = False
    pre_combat_turn_order: list[str] | None = None
    log: list[str] = field(default_factory=list)
    # Task 1 adds: location, scene_mood, active_objectives

# ruleset/resolution.py (unchanged)
class Outcome(StrEnum):
    CLEAN_SUCCESS = "clean_success"
    COMPLICATION = "complication"
    FAILURE = "failure"

def resolve_roll(die_result: int, attribute_mod: int, skill_mod: int, dc: int) -> Outcome: ...

# ruleset/difficulty.py (unchanged)
class Difficulty(IntEnum):
    EASY = 8
    MODERATE = 12
    HARD = 16
    EXTREME = 20
```

---

### Task 1: Session world-state fields

**Files:**
- Modify: `engine/session.py`
- Modify: `engine/persistence.py`
- Modify: `tests/test_session.py`
- Modify: `tests/test_persistence.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Session.location: str | None`, `Session.scene_mood: str | None`, `Session.active_objectives: list[str]` — used by Task 2's `update_world` tool.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_session.py`:

```python
def test_session_world_state_starts_empty():
    session = Session(session_id="test-session")
    assert session.location is None
    assert session.scene_mood is None
    assert session.active_objectives == []


def test_two_sessions_do_not_share_mutable_objectives_list():
    a = Session(session_id="a")
    b = Session(session_id="b")
    a.active_objectives.append("find the fixer")
    assert b.active_objectives == []
```

Add to `tests/test_persistence.py`, inside `test_save_then_load_round_trips_a_session_with_a_character` (extend the existing test rather than duplicating the whole session setup):

```python
    session.location = "Night City - Watson district"
    session.scene_mood = "tense"
    session.active_objectives = ["find the fixer", "avoid corpo patrols"]
```

and, alongside the existing assertions after `loaded = store.load("test-session")`:

```python
    assert loaded.location == "Night City - Watson district"
    assert loaded.scene_mood == "tense"
    assert loaded.active_objectives == ["find the fixer", "avoid corpo patrols"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py tests/test_persistence.py -v`
Expected: FAIL — `TypeError: Session.__init__() got an unexpected keyword argument` or `AttributeError: 'Session' object has no attribute 'location'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/session.py
from dataclasses import dataclass, field

from engine.character import CharacterSheet


@dataclass
class Session:
    session_id: str
    characters: dict[str, CharacterSheet] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)
    current_turn_index: int = 0
    in_combat: bool = False
    pre_combat_turn_order: list[str] | None = None
    log: list[str] = field(default_factory=list)
    location: str | None = None
    scene_mood: str | None = None
    active_objectives: list[str] = field(default_factory=list)
```

In `engine/persistence.py`, update the `load` method's `Session(...)` construction to include the 3 new fields (everything else in the file is unchanged):

```python
    def load(self, session_id: str) -> Session | None:
        path = self._path_for(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        characters = {
            player_id: CharacterSheet(**character_data)
            for player_id, character_data in data["characters"].items()
        }
        return Session(
            session_id=data["session_id"],
            characters=characters,
            turn_order=data["turn_order"],
            current_turn_index=data["current_turn_index"],
            in_combat=data["in_combat"],
            pre_combat_turn_order=data["pre_combat_turn_order"],
            log=data["log"],
            location=data["location"],
            scene_mood=data["scene_mood"],
            active_objectives=data["active_objectives"],
        )
```

(`save` needs no change — it already does `json.dumps(asdict(session), indent=2)`, which picks up new dataclass fields automatically.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py tests/test_persistence.py -v`
Expected: PASS (5 tests in test_session.py, 8 tests in test_persistence.py)

- [ ] **Step 5: Commit**

```bash
git add engine/session.py engine/persistence.py tests/test_session.py tests/test_persistence.py
git commit -m "feat: add world-state fields (location, scene_mood, active_objectives) to Session"
```

---

### Task 2: Tool schemas and execution

**Files:**
- Create: `narrator/__init__.py`
- Create: `narrator/tools.py`
- Test: `tests/test_narrator_tools.py`
- Modify: `pyproject.toml` — add `pydantic>=2.13` as an explicit runtime dependency (currently only present transitively via `fastapi`).

**Interfaces:**
- Consumes: `engine.session.Session` (with Task 1's fields), `engine.character.CharacterSheet`, `ruleset.resolution.resolve_roll`, `ruleset.difficulty.Difficulty`.
- Produces: `execute_tool(session: Session, tool_name: str, tool_args: dict) -> dict`, raising `ValueError` on an unknown tool name or invalid arguments (including an unknown `player_id`) — used by Task 3's `NarratorClient`-driven flow and Task 4's harness scoring.

- [ ] **Step 0: Add pydantic dependency**

```toml
# pyproject.toml
[project]
name = "nightwire"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.13",
]
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_narrator_tools.py
import pytest

from engine.character import CharacterSheet
from engine.session import Session
from narrator.tools import execute_tool


def _session_with_character(**overrides) -> Session:
    session = Session(session_id="s1")
    defaults = dict(
        player_id="p1", name="Rook", role="solo", lifepath="streetkid",
        health=7, max_health=10, armor=2,
        conditions=["bleeding"], inventory=["stim pack"],
    )
    defaults.update(overrides)
    session.characters["p1"] = CharacterSheet(**defaults)
    return session


def test_request_roll_rolls_a_real_die_and_resolves_the_outcome():
    session = Session(session_id="s1")
    result = execute_tool(session, "request_roll", {
        "attribute_mod": 3, "skill_mod": 2, "difficulty": "easy", "reason": "climbing a wall",
    })
    assert 1 <= result["die_result"] <= 10
    assert result["dc"] == 8
    assert result["outcome"] in ("clean_success", "complication", "failure")


def test_request_roll_rejects_an_unknown_difficulty():
    session = Session(session_id="s1")
    with pytest.raises(ValueError):
        execute_tool(session, "request_roll", {
            "attribute_mod": 0, "skill_mod": 0, "difficulty": "impossible", "reason": "x",
        })


def test_apply_character_update_adjusts_health_and_armor():
    session = _session_with_character(health=7, max_health=10, armor=2)
    result = execute_tool(session, "apply_character_update", {
        "player_id": "p1", "health_delta": -3, "armor_delta": 1,
    })
    assert session.characters["p1"].health == 4
    assert session.characters["p1"].armor == 3
    assert result == {"player_id": "p1", "health": 4, "armor": 3}


def test_apply_character_update_clamps_health_to_max_and_zero():
    session = _session_with_character(health=9, max_health=10)
    execute_tool(session, "apply_character_update", {"player_id": "p1", "health_delta": 100})
    assert session.characters["p1"].health == 10

    execute_tool(session, "apply_character_update", {"player_id": "p1", "health_delta": -100})
    assert session.characters["p1"].health == 0


def test_apply_character_update_adds_and_removes_conditions_and_inventory():
    session = _session_with_character(conditions=["bleeding"], inventory=["stim pack"])
    execute_tool(session, "apply_character_update", {
        "player_id": "p1",
        "add_conditions": ["stunned"], "remove_conditions": ["bleeding"],
        "add_inventory": ["pistol"], "remove_inventory": ["stim pack"],
    })
    character = session.characters["p1"]
    assert character.conditions == ["stunned"]
    assert character.inventory == ["pistol"]


def test_apply_character_update_removing_absent_items_is_a_no_op():
    session = _session_with_character(conditions=[], inventory=[])
    execute_tool(session, "apply_character_update", {
        "player_id": "p1", "remove_conditions": ["not_present"], "remove_inventory": ["ghost item"],
    })
    assert session.characters["p1"].conditions == []
    assert session.characters["p1"].inventory == []


def test_apply_character_update_rejects_an_unknown_player_id():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        execute_tool(session, "apply_character_update", {"player_id": "ghost"})


def test_update_world_sets_location_and_mood():
    session = Session(session_id="s1")
    execute_tool(session, "update_world", {"location": "Watson district", "scene_mood": "tense"})
    assert session.location == "Watson district"
    assert session.scene_mood == "tense"


def test_update_world_leaves_unset_fields_unchanged():
    session = Session(session_id="s1")
    session.location = "Watson district"
    execute_tool(session, "update_world", {"scene_mood": "calm"})
    assert session.location == "Watson district"
    assert session.scene_mood == "calm"


def test_update_world_adds_and_removes_objectives():
    session = Session(session_id="s1")
    session.active_objectives = ["find the fixer"]
    execute_tool(session, "update_world", {
        "add_objectives": ["avoid corpo patrols"], "remove_objectives": ["find the fixer"],
    })
    assert session.active_objectives == ["avoid corpo patrols"]


def test_start_combat_tool_never_mutates_session_state():
    session = Session(session_id="s1")
    result = execute_tool(session, "start_combat", {"reason": "ambush"})
    assert session.in_combat is False
    assert "note" in result


def test_end_combat_tool_never_mutates_session_state():
    session = Session(session_id="s1")
    session.in_combat = True
    result = execute_tool(session, "end_combat", {"reason": "enemies fled"})
    assert session.in_combat is True
    assert "note" in result


def test_unknown_tool_name_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown tool"):
        execute_tool(session, "nonsense", {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrator_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator'`

- [ ] **Step 3: Write minimal implementation**

```python
# narrator/__init__.py
```

```python
# narrator/tools.py
import random
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from engine.session import Session
from ruleset.difficulty import Difficulty
from ruleset.resolution import resolve_roll


class RequestRoll(BaseModel):
    attribute_mod: int
    skill_mod: int
    difficulty: Literal["easy", "moderate", "hard", "extreme"]
    reason: str


class ApplyCharacterUpdate(BaseModel):
    player_id: str
    health_delta: int = 0
    armor_delta: int = 0
    add_conditions: list[str] = []
    remove_conditions: list[str] = []
    add_inventory: list[str] = []
    remove_inventory: list[str] = []


class UpdateWorld(BaseModel):
    location: str | None = None
    scene_mood: str | None = None
    add_objectives: list[str] = []
    remove_objectives: list[str] = []


class StartCombat(BaseModel):
    reason: str


class EndCombat(BaseModel):
    reason: str


def _execute_request_roll(session: Session, tool: RequestRoll) -> dict:
    die_result = random.randint(1, 10)
    dc = Difficulty[tool.difficulty.upper()].value
    outcome = resolve_roll(die_result, tool.attribute_mod, tool.skill_mod, dc)
    return {"die_result": die_result, "dc": dc, "outcome": outcome.value}


def _execute_apply_character_update(session: Session, tool: ApplyCharacterUpdate) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    character = session.characters[tool.player_id]

    character.health = max(0, min(character.max_health, character.health + tool.health_delta))
    character.armor = max(0, character.armor + tool.armor_delta)

    for condition in tool.add_conditions:
        if condition not in character.conditions:
            character.conditions.append(condition)
    for condition in tool.remove_conditions:
        if condition in character.conditions:
            character.conditions.remove(condition)

    for item in tool.add_inventory:
        character.inventory.append(item)
    for item in tool.remove_inventory:
        if item in character.inventory:
            character.inventory.remove(item)

    return {"player_id": tool.player_id, "health": character.health, "armor": character.armor}


def _execute_update_world(session: Session, tool: UpdateWorld) -> dict:
    if tool.location is not None:
        session.location = tool.location
    if tool.scene_mood is not None:
        session.scene_mood = tool.scene_mood
    for objective in tool.add_objectives:
        if objective not in session.active_objectives:
            session.active_objectives.append(objective)
    for objective in tool.remove_objectives:
        if objective in session.active_objectives:
            session.active_objectives.remove(objective)

    return {
        "location": session.location,
        "scene_mood": session.scene_mood,
        "active_objectives": session.active_objectives,
    }


def _execute_start_combat(session: Session, tool: StartCombat) -> dict:
    return {"acknowledged": True, "note": "combat start requires a player-sent start_combat message"}


def _execute_end_combat(session: Session, tool: EndCombat) -> dict:
    return {"acknowledged": True, "note": "combat end requires a player-sent end_combat message"}


TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Callable[[Session, BaseModel], dict]]] = {
    "request_roll": (RequestRoll, _execute_request_roll),
    "apply_character_update": (ApplyCharacterUpdate, _execute_apply_character_update),
    "update_world": (UpdateWorld, _execute_update_world),
    "start_combat": (StartCombat, _execute_start_combat),
    "end_combat": (EndCombat, _execute_end_combat),
}


def execute_tool(session: Session, tool_name: str, tool_args: dict) -> dict:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"unknown tool: {tool_name!r}")
    model_cls, executor = TOOL_REGISTRY[tool_name]
    tool = model_cls(**tool_args)
    return executor(session, tool)
```

Note: `RequestRoll`'s `Literal["easy", "moderate", "hard", "extreme"]` already makes pydantic reject an unknown `difficulty` value with a `ValidationError` — which is a subclass of `ValueError`, so `test_request_roll_rejects_an_unknown_difficulty`'s `pytest.raises(ValueError)` passes without extra code.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrator_tools.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml narrator/__init__.py narrator/tools.py tests/test_narrator_tools.py
git commit -m "feat: narrator tool surface (request_roll, apply_character_update, update_world, start/end_combat)"
```

---

### Task 3: Ollama structured-output client

**Files:**
- Create: `narrator/client.py`
- Test: `tests/test_narrator_client.py`
- Modify: `pyproject.toml` — add `ollama>=0.6.2` as a runtime dependency.

**Interfaces:**
- Consumes: nothing from Task 1/2 directly (the client is transport-agnostic about tool content — it returns a `tool` name string and `tool_args` dict that Task 2's `execute_tool` can consume, but this task doesn't call `execute_tool` itself).
- Produces: `NarratorResponse` (pydantic: `narration: str`, `tool: str | None`, `tool_args: dict`), `NarratorClient` with `.respond(messages: list[dict]) -> NarratorResponse` — used by Task 4's harness.

- [ ] **Step 0: Add ollama dependency**

```toml
# pyproject.toml
[project]
name = "nightwire"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "pydantic>=2.13",
    "ollama>=0.6.2",
]
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_narrator_client.py
import json

import pytest

from narrator.client import NarratorClient, NarratorResponse


def _fake_chat_returning(payload: dict):
    def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps(payload)}}
    return chat_fn


def test_respond_returns_narration_only_when_no_tool_call():
    client = NarratorClient(
        model="qwen3:8b",
        system_prompt="You are a cyberpunk GM.",
        chat_fn=_fake_chat_returning({"narration": "The alley is quiet.", "tool": None, "tool_args": {}}),
    )
    response = client.respond([{"role": "user", "content": "I look around."}])
    assert isinstance(response, NarratorResponse)
    assert response.narration == "The alley is quiet."
    assert response.tool is None
    assert response.tool_args == {}


def test_respond_returns_a_tool_call():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": "You lunge for the ledge.",
            "tool": "request_roll",
            "tool_args": {"attribute_mod": 2, "skill_mod": 1, "difficulty": "hard", "reason": "leap across a gap"},
        }),
    )
    response = client.respond([{"role": "user", "content": "I try to jump the gap."}])
    assert response.tool == "request_roll"
    assert response.tool_args["difficulty"] == "hard"


def test_respond_passes_the_structured_output_schema_to_chat_fn():
    seen = {}

    def chat_fn(*, model, messages, format):
        seen["format"] = format
        seen["model"] = model
        return {"message": {"content": json.dumps({"narration": "ok", "tool": None, "tool_args": {}})}}

    client = NarratorClient(model="qwen3:8b", chat_fn=chat_fn)
    client.respond([{"role": "user", "content": "hi"}])

    assert seen["model"] == "qwen3:8b"
    assert seen["format"] == NarratorResponse.model_json_schema()


def test_respond_prepends_the_system_prompt():
    seen = {}

    def chat_fn(*, model, messages, format):
        seen["messages"] = messages
        return {"message": {"content": json.dumps({"narration": "ok", "tool": None, "tool_args": {}})}}

    client = NarratorClient(system_prompt="You are a cyberpunk GM.", chat_fn=chat_fn)
    client.respond([{"role": "user", "content": "hi"}])

    assert seen["messages"][0] == {"role": "system", "content": "You are a cyberpunk GM."}
    assert seen["messages"][1] == {"role": "user", "content": "hi"}


def test_respond_raises_on_malformed_model_output():
    client = NarratorClient(chat_fn=lambda **kwargs: {"message": {"content": "not json"}})
    with pytest.raises(ValueError):
        client.respond([{"role": "user", "content": "hi"}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrator_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.client'`

- [ ] **Step 3: Write minimal implementation**

```python
# narrator/client.py
from collections.abc import Callable

import ollama
from pydantic import BaseModel, ValidationError


class NarratorResponse(BaseModel):
    narration: str
    tool: str | None = None
    tool_args: dict = {}


class NarratorClient:
    def __init__(
        self,
        model: str = "qwen3:8b",
        system_prompt: str = "",
        chat_fn: Callable[..., dict] | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self._chat_fn = chat_fn or ollama.chat

    def respond(self, messages: list[dict]) -> NarratorResponse:
        full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        response = self._chat_fn(
            model=self.model,
            messages=full_messages,
            format=NarratorResponse.model_json_schema(),
        )
        try:
            return NarratorResponse.model_validate_json(response["message"]["content"])
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e
```

Note: `NarratorResponse.model_validate_json("not json")` raises a pydantic `ValidationError` (JSON parse failures surface through the same validation path as schema mismatches in pydantic v2), which is caught and re-raised as `ValueError` — matching this project's existing convention of `ValueError` for "bad input at a trust boundary" (`server/dispatch.py`, `narrator/tools.py`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrator_client.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml narrator/client.py tests/test_narrator_client.py
git commit -m "feat: Ollama structured-output narrator client"
```

---

### Task 4: Reliability measurement harness

**Files:**
- Create: `narrator/harness.py`
- Test: `tests/test_harness.py`

**Interfaces:**
- Consumes: `narrator.client.NarratorClient`, `narrator.client.NarratorResponse` (Task 3); `narrator.tools.TOOL_REGISTRY` (Task 2) — a scenario only scores as a pass if the returned `tool` name matches AND `tool_args` actually validates against that tool's pydantic schema. Matching the tool name alone isn't a strong enough reliability signal: a model can name the right tool with garbage args.
- Produces: `Scenario` (a small dataclass), `HarnessReport` (a small dataclass), `run_harness(client: NarratorClient, scenarios: list[Scenario], repeat: int) -> HarnessReport`, plus a `python -m narrator.harness` CLI entrypoint. Nothing downstream in this plan consumes these — this is the terminal task.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_harness.py
import json

from narrator.client import NarratorClient
from narrator.harness import Scenario, run_harness


def _fake_chat_always_returning(payload: dict):
    def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps(payload)}}
    return chat_fn


def test_run_harness_scores_a_correct_tool_call_as_a_pass():
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "You reach for your pistol.",
        "tool": "request_roll",
        "tool_args": {"attribute_mod": 1, "skill_mod": 2, "difficulty": "moderate", "reason": "quickdraw"},
    }))
    scenarios = [
        Scenario(
            name="risky_action_calls_request_roll",
            messages=[{"role": "user", "content": "I try to quickdraw on the ganger."}],
            expected_tool="request_roll",
        ),
    ]

    report = run_harness(client, scenarios, repeat=3)

    assert report.results["risky_action_calls_request_roll"].passes == 3
    assert report.results["risky_action_calls_request_roll"].total == 3


def test_run_harness_scores_a_wrong_tool_call_as_a_fail():
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

    report = run_harness(client, scenarios, repeat=2)

    assert report.results["risky_action_calls_request_roll"].passes == 0
    assert report.results["risky_action_calls_request_roll"].total == 2


def test_run_harness_scores_narration_only_scenarios_correctly():
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

    report = run_harness(client, scenarios, repeat=1)

    assert report.results["idle_description_has_no_tool_call"].passes == 1


def test_run_harness_covers_every_scenario_in_the_report():
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "ok", "tool": None, "tool_args": {},
    }))
    scenarios = [
        Scenario(name="a", messages=[{"role": "user", "content": "x"}], expected_tool=None),
        Scenario(name="b", messages=[{"role": "user", "content": "y"}], expected_tool=None),
    ]

    report = run_harness(client, scenarios, repeat=1)

    assert set(report.results.keys()) == {"a", "b"}


def test_run_harness_fails_a_scenario_whose_tool_args_dont_validate():
    # Right tool name, garbage args (difficulty isn't one of the Literal values) -
    # matching the tool name alone isn't a strong enough signal; the args must
    # actually parse against that tool's schema.
    client = NarratorClient(chat_fn=_fake_chat_always_returning({
        "narration": "You lunge for the ledge.",
        "tool": "request_roll",
        "tool_args": {"attribute_mod": 2, "skill_mod": 1, "difficulty": "nightmarish", "reason": "leap"},
    }))
    scenarios = [
        Scenario(
            name="risky_action_calls_request_roll",
            messages=[{"role": "user", "content": "I try to leap the gap."}],
            expected_tool="request_roll",
        ),
    ]

    report = run_harness(client, scenarios, repeat=1)

    assert report.results["risky_action_calls_request_roll"].passes == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_harness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.harness'`

- [ ] **Step 3: Write minimal implementation**

```python
# narrator/harness.py
import argparse
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


def run_harness(client: NarratorClient, scenarios: list[Scenario], repeat: int) -> HarnessReport:
    report = HarnessReport()
    for scenario in scenarios:
        result = ScenarioResult()
        for _ in range(repeat):
            response = client.respond(scenario.messages)
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
    report = run_harness(client, DEFAULT_SCENARIOS, args.repeat)

    for name, result in report.results.items():
        rate = result.passes / result.total if result.total else 0.0
        print(f"{name}: {result.passes}/{result.total} ({rate:.0%})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_harness.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add narrator/harness.py tests/test_harness.py
git commit -m "feat: narrator reliability measurement harness"
```

---

### Task 5: Full suite sanity check

**Files:** none created — verification only, and a fix commit if anything surfaces.

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: all tests from Phase 1/2a/2b plus every test added in Tasks 1-4 pass; only the 2 pre-existing expected skips remain.

- [ ] **Step 2: Confirm no import errors across modules**

Run: `python -c "import narrator.tools, narrator.client, narrator.harness"`
Expected: exits 0, no output.

- [ ] **Step 3: Manually run the harness against the real local model (not part of the automated suite)**

Run: `python -m narrator.harness --repeat 3`
Expected: prints a pass rate line per scenario in `DEFAULT_SCENARIOS`, against the real `qwen3:8b` model already pulled locally. This is the actual reliability measurement the spec calls for — record the result in this task's commit message or report, but do not block the plan on any particular pass rate (per the spec, whether the base instruct model needs the Dolphin-fallback path "stays hypothetical until real play-testing" — this is that first real data point, not a gate).

- [ ] **Step 4: Commit if anything was fixed during this check**

```bash
git add -A
git commit -m "fix: address issues found in Phase 3a full-suite check"
```

(Skip this step if Steps 1-2 passed clean and nothing needed fixing — nothing to commit. Step 3's harness output is observational, not a fix.)
