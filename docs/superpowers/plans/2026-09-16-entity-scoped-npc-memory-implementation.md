# Entity-Scoped NPC Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `remember_npc` tool the narrator can call to persist a durable NPC fact, and have every turn's context automatically include a small, token-budget-aware "Known NPCs" block — no `recall_npc` tool, no multi-round tool loop (nightwire's turn structure is single-shot; see the design spec for why that pattern doesn't transfer).

**Architecture:** `Session.npc_memory: dict[str, list[str]]` stores everything the session has learned about NPCs (write-time sanity-capped, never lossily pruned by relevance). A new `remember_npc` tool (joining `request_roll`/`apply_character_update`/`update_world` in the existing `ToolCall` discriminated union and `TOOL_REGISTRY`) writes to it. A new `_select_npc_memory_for_context` function in `server/narration.py` — mirroring Phase 11's `_select_verbatim_narrative` exactly — decides what fits a small, `num_ctx`-adaptive token budget each turn, most-recently-touched NPCs first.

**Tech Stack:** Python 3.11+, existing `pydantic`/dataclasses — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-16-entity-scoped-npc-memory-design.md`

## Global Constraints

- `Session.npc_memory: dict[str, list[str]] = field(default_factory=dict)` — NPC name → ordered facts (oldest first).
- Write-time sanity caps (LRU by touch, zero extra state via dict re-insertion order): `_MAX_NPCS = 50` (in `narrator/tools.py`), `_MAX_FACTS_PER_NPC = 5` (in `narrator/tools.py`).
- `RememberNPC` schema: `name: str = Field(..., max_length=100)`, `fact: str = Field(..., max_length=200)` — matches the existing schema-bounding precedent already used by `ApplyCharacterUpdate`'s `skill_points_delta`/`attribute_points_delta`.
- Read-time context budget: `_NPC_MEMORY_BUDGET_FRACTION = 0.05` of `num_ctx` (in `server/narration.py`), converted to a character budget the same way `_VERBATIM_BUDGET_FRACTION` already is (`int(num_ctx * fraction * _CHARS_PER_TOKEN_ESTIMATE)`) — a separate, smaller reserved slice, not renegotiating the existing 65% verbatim-narrative fraction.
- No `recall_npc` tool, no multi-round tool-calling loop — out of scope entirely, not deferred-but-stubbed.
- `Session.npc_memory` must round-trip through `JSONFileSessionStore.save()`/`load()`, with `.get("npc_memory", {})` defaulting for pre-existing session files — the same pattern every prior `Session` field addition in this project uses.

---

## File Structure

- **Modify** `engine/session.py` — one new `Session` field.
- **Modify** `engine/persistence.py` — `load()` defaults the new field.
- **Modify** `narrator/tools.py` — `RememberNPC` model, `_execute_remember_npc`, cap/eviction logic, `TOOL_REGISTRY` entry.
- **Modify** `narrator/client.py` — `_RememberNPCCall` variant added to the `ToolCall` discriminated union.
- **Modify** `server/narration.py` — `_select_npc_memory_for_context`, `_build_messages` updated to inject it.
- **Modify** `server/__main__.py` — system prompt gains `remember_npc` restraint guidance.
- **Test**: `tests/test_session.py`, `tests/test_persistence.py`, `tests/test_narrator_tools.py`, `tests/test_narrator_client.py`, `tests/test_narration.py` (all modified, no new test files).

---

### Task 1: `Session.npc_memory` field and persistence

**Files:**
- Modify: `engine/session.py`
- Modify: `engine/persistence.py`
- Test: `tests/test_session.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Produces: `Session.npc_memory: dict[str, list[str]]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session.py`:

```python
def test_session_npc_memory_defaults_to_empty_and_is_independent_per_instance():
    session_a = Session(session_id="a")
    session_b = Session(session_id="b")

    assert session_a.npc_memory == {}
    session_a.npc_memory["Jax"] = ["offered the party a job"]

    assert session_b.npc_memory == {}
```

