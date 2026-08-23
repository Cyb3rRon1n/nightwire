# Phase 2b: WebSocket Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing engine (`engine/session.py`, `engine/turns.py`, `engine/persistence.py`) in a WebSocket server so multiple real clients can join a session, trigger the already-implemented turn/combat mutations, and receive a server-authoritative, per-player-filtered view of state after every change.

**Architecture:** A thin transport layer over the pure engine, in a new top-level `server/` package. Three pure/stub-testable modules do the real work (`views.build_view`, `dispatch.handle_message`, `connection_manager.ConnectionManager`) with zero dependency on a running network stack, so they're unit-tested directly. A fourth module (`server/app.py`) wires them into a FastAPI app with one `/ws/{session_id}` WebSocket endpoint; it is the only module that needs a real (in-process) WebSocket to test, via Starlette's `TestClient.websocket_connect`.

**Tech Stack:** FastAPI + `uvicorn[standard]` (bundles a websockets implementation) for the ASGI/WebSocket layer — chosen because its `TestClient` (via `httpx`) drives WebSocket tests in-process against the real ASGI app with no live server or socket needed, which fits this project's existing "deterministic scripted client" testing convention (see `docs/superpowers/specs/2026-08-22-core-engine-design.md`'s Testing section) directly. `httpx` added as a dev dependency for `TestClient`.

**Spec:** `docs/superpowers/specs/2026-08-22-core-engine-design.md` (Real-time transport, Server-authoritative state, Testing sections)

## Global Constraints

- Python >=3.11, existing `engine`/`ruleset` packages are not modified — this plan only adds a `server/` package.
- No message/envelope catalog beyond what this plan's tasks need — the spec explicitly defers the full catalog ("built alongside the features that need each one, not pre-declared speculatively"). Only `join`, `start_combat`, `advance_turn`, `end_combat` are wired here, matching the turn-model messages the engine already implements.
- Server-authoritative filtering: each connected player receives their own full character sheet plus, for every other player, only `name`, `role`, `health`, `max_health`, `armor`, `conditions` — never `inventory`, `attributes`, or notes (per spec).
- Persistence: every state-mutating message is followed by `JSONFileSessionStore.save()` before broadcasting, so a crash after a mutation never loses it silently.
- Combat/session-start-stop stays player-triggered via explicit messages, never inferred from narration (per spec) — this plan doesn't touch narration at all, so this constraint is inherited, not implemented here.

---

## File Structure

- `server/__init__.py` — empty, makes `server` a package.
- `server/views.py` — `build_view(session, viewer_id) -> dict`. Pure function, no I/O.
- `server/dispatch.py` — `handle_message(session, message) -> None`. Pure function over the engine, no I/O.
- `server/connection_manager.py` — `ConnectionManager` class tracking live per-session WebSocket connections and broadcasting filtered views. Takes any object with an async `send_json`, so it's testable with a fake — no FastAPI import needed.
- `server/app.py` — `create_app(store) -> FastAPI`, the one module that imports FastAPI/Starlette and owns the `/ws/{session_id}` endpoint.
- `tests/test_views.py`, `tests/test_dispatch.py`, `tests/test_connection_manager.py`, `tests/test_app.py` — one test file per module above.

## Interfaces this plan builds on (already implemented, unchanged)

```python
# engine/character.py
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

# engine/session.py
@dataclass
class Session:
    session_id: str
    characters: dict[str, CharacterSheet] = field(default_factory=dict)
    turn_order: list[str] = field(default_factory=list)
    current_turn_index: int = 0
    in_combat: bool = False
    pre_combat_turn_order: list[str] | None = None
    log: list[str] = field(default_factory=list)

# engine/turns.py
def join(session: Session, character: CharacterSheet) -> None: ...
def current_turn(session: Session) -> str | None: ...
def is_players_turn(session: Session, player_id: str) -> bool: ...
def start_combat(session: Session, initiative_rolls: dict[str, int]) -> None: ...
def end_combat(session: Session) -> None: ...
def advance_turn(session: Session) -> None: ...

# engine/persistence.py
class SessionStoreUnwritable(Exception): ...
class JSONFileSessionStore:
    def __init__(self, directory: str | Path) -> None: ...
    def save(self, session: Session) -> None: ...
    def load(self, session_id: str) -> Session | None: ...
```

---

### Task 1: Per-client filtered view

**Files:**
- Create: `server/__init__.py`
- Create: `server/views.py`
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: `engine.session.Session`, `engine.character.CharacterSheet` (as above).
- Produces: `build_view(session: Session, viewer_id: str) -> dict` — used by Task 3's `ConnectionManager.broadcast` and Task 4's app.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_views.py
from engine.character import CharacterSheet
from engine.session import Session
from server.views import build_view


