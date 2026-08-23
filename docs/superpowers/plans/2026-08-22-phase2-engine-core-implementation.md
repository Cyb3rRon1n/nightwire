# Phase 2a: Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the stateful core of Nightwire's engine — a character model, a session model, the free-flowing/initiative-gated turn logic, and JSON file-per-session persistence. No networking yet (no WebSocket transport, no narrator backend) — this plan is scoped to the data/logic layer only, matching the "smallest real slice" discipline the ruleset phase already followed. A follow-up plan wires this into a real server once this core exists to build on.

**Architecture:** A new top-level `engine` package, sibling to `ruleset`. `engine/character.py` (CharacterSheet), `engine/session.py` (Session), `engine/turns.py` (pure functions over a Session — join, whose-turn-is-it, advance, start/end combat), `engine/persistence.py` (JSON file-per-session store). Plain dataclasses throughout, matching `ruleset`'s existing style — no ORM, no framework.

**Tech Stack:** Python 3.11+, pytest, stdlib only (`dataclasses`, `json`, `pathlib`).

**Spec:** `docs/superpowers/specs/2026-08-22-core-engine-design.md`

## Global Constraints

- **Turn model (the spec's own headline decision)**: outside combat, no turn concept applies at all — any joined player may act at any time. Only once `in_combat` is true does `turn_order`/`current_turn_index` gate who may act.
- `start_combat`/`end_combat` are idempotent (a second `start_combat` while already in combat, or `end_combat` while not, is a no-op) — spec's turn-model section.
- `end_combat` restores the pre-combat turn order, with anyone who joined mid-combat appended at the end (not lost) — spec's turn-model section, matching oracle's own validated precedent for this specific detail.
- Persistence does a real write-and-delete probe at construction, not just `mkdir` (a directory that exists but isn't writable must fail loudly at startup, not silently) — spec's persistence section.
- CharacterSheet's `role`/`lifepath` fields are plain id strings (e.g. `"solo"`, `"corpo"`) matching `ruleset.roles.ROLES`/`ruleset.lifepaths.LIFEPATHS`' own dict keys — this task does not duplicate the `Role`/`Lifepath` objects onto the character, a caller looks them up by id when it needs the full flavor text.
- CharacterSheet's `attributes` field is `dict[str, int]` (plain attribute-id strings as keys, e.g. `"body"`), not `ruleset.attributes.Attribute` enum instances — keeps JSON round-tripping trivial (no custom enum encode/decode needed) since nothing here requires the stronger type yet.

---

### Task 1: CharacterSheet model

**Files:**
- Create: `engine/__init__.py`
- Create: `engine/character.py`
- Test: `tests/test_character.py`

**Interfaces:**
- Consumes: nothing from `ruleset` directly (deliberately decoupled — see Global Constraints).
- Produces: `engine.character.CharacterSheet` (plain dataclass, not frozen — health/conditions/inventory change during play): `player_id: str`, `name: str`, `role: str`, `lifepath: str`, `attributes: dict[str, int]` (default `{}`), `health: int` (default `10`), `max_health: int` (default `10`), `armor: int` (default `0`), `conditions: list[str]` (default `[]`), `inventory: list[str]` (default `[]`).

- [ ] **Step 1: Write the failing test**

Create `engine/__init__.py` (empty file).

Create `tests/test_character.py`:

```python
from engine.character import CharacterSheet


def test_character_sheet_requires_only_identity_and_build_fields():
    sheet = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    assert sheet.player_id == "p1"
    assert sheet.name == "Rook"
    assert sheet.role == "solo"
    assert sheet.lifepath == "streetkid"


def test_character_sheet_has_sensible_defaults():
    sheet = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    assert sheet.attributes == {}
    assert sheet.health == 10
    assert sheet.max_health == 10
    assert sheet.armor == 0
    assert sheet.conditions == []
    assert sheet.inventory == []


def test_character_sheet_fields_are_mutable():
    # Health/conditions/inventory change during play - not a frozen dataclass.
    sheet = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    sheet.health -= 3
    sheet.conditions.append("bleeding")
    sheet.inventory.append("stim pack")
    assert sheet.health == 7
    assert sheet.conditions == ["bleeding"]
    assert sheet.inventory == ["stim pack"]


def test_two_characters_do_not_share_mutable_default_state():
    # A real dataclass footgun: mutable defaults must use default_factory,
    # not a bare [] literal, or every instance shares the same list.
    a = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    b = CharacterSheet(player_id="p2", name="Ash", role="fixer", lifepath="corpo")
    a.conditions.append("bleeding")
    assert b.conditions == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_character.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.character'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/character.py`:

```python
from dataclasses import dataclass, field


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_character.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/__init__.py engine/character.py tests/test_character.py
git commit -m "feat: CharacterSheet model"
```

---

### Task 2: Session model

**Files:**
- Create: `engine/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `engine.character.CharacterSheet` (Task 1).
- Produces: `engine.session.Session` (plain dataclass): `session_id: str`, `characters: dict[str, CharacterSheet]` (default `{}`), `turn_order: list[str]` (default `[]`), `current_turn_index: int` (default `0`), `in_combat: bool` (default `False`), `pre_combat_turn_order: list[str] | None` (default `None`), `log: list[str]` (default `[]`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_session.py`:

```python
from engine.character import CharacterSheet
from engine.session import Session


def test_session_starts_empty():
    session = Session(session_id="test-session")
    assert session.characters == {}
    assert session.turn_order == []
    assert session.current_turn_index == 0
    assert session.in_combat is False
    assert session.pre_combat_turn_order is None
    assert session.log == []


def test_session_can_hold_characters():
    session = Session(session_id="test-session")
    rook = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    session.characters["p1"] = rook
    assert session.characters["p1"] is rook


def test_two_sessions_do_not_share_mutable_default_state():
    a = Session(session_id="a")
    b = Session(session_id="b")
    a.turn_order.append("p1")
    a.log.append("something happened")
    assert b.turn_order == []
    assert b.log == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.session'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/session.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/session.py tests/test_session.py
git commit -m "feat: Session model"
```

---

### Task 3: Turn model - join and free-flowing action

**Files:**
- Create: `engine/turns.py`
- Test: `tests/test_turns.py`

**Interfaces:**
- Consumes: `engine.session.Session` (Task 2), `engine.character.CharacterSheet` (Task 1).
- Produces: `engine.turns.join(session: Session, character: CharacterSheet) -> None`; `engine.turns.current_turn(session: Session) -> str | None`; `engine.turns.is_players_turn(session: Session, player_id: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_turns.py`:

```python
from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import current_turn, is_players_turn, join


def _character(player_id: str, name: str = "Rook") -> CharacterSheet:
    return CharacterSheet(player_id=player_id, name=name, role="solo", lifepath="streetkid")


def test_join_adds_the_character_and_the_turn_order():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    assert "p1" in session.characters
    assert "p1" in session.turn_order


def test_join_is_safe_to_call_again_for_a_reconnecting_player():
    # A rejoining player shouldn't get a duplicate turn_order slot.
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p1"))
    assert session.turn_order.count("p1") == 1


def test_current_turn_is_none_outside_combat():
    # The spec's own headline decision: no turn concept applies at all
    # outside combat, regardless of who's joined.
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    assert current_turn(session) is None


def test_current_turn_is_none_with_no_players_joined():
    session = Session(session_id="test-session")
    assert current_turn(session) is None


def test_is_players_turn_is_always_true_outside_combat():
    # Free-flowing action: anyone may act at any time when not in combat.
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    assert is_players_turn(session, "p1") is True
    assert is_players_turn(session, "p2") is True


def test_is_players_turn_is_true_even_for_an_unrecognized_player_outside_combat():
    # Free-flowing means free-flowing - outside combat there's no roster
    # check either, matching "no turn concept applies at all."
    session = Session(session_id="test-session")
    assert is_players_turn(session, "someone-not-joined") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_turns.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.turns'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/turns.py`:

```python
from engine.character import CharacterSheet
from engine.session import Session


def join(session: Session, character: CharacterSheet) -> None:
    session.characters[character.player_id] = character
    if character.player_id not in session.turn_order:
        session.turn_order.append(character.player_id)


def current_turn(session: Session) -> str | None:
    if not session.in_combat or not session.turn_order:
        return None
    return session.turn_order[session.current_turn_index % len(session.turn_order)]


def is_players_turn(session: Session, player_id: str) -> bool:
    if not session.in_combat:
        return True
    return current_turn(session) == player_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_turns.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/turns.py tests/test_turns.py
git commit -m "feat: turn model - join and free-flowing action outside combat"
```

---

### Task 4: Combat turn model - start_combat, end_combat, advance_turn

**Files:**
- Modify: `engine/turns.py`
- Modify: `tests/test_turns.py`

**Interfaces:**
- Consumes: `engine.session.Session` (Task 2).
- Produces (added to `engine.turns`): `start_combat(session: Session, initiative_rolls: dict[str, int]) -> None`; `end_combat(session: Session) -> None`; `advance_turn(session: Session) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_turns.py`:

```python
def test_start_combat_orders_turn_order_by_initiative_descending():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    assert session.turn_order == ["p2", "p1"]
    assert session.in_combat is True
    assert session.current_turn_index == 0


def test_start_combat_is_idempotent():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    start_combat(session, {"p1": 99, "p2": 1})  # would flip the order if re-run
    assert session.turn_order == ["p2", "p1"]


def test_current_turn_and_is_players_turn_during_combat():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    assert current_turn(session) == "p2"
    assert is_players_turn(session, "p2") is True
    assert is_players_turn(session, "p1") is False


def test_advance_turn_cycles_through_the_order():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    advance_turn(session)
    assert current_turn(session) == "p1"
    advance_turn(session)
    assert current_turn(session) == "p2"  # wraps back around


def test_advance_turn_outside_combat_is_a_no_op():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    advance_turn(session)  # not in combat - nothing to advance
    assert session.current_turn_index == 0


def test_end_combat_restores_the_pre_combat_join_order():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})  # reorders to [p2, p1]
    end_combat(session)
    assert session.turn_order == ["p1", "p2"]  # restored to join order
    assert session.in_combat is False
    assert session.pre_combat_turn_order is None


def test_end_combat_appends_a_mid_combat_joiner_at_the_end():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    join(session, _character("p2"))
    start_combat(session, {"p1": 8, "p2": 15})
    join(session, _character("p3"))  # joins mid-combat, appended live to turn_order
    end_combat(session)
    assert session.turn_order == ["p1", "p2", "p3"]


def test_end_combat_is_idempotent():
    session = Session(session_id="test-session")
    join(session, _character("p1"))
    end_combat(session)  # never in combat - no-op, no error
    assert session.in_combat is False
```

Update the import line at the top of `tests/test_turns.py` to add the new names:

```python
from engine.turns import advance_turn, current_turn, end_combat, is_players_turn, join, start_combat
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_turns.py -v`
Expected: FAIL with `ImportError: cannot import name 'start_combat' from 'engine.turns'`

- [ ] **Step 3: Write minimal implementation**

Add to `engine/turns.py` (after the existing `is_players_turn` function):

```python
def start_combat(session: Session, initiative_rolls: dict[str, int]) -> None:
    if session.in_combat:
        return
    session.pre_combat_turn_order = list(session.turn_order)
    session.turn_order = sorted(initiative_rolls, key=lambda pid: -initiative_rolls[pid])
    session.current_turn_index = 0
    session.in_combat = True


def end_combat(session: Session) -> None:
    if not session.in_combat:
        return
    pre_combat = session.pre_combat_turn_order or []
    latecomers = [pid for pid in session.turn_order if pid not in pre_combat]
    session.turn_order = pre_combat + latecomers
    session.pre_combat_turn_order = None
    session.current_turn_index = 0
    session.in_combat = False


def advance_turn(session: Session) -> None:
    if session.in_combat and session.turn_order:
        session.current_turn_index = (session.current_turn_index + 1) % len(session.turn_order)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_turns.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add engine/turns.py tests/test_turns.py
git commit -m "feat: combat turn model - start_combat/end_combat/advance_turn"
```

---

### Task 5: Persistence - JSON file-per-session store

**Files:**
- Create: `engine/persistence.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Consumes: `engine.session.Session` (Task 2), `engine.character.CharacterSheet` (Task 1).
- Produces: `engine.persistence.SessionStoreUnwritable` (Exception subclass); `engine.persistence.JSONFileSessionStore` (class: `__init__(self, directory: str | pathlib.Path)` raises `SessionStoreUnwritable` if the directory can't be written to; `.save(session: Session) -> None`; `.load(session_id: str) -> Session | None`, returns `None` if no saved file exists for that id).

- [ ] **Step 1: Write the failing test**

Create `tests/test_persistence.py`:

```python
import os

import pytest

from engine.character import CharacterSheet
from engine.persistence import JSONFileSessionStore, SessionStoreUnwritable
from engine.session import Session


def test_store_creates_the_directory_if_missing(tmp_path):
    store_dir = tmp_path / "sessions"
    JSONFileSessionStore(store_dir)
    assert store_dir.is_dir()


def test_save_then_load_round_trips_a_session_with_a_character(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="test-session")
    session.characters["p1"] = CharacterSheet(
        player_id="p1",
        name="Rook",
        role="solo",
        lifepath="streetkid",
        attributes={"body": 14, "reflexes": 12},
        health=7,
        max_health=10,
        armor=2,
        conditions=["bleeding"],
        inventory=["stim pack"],
    )
    session.turn_order = ["p1"]
    session.current_turn_index = 0
    session.in_combat = True
    session.pre_combat_turn_order = ["p1"]
    session.log = ["Rook draws a pistol."]

    store.save(session)
    loaded = store.load("test-session")

    assert loaded is not None
    assert loaded.session_id == "test-session"
    assert loaded.turn_order == ["p1"]
    assert loaded.in_combat is True
    assert loaded.pre_combat_turn_order == ["p1"]
    assert loaded.log == ["Rook draws a pistol."]
    loaded_character = loaded.characters["p1"]
    assert loaded_character.name == "Rook"
    assert loaded_character.role == "solo"
    assert loaded_character.lifepath == "streetkid"
    assert loaded_character.attributes == {"body": 14, "reflexes": 12}
    assert loaded_character.health == 7
    assert loaded_character.max_health == 10
    assert loaded_character.armor == 2
    assert loaded_character.conditions == ["bleeding"]
    assert loaded_character.inventory == ["stim pack"]


def test_load_returns_none_for_a_session_id_with_no_saved_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    assert store.load("never-saved") is None


def test_construction_raises_on_an_unwritable_existing_directory(tmp_path):
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o500)
    try:
        if os.access(readonly_dir, os.W_OK):
            pytest.skip("running as a user that can write read-only directories (e.g. root)")
        with pytest.raises(SessionStoreUnwritable):
            JSONFileSessionStore(readonly_dir)
    finally:
        readonly_dir.chmod(0o700)


def test_construction_raises_when_parent_directory_blocks_creation(tmp_path):
    readonly_parent = tmp_path / "readonly_parent"
    readonly_parent.mkdir()
    readonly_parent.chmod(0o500)
    try:
        if os.access(readonly_parent, os.W_OK):
            pytest.skip("running as a user that can write read-only directories (e.g. root)")
        with pytest.raises(SessionStoreUnwritable):
            JSONFileSessionStore(readonly_parent / "sessions")
    finally:
        readonly_parent.chmod(0o700)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_persistence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.persistence'`

- [ ] **Step 3: Write minimal implementation**

Create `engine/persistence.py`:

```python
import json
from dataclasses import asdict
from pathlib import Path

from engine.character import CharacterSheet
from engine.session import Session


class SessionStoreUnwritable(Exception):
    pass


class JSONFileSessionStore:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._check_writable()

    def _check_writable(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            probe = self.directory / ".write_probe"
            probe.write_text("")
            probe.unlink()
        except OSError as e:
            raise SessionStoreUnwritable(
                f"Session store directory {self.directory} is not writable: {e}"
            ) from e

    def _path_for(self, session_id: str) -> Path:
        return self.directory / f"{session_id}.json"

    def save(self, session: Session) -> None:
        self._path_for(session.session_id).write_text(json.dumps(asdict(session), indent=2))

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
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_persistence.py -v`
Expected: PASS (5 passed, or 3 passed + 2 skipped if running as root — `chmod` doesn't block root, this is a known environment artifact, not a real failure)

- [ ] **Step 5: Commit**

```bash
git add engine/persistence.py tests/test_persistence.py
git commit -m "feat: JSON file-per-session persistence with startup writability check"
```

---

### Task 6: Full suite sanity check

**Files:**
- None created or modified — verification only.

**Interfaces:**
- Consumes: everything from Tasks 1-5, plus the existing `ruleset` package from Phase 1.
- Produces: nothing new.

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: PASS (23 from Phase 1 + 4 + 3 + 6 + 8 + 5 = 49 passed, or 47 passed/2 skipped if running as root)

- [ ] **Step 2: Confirm no import errors across modules**

Run: `python -c "from engine.character import CharacterSheet; from engine.session import Session; from engine.turns import join, current_turn, is_players_turn, start_combat, end_combat, advance_turn; from engine.persistence import JSONFileSessionStore, SessionStoreUnwritable; print('all imports OK')"`
Expected: prints `all imports OK` with no errors

- [ ] **Step 3: Commit if anything was fixed during this check**

Only if Steps 1-2 required any fix:

```bash
git add -A
git commit -m "fix: resolve cross-module import issue found in full suite check"
```

If nothing needed fixing, skip this step - no empty commits.