In `tests/test_persistence.py`, add this line to `test_save_then_load_round_trips_a_session_with_a_character`, right after `session.narrative_summary_line_count = 14`:

```python
    session.npc_memory["Jax"] = ["offered the party a job", "runs a noodle stand in Watson"]
```

And add this assertion right after `assert loaded.narrative_summary_line_count == 14`:

```python
    assert loaded.npc_memory == {"Jax": ["offered the party a job", "runs a noodle stand in Watson"]}
```

Then append this new test at the end of `tests/test_persistence.py`, mirroring the existing `test_load_defaults_narrative_summary_when_missing_from_an_older_file` pattern exactly:

```python
def test_load_defaults_npc_memory_when_missing_from_an_older_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    from dataclasses import asdict

    legacy_data = asdict(session)
    del legacy_data["npc_memory"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(legacy_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.npc_memory == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_session.py tests/test_persistence.py -v`
Expected: `FAIL` — `AttributeError: 'Session' object has no attribute 'npc_memory'` (or similar).

- [ ] **Step 3: Add the field to `engine/session.py`**

In the `Session` dataclass, add this line right after `narrative_summary_line_count: int = 0`:

```python
    npc_memory: dict[str, list[str]] = field(default_factory=dict)
```

- [ ] **Step 4: Update `engine/persistence.py`'s `load()`**

Add this line to the `Session(...)` constructor call, right after `narrative_summary_line_count=data.get("narrative_summary_line_count", 0),`:

```python
            npc_memory=data.get("npc_memory", {}),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_session.py tests/test_persistence.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add engine/session.py engine/persistence.py tests/test_session.py tests/test_persistence.py
git commit -m "feat: add npc_memory field to Session, with persistence round-trip"
```

---

### Task 2: `remember_npc` tool — executor, caps, discriminated union

**Files:**
- Modify: `narrator/tools.py`
- Modify: `narrator/client.py`
- Test: `tests/test_narrator_tools.py`
- Test: `tests/test_narrator_client.py`

**Interfaces:**
- Consumes: `Session.npc_memory` (Task 1).
- Produces: `RememberNPC` (Pydantic model, `narrator/tools.py`), registered in `TOOL_REGISTRY` under `"remember_npc"`; `_RememberNPCCall` added to `narrator/client.py`'s `ToolCall` union so `NarratorResponse.tool == "remember_npc"` / `.tool_args == {"name": ..., "fact": ...}` parse correctly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narrator_tools.py`:

```python
def test_remember_npc_stores_a_fact():
    session = Session(session_id="s1")
    result = execute_tool(session, "remember_npc", {"name": "Jax", "fact": "offered the party a job"})
    assert session.npc_memory["Jax"] == ["offered the party a job"]
    assert result == {"name": "Jax", "facts": ["offered the party a job"]}


def test_remember_npc_appends_multiple_facts_for_the_same_npc():
    session = Session(session_id="s1")
    execute_tool(session, "remember_npc", {"name": "Jax", "fact": "first fact"})
    execute_tool(session, "remember_npc", {"name": "Jax", "fact": "second fact"})
    assert session.npc_memory["Jax"] == ["first fact", "second fact"]


def test_remember_npc_caps_facts_per_npc_dropping_the_oldest():
    session = Session(session_id="s1")
    for i in range(7):
        execute_tool(session, "remember_npc", {"name": "Jax", "fact": f"fact {i}"})
    assert session.npc_memory["Jax"] == ["fact 2", "fact 3", "fact 4", "fact 5", "fact 6"]


def test_remember_npc_evicts_the_least_recently_touched_npc_once_over_the_cap():
    session = Session(session_id="s1")
    for i in range(51):
        execute_tool(session, "remember_npc", {"name": f"npc{i}", "fact": "x"})
    assert len(session.npc_memory) == 50
    assert "npc0" not in session.npc_memory
    assert "npc50" in session.npc_memory


def test_remember_npc_touching_an_existing_npc_protects_it_from_eviction():
    session = Session(session_id="s1")
    for i in range(50):
        execute_tool(session, "remember_npc", {"name": f"npc{i}", "fact": "x"})
    # Touch npc0 again - it moves to most-recently-touched.
    execute_tool(session, "remember_npc", {"name": "npc0", "fact": "y"})
    # One more new NPC should now evict npc1 (the new least-recently-touched), not npc0.
    execute_tool(session, "remember_npc", {"name": "npc50", "fact": "x"})
    assert "npc0" in session.npc_memory
    assert "npc1" not in session.npc_memory


def test_remember_npc_rejects_a_fact_over_the_length_limit():
    session = Session(session_id="s1")
    with pytest.raises(ValueError):
        execute_tool(session, "remember_npc", {"name": "Jax", "fact": "x" * 500})


def test_remember_npc_rejects_a_name_over_the_length_limit():
    session = Session(session_id="s1")
    with pytest.raises(ValueError):
        execute_tool(session, "remember_npc", {"name": "x" * 500, "fact": "a fact"})
```