def _character(player_id: str, name: str) -> CharacterSheet:
    return CharacterSheet(
        player_id=player_id,
        name=name,
        role="solo",
        lifepath="streetkid",
        attributes={"body": 14},
        health=7,
        max_health=10,
        armor=2,
        conditions=["bleeding"],
        inventory=["stim pack"],
    )


def test_viewer_sees_their_own_full_sheet():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")

    view = build_view(session, "p1")

    assert view["characters"]["p1"] == {
        "player_id": "p1",
        "name": "Rook",
        "role": "solo",
        "lifepath": "streetkid",
        "attributes": {"body": 14},
        "health": 7,
        "max_health": 10,
        "armor": 2,
        "conditions": ["bleeding"],
        "inventory": ["stim pack"],
    }


def test_viewer_sees_a_redacted_view_of_other_players():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.characters["p2"] = _character("p2", "Ghost")

    view = build_view(session, "p1")

    assert view["characters"]["p2"] == {
        "name": "Ghost",
        "role": "solo",
        "health": 7,
        "max_health": 10,
        "armor": 2,
        "conditions": ["bleeding"],
    }
    assert "inventory" not in view["characters"]["p2"]
    assert "attributes" not in view["characters"]["p2"]
    assert "player_id" not in view["characters"]["p2"]


def test_view_includes_shared_session_state():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")
    session.characters["p2"] = _character("p2", "Ghost")
    session.turn_order = ["p2", "p1"]
    session.in_combat = True
    session.current_turn_index = 0
    session.log = ["Rook draws a pistol."]

    view = build_view(session, "p1")

    assert view["session_id"] == "s1"
    assert view["in_combat"] is True
    assert view["current_turn"] == "p2"
    assert view["is_your_turn"] is False
    assert view["log"] == ["Rook draws a pistol."]


def test_is_your_turn_true_outside_combat():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")

    view = build_view(session, "p1")

    assert view["current_turn"] is None
    assert view["is_your_turn"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_views.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/__init__.py
```

```python
# server/views.py
from dataclasses import asdict

from engine.session import Session
from engine.turns import current_turn, is_players_turn

_REDACTED_FIELDS = ("name", "role", "health", "max_health", "armor", "conditions")


def build_view(session: Session, viewer_id: str) -> dict:
    characters = {}
    for player_id, character in session.characters.items():
        if player_id == viewer_id:
            characters[player_id] = asdict(character)
        else:
            full = asdict(character)
            characters[player_id] = {field: full[field] for field in _REDACTED_FIELDS}

    return {
        "session_id": session.session_id,
        "in_combat": session.in_combat,
        "current_turn": current_turn(session),
        "is_your_turn": is_players_turn(session, viewer_id),
        "log": session.log,
        "characters": characters,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_views.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add server/__init__.py server/views.py tests/test_views.py
git commit -m "feat: server-authoritative per-client filtered view"
```

---

### Task 2: Message dispatch

**Files:**
- Create: `server/dispatch.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `engine.turns.{join,start_combat,end_combat,advance_turn}`, `engine.character.CharacterSheet`, `engine.session.Session` (as above).
- Produces: `handle_message(session: Session, message: dict) -> None`, raising `ValueError` on any invalid message — used by Task 4's app.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dispatch.py
import pytest

from engine.session import Session
from server.dispatch import handle_message


def test_join_creates_a_character_and_adds_it_to_turn_order():
    session = Session(session_id="s1")
    message = {
        "type": "join",
        "character": {
            "player_id": "p1",
            "name": "Rook",
            "role": "solo",
            "lifepath": "streetkid",
        },
    }

    handle_message(session, message)

    assert session.characters["p1"].name == "Rook"
    assert "p1" in session.turn_order


def test_join_reconnect_does_not_reset_live_state():
    session = Session(session_id="s1")
    join_message = {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }
    handle_message(session, join_message)
    session.characters["p1"].health = 3

    handle_message(session, join_message)

    assert session.characters["p1"].health == 3


def test_start_combat_orders_turn_order_by_initiative():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    })
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
    })

    handle_message(session, {
        "type": "start_combat",
        "initiative_rolls": {"p1": 5, "p2": 12},
    })

    assert session.in_combat is True
    assert session.turn_order == ["p2", "p1"]


def test_advance_turn_cycles_the_order():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    })
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
    })
    handle_message(session, {"type": "start_combat", "initiative_rolls": {"p1": 5, "p2": 12}})

    handle_message(session, {"type": "advance_turn"})

    assert session.current_turn_index == 1


def test_end_combat_restores_pre_combat_order():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    })
    handle_message(session, {"type": "start_combat", "initiative_rolls": {"p1": 5}})

    handle_message(session, {"type": "end_combat"})

    assert session.in_combat is False


