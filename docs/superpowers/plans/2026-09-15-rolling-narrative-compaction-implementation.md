# Rolling Narrative Compaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace nightwire's hardcoded `narrative[-10:]` context window with a token-budget-aware verbatim window plus a rolling narrative summary, and pin `num_ctx=8192` on the Ollama call so the budget the compaction logic targets is a real, known number instead of Ollama's undocumented, silently-truncating default.

**Architecture:** `NarratorClient` gains a configurable `num_ctx` (default 8192, applied to every Ollama call) and a `summarize()` method (a separate, unstructured chat call). `Session` gains `narrative_summary: str` and `narrative_summary_line_count: int`, persisted like every other session field. `server/narration.py`'s `_build_messages` selects as much recent verbatim narrative as fits a token-budget estimate instead of a fixed 10 lines, prepending `session.narrative_summary` when present; a new `_maybe_compact` function (called once per turn from `handle_action`) regenerates that summary — via one full-rebuild LLM call — only when the excluded (too-old-to-fit) narrative has grown since the last compaction.

**Tech Stack:** Python 3.11+, existing `ollama`/`httpx` dependencies — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-rolling-narrative-compaction-design.md`

## Global Constraints

- `num_ctx` defaults to `8192` on `NarratorClient`, applied via `options={"temperature": 0.3, "num_ctx": self.num_ctx}` on every Ollama chat call (both narration and summarization) — no call should omit it.
- Token estimate: `len(text) // 4` (chars-per-token heuristic), no tokenizer dependency.
- Verbatim narrative budget: `_VERBATIM_BUDGET_FRACTION = 0.65` of `num_ctx` tokens, converted to a character budget via the chars-per-token estimate.
- Compaction is a **full rebuild** each time it fires (summarize all currently-excluded narrative lines from scratch), not an incremental patch onto the previous summary.
- Compaction must only fire when the excluded-line count has **grown** since the last compaction (tracked via `Session.narrative_summary_line_count`) — never on every turn once the budget is first exceeded.
- Fail-soft: a summarization error logs `[summary error: {e}]` to `session.log` and leaves the previous `narrative_summary` unchanged; it must never block the player's turn (matches `[image error: ...]`/`[audio error: ...]`/`[tool error: ...]`).
- New `Session` fields must round-trip through `JSONFileSessionStore.save()`/`load()`, and `load()` must default them (`.get(..., default)`) for pre-existing session files that predate this phase — the exact bug class Phase 6 hit and fixed for `speaker_voices`.

---

## File Structure

- **Modify** `narrator/client.py` — `NarratorClient.__init__` gains `num_ctx`/`summarize_fn` params; `_default_chat` passes `num_ctx`; new `_default_summarize` and `summarize()`.
- **Modify** `engine/session.py` — two new `Session` fields.
- **Modify** `engine/persistence.py` — `load()` defaults the two new fields.
- **Modify** `server/narration.py` — token-budget-aware `_select_verbatim_narrative`, updated `_build_messages`, new `_maybe_compact`, wired into `handle_action`.
- **Test**: `tests/test_narrator_client.py`, `tests/test_session.py`, `tests/test_persistence.py`, `tests/test_narration.py` (all modified, no new test files).

---

### Task 1: NarratorClient — num_ctx pin and summarize()

**Files:**
- Modify: `narrator/client.py`
- Test: `tests/test_narrator_client.py`

**Interfaces:**
- Produces: `NarratorClient(..., num_ctx: int = 8192, summarize_fn: Callable[..., Awaitable[dict]] | None = None)`; `client.num_ctx: int`; `async def summarize(self, text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narrator_client.py`:

```python
def test_num_ctx_defaults_to_8192():
    client = NarratorClient()
    assert client.num_ctx == 8192


def test_num_ctx_is_configurable():
    client = NarratorClient(num_ctx=4096)
    assert client.num_ctx == 4096


@pytest.mark.asyncio
async def test_summarize_builds_system_and_user_messages():
    seen = {}

    async def summarize_fn(*, model, messages):
        seen["model"] = model
        seen["messages"] = messages
        return {"message": {"content": "The party met a fixer and agreed to a job."}}

    client = NarratorClient(model="qwen3:8b", summarize_fn=summarize_fn)
    result = await client.summarize("p1: I approach the fixer.\nThe fixer nods.")

    assert seen["model"] == "qwen3:8b"
    assert seen["messages"][0]["role"] == "system"
    assert seen["messages"][1] == {"role": "user", "content": "p1: I approach the fixer.\nThe fixer nods."}
    assert result == "The party met a fixer and agreed to a job."


@pytest.mark.asyncio
async def test_summarize_strips_whitespace_from_the_response():
    async def summarize_fn(*, model, messages):
        return {"message": {"content": "  A tense standoff at the docks.  \n"}}

    client = NarratorClient(summarize_fn=summarize_fn)
    result = await client.summarize("some events")

    assert result == "A tense standoff at the docks."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narrator_client.py -v`
Expected: `FAIL` — `NarratorClient() got an unexpected keyword argument 'num_ctx'` (or `AttributeError: 'NarratorClient' object has no attribute 'summarize'`).

- [ ] **Step 3: Implement the changes in `narrator/client.py`**

Add this constant near the top of the file, after the existing imports:

```python
_SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following tabletop RPG session events in 2-3 sentences. "
    "Preserve named characters, promises, and key decisions made. Prose only, no lists."
)
```

Replace the `NarratorClient.__init__` method with:

```python
    def __init__(
        self,
        model: str = "qwen3:8b",
        system_prompt: str = "",
        chat_fn: Callable[..., Awaitable[dict]] | None = None,
        generate_fn: Callable[..., Awaitable[object]] | None = None,
        summarize_fn: Callable[..., Awaitable[dict]] | None = None,
        num_ctx: int = 8192,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.num_ctx = num_ctx
        self._client = ollama.AsyncClient(timeout=60)
        self._chat_fn = chat_fn or self._default_chat
        self._generate_fn = generate_fn or self._client.generate
        self._summarize_fn = summarize_fn or self._default_summarize
```