Append to `tests/test_narrator_client.py`:

```python
@pytest.mark.asyncio
async def test_respond_returns_a_remember_npc_tool_call():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": [{"speaker": "narrator", "text": "Jax nods slowly."}],
            "tool_call": {
                "tool": "remember_npc",
                "tool_args": {"name": "Jax", "fact": "offered the party a job"},
            },
        }),
    )
    response = await client.respond([{"role": "user", "content": "I shake Jax's hand."}])
    assert response.tool == "remember_npc"
    assert response.tool_args == {"name": "Jax", "fact": "offered the party a job"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narrator_tools.py tests/test_narrator_client.py -v`
Expected: `FAIL` — `ValueError: unknown tool: 'remember_npc'` for the tools tests, and a Pydantic validation error (the model refuses `"remember_npc"` as a `tool_call.tool` value) for the client test.

- [ ] **Step 3: Implement in `narrator/tools.py`**

Add these near the top of the file, after the existing imports:

```python
# Write-time sanity caps, not the primary context-budget mechanism (that's
# server/narration.py's _select_npc_memory_for_context, a separate,
# num_ctx-adaptive read-time bound) - these just stop truly unbounded
# growth over a very long campaign. Deliberately generous.
_MAX_NPCS = 50
_MAX_FACTS_PER_NPC = 5
```

Add this model, near the other tool models (after `UpdateWorld`):

```python
class RememberNPC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Schema-bounded so one verbose value from an 8B model can't consume a
    # large fraction of the already-small NPC memory context budget on its
    # own - same precedent ApplyCharacterUpdate's skill_points_delta/
    # attribute_points_delta already establishes in this file.
    name: str = Field(..., max_length=100)
    fact: str = Field(..., max_length=200)
```

Add this executor function, near the other executor functions:

```python
def _execute_remember_npc(session: Session, tool: RememberNPC) -> dict:
    # .pop then re-insert moves this NPC to the end of the dict - Python's
    # insertion-ordering gives LRU-by-touch for free, no extra state needed.
    facts = session.npc_memory.pop(tool.name, [])
    facts.append(tool.fact)
    facts = facts[-_MAX_FACTS_PER_NPC:]
    session.npc_memory[tool.name] = facts
    if len(session.npc_memory) > _MAX_NPCS:
        oldest = next(iter(session.npc_memory))
        del session.npc_memory[oldest]
    return {"name": tool.name, "facts": list(facts)}
```

Add this line to `TOOL_REGISTRY`:

```python
    "remember_npc": (RememberNPC, _execute_remember_npc),
```

- [ ] **Step 4: Implement in `narrator/client.py`**

Change the import line:
```python
from narrator.tools import ApplyCharacterUpdate, RequestRoll, UpdateWorld
```
to:
```python
from narrator.tools import ApplyCharacterUpdate, RememberNPC, RequestRoll, UpdateWorld
```

Add this class, after `_UpdateWorldCall`:

```python
class _RememberNPCCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["remember_npc"]
    tool_args: RememberNPC
```