def test_unknown_message_type_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown message type"):
        handle_message(session, {"type": "nonsense"})


def test_missing_type_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'type'"):
        handle_message(session, {})


def test_join_missing_character_field_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'character'"):
        handle_message(session, {"type": "join"})


def test_start_combat_missing_initiative_rolls_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="missing 'initiative_rolls'"):
        handle_message(session, {"type": "start_combat"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dispatch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.dispatch'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/dispatch.py
from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import advance_turn, end_combat, join, start_combat


def handle_message(session: Session, message: dict) -> None:
    message_type = message.get("type")
    if message_type is None:
        raise ValueError("missing 'type' in message")

    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        join(session, CharacterSheet(**character_data))

    elif message_type == "start_combat":
        initiative_rolls = message.get("initiative_rolls")
        if initiative_rolls is None:
            raise ValueError("missing 'initiative_rolls' in start_combat message")
        start_combat(session, initiative_rolls)

    elif message_type == "advance_turn":
        advance_turn(session)

    elif message_type == "end_combat":
        end_combat(session)

    else:
        raise ValueError(f"unknown message type: {message_type!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dispatch.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add server/dispatch.py tests/test_dispatch.py
git commit -m "feat: WebSocket message dispatch over the existing engine"
```

---

### Task 3: Connection manager

**Files:**
- Create: `server/connection_manager.py`
- Test: `tests/test_connection_manager.py`

**Interfaces:**
- Consumes: `server.views.build_view` (Task 1). Any object with an async `send_json(data: dict)` method counts as a connection — no FastAPI/Starlette import in this module.
- Produces: `ConnectionManager` with `connect(session_id, player_id, connection)`, `disconnect(session_id, player_id)`, `async broadcast(session_id, session)` — used by Task 4's app.

- [ ] **Step 0: Add pytest-asyncio**

This task's tests use `@pytest.mark.asyncio`, so `pytest-asyncio` and its pytest
config must exist before Step 2 runs — don't defer this to Task 4.

```toml
# pyproject.toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_connection_manager.py
import pytest

from engine.character import CharacterSheet
from engine.session import Session
from server.connection_manager import ConnectionManager


class FakeConnection:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)


def _session_with_two_players():
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    session.characters["p2"] = CharacterSheet(player_id="p2", name="Ghost", role="netrunner", lifepath="corpo")
    return session


@pytest.mark.asyncio
async def test_broadcast_sends_each_connection_its_own_filtered_view():
    manager = ConnectionManager()
    conn1, conn2 = FakeConnection(), FakeConnection()
    manager.connect("s1", "p1", conn1)
    manager.connect("s1", "p2", conn2)
    session = _session_with_two_players()

    await manager.broadcast("s1", session)

    assert conn1.sent[0]["characters"]["p1"]["name"] == "Rook"
    assert "inventory" in conn1.sent[0]["characters"]["p1"]
    assert "inventory" not in conn1.sent[0]["characters"]["p2"]
    assert conn2.sent[0]["characters"]["p2"]["name"] == "Ghost"


@pytest.mark.asyncio
async def test_broadcast_only_reaches_connections_in_that_session():
    manager = ConnectionManager()
    conn1 = FakeConnection()
    manager.connect("s1", "p1", conn1)
    other_session = Session(session_id="s2")

    await manager.broadcast("s2", other_session)

    assert conn1.sent == []


@pytest.mark.asyncio
async def test_disconnect_removes_the_connection_from_future_broadcasts():
    manager = ConnectionManager()
    conn1 = FakeConnection()
    manager.connect("s1", "p1", conn1)
    manager.disconnect("s1", "p1")
    session = _session_with_two_players()

    await manager.broadcast("s1", session)

    assert conn1.sent == []


def test_disconnect_of_an_unknown_connection_is_a_no_op():
    manager = ConnectionManager()
    manager.disconnect("never-connected", "p1")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_connection_manager.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.connection_manager'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/connection_manager.py
from typing import Protocol

from engine.session import Session
from server.views import build_view


class SendsJSON(Protocol):
    async def send_json(self, data: dict) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[str, SendsJSON]] = {}

    def connect(self, session_id: str, player_id: str, connection: SendsJSON) -> None:
        self._connections.setdefault(session_id, {})[player_id] = connection

    def disconnect(self, session_id: str, player_id: str) -> None:
        self._connections.get(session_id, {}).pop(player_id, None)

    async def broadcast(self, session_id: str, session: Session) -> None:
        for player_id, connection in self._connections.get(session_id, {}).items():
            await connection.send_json(build_view(session, player_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_connection_manager.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add server/connection_manager.py tests/test_connection_manager.py
git commit -m "feat: per-session WebSocket connection manager with filtered broadcast"
```

---

### Task 4: WebSocket app

**Files:**
- Modify: `pyproject.toml` — add `fastapi`, `uvicorn[standard]` as runtime dependencies; add `httpx` to the `dev` extra (alongside `pytest-asyncio`, already added by Task 3).
- Create: `server/app.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `server.views.build_view` (Task 1, used indirectly via `ConnectionManager`), `server.dispatch.handle_message` (Task 2), `server.connection_manager.ConnectionManager` (Task 3), `engine.session.Session`, `engine.persistence.JSONFileSessionStore`.
- Produces: `create_app(store: JSONFileSessionStore) -> FastAPI`, the app factory used to run the real server and to build tests.

- [ ] **Step 0: Add dependencies**

Task 3 already added `pytest-asyncio` and the `asyncio_mode` pytest config. This step
adds the runtime web framework and the test client, on top of that — the resulting
`pyproject.toml` looks like:

```toml
# pyproject.toml
[project]
name = "nightwire"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.27"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_app.py
from fastapi.testclient import TestClient

from engine.persistence import JSONFileSessionStore
from server.app import create_app


def _client(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    return TestClient(create_app(store))


def test_join_broadcasts_a_filtered_view_back_to_the_sender(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        view = ws.receive_json()

    assert view["characters"]["p1"]["name"] == "Rook"
    assert view["session_id"] == "s1"


def test_second_player_join_broadcasts_a_redacted_view_to_the_first(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws1:
        ws1.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws1.receive_json()  # p1's own join broadcast

        with client.websocket_connect("/ws/s1/p2") as ws2:
            ws2.send_json({
                "type": "join",
                "character": {"player_id": "p2", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
            })
            ws2.receive_json()  # p2's own join broadcast

            view = ws1.receive_json()  # p1 re-broadcast after p2 joins

    assert "inventory" not in view["characters"]["p2"]
    assert view["characters"]["p2"]["name"] == "Ghost"


def test_invalid_message_sends_an_error_without_closing_the_connection(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({"type": "nonsense"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "unknown message type" in error["message"]

        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        view = ws.receive_json()
        assert view["characters"]["p1"]["name"] == "Rook"


def test_join_with_a_character_id_not_matching_the_url_is_rejected(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "someone-else", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "does not match" in error["message"]


def test_state_persists_across_a_reconnect(tmp_path):
    client = _client(tmp_path)
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({"type": "advance_turn"})
        view = ws.receive_json()

    assert "p1" in view["characters"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.app'`

- [ ] **Step 3: Write minimal implementation**

Player identity comes from the URL (`/ws/{session_id}/{player_id}`), not from message
content — a connection registers with the `ConnectionManager` immediately on connect, so
every connection gets its own broadcast reply even if its first message isn't a `join`
(the reconnect case in Step 1's tests). A `join` message's `character.player_id` is
validated against the URL's `player_id` so one connection can't inject state for another
player's id.

```python
# server/app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from server.connection_manager import ConnectionManager
from server.dispatch import handle_message


def create_app(store: JSONFileSessionStore) -> FastAPI:
    app = FastAPI()
    manager = ConnectionManager()

    @app.websocket("/ws/{session_id}/{player_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str, player_id: str) -> None:
        await websocket.accept()
        session = store.load(session_id) or Session(session_id=session_id)
        manager.connect(session_id, player_id, websocket)

        try:
            while True:
                message = await websocket.receive_json()

                if message.get("type") == "join":
                    character_id = (message.get("character") or {}).get("player_id")
                    if character_id != player_id:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"character.player_id {character_id!r} does not match connection player_id {player_id!r}",
                        })
                        continue

                try:
                    handle_message(session, message)
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
                    continue

                store.save(session)
                await manager.broadcast(session_id, session)
        except WebSocketDisconnect:
            manager.disconnect(session_id, player_id)

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml server/app.py tests/test_app.py
git commit -m "feat: FastAPI WebSocket server wiring session persistence and broadcast"
```

---

### Task 5: Full suite sanity check

**Files:** none created — verification only, and a fix commit if anything surfaces.

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: all tests from Phase 2a plus every test added in Tasks 1-4 pass; only the 2 pre-existing expected skips remain.

- [ ] **Step 2: Confirm no import errors across modules**

Run: `python -c "import server.app, server.dispatch, server.views, server.connection_manager"`
Expected: exits 0, no output.

- [ ] **Step 3: Commit if anything was fixed during this check**

```bash
git add -A
git commit -m "fix: address issues found in Phase 2b full-suite check"
```

(Skip this step if Step 1 and Step 2 both passed clean — nothing to commit.)
