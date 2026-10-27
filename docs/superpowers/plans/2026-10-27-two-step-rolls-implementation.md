# Two-Step Player Rolls Implementation Plan (Phase 16)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the narrator requests a roll, the engine holds it as a pending roll. The player clicks **Roll**, sees the die land, and the narrator then narrates the outcome knowing the real result. The result is kept as a visible story line, so later turns remember it.

**Architecture:** `server/narration.py`'s turn body becomes a shared `_run_turn` helper.
- **Action turns:** a `request_roll` stores `session.pending_rolls[player_id]` instead of rolling.
- **The roll:** a new `roll` message (`handle_roll`) executes the existing roll math, logs a visible line plus a JSON `[roll: …]` line, and runs `_run_turn` again as the resolution, where rolls are disallowed.
- **Frontend:** a `RollCard` renders the pending roll (from the view) and the rolled result (from the `[roll: …]` lines).

**Tech Stack:** Python 3.11+ (FastAPI websockets, pydantic, pytest), Next.js/React/TypeScript (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-10-27-two-step-rolls-design.md`

## Global Constraints

- No new dependencies, Python or JS. The die animation is CSS-only and respects `prefers-reduced-motion`.
- The roll math is unchanged: `1d10 + attribute modifier + skill rank` vs DC (easy 8, moderate 12, hard 16, extreme 20); a natural 10 is always a clean success and a natural 1 is always a failure. Reuse `narrator/tools.py::execute_tool(session, "request_roll", args)`. Don't reimplement it.
- **Non-roll turns behave exactly as before.** Every existing test passes, except the two `request_roll` tests that Task 2 explicitly rewrites.
- **New log lines:**
  - `[roll pending: <json>]` and `[roll: <json>]` are bracketed, and their payload is `json.dumps(...)`, not a Python repr, so the frontend can `JSON.parse` it.
  - The visible roll line is **not** bracketed.
- Error messages, exact: `"roll first"` (an action while that player's roll is pending), `"no roll pending"` (a roll with nothing pending), and the log line `[tool error: no new rolls during a roll resolution]`.
- `Session.pending_rolls: dict[str, dict]` defaults to `{}`. Old session files load with `{}`.
- Commits carry **no** `Co-Authored-By` or AI-attribution trailer. Don't push.
- Backend tests: `.venv/bin/python -m pytest tests/ -q` (338 pass before this phase, with one pre-existing fastapi warning). Frontend: `cd frontend && npm run lint && npm run build`. `page.tsx` has one known pre-existing lint error (`react-hooks/set-state-in-effect`); don't fix it, and don't add new ones.

## File Structure

| File | Change |
|---|---|
| `engine/session.py` | `pending_rolls` field |
| `engine/persistence.py` | load `pending_rolls` with a default |
| `server/views.py` | expose `pending_rolls` |
| `server/narration.py` | `_run_turn` refactor, pending-roll capture, `"roll first"`, `handle_roll`, roll-line formatting |
| `server/app.py` | route `{"type": "roll"}` |
| `server/__main__.py` | the setup-then-resolve rule in the system prompt |
| `frontend/src/lib/nightwire/protocol.ts` | `PendingRoll`, `StateView.pending_rolls` |
| `frontend/src/app/nightwire/RollCard.tsx` (new) | pending card + rolled result display |
| `frontend/src/app/nightwire/page.tsx`, `theme.css` | render the card and results, Roll button, composer lock, CSS tumble |
| `tests/test_session.py` or `tests/test_persistence.py`, `tests/test_views.py`, `tests/test_narration.py`, `tests/test_server_main.py`, `tests/test_app.py` | tests |
| `README.md`, `ROADMAP.md` | Task 5 |

---

### Task 1: `pending_rolls` state (session, persistence, view)

**Files:**
- Modify: `engine/session.py`, `engine/persistence.py`, `server/views.py`
- Test: `tests/test_persistence.py`, `tests/test_views.py`

**Interfaces:**
- Produces:
  - `Session.pending_rolls: dict[str, dict]`, default `{}`, keyed by player_id;
  - `build_view(...)["pending_rolls"]`, the same dict for every viewer (party-public).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_persistence.py`. Match that file's existing imports; it already imports `Session` and `JSONFileSessionStore`:

```python
def test_pending_rolls_round_trip(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="s1")
    session.pending_rolls["p1"] = {"player_id": "p1", "skill": "stealth", "dc": 16}

    store.save(session)

    assert store.load("s1").pending_rolls == {"p1": {"player_id": "p1", "skill": "stealth", "dc": 16}}


def test_load_defaults_pending_rolls_when_missing_from_an_older_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="s1"))
    path = tmp_path / "s1.json"
    data = json.loads(path.read_text())
    del data["pending_rolls"]
    path.write_text(json.dumps(data))

    assert store.load("s1").pending_rolls == {}
```

(Add `import json` at the top if the file doesn't already have it.)

Append to `tests/test_views.py`. Use that file's existing helpers and imports to build a session with two characters, `p1` and `p2`. If the file builds sessions inline, do the same:

```python
def test_view_exposes_pending_rolls_to_every_viewer():
    session = Session(session_id="s1")
    session.pending_rolls["p1"] = {"player_id": "p1", "skill": "stealth", "dc": 16}

    assert build_view(session, "p1")["pending_rolls"] == {"p1": {"player_id": "p1", "skill": "stealth", "dc": 16}}
    assert build_view(session, "p2")["pending_rolls"] == {"p1": {"player_id": "p1", "skill": "stealth", "dc": 16}}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_persistence.py tests/test_views.py -q`
Expected: FAIL (`AttributeError: 'Session' object has no attribute 'pending_rolls'`, and a `KeyError`).

- [ ] **Step 3: Implement**

`engine/session.py`: add the field after `npc_memory`:

```python
    # Rolls the narrator requested that the player hasn't rolled yet
    # (two-step rolls, Phase 16): player_id -> RequestRoll args + dc + name.
    pending_rolls: dict[str, dict] = field(default_factory=dict)
```

`engine/persistence.py`: in `load`'s `Session(...)` call, after `npc_memory=...`, add:

```python
            pending_rolls=data.get("pending_rolls", {}),
```

`server/views.py`: in `build_view`'s returned dict, after `"active_objectives"`, add:

```python
        "pending_rolls": session.pending_rolls,
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass. If an existing view test asserts the view's exact key set, add `"pending_rolls"` to it.

- [ ] **Step 5: Commit**

```bash
git add engine/session.py engine/persistence.py server/views.py tests/test_persistence.py tests/test_views.py
git commit -m "feat: pending_rolls session state, persisted and shown to the party"
```

---

### Task 2: Shared turn pipeline and pending-roll capture

**Files:**
- Modify: `server/narration.py`, `server/__main__.py`
- Test: `tests/test_narration.py`, `tests/test_server_main.py`

**Interfaces:**
- Consumes: `Session.pending_rolls` (Task 1); `narrator.tools.RequestRoll` (a pydantic model); `ruleset.difficulty.Difficulty` (an IntEnum: EASY 8, MODERATE 12, HARD 16, EXTREME 20).
- Produces:
  - `async def _run_turn(session, narrator_client, store, image_backend, tts_backend, player_id: str, prompt_text: str, actor_line: str | None, allow_roll: bool) -> None`;
  - `handle_action` (same signature) raises `ValueError("roll first")` while `player_id in session.pending_rolls`;
  - a pending entry is `RequestRoll(...).model_dump()` with `player_id` forced to the actor, plus `"dc": int` and `"name": str` (the character's name).

- [ ] **Step 1: Write the failing tests**

In `tests/test_narration.py`:

(a) **Replace** the whole of `test_handle_action_executes_a_tool_call_and_logs_the_result` with:

```python
@pytest.mark.asyncio
async def test_request_roll_becomes_a_pending_roll_not_a_roll(tmp_path):
    session = _session_with_character()
    client = _fake_client(
        "You eye the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill": "athletics",
            "difficulty": "hard", "reason": "leap the gap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    pending = session.pending_rolls["p1"]
    assert pending["player_id"] == "p1"
    assert pending["skill"] == "athletics" and pending["difficulty"] == "hard"
    assert pending["dc"] == 16 and pending["name"] == "Rook"
    assert "You eye the ledge." in session.log
    pending_line = next(line for line in session.log if line.startswith("[roll pending: "))
    assert json.loads(pending_line[len("[roll pending: "):-1])["skill"] == "athletics"
    assert not any(line.startswith("[request_roll") for line in session.log)
```

(b) **Replace** the whole of `test_handle_action_overrides_the_models_player_id_for_request_roll` with:

```python
@pytest.mark.asyncio
async def test_pending_roll_is_keyed_to_the_actor_not_the_models_player_id(tmp_path):
    # Server-authoritative: the acting player always owns the roll they
    # triggered, whatever player_id the model put in tool_args.
    session = _session_with_two_characters()
    client = _fake_client(
        "You eye the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill": "athletics",
            "difficulty": "easy", "reason": "leap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    assert list(session.pending_rolls) == ["p1"]
    assert session.pending_rolls["p1"]["player_id"] == "p1"
```

(c) Append:

```python
@pytest.mark.asyncio
async def test_action_is_refused_while_that_players_roll_is_pending(tmp_path):
    session = _session_with_character()
    session.pending_rolls["p1"] = {"player_id": "p1"}
    client = _fake_client("unused")

    with pytest.raises(ValueError, match="roll first"):
        await _call(session, client, "p1", {"text": "I run."}, tmp_path)


@pytest.mark.asyncio
async def test_other_players_can_act_while_one_roll_is_pending(tmp_path):
    session = _session_with_two_characters()
    session.pending_rolls["p1"] = {"player_id": "p1"}
    client = _fake_client("Ghost waits.")

    await _call(session, client, "someone-else", {"text": "I wait."}, tmp_path, tts_backend=FakeTTSBackend())

    assert "Ghost waits." in session.log
```

In `tests/test_server_main.py`, append:

```python
def test_system_prompt_tells_the_narrator_to_stop_before_the_roll_result():
    from server.__main__ import build_system_prompt

    prompt = build_system_prompt()

    assert "narrate only the lead-up" in prompt
    assert "never contradict it" in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration.py tests/test_server_main.py -q`
Expected: the new and replaced tests fail (no `pending_rolls` entry; no "roll first"; prompt text missing).

- [ ] **Step 3: Refactor `server/narration.py` into `_run_turn`**

Add these imports next to the existing ones:

```python
import json

from narrator.tools import RequestRoll, execute_tool
from ruleset.difficulty import Difficulty
```

(`execute_tool` is already imported; merge, don't duplicate.)

Replace `handle_action` with the two functions below. The body of `_run_turn` is the old `handle_action` body, moved, with only these changes:
- `action_text` becomes `prompt_text`;
- the actor line is optional;
- the `request_roll` branch is new.

```python
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
    messages = _build_messages(session, prompt_text, narrator_client.num_ctx)
    response = await narrator_client.respond(messages)

    if actor_line is not None:
        session.log.append(actor_line)

    # ... (the existing narration-segment loop, unchanged) ...

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

    # ... (the existing image-cooldown block and compaction, unchanged) ...
```

Copy the elided parts verbatim from the current `handle_action`: the narration loop, and everything from `generated_image = False` to the end.

Add `_hold_roll` above `handle_action`:

```python
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
```

- [ ] **Step 4: Add the system-prompt rule (`server/__main__.py`)**

In `build_system_prompt`, append to the end of the existing `rules = (...)` string literal, inside it and before its closing parenthesis, with a leading space so it joins the previous sentence:

```python
        " When you call request_roll, narrate only the lead-up to the moment of risk "
        "and stop before the result - the player rolls next, then you'll be told the "
        "outcome and narrate it. Example: player sneaks past a guard -> narrate the "
        "guard turning toward the curtain, the creak of a floorboard, then request_roll "
        "(stealth, hard). Don't narrate whether they made it. When you're given a roll "
        "result, narrate what happens true to that result; never contradict it."
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass. Every other existing `handle_action` test must pass **unchanged**, because that is the refactor guard. If one fails, fix the refactor, not the test.

- [ ] **Step 6: Commit**

```bash
git add server/narration.py server/__main__.py tests/test_narration.py tests/test_server_main.py
git commit -m "feat: hold requested rolls as pending; shared turn pipeline"
```

---

### Task 3: `handle_roll` (player rolls, then the narrator resolves) and routing

**Files:**
- Modify: `server/narration.py`, `server/app.py`
- Test: `tests/test_narration.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `_run_turn` and `_hold_roll`'s pending entry shape (Task 2); `execute_tool(session, "request_roll", args) -> {"die_result", "attribute_mod", "skill_mod", "dc", "outcome"}`, where `outcome` is one of `"clean_success"`, `"complication"` or `"failure"`.
- Produces:
  - `async def handle_roll(session, narrator_client, store, image_backend, tts_backend, player_id: str) -> None`;
  - `def _roll_line(pending: dict, result: dict) -> str`;
  - `server/app.py` routes `{"type": "roll"}` to `handle_roll`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narration.py`:

```python
async def _roll(session, client, player_id, tmp_path, tts_backend=None):
    from server.narration import handle_roll

    store = JSONFileSessionStore(tmp_path)
    await handle_roll(session, client, store, _UnusedImageBackend(), tts_backend or FakeTTSBackend(), player_id)
    return store


def _pending(session, difficulty="hard", dc=16):
    session.pending_rolls["p1"] = {
        "player_id": "p1", "attribute": "reflexes", "skill": "stealth",
        "difficulty": difficulty, "reason": "slip past the guard", "dc": dc, "name": "Rook",
    }


@pytest.mark.asyncio
async def test_roll_with_nothing_pending_is_refused(tmp_path):
    session = _session_with_character()

    with pytest.raises(ValueError, match="no roll pending"):
        await _roll(session, _fake_client("unused"), "p1", tmp_path)


@pytest.mark.asyncio
async def test_roll_resolves_logs_visible_line_and_clears_pending(tmp_path, monkeypatch):
    session = _session_with_character()  # reflexes 14 -> modifier +2, stealth rank 0
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 7)

    await _roll(session, _fake_client("The guard never turns."), "p1", tmp_path)

    assert "p1" not in session.pending_rolls
    assert "Rook rolls Stealth (Reflexes) vs Hard: a failure (7 +2 +0 = 9 vs 16)." in session.log
    roll_line = next(line for line in session.log if line.startswith("[roll: "))
    data = json.loads(roll_line[len("[roll: "):-1])
    assert data["die_result"] == 7 and data["outcome"] == "failure" and data["skill"] == "stealth"
    assert "The guard never turns." in session.log


@pytest.mark.asyncio
async def test_natural_ten_and_one_are_called_out(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 10)
    await _roll(session, _fake_client("ok"), "p1", tmp_path)
    assert any(line.endswith("vs 16) — a natural 10.") and "a clean success" in line for line in session.log)

    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 1)
    await _roll(session, _fake_client("ok"), "p1", tmp_path)
    assert any(line.endswith("vs 16) — a natural 1.") and "a failure" in line for line in session.log)


@pytest.mark.asyncio
async def test_resolution_prompt_contains_the_result(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 7)
    sent = []

    async def chat_fn(*, model, messages, format):
        sent.append(messages)
        payload = {"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    await _roll(session, NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn), "p1", tmp_path)

    content = sent[0][-1]["content"]
    assert "Roll result for Rook: a failure on slip past the guard." in content
    assert "Rook rolls Stealth (Reflexes) vs Hard: a failure" in content


@pytest.mark.asyncio
async def test_no_new_roll_during_a_resolution(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 7)
    client = _fake_client(
        "The guard spins.", tool="request_roll",
        tool_args={"player_id": "p1", "attribute": "reflexes", "skill": "athletics", "difficulty": "easy", "reason": "dodge"},
    )

    await _roll(session, client, "p1", tmp_path)

    assert session.pending_rolls == {}
    assert "[tool error: no new rolls during a roll resolution]" in session.log


@pytest.mark.asyncio
async def test_resolution_can_apply_consequences(tmp_path, monkeypatch):
    session = _session_with_character()
    _pending(session)
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 2)
    client = _fake_client(
        "The guard's baton cracks your ribs.", tool="apply_character_update",
        tool_args={"player_id": "p1", "health_delta": -20},
    )

    await _roll(session, client, "p1", tmp_path)

    assert session.characters["p1"].health == 80
```

In `tests/test_app.py`, append a websocket test using that file's existing client and fake-narrator pattern. It must send `join`, then `{"type": "roll"}` with nothing pending, and assert the error message contains `"no roll pending"`. Copy the closest existing websocket test in that file for the setup. Its fake narrator is never called on this path.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration.py tests/test_app.py -q`
Expected: FAIL. `handle_roll` can't be imported, and the app returns no "no roll pending" error.

- [ ] **Step 3: Implement in `server/narration.py`**

```python
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
    total = die + attr_mod + skill_mod
    line = (
        f"{pending['name']} rolls {_label(pending['skill'])} ({_label(pending['attribute'])}) "
        f"vs {_label(pending['difficulty'])}: {_OUTCOME_TEXT[result['outcome']]} "
        f"({die} {attr_mod:+d} {skill_mod:+d} = {total} vs {result['dc']})"
    )
    if die in (1, 10):
        line += f" — a natural {die}"
    return line + "."


async def handle_roll(
    session: Session,
    narrator_client: NarratorClient,
    store: JSONFileSessionStore,
    image_backend: ImageBackend,
    tts_backend: TTSBackend,
    player_id: str,
) -> None:
    pending = session.pending_rolls.pop(player_id, None)
    if pending is None:
        raise ValueError("no roll pending")
    args = {k: pending[k] for k in ("player_id", "attribute", "skill", "difficulty", "reason")}
    result = execute_tool(session, "request_roll", args)
    session.log.append(_roll_line(pending, result))
    session.log.append(f"[roll: {json.dumps({**result, **pending})}]")
    await _run_turn(
        session, narrator_client, store, image_backend, tts_backend, player_id,
        prompt_text=(
            f"Roll result for {pending['name']}: {_OUTCOME_TEXT[result['outcome']]} on "
            f"{pending['reason']}. Narrate what happens now, true to that result."
        ),
        actor_line=None, allow_roll=False,
    )
```

- [ ] **Step 4: Route it in `server/app.py`**

Import `handle_roll` next to `handle_action`. In the message `try` block, after the `action` branch, add:

```python
                    elif message.get("type") == "roll":
                        await handle_roll(session, narrator_client, store, image_backend, tts_backend, player_id)
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/narration.py server/app.py tests/test_narration.py tests/test_app.py
git commit -m "feat: player-triggered roll resolves pending rolls, then the narrator narrates the result"
```

---

### Task 4: Roll card UI

**Files:**
- Modify: `frontend/src/lib/nightwire/protocol.ts`, `frontend/src/app/nightwire/page.tsx`, `frontend/src/app/nightwire/theme.css`
- Create: `frontend/src/app/nightwire/RollCard.tsx`

**Interfaces:**
- Consumes: `view.pending_rolls` (Task 1); `[roll: <json>]` and `[roll pending: <json>]` log lines (Tasks 2–3); the outgoing message `{ type: "roll" }` (Task 3). JSON keys:
  - pending entries: `player_id`, `attribute`, `skill`, `difficulty`, `reason`, `dc`, `name`;
  - rolled entries add `die_result`, `attribute_mod`, `skill_mod` and `outcome`.

- [ ] **Step 1: Protocol types (`protocol.ts`)**

```ts
export interface PendingRoll {
  player_id: string
  attribute: string
  skill: string
  difficulty: 'easy' | 'moderate' | 'hard' | 'extreme'
  reason: string
  dc: number
  name: string
}

export interface RollResult extends PendingRoll {
  die_result: number
  attribute_mod: number
  skill_mod: number
  outcome: 'clean_success' | 'complication' | 'failure'
}
```

Add `pending_rolls: Record<string, PendingRoll>` to `StateView`.

- [ ] **Step 2: `RollCard.tsx`**

Create `frontend/src/app/nightwire/RollCard.tsx`, exporting `PendingRollCard` and `RollResultCard`:

```tsx
"use client";

import { useEffect, useState } from "react";
import type { PendingRoll, RollResult } from "@/lib/nightwire/protocol";

const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
const sign = (n: number) => (n >= 0 ? `+${n}` : `${n}`);
const OUTCOME = {
  clean_success: { text: "Clean success", cls: "nw-roll-success" },
  complication: { text: "Complication", cls: "nw-roll-complication" },
  failure: { text: "Failure", cls: "nw-roll-failure" },
} as const;

export function PendingRollCard({ roll, isMine, onRoll, rolling }: {
  roll: PendingRoll; isMine: boolean; onRoll: () => void; rolling: boolean;
}) {
  return (
    <div className="nw-roll-card" role="group" aria-label={`Roll for ${roll.name}`}>
      <p className="nw-text-muted text-xs">{roll.reason}</p>
      <p className="font-semibold">
        {label(roll.skill)} ({label(roll.attribute)}) · {label(roll.difficulty)} {roll.dc}
      </p>
      {isMine ? (
        <button type="button" className="nw-btn-primary mt-2" onClick={onRoll} disabled={rolling}>
          {rolling ? "Rolling…" : "Roll"}
        </button>
      ) : (
        <p className="nw-text-faint mt-2 text-xs">Waiting for {roll.name} to roll…</p>
      )}
    </div>
  );
}

export function RollResultCard({ roll, animate }: { roll: RollResult; animate: boolean }) {
  const [landed, setLanded] = useState(!animate);
  useEffect(() => {
    if (!animate) return;
    const t = setTimeout(() => setLanded(true), 700);
    return () => clearTimeout(t);
  }, [animate]);
  const total = roll.die_result + roll.attribute_mod + roll.skill_mod;
  const natural = roll.die_result === 10 || roll.die_result === 1;
  const outcome = OUTCOME[roll.outcome];
  return (
    <div className={`nw-roll-card ${landed && natural ? "nw-roll-natural" : ""}`}>
      <p className="nw-text-muted text-xs">{roll.name} · {label(roll.skill)} vs {label(roll.difficulty)} {roll.dc}</p>
      <div className="flex items-center gap-3">
        <span className={`nw-d10 ${landed ? "" : "nw-d10-tumble"}`} aria-hidden={!landed}>
          {landed ? roll.die_result : "?"}
        </span>
        {landed && (
          <>
            <span className="text-sm">
              {roll.die_result} {sign(roll.attribute_mod)} {label(roll.attribute)} {sign(roll.skill_mod)} {label(roll.skill)} = {total} vs {roll.dc}
            </span>
            <span className={`nw-roll-badge ${outcome.cls}`}>{outcome.text}{natural ? ` · natural ${roll.die_result}` : ""}</span>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Styles (`theme.css`)**

Append, using existing `--nw-*` tokens where the file defines them:

```css
.nw-roll-card { border: 1px solid var(--nw-border, #333); border-radius: 0.75rem; padding: 0.75rem 1rem; max-width: 85%; }
.nw-d10 { display: inline-flex; align-items: center; justify-content: center; width: 2.5rem; height: 2.5rem;
  clip-path: polygon(50% 0, 100% 38%, 82% 100%, 18% 100%, 0 38%); background: var(--nw-accent, #e0245e); font-weight: 700; }
.nw-d10-tumble { animation: nw-tumble 0.7s ease-out; }
@keyframes nw-tumble { 0% { transform: rotate(0) scale(0.6); } 60% { transform: rotate(540deg) scale(1.1); } 100% { transform: rotate(720deg) scale(1); } }
.nw-roll-badge { border-radius: 9999px; padding: 0.1rem 0.6rem; font-size: 0.75rem; font-weight: 600; }
.nw-roll-success { background: #14532d; color: #bbf7d0; }
.nw-roll-complication { background: #713f12; color: #fde68a; }
.nw-roll-failure { background: #7f1d1d; color: #fecaca; }
.nw-roll-natural { animation: nw-flash 0.6s ease-out 2; }
@keyframes nw-flash { 50% { box-shadow: 0 0 0 3px var(--nw-accent, #e0245e); } }
@media (prefers-reduced-motion: reduce) { .nw-d10-tumble, .nw-roll-natural { animation: none; } }
```

- [ ] **Step 4: Wire it into `page.tsx`**

1. Import `PendingRollCard` and `RollResultCard`, plus the `RollResult` type.
2. Next to `IMAGE_LINE`, add:
   ```ts
   const ROLL_LINE = /^\[roll: (.+)\]$/;
   const ROLL_PENDING_LINE = /^\[roll pending: .+\]$/;
   ```
3. In the `view.log.map(...)` render, before the `IMAGE_LINE` check:
   - lines matching `ROLL_PENDING_LINE` render nothing (`return null`); the card comes from `view.pending_rolls`;
   - lines matching `ROLL_LINE` render `<RollResultCard key={i} roll={JSON.parse(m[1]) as RollResult} animate={i === lastRollIndex} />`, where `lastRollIndex` is the index of the last `ROLL_LINE` in `view.log`, computed once before the map. Only the newest roll animates.
   - Wrap `JSON.parse` in a try/catch that falls back to the existing meta rendering.
4. After the log list and before `<VitalsBand …>`, render one `PendingRollCard` per `Object.values(view.pending_rolls)`:
   - `isMine={roll.player_id === playerId}`;
   - `onRoll={() => { setRolling(true); send({ type: "roll" }); }}`;
   - `rolling={rolling}`.
   
   Add `const [rolling, setRolling] = useState(false)`. Reset it to `false` wherever the page already resets `sending` when a new state or error message arrives (follow that existing pattern exactly).
5. Composer lock: compute `const myRollPending = Boolean(view?.pending_rolls?.[playerId])`. Disable the composer textarea and send button when it's true, and show the placeholder `"Roll first"`. Keep the existing `sending` disable logic as well (OR them).

- [ ] **Step 5: Lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: build succeeds. Lint shows only the one known pre-existing `react-hooks/set-state-in-effect` error in `page.tsx` and nothing new. If `RollResultCard`'s `useEffect` triggers the same rule, restructure it (for example, key the component so it mounts landed state from a CSS animation end, or use `onAnimationEnd` to set `landed`) rather than suppressing the rule.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/nightwire/protocol.ts frontend/src/app/nightwire/RollCard.tsx frontend/src/app/nightwire/page.tsx frontend/src/app/nightwire/theme.css
git commit -m "feat: roll card UI - Roll button, d10 tumble, outcome badge, composer lock"
```

---

### Task 5: Live verification and docs (run by the controller, not a subagent)

**Files:** `README.md`, `ROADMAP.md`. A throwaway probe goes in the plan's git-ignored `.superpowers/sdd/<plan>/probe/`.

- [ ] **Step 1: Narrator probe**

Use the GPU box (`OLLAMA_HOST=http://192.168.10.19:11434`) with a 300s `ollama.AsyncClient`, following the Phase 14 and 15 probe pattern. Send 8 risky actions:
1. sneak past a guard;
2. punch a ganger;
3. talk a bouncer down;
4. jack a door lock;
5. leap a rooftop gap;
6. spot a tail;
7. lie to a cop;
8. outrun a drone.

After each `handle_action`, if `pending_rolls` holds the player, call `handle_roll`.

- [ ] **Step 2: Score it** (n = 8, single pass: indicative only)

Record:
- rolls requested out of 8;
- **leaks**: setup narration that already states success or failure; quote each one;
- **fidelity**: does each resolution match the real outcome? Quote any contradictions;
- consequences applied on failures;
- extra latency on roll turns (the resolution call time);
- schema and tool errors.

- [ ] **Step 3: Browser check**

Start the backend and frontend locally against the GPU box's Ollama. In two browser windows (two players), check:
- the pending card in both windows;
- the Roll button only for the roller;
- "Waiting for…" for the other player;
- the composer showing "Roll first";
- the tumble, the breakdown and the badge;
- the resolution narration after the roll.

Use the claude-in-chrome tools or Playwright, and capture a screenshot for the README.

- [ ] **Step 4: Docs**

- **README:** a short "Rolls" note under "What makes it Nightwire": the narrator sets up the moment, you roll, and the narrator tells what happens knowing the result.
- **ROADMAP:** a `16. **Two-step player rolls**` entry after Phase 15, in the same shape as earlier entries: spec and plan paths, what was built, live numbers with n, and what was deferred (rerolls and advantage go to Phase 17's Kagerou; group rolls; timeouts).

- [ ] **Step 5: Commit**

```bash
git add README.md ROADMAP.md
git commit -m "docs: record Phase 16 (two-step player rolls) and its live verification"
```

Ask the owner before pushing.