Change `ToolCall`'s definition from:
```python
ToolCall = Annotated[
    Union[_NoTool, _RequestRollCall, _ApplyCharacterUpdateCall, _UpdateWorldCall],
    Field(discriminator="tool"),
]
```
to:
```python
ToolCall = Annotated[
    Union[_NoTool, _RequestRollCall, _ApplyCharacterUpdateCall, _UpdateWorldCall, _RememberNPCCall],
    Field(discriminator="tool"),
]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narrator_tools.py tests/test_narrator_client.py -v`
Expected: all tests pass.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all passing (the pre-existing 282 baseline plus this task's new tests) — this also confirms `_RememberNPCCall` didn't break `AnthropicNarratorBackend`/`OpenAICompatNarratorBackend`'s existing tests, since both validate against the same shared `NarratorResponse`/`ToolCall` schema.

- [ ] **Step 7: Commit**

```bash
git add narrator/tools.py narrator/client.py tests/test_narrator_tools.py tests/test_narrator_client.py
git commit -m "feat: add remember_npc tool with LRU-capped storage"
```

---

### Task 3: Context selection and injection

**Files:**
- Modify: `server/narration.py`
- Test: `tests/test_narration.py`

**Interfaces:**
- Consumes: `Session.npc_memory` (Task 1), `execute_tool`'s `"remember_npc"` registration (Task 2 — exercised indirectly via `handle_action`, not called directly by this task's own code).
- Produces: `_select_npc_memory_for_context(session: Session, num_ctx: int) -> dict[str, list[str]]`; `_build_messages` (unchanged signature) now also injects a "Known NPCs" block when non-empty.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narration.py`:

```python
def test_select_npc_memory_for_context_keeps_everything_under_budget():
    from server.narration import _select_npc_memory_for_context

    session = Session(session_id="s1")
    session.npc_memory = {"Jax": ["offered a job"], "Mora": ["bypassed a lock"]}

    result = _select_npc_memory_for_context(session, num_ctx=8192)

    assert result == session.npc_memory


def test_select_npc_memory_for_context_drops_everything_past_a_tiny_budget():
    from server.narration import _select_npc_memory_for_context

    # num_ctx=10 -> budget = int(10 * 0.05 * 4) = 2 chars - nothing fits.
    session = Session(session_id="s1")
    session.npc_memory = {"Jax": ["a fact"], "Mora": ["another fact"]}

    result = _select_npc_memory_for_context(session, num_ctx=10)

    assert result == {}


def test_build_messages_includes_known_npcs_when_present():
    from server.narration import _build_messages

    session = _session_with_character()
    session.npc_memory = {"Jax": ["offered the party a job"]}
    session.log = ["p1: I look around."]

    messages = _build_messages(session, "I ask about Jax.", num_ctx=8192)

    assert "Known NPCs:\nJax: offered the party a job" in messages[0]["content"]