Replace `_default_chat` with (adds `num_ctx` to the existing options dict — the comment about temperature stays, it's still true):

```python
    async def _default_chat(self, *, model: str, messages: list[dict], format: dict) -> dict:
        # Live probing found start_combat firing on 2/5, then 5/5, then 5/5 of
        # five identical test turns across separate runs - default sampling
        # temperature (~0.7-0.8 for Qwen3) makes the tool_call.tool decision
        # too noisy to be steered by prompt wording alone. Lower temperature
        # trades a little narrative prose variety for a lot more consistency
        # on this specific structured decision.
        return await self._client.chat(
            model=model,
            messages=messages,
            format=format,
            options={"temperature": 0.3, "num_ctx": self.num_ctx},
        )

    async def _default_summarize(self, *, model: str, messages: list[dict]) -> dict:
        return await self._client.chat(
            model=model,
            messages=messages,
            options={"temperature": 0.3, "num_ctx": self.num_ctx},
        )
```

Add this method after `respond()` (at the end of the class):

```python
    async def summarize(self, text: str) -> str:
        messages = [
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
        response = await self._summarize_fn(model=self.model, messages=messages)
        return response["message"]["content"].strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narrator_client.py -v`
Expected: all tests pass (the 4 new ones plus every pre-existing test in the file, unchanged).

- [ ] **Step 5: Commit**

```bash
git add narrator/client.py tests/test_narrator_client.py
git commit -m "feat: pin num_ctx on NarratorClient, add summarize() for narrative compaction"
```

---

### Task 2: Session fields and persistence

**Files:**
- Modify: `engine/session.py`
- Modify: `engine/persistence.py`
- Test: `tests/test_session.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Produces: `Session.narrative_summary: str = ""`, `Session.narrative_summary_line_count: int = 0`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session.py`:

```python
def test_session_narrative_summary_defaults_to_empty_and_is_independent_per_instance():
    session_a = Session(session_id="a")
    session_b = Session(session_id="b")

    assert session_a.narrative_summary == ""
    assert session_a.narrative_summary_line_count == 0
    session_a.narrative_summary = "The party met a fixer."
    session_a.narrative_summary_line_count = 12

    assert session_b.narrative_summary == ""
    assert session_b.narrative_summary_line_count == 0
```

In `tests/test_persistence.py`, add these two lines to `test_save_then_load_round_trips_a_session_with_a_character`, right after `session.last_turn_had_image = True`:

```python
    session.narrative_summary = "The party met a fixer and agreed to a job."
    session.narrative_summary_line_count = 14
```

And add these two assertions right after `assert loaded.last_turn_had_image is True`:

```python
    assert loaded.narrative_summary == "The party met a fixer and agreed to a job."
    assert loaded.narrative_summary_line_count == 14
```

Then append this new test at the end of `tests/test_persistence.py`, mirroring the existing `test_load_defaults_speaker_voices_when_missing_from_a_pre_phase6_file` pattern exactly:

```python
def test_load_defaults_narrative_summary_when_missing_from_an_older_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    from dataclasses import asdict

    legacy_data = asdict(session)
    del legacy_data["narrative_summary"]
    del legacy_data["narrative_summary_line_count"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(legacy_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.narrative_summary == ""
    assert loaded.narrative_summary_line_count == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_session.py tests/test_persistence.py -v`
Expected: `FAIL` — `AttributeError: 'Session' object has no attribute 'narrative_summary'` (or similar).

- [ ] **Step 3: Add the fields to `engine/session.py`**

In the `Session` dataclass, add these two lines right after `last_turn_had_image: bool = False`:

```python
    narrative_summary: str = ""
    narrative_summary_line_count: int = 0
```

- [ ] **Step 4: Update `engine/persistence.py`'s `load()`**

In `JSONFileSessionStore.load()`, add these two lines to the `Session(...)` constructor call, right after `last_turn_had_image=data.get("last_turn_had_image", False),`:

```python
            narrative_summary=data.get("narrative_summary", ""),
            narrative_summary_line_count=data.get("narrative_summary_line_count", 0),
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_session.py tests/test_persistence.py -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add engine/session.py engine/persistence.py tests/test_session.py tests/test_persistence.py
git commit -m "feat: add narrative_summary fields to Session, with persistence round-trip"
```

---

### Task 3: Token-budget-aware context window and compaction trigger

**Files:**
- Modify: `server/narration.py`
- Test: `tests/test_narration.py`

**Interfaces:**
- Consumes: `narrator_client.num_ctx` (Task 1), `narrator_client.summarize(text: str) -> str` (Task 1), `session.narrative_summary`/`session.narrative_summary_line_count` (Task 2).
- Produces: `_select_verbatim_narrative(narrative: list[str], num_ctx: int) -> list[str]`, `_build_messages(session: Session, action_text: str, num_ctx: int) -> list[dict]` (signature changed — now takes `num_ctx`), `async def _maybe_compact(session: Session, narrator_client: NarratorClient) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narration.py`. These tests need a `_fake_client_with_summary` helper alongside the file's existing `_fake_client`/`_fake_client_with_segments`:

```python
def _fake_client_with_summary(narration: str, summary_text: str) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        payload = {"narration": [{"speaker": "narrator", "text": narration}], "tool_call": {"tool": None}}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    async def summarize_fn(*, model, messages):
        return {"message": {"content": summary_text}}

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn, summarize_fn=summarize_fn, num_ctx=100)
```

Then add these tests (using a small `num_ctx=100` so budget math is easy to exceed with short test strings — the real default of 8192 is exercised only by live verification, not unit tests):

```python
def test_select_verbatim_narrative_keeps_everything_under_budget():
    from server.narration import _select_verbatim_narrative

    narrative = ["short line one", "short line two"]
    # num_ctx=100 -> budget = int(100 * 0.65 * 4) = 260 chars, both lines fit
    result = _select_verbatim_narrative(narrative, num_ctx=100)

    assert result == narrative


def test_select_verbatim_narrative_drops_oldest_lines_past_budget():
    from server.narration import _select_verbatim_narrative

    # num_ctx=10 -> budget = int(10 * 0.65 * 4) = 26 chars
    narrative = ["a" * 20, "b" * 20, "c" * 20]
    result = _select_verbatim_narrative(narrative, num_ctx=10)

    # Only the most recent line(s) that fit within 26 chars survive, in order
    assert result == ["c" * 20]


def test_build_messages_includes_narrative_summary_when_present():
    from server.narration import _build_messages

    session = _session_with_character()
    session.narrative_summary = "Earlier, the party met a fixer named Jax."
    session.log = ["p1: I nod at Jax."]

    messages = _build_messages(session, "I ask Jax about the job.", num_ctx=8192)

    content = messages[0]["content"]
    assert "Summary of earlier events: Earlier, the party met a fixer named Jax." in content
    assert "Recent events:\np1: I nod at Jax." in content


def test_build_messages_omits_summary_section_when_empty():
    from server.narration import _build_messages

    session = _session_with_character()
    session.log = ["p1: I look around."]

    messages = _build_messages(session, "I move forward.", num_ctx=8192)

    assert "Summary of earlier events" not in messages[0]["content"]


@pytest.mark.asyncio
async def test_maybe_compact_does_nothing_when_nothing_excluded():
    from server.narration import _maybe_compact

    session = _session_with_character()
    session.log = ["p1: I look around.", "The alley is quiet."]
    client = _fake_client_with_summary("ok", "should not be called")

    await _maybe_compact(session, client)

    assert session.narrative_summary == ""
    assert session.narrative_summary_line_count == 0


@pytest.mark.asyncio
async def test_maybe_compact_summarizes_excluded_lines_once_budget_exceeded():
    from server.narration import _maybe_compact

    session = _session_with_character()
    # num_ctx=100 on the fake client -> budget = 260 chars; make the log
    # clearly exceed that so some lines are excluded from the verbatim window.
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    client = _fake_client_with_summary("ok", "The party wandered the district for a while.")

    await _maybe_compact(session, client)

    assert session.narrative_summary == "The party wandered the district for a while."
    assert session.narrative_summary_line_count > 0


@pytest.mark.asyncio
async def test_maybe_compact_does_not_re_summarize_when_excluded_count_unchanged():
    from server.narration import _maybe_compact

    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    client = _fake_client_with_summary("ok", "first summary")

    await _maybe_compact(session, client)
    first_summary = session.narrative_summary
    assert first_summary == "first summary"

    # Same client would return "first summary" again if called - but nothing
    # new was added to session.log, so a second call must be a no-op.
    await _maybe_compact(session, client)

    assert session.narrative_summary == first_summary


@pytest.mark.asyncio
async def test_maybe_compact_logs_summary_error_and_keeps_prior_summary_on_failure():
    from server.narration import _maybe_compact

    session = _session_with_character()
    session.log = [f"line {i}: " + ("x" * 30) for i in range(20)]
    session.narrative_summary = "an existing summary"
    session.narrative_summary_line_count = 0  # force the trigger to fire again

    async def failing_summarize_fn(*, model, messages):
        raise ValueError("model unavailable")

    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps({"narration": [], "tool_call": {"tool": None}})}}

    client = NarratorClient(chat_fn=chat_fn, summarize_fn=failing_summarize_fn, num_ctx=100)

    await _maybe_compact(session, client)

    assert session.narrative_summary == "an existing summary"
    assert any("[summary error:" in line for line in session.log)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration.py -v`
Expected: `FAIL` — `ImportError: cannot import name '_select_verbatim_narrative' from 'server.narration'` (or similar) for the new tests; existing tests in the file still pass at this point since nothing has changed yet.

- [ ] **Step 3: Implement the changes in `server/narration.py`**

Replace the file's `_build_messages` function and everything above it up to (not including) `async def handle_action` with:

```python
import httpx

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend
from narrator.tools import execute_tool
from narrator.tts_backend import TTSBackend
from narrator.voice_assignment import assign_voice

# Verbatim recent narrative gets this fraction of num_ctx (in estimated
# tokens), leaving room for the system prompt, party roster, the action
# text, and response generation. A starting value, not a tuned optimum -
# see the Phase 11 design spec.
_VERBATIM_BUDGET_FRACTION = 0.65
# No tokenizer dependency - this is a "getting close to budget" trigger,
# not an exact accounting requirement.
_CHARS_PER_TOKEN_ESTIMATE = 4


def _select_verbatim_narrative(narrative: list[str], num_ctx: int) -> list[str]:
    budget_chars = int(num_ctx * _VERBATIM_BUDGET_FRACTION * _CHARS_PER_TOKEN_ESTIMATE)
    selected: list[str] = []
    total = 0
    for line in reversed(narrative):
        total += len(line) + 1
        if total > budget_chars:
            break
        selected.append(line)
    selected.reverse()
    return selected


def _build_messages(session: Session, action_text: str, num_ctx: int) -> list[dict]:
    # apply_character_update's player_id is trusted as-is (it legitimately
    # targets a different character than the actor, e.g. damage to a
    # teammate) - but the model was never told what real player_ids exist,
    # so on an early turn (nothing in the log yet to infer one from) it
    # invents a plausible-looking placeholder like "player" instead of the
    # real "p1", and the update silently fails validation. Grounding every
    # turn in the real roster fixes the root cause without narrowing who a
    # future multi-target tool call can address.
    roster = ", ".join(f"{c.player_id} ({c.name})" for c in session.characters.values())
    party = f"Party (use these exact player_ids): {roster}\n\n" if roster else ""
    # [start_combat: {...}]-style lines are tool-execution annotations for the
    # UI, not narrative fact - feeding them back verbatim let the model read
    # its own acknowledgment ("combat start requires...") as evidence combat
    # was actually ongoing, and re-trigger the tool turn after turn.
    narrative = [line for line in session.log if not line.startswith("[")]
    verbatim = _select_verbatim_narrative(narrative, num_ctx)
    parts = []
    if session.narrative_summary:
        parts.append(f"Summary of earlier events: {session.narrative_summary}")
    if verbatim:
        parts.append("Recent events:\n" + "\n".join(verbatim))
    context = "\n\n".join(parts) + "\n\n" if parts else ""
    return [{"role": "user", "content": f"{party}{context}Player action: {action_text}"}]


async def _maybe_compact(session: Session, narrator_client: NarratorClient) -> None:
    narrative = [line for line in session.log if not line.startswith("[")]
    verbatim = _select_verbatim_narrative(narrative, narrator_client.num_ctx)
    excluded_count = len(narrative) - len(verbatim)
    if excluded_count <= session.narrative_summary_line_count:
        return
    excluded = narrative[:excluded_count]
    try:
        session.narrative_summary = await narrator_client.summarize("\n".join(excluded))
        session.narrative_summary_line_count = excluded_count
    except (ValueError, TypeError, httpx.HTTPError) as e:
        session.log.append(f"[summary error: {e}]")
```

Then update `handle_action`'s call to `_build_messages` — change:

```python
    messages = _build_messages(session, action_text)
```

to:

```python
    messages = _build_messages(session, action_text, narrator_client.num_ctx)
```

Finally, add this as the very last line of `handle_action` (after the existing `session.last_turn_had_image = generated_image` line):

```python
    await _maybe_compact(session, narrator_client)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_narration.py -v`
Expected: all tests pass, including every pre-existing test in the file (none of their assertions reference the exact old 10-line-window behavior by count, so they should be unaffected — but verify this directly rather than assuming).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all tests passing, pristine output (matching the pre-existing 241 baseline plus the new tests added across Tasks 1-3).

- [ ] **Step 6: Commit**

```bash
git add server/narration.py tests/test_narration.py
git commit -m "feat: token-budget-aware narrative window with rolling summary compaction"
```

---

### Task 4: Live verification

**Files:** none (verification only — no code changes, beyond a ROADMAP.md record at the end).

- [ ] **Step 1: Locate the real, reachable Ollama instance actually running qwen3:8b for nightwire**

This is NOT necessarily the same box as Phase 10's ComfyUI instance (sentinel) — nightwire's narrator backend and its image-generation backend are documented as running on different LAN machines in `ROADMAP.md`'s Phase 3/5/6/8 entries. Check `OLLAMA_HOST` in any local `.env`, check this session's own memory/context for a known reachable Ollama host serving `qwen3:8b`, or ask if neither turns up a clear answer. Do not assume; confirm reachability with a real request (e.g. `curl <host>:11434/api/tags` and confirm `qwen3:8b` is in the list) before proceeding.

If no such host is reachable from this environment, report BLOCKED with exactly what you checked — do not fabricate or skip this verification.

- [ ] **Step 2: Verify num_ctx=8192 fits in real VRAM alongside the other resident services**

On the box hosting Ollama, check available/used VRAM before and during a request with `num_ctx=8192` set (e.g. `nvidia-smi` before and during a real `ollama run qwen3:8b` or an API call with `options: {num_ctx: 8192}`). Confirm it coexists with whatever else is resident there per this project's own documented deployment (Kokoro TTS, on-demand image generation) — or find the real number of headroom. If 8192 doesn't fit, the fallback per the design spec is a smaller value (e.g. 6144), not abandoning the pin.

- [ ] **Step 3: Run a real long-session compaction end to end**

Using the real deployed nightwire server (or a local instance pointed at the real Ollama host), drive a synthetic session with enough turns/narration to exceed the verbatim budget at `num_ctx=8192` (roughly: budget = `int(8192 * 0.65 * 4)` ≈ 21,300 characters of narrative — construct or play through enough turns to clearly exceed this). Confirm: `session.narrative_summary` gets populated with a real, coherent 2-3 sentence summary (not empty, not an error string); a later turn's actual request to the model includes that summary (verify via logging the real outgoing message content, not just trusting the code path); no `[summary error: ...]` lines appear in a successful run.

- [ ] **Step 4: Record the result in ROADMAP.md**

Add a Phase 11 entry to `ROADMAP.md`'s Phases section (after Phase 10), following the same convention every other phase entry uses: design spec link, what was built, and the live-verification result from Steps 2-3 (real VRAM numbers, real summary text generated, confirmation the summary reached a later turn's context).