def test_build_messages_omits_known_npcs_when_empty():
    from server.narration import _build_messages

    session = _session_with_character()
    session.log = ["p1: I look around."]

    messages = _build_messages(session, "I move forward.", num_ctx=8192)

    assert "Known NPCs" not in messages[0]["content"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration.py -v`
Expected: `FAIL` — `ImportError: cannot import name '_select_npc_memory_for_context' from 'server.narration'` for the first two new tests; the `_build_messages` tests fail on the `"Known NPCs"` assertions.

- [ ] **Step 3: Implement in `server/narration.py`**

Add this constant near the other budget constants (after `_MAX_SUMMARIZE_INPUT_CHARS`):

```python
# A separate, smaller reserved slice of num_ctx - not renegotiating
# _VERBATIM_BUDGET_FRACTION. 5% at num_ctx=8192 is ~410 tokens (~1,640
# chars), conservative against the ~1,940 tokens of generation headroom
# Phase 11's own final review measured. A starting value, not tuned.
_NPC_MEMORY_BUDGET_FRACTION = 0.05
```

Add this function, after `_select_verbatim_narrative`:

```python
def _select_npc_memory_for_context(session: Session, num_ctx: int) -> dict[str, list[str]]:
    budget_chars = int(num_ctx * _NPC_MEMORY_BUDGET_FRACTION * _CHARS_PER_TOKEN_ESTIMATE)
    selected: list[tuple[str, list[str]]] = []
    total = 0
    for name, facts in reversed(session.npc_memory.items()):
        entry = f"{name}: {'; '.join(facts)}"
        total += len(entry) + 1
        if total > budget_chars:
            break
        selected.append((name, facts))
    selected.reverse()
    return dict(selected)
```

In `_build_messages`, change:
```python
    parts = []
    if session.narrative_summary:
        parts.append(f"Summary of earlier events: {session.narrative_summary}")
    if verbatim:
        parts.append("Recent events:\n" + "\n".join(verbatim))
```
to:
```python
    parts = []
    if session.narrative_summary:
        parts.append(f"Summary of earlier events: {session.narrative_summary}")
    npc_memory = _select_npc_memory_for_context(session, num_ctx)
    if npc_memory:
        npc_lines = "\n".join(f"{name}: {'; '.join(facts)}" for name, facts in npc_memory.items())
        parts.append(f"Known NPCs:\n{npc_lines}")
    if verbatim:
        parts.append("Recent events:\n" + "\n".join(verbatim))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narration.py -v`
Expected: all tests pass, including every pre-existing test in the file.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all passing, pristine output.

- [ ] **Step 6: Commit**

```bash
git add server/narration.py tests/test_narration.py
git commit -m "feat: inject a token-budget-aware Known NPCs block into every turn's context"
```

---

### Task 4: Prompt guidance and live verification

**Files:**
- Modify: `server/__main__.py`
- Files: none beyond that + a `ROADMAP.md` record at the end (verification only — no other code changes).

- [ ] **Step 1: Add restraint guidance to the system prompt**

In `server/__main__.py`, the `system_prompt` string currently ends with:
```python
        "earned, set apply_character_update's skill_points_delta to 1-2, or "
        "attribute_points_delta to 1 (never more); a whole campaign hands out only a few."
    )
```

Change it to add a new sentence before the closing `)`:
```python
        "earned, set apply_character_update's skill_points_delta to 1-2, or "
        "attribute_points_delta to 1 (never more); a whole campaign hands out only a few. "
        "You may also call remember_npc to record a durable fact about a named NPC - use it "
        "rarely, only for facts likely to matter again: a name, a promise made, a debt owed, "
        "a distinguishing trait or motive. Example: a fixer named Jax offers a job and says "
        "he'll remember who helps him -> call remember_npc with name 'Jax' and fact 'offered "
        "the party a job; said he'll remember who helps him'. Don't call it for routine "
        "dialogue, restating something already established, or NPCs who won't matter again "
        "(a random ganger in a fight, a background vendor)."
    )