```bash
git add ROADMAP.md
git commit -m "docs: record Phase 11 (rolling narrative compaction) and its live verification"
```

---

## Self-Review

**Spec coverage:**
- `num_ctx=8192` pin, applied to every Ollama call → Task 1 (`_default_chat`, `_default_summarize` both use `self.num_ctx`). ✓
- Token-budget-aware trigger, not turn-count → Task 3's `_select_verbatim_narrative` + `_maybe_compact`. ✓
- `len(text) // 4` heuristic, 60-70% budget split → `_CHARS_PER_TOKEN_ESTIMATE = 4`, `_VERBATIM_BUDGET_FRACTION = 0.65`, both in Task 3. ✓
- Full-rebuild summarization, not incremental → `_maybe_compact` always summarizes the complete `excluded` slice from `session.log`, never appends to the prior summary text. ✓
- Compaction fires only when excluded count grows → the `excluded_count <= session.narrative_summary_line_count: return` guard, tested explicitly in Task 3. ✓
- Fail-soft `[summary error: ...]`, prior summary preserved on failure → Task 3's `except` clause, tested explicitly. ✓
- `Session.narrative_summary`/`narrative_summary_line_count`, persisted with legacy-file defaulting → Task 2, mirroring the exact `speaker_voices` pattern. ✓
- Live verification (VRAM headroom, real long-session compaction) → Task 4. ✓
- Deferred items (entity-scoped memory, lorebook, budget-split tuning, incremental summarization) → none touched by any task. ✓

**Placeholder scan:** No TBD/TODO/"add appropriate" phrasing; every step has real, runnable code or exact commands.

**Type consistency:** `_build_messages(session, action_text, num_ctx)`'s new third parameter matches its one call site in `handle_action` (`narrator_client.num_ctx`, Task 3 Step 3). `_maybe_compact(session, narrator_client)` matches its call site (added as the last line of `handle_action`). `NarratorClient.summarize(text: str) -> str` (Task 1) matches its one caller in `_maybe_compact` (Task 3). `Session.narrative_summary`/`narrative_summary_line_count` (Task 2) match the field names read/written in `_maybe_compact` and `_build_messages` (Task 3) exactly.