```

- [ ] **Step 2: Run the full suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all passing, pristine output. (This step has no new tests of its own — it's a plain-text prompt change with no unit-testable behavior; the real check is the live reliability probe below.)

- [ ] **Step 3: Commit the prompt change**

```bash
git add server/__main__.py
git commit -m "feat: add remember_npc restraint guidance to the system prompt"
```

- [ ] **Step 4: Locate the real, reachable Ollama instance actually running qwen3:8b**

Phase 11's own live verification found it on `sentinel` (Fedora, RTX 2080 8GB), reachable only via SSH (`ssh -i ~/.ssh/lan_ollama sentinel@<ip>` — the native Ollama install is bound to `127.0.0.1:11434`, not LAN-exposed) — but sentinel's IP is DHCP-assigned and has drifted before (it was `192.168.10.19` as of Phase 11's verification). Re-confirm reachability directly (`curl 127.0.0.1:11434/api/tags` on sentinel itself, over SSH) rather than trusting the cached IP. If unreachable after reasonable troubleshooting, report BLOCKED with exactly what you tried.

- [ ] **Step 5: Verify the combined real token budget**

Using this branch's real, unmocked code (archive it to sentinel the same way Phase 11's verification did: `git archive HEAD | ssh sentinel tar -x -C ~/some-dir`, then `uv sync`/`pip install` there), construct a session with both a long narrative history (enough to exceed the verbatim budget, same shape Phase 11's own verification used) *and* several remembered NPCs (enough to exceed the 5% NPC memory budget too), and confirm via real, driven `_build_messages` output: the "Known NPCs" block is present and correctly budget-limited, the verbatim/summary sections are unaffected, and the combined real message size stays within reasonable bounds of the ~1,940-token generation headroom Phase 11's own review measured (leave real numbers in the report — don't assume the exact prior figure still holds with this phase's addition).

- [ ] **Step 6: Run a live reliability probe for `remember_npc`'s firing rate**

Drive a handful of real turns against the live model: at least one turn that should clearly trigger `remember_npc` (an NPC making a promise, introducing themselves with a name) and at least one turn that should clearly not (routine dialogue, restating something already known). Record the real `tool_call.tool` value the model actually returned for each, and whether `session.npc_memory` was updated correctly when it did fire. This project's own history (`start_combat`, `image_request`) shows prompt-only restraint guidance often needs more than one round of tuning — report the real firing behavior honestly rather than assuming the Step 1 wording works on the first try; if it clearly over- or under-fires, note it as a known limitation for a later prompt-tuning pass rather than blocking this phase (the mechanism itself — storage, caps, injection — is what this phase is verifying; prompt-wording perfection is not required to call the mechanism done, the same standard Phase 5's `image_request` restraint tuning was held to across multiple documented passes).

- [ ] **Step 7: Record the result in ROADMAP.md**

Add a Phase 13 entry to `ROADMAP.md`'s Phases section (after Phase 12), following the same convention every other phase entry uses: design spec link, what was built, and the live-verification results from Steps 5-6 (real combined token/character numbers, the real `remember_npc` firing behavior observed, any known limitation noted honestly rather than glossed over).

```bash
git add ROADMAP.md
git commit -m "docs: record Phase 13 (entity-scoped NPC memory) and its live verification"
```

---

## Self-Review

**Spec coverage:**
- `remember_npc` tool (write) + always-injected context (read), no `recall_npc`/multi-round loop → Tasks 2-3; explicitly absent from any task. ✓
- `Session.npc_memory` storage, write-time-capped, not lossily pruned by relevance → Task 1 (field) + Task 2 (executor's cap/eviction logic). ✓
- Schema-bounded `name`/`fact` (max_length), matching `ApplyCharacterUpdate`'s precedent → Task 2. ✓
- `_select_npc_memory_for_context`, a separate `num_ctx`-adaptive budget (5%), mirroring `_select_verbatim_narrative`'s shape → Task 3. ✓
- LRU-by-touch eviction via dict re-insertion, zero extra state → Task 2's executor. ✓
- Persistence round-trip + legacy-file defaulting → Task 1. ✓
- Prompt restraint guidance (positive + negative example, same technique as `image_request`) → Task 4 Step 1. ✓
- Live verification: combined token budget, real firing-rate probe → Task 4 Steps 4-6. ✓
- Deferred items (`recall_npc`, multi-round loop, relevance-filtered selection, UI surface, cross-session memory, cap/budget tuning) → none touched by any task. ✓

**Placeholder scan:** No TBD/TODO/"add appropriate" phrasing; every step has real, runnable code or exact commands. Task 4's live-verification steps are necessarily less prescriptive than a unit test (real infrastructure work), matching the exact shape Phase 11's own Task 4 and Phase 10's Task 3 already used successfully for this project.

**Type consistency:** `RememberNPC(name: str, fact: str)` (Task 2) matches `_execute_remember_npc(session, tool: RememberNPC)`'s field access (`tool.name`, `tool.fact`) and `_RememberNPCCall.tool_args: RememberNPC` (also Task 2). `Session.npc_memory: dict[str, list[str]]` (Task 1) matches the type used in `_execute_remember_npc` (Task 2) and `_select_npc_memory_for_context`/`_build_messages` (Task 3) exactly. `_select_npc_memory_for_context(session: Session, num_ctx: int) -> dict[str, list[str]]`'s signature matches its one call site in `_build_messages` (Task 3).
