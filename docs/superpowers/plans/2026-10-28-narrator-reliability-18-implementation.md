# Narrator Reliability (Phase 18) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move state decisions the 8B narrator keeps missing to a small required-field referee call, let the engine set roll difficulty from model-rated stakes with a cap, redo a turn once when the engine refuses the narrator's tool call, and drop narration voiced as a player character.

**Architecture:** A new `narrator/referee.py` builds a per-turn yes/no schema from the actor's state, calls a new `judge()` method on the narrator backend, validates, and applies answers through existing engine functions. `server/narration.py::_run_turn` gains the voice filter, a refusal signal, the redo, and the referee call. `RequestRoll` takes `stakes`; `ruleset/difficulty.py` maps stakes with a cap held on the session.

**Tech Stack:** Python 3, pydantic, pytest (`asyncio_mode = "auto"`), Ollama Python client (`think` kwarg supported), httpx for hosted backends.

**Spec:** `docs/superpowers/specs/2026-10-28-narrator-reliability-18-design.md`

## Global Constraints

- Referee fields (exact names): `human_moment` (`none|small|big`), `acted_as_machine` (`none|small|big`, tsukumogami only), `gave_up_repo_item` (bool, only while `pending_repo`), `gig_paid_out` (bool, only while `installments_owed > 0` and not bodiless), `got_new_shell` (bool, only while bodiless), `hara_unlocked_chrome` (bool, only while `throttled`). All asked fields are required.
- Amounts: small = 2, big = 4 (gain for `human_moment`, loss for `acted_as_machine`).
- Referee call: `think=False`, `temperature: 0`, `num_predict: 80`. Failure logs `[referee error: …]` and applies nothing.
- Referee runs after narration on action turns that did not open a pending roll, and on roll-resolution turns. Never on the setup turn that opens a roll.
- The narrator's `ApplyCharacterUpdate` loses `humanity_delta`, `selfhood_loss`, `repossess`, `installments_paid`, `new_shell`, `unthrottle`.
- Stakes: `low|normal|high|extreme` → EASY|MODERATE|HARD|EXTREME. Cap window 6; if ≥ 2 of the window are high/extreme: high → normal, extreme → high. Window stores effective stakes.
- Pending roll dicts keep `difficulty` (effective) and `dc`, and add `stakes` (as the model gave it).
- Redo prompt suffix, exactly: `Engine: {error}. That does not happen - narrate the attempt failing or not being possible.` Log `[redo: {error}]`. One redo max; action turns only.
- Voice filter: drop segments whose speaker (trimmed, case-insensitive) equals a session character's `name` or `player_id`; log `[voice filtered: {speaker}]`.
- `NIGHTWIRE_THINK` env: `on` → `think=True`, `off` → `think=False`, unset → not passed.
- Existing log line formats from 17b/17c (`[torite: …]`, `[utsusemi: …]`, `[selfhood: ±N]`, objective "Owe Old Hara a favor") are unchanged — only who triggers them moves.
- Never add Co-Authored-By or AI-attribution trailers to commits. Run tests with `.venv/bin/python -m pytest tests/ -q` from the repo root.

---

### Task 1: Stakes instead of difficulty

**Files:**
- Modify: `ruleset/difficulty.py`, `narrator/tools.py` (RequestRoll, `_execute_request_roll`), `engine/session.py`, `engine/persistence.py`, `server/narration.py` (`_hold_roll`), `server/__main__.py` (roll sentence)
- Test: `tests/test_difficulty.py`, `tests/test_narration.py`, `tests/test_persistence.py`, and every existing test that builds `request_roll` args with `"difficulty"` (tests/test_app.py, test_harness.py, test_narrator_client.py, test_narrator_tools.py, test_narration.py) — change those args to `"stakes"` with the matching value (`easy→low`, `moderate→normal`, `hard→high`, `extreme→extreme`) and keep their assertions on the resulting `difficulty`/`dc`.

**Interfaces:**
- Produces: `STAKES: dict[str, Difficulty]`; `difficulty_for(stakes: str, recent: list[str]) -> tuple[str, Difficulty]` returning (effective_stakes, difficulty); `Session.recent_stakes: list[str]`; `RequestRoll.stakes: Literal["low","normal","high","extreme"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_difficulty.py`:

```python
from ruleset.difficulty import Difficulty, difficulty_for


def test_stakes_map_to_difficulty():
    assert difficulty_for("low", []) == ("low", Difficulty.EASY)
    assert difficulty_for("normal", []) == ("normal", Difficulty.MODERATE)
    assert difficulty_for("high", []) == ("high", Difficulty.HARD)
    assert difficulty_for("extreme", []) == ("extreme", Difficulty.EXTREME)


def test_third_high_in_window_is_downgraded():
    recent = ["high", "normal", "extreme", "normal", "low", "normal"]
    assert difficulty_for("high", recent) == ("normal", Difficulty.MODERATE)
    assert difficulty_for("extreme", recent) == ("high", Difficulty.HARD)


def test_only_last_six_count():
    recent = ["high", "high", "normal", "normal", "normal", "normal", "normal", "normal"]
    assert difficulty_for("high", recent) == ("high", Difficulty.HARD)
```

Append to `tests/test_narration.py`:

```python
async def test_pending_roll_carries_stakes_difficulty_and_dc(tmp_path):
    session = _session_with_character()
    client = _fake_client("You eye the ledge.", tool="request_roll", tool_args={
        "player_id": "p1", "attribute": "reflexes", "skill": "athletics", "stakes": "high", "reason": "leap"})
    await _call(session, client, "p1", {"text": "I leap."}, tmp_path, tts_backend=FakeTTSBackend())
    pending = session.pending_rolls["p1"]
    assert (pending["stakes"], pending["difficulty"], pending["dc"]) == ("high", "hard", 12)
    assert session.recent_stakes == ["high"]


async def test_capped_high_becomes_moderate(tmp_path):
    session = _session_with_character()
    session.recent_stakes = ["high", "high"]
    client = _fake_client("You eye the ledge.", tool="request_roll", tool_args={
        "player_id": "p1", "attribute": "reflexes", "skill": "athletics", "stakes": "high", "reason": "leap"})
    await _call(session, client, "p1", {"text": "I leap."}, tmp_path, tts_backend=FakeTTSBackend())
    pending = session.pending_rolls["p1"]
    assert (pending["stakes"], pending["difficulty"], pending["dc"]) == ("high", "moderate", 9)
    assert session.recent_stakes[-1] == "normal"


def test_old_pending_roll_with_only_difficulty_still_resolves():
    from server.narration import resolve_roll
    session = _session_with_character()
    session.pending_rolls["p1"] = {"player_id": "p1", "attribute": "reflexes", "skill": "athletics",
                                   "difficulty": "hard", "reason": "leap", "dc": 12, "name": "Rook"}
    rolled = resolve_roll(session, "p1")
    assert rolled["dc"] == 12
```

Append to `tests/test_persistence.py`:

```python
def test_recent_stakes_round_trip_and_default(tmp_path):
    import json
    from engine.persistence import JSONFileSessionStore
    from engine.session import Session
    store = JSONFileSessionStore(tmp_path)
    s = Session(session_id="s1", recent_stakes=["high", "normal"])
    store.save(s)
    assert store.load("s1").recent_stakes == ["high", "normal"]
    data = json.loads((tmp_path / "s1.json").read_text())
    del data["recent_stakes"]
    (tmp_path / "s1.json").write_text(json.dumps(data))
    assert store.load("s1").recent_stakes == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_difficulty.py tests/test_narration.py tests/test_persistence.py -q`
Expected: FAIL (`difficulty_for` missing, `stakes` rejected, `recent_stakes` unknown).

- [ ] **Step 3: Implement**

`ruleset/difficulty.py`, append:

```python
STAKES: dict[str, Difficulty] = {
    "low": Difficulty.EASY,
    "normal": Difficulty.MODERATE,
    "high": Difficulty.HARD,
    "extreme": Difficulty.EXTREME,
}
_CAP_WINDOW = 6
_CAP_HIGH = 2
_DOWNGRADE = {"high": "normal", "extreme": "high"}


def difficulty_for(stakes: str, recent: list[str]) -> tuple[str, Difficulty]:
    # Phase 18: the model rates stakes; the engine caps how often they run hot,
    # because qwen3:8b picked Hard on 13/13 risky rolls whatever the prompt said.
    window = recent[-_CAP_WINDOW:]
    if stakes in _DOWNGRADE and sum(s in ("high", "extreme") for s in window) >= _CAP_HIGH:
        stakes = _DOWNGRADE[stakes]
    return stakes, STAKES[stakes]
```

`engine/session.py`, add after `pending_world_events`:

```python
    # Phase 18: effective stakes of recent rolls, for the "high" cap.
    recent_stakes: list[str] = field(default_factory=list)
```

`engine/persistence.py` `load`, add to the `Session(...)` call:

```python
            recent_stakes=data.get("recent_stakes", []),
```

`narrator/tools.py` `RequestRoll`: replace the `difficulty` field with

```python
    stakes: Literal["low", "normal", "high", "extreme"]
```

and `_execute_request_roll`:

```python
def _execute_request_roll(session: Session, tool: RequestRoll) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    difficulty = STAKES[tool.stakes].name.lower()
    return roll_check(session.characters[tool.player_id], tool.attribute, tool.skill, difficulty)
```

(import `STAKES` from `ruleset.difficulty`).

`server/narration.py` `_hold_roll`: import `difficulty_for` from `ruleset.difficulty`; replace the two `pending[...]` lines that set `dc` with:

```python
    pending = request.model_dump()
    effective, difficulty = difficulty_for(request.stakes, session.recent_stakes)
    session.recent_stakes = (session.recent_stakes + [effective])[-6:]
    pending["difficulty"] = difficulty.name.lower()
    pending["dc"] = difficulty.value
```

(`pending["stakes"]` is already present from `model_dump()`.)

`server/__main__.py`: replace `" Most risks are Moderate; Hard is for real danger; Extreme is rare."` with

```python
        " request_roll takes stakes, not difficulty: low (routine but uncertain), normal (most "
        "risks), high (real danger), extreme (desperate odds); the engine sets the difficulty."
```

and change the example in the roll sentence from `(stealth, hard)` to `(stealth, normal stakes)`.

Then update every existing test that sends `request_roll` args with `"difficulty"` per the Files list above.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ruleset/difficulty.py narrator/tools.py engine/session.py engine/persistence.py server/narration.py server/__main__.py tests/
git commit -m "feat(18): model rates stakes, engine sets difficulty with a high-stakes cap"
```

---

### Task 2: Backend `judge()` and the `think` option

**Files:**
- Modify: `narrator/client.py`, `narrator/anthropic_backend.py`, `narrator/openai_compat_backend.py`
- Test: `tests/test_narrator_client.py`, `tests/test_anthropic_backend.py`, `tests/test_openai_compat_backend.py`

**Interfaces:**
- Produces: `NarratorBackend.judge(self, messages: list[dict], schema: dict) -> dict` on all three backends. `NarratorClient(..., judge_fn=None, think: bool | None = None)`. A `NarratorClient` built with an injected `chat_fn` and no `judge_fn` uses a no-op judge that answers `"none"` for enum fields and `False` for booleans (so existing scripted tests see no referee effects).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narrator_client.py`:

```python
import json as _json

_SCHEMA = {"type": "object", "properties": {
    "human_moment": {"type": "string", "enum": ["none", "small", "big"]},
    "gig_paid_out": {"type": "boolean"}}, "required": ["human_moment", "gig_paid_out"], "additionalProperties": False}


async def test_judge_passes_schema_and_returns_parsed_json():
    calls = []
    async def judge_fn(*, model, messages, format):
        calls.append(format)
        return {"message": {"content": _json.dumps({"human_moment": "big", "gig_paid_out": True})}}
    async def chat_fn(**kw): raise AssertionError("not used")
    client = NarratorClient(chat_fn=chat_fn, judge_fn=judge_fn)
    assert await client.judge([{"role": "user", "content": "x"}], _SCHEMA) == {"human_moment": "big", "gig_paid_out": True}
    assert calls == [_SCHEMA]


async def test_scripted_client_without_judge_fn_gets_a_noop_judge():
    async def chat_fn(**kw): raise AssertionError("not used")
    client = NarratorClient(chat_fn=chat_fn)
    assert await client.judge([], _SCHEMA) == {"human_moment": "none", "gig_paid_out": False}


async def test_default_judge_sends_think_false_and_zero_temperature():
    client = NarratorClient()
    seen = {}
    class _Fake:
        async def chat(self, **kw):
            seen.update(kw)
            return {"message": {"content": "{}"}}
    client._client = _Fake()
    await client.judge([], {"type": "object", "properties": {}, "required": []})
    assert seen["think"] is False
    assert seen["options"]["temperature"] == 0 and seen["options"]["num_predict"] == 80


async def test_think_option_reaches_narrator_chat_only_when_set():
    seen = []
    class _Fake:
        async def chat(self, **kw):
            seen.append(kw)
            return {"message": {"content": _json.dumps({"narration": [{"speaker": "narrator", "text": "x"}], "tool_call": {"tool": None}})}}
    for think, expected_present in ((None, False), (False, True)):
        client = NarratorClient(think=think)
        client._client = _Fake()
        await client.respond([{"role": "user", "content": "x"}])
        assert ("think" in seen[-1]) is expected_present
    assert seen[-1]["think"] is False


def test_create_narrator_backend_reads_nightwire_think(monkeypatch):
    from narrator.client import create_narrator_backend
    monkeypatch.setenv("NARRATOR_BACKEND", "ollama")
    monkeypatch.setenv("NIGHTWIRE_THINK", "off")
    assert create_narrator_backend().think is False
    monkeypatch.setenv("NIGHTWIRE_THINK", "on")
    assert create_narrator_backend().think is True
    monkeypatch.delenv("NIGHTWIRE_THINK")
    assert create_narrator_backend().think is None
```

Append to `tests/test_anthropic_backend.py` (uses the file's `_FakeAnthropicClient`, `_tool_use_response`):

```python
async def test_judge_forces_a_tool_with_the_given_schema():
    schema = {"type": "object", "properties": {"gig_paid_out": {"type": "boolean"}}, "required": ["gig_paid_out"]}
    client = _FakeAnthropicClient(_tool_use_response({"gig_paid_out": True}))
    backend = AnthropicNarratorBackend(api_key="k", model="m", client=client)
    assert await backend.judge([{"role": "user", "content": "x"}], schema) == {"gig_paid_out": True}
    body = client.calls[0][1]
    assert body["tools"][0]["input_schema"] == schema
    assert body["temperature"] == 0
```

Append to `tests/test_openai_compat_backend.py` (use the file's fake client and `_chat_response` helper; adapt the constructor call to match the file's existing tests):

```python
async def test_judge_uses_json_schema_response_format():
    import json
    schema = {"type": "object", "properties": {"gig_paid_out": {"type": "boolean"}}, "required": ["gig_paid_out"]}
    client = _FakeOpenAIClient(_chat_response(json.dumps({"gig_paid_out": False})))
    backend = OpenAICompatNarratorBackend(base_url="http://x", model="m", client=client)
    assert await backend.judge([{"role": "user", "content": "x"}], schema) == {"gig_paid_out": False}
    body = client.calls[0][1]
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert body["temperature"] == 0
```

(If the fake class in that file has a different name, use it — read the file's top first.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narrator_client.py tests/test_anthropic_backend.py tests/test_openai_compat_backend.py -q`
Expected: FAIL (`judge` / `think` / `judge_fn` missing).

- [ ] **Step 3: Implement**

`narrator/client.py`:

- Add `judge` to the `NarratorBackend` protocol:

```python
    async def judge(self, messages: list[dict], schema: dict) -> dict: ...
```

- Module-level helper:

```python
async def _noop_judge(*, model: str, messages: list[dict], format: dict) -> dict:
    # Scripted clients (tests, UI checks) get a referee that never changes state.
    answer = {k: ("none" if "enum" in v else False) for k, v in format.get("properties", {}).items()}
    return {"message": {"content": json.dumps(answer)}}
```

(add `import json` if missing).

- `NarratorClient.__init__`: add parameters `judge_fn: Callable[..., Awaitable[dict]] | None = None` and `think: bool | None = None`; set `self.think = think` and

```python
        self._judge_fn = judge_fn or (_noop_judge if chat_fn is not None else self._default_judge)
```

(place it next to where `self._chat_fn` is assigned, after `self._client` exists).

- `_default_chat`: pass `think` only when set:

```python
        kwargs = {"think": self.think} if self.think is not None else {}
        return await self._client.chat(
            model=model,
            messages=messages,
            format=format,
            options={"temperature": 0.3, "num_ctx": self.num_ctx},
            **kwargs,
        )
```

- Add:

```python
    async def _default_judge(self, *, model: str, messages: list[dict], format: dict) -> dict:
        return await self._client.chat(
            model=model, messages=messages, format=format, think=False,
            options={"temperature": 0, "num_predict": 80, "num_ctx": self.num_ctx},
        )

    async def judge(self, messages: list[dict], schema: dict) -> dict:
        response = await self._judge_fn(model=self.model, messages=messages, format=schema)
        return json.loads(response["message"]["content"])
```

- `create_narrator_backend`, ollama branch:

```python
    if backend == "ollama":
        think_env = os.environ.get("NIGHTWIRE_THINK", "").strip().lower()
        think = {"on": True, "off": False}.get(think_env)
        return NarratorClient(model=os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b"), think=think)
```

`narrator/anthropic_backend.py`, add:

```python
    async def judge(self, messages: list[dict], schema: dict) -> dict:
        body = {
            "model": self.model,
            "max_tokens": 200,
            "temperature": 0,
            "messages": messages,
            "tools": [{"name": "referee", "description": "Answer every referee question.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": "referee"},
        }
        result = await self._client.post(_API_URL, json=body, headers=self._headers())
        result.raise_for_status()
        tool_use = next((b for b in result.json().get("content", []) if b.get("type") == "tool_use"), None)
        if tool_use is None:
            raise ValueError("Anthropic referee response had no tool_use block")
        return tool_use["input"]
```

`narrator/openai_compat_backend.py`, add:

```python
    async def judge(self, messages: list[dict], schema: dict) -> dict:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "referee", "schema": schema}},
        }
        result = await self._client.post(f"{self.base_url}/chat/completions", json=body, headers=self._headers())
        result.raise_for_status()
        return json.loads(result.json()["choices"][0]["message"]["content"])
```

(add `import json` if missing).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/client.py narrator/anthropic_backend.py narrator/openai_compat_backend.py tests/test_narrator_client.py tests/test_anthropic_backend.py tests/test_openai_compat_backend.py
git commit -m "feat(18): judge() on narrator backends and the NIGHTWIRE_THINK option"
```

---

### Task 3: The referee module

**Files:**
- Create: `narrator/referee.py`
- Test: `tests/test_referee.py`

**Interfaces:**
- Consumes: `judge()` (Task 2); engine functions `change_humanity` (engine/chrome.py), `repossess`, `pay_installment`, `unthrottle`, `new_shell`, `SHELL`, `repo_target_name` (engine/debt.py); `is_tsukumogami` (engine/character.py); `CHROME` (ruleset/cyberware.py).
- Produces: `build_questions(session, player_id) -> dict[str, str]`, `build_schema(questions) -> dict`, `validate_verdict(verdict, questions) -> None` (raises ValueError), `apply_verdict(session, player_id, verdict) -> None`, `async run_referee(session, client, player_id, action_text, narration_text) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_referee.py`:

```python
import json

import pytest

from engine.character import CharacterSheet
from engine.chrome import install_chrome
from engine.debt import SHELL
from engine.session import Session
from narrator.referee import apply_verdict, build_questions, build_schema, run_referee, validate_verdict


def _session(**kw) -> Session:
    s = Session(session_id="s1")
    defaults = dict(player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"body": 12}, humanity=50)
    defaults.update(kw)
    s.characters["p1"] = CharacterSheet(**defaults)
    return s


def test_human_with_no_debt_is_only_asked_about_human_moments():
    assert list(build_questions(_session(), "p1")) == ["human_moment"]


def test_conditional_questions_follow_state():
    s = _session(lifepath="tsukumogami", installments_owed=4, pending_repo="kagerou", throttled="kagerou")
    assert set(build_questions(s, "p1")) == {"human_moment", "acted_as_machine", "gave_up_repo_item",
                                             "gig_paid_out", "hara_unlocked_chrome"}
    bodiless = _session(lifepath="tsukumogami", installments_owed=4, bodiless=True)
    assert set(build_questions(bodiless, "p1")) == {"human_moment", "acted_as_machine", "got_new_shell"}


def test_schema_requires_every_question():
    schema = build_schema({"human_moment": "q", "gig_paid_out": "q"})
    assert schema["required"] == ["human_moment", "gig_paid_out"]
    assert schema["properties"]["human_moment"]["enum"] == ["none", "small", "big"]
    assert schema["properties"]["gig_paid_out"]["type"] == "boolean"
    assert schema["additionalProperties"] is False


def test_validate_rejects_missing_or_wrong_types():
    q = {"human_moment": "q", "gig_paid_out": "q"}
    validate_verdict({"human_moment": "small", "gig_paid_out": False}, q)
    for bad in ({"human_moment": "small"}, {"human_moment": "huge", "gig_paid_out": False},
                {"human_moment": "small", "gig_paid_out": "yes"}):
        with pytest.raises(ValueError):
            validate_verdict(bad, q)


def test_human_moment_gains_and_machine_act_loses():
    s = _session()
    apply_verdict(s, "p1", {"human_moment": "big"})
    assert s.characters["p1"].humanity == 54
    t = _session(lifepath="tsukumogami", humanity=30)
    apply_verdict(t, "p1", {"human_moment": "small", "acted_as_machine": "big"})
    assert t.characters["p1"].humanity == 28
    assert "[selfhood: -2]" in t.log


def test_none_and_false_change_nothing():
    s = _session(installments_owed=4)
    apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": False})
    assert s.characters["p1"].humanity == 50 and s.characters["p1"].installments_owed == 4 and s.log == []


def test_gave_up_repo_item_repossesses_with_torite_log():
    s = _session()
    install_chrome(s.characters["p1"], "kagerou")
    s.characters["p1"].pending_repo = "kagerou"
    apply_verdict(s, "p1", {"human_moment": "none", "gave_up_repo_item": True, "gig_paid_out": False})
    assert "kagerou" not in s.characters["p1"].chrome
    assert "[torite: Saeko's crew took Rook's Kagerou]" in s.log


def test_shell_repo_logs_the_drop():
    s = _session(name="Hachi", lifepath="tsukumogami", humanity=30, installments_owed=4, pending_repo=SHELL)
    apply_verdict(s, "p1", {"human_moment": "none", "acted_as_machine": "none", "gave_up_repo_item": True, "gig_paid_out": False})
    assert s.characters["p1"].bodiless
    assert "[torite: Saeko's crew took Hachi's shell - Hachi drops into the nearest machine]" in s.log


def test_repo_and_unthrottle_run_before_payment():
    s = _session()
    c = s.characters["p1"]
    install_chrome(c, "kagerou")
    c.throttled = c.pending_repo = "kagerou"
    apply_verdict(s, "p1", {"human_moment": "none", "gave_up_repo_item": True, "gig_paid_out": True,
                            "hara_unlocked_chrome": False})
    assert "kagerou" not in c.chrome and c.installments_owed == 4


def test_unthrottle_adds_hara_objective_once():
    s = _session()
    c = s.characters["p1"]
    install_chrome(c, "kagerou")
    for _ in range(2):
        c.throttled = "kagerou"
        apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": False, "hara_unlocked_chrome": True})
    assert c.throttled is None
    assert s.active_objectives.count("Owe Old Hara a favor") == 1


def test_new_shell_wakes_them():
    s = _session(name="Hachi", lifepath="tsukumogami", bodiless=True)
    apply_verdict(s, "p1", {"human_moment": "none", "acted_as_machine": "none", "got_new_shell": True})
    assert not s.characters["p1"].bodiless
    assert "[utsusemi: Hachi wakes in a new shell]" in s.log


def test_gig_paid_out_pays_one():
    s = _session(installments_owed=4)
    apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": True})
    assert s.characters["p1"].installments_owed == 3


class _Client:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []
    async def judge(self, messages, schema):
        self.calls.append((messages, schema))
        if self.error:
            raise self.error
        return self.answer


async def test_run_referee_applies_a_valid_verdict_and_sends_context():
    s = _session(installments_owed=4)
    client = _Client({"human_moment": "small", "gig_paid_out": True})
    await run_referee(s, client, "p1", "I finish Arakawa's job.", "Arakawa pays you in cash.")
    assert s.characters["p1"].humanity == 52 and s.characters["p1"].installments_owed == 3
    prompt = json.dumps(client.calls[0][0])
    assert "Arakawa pays you in cash." in prompt and "owes 4" in prompt


async def test_run_referee_failure_logs_and_changes_nothing():
    for client in (_Client(error=ValueError("bad json")), _Client({"human_moment": "small"})):
        s = _session(installments_owed=4)
        await run_referee(s, client, "p1", "a", "b")
        assert s.characters["p1"].humanity == 50
        assert any(line.startswith("[referee error: ") for line in s.log)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_referee.py -q`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Implement `narrator/referee.py`**

```python
"""Phase 18 referee: a small required-field yes/no pass after narration that
decides the state changes qwen3:8b never volunteered as optional tool fields.
See docs/superpowers/specs/2026-10-28-narrator-reliability-18-design.md."""

from engine.character import is_tsukumogami
from engine.chrome import change_humanity
from engine.debt import SHELL, new_shell, pay_installment, repo_target_name, repossess, unthrottle
from engine.session import Session
from ruleset.cyberware import CHROME

_LEVELS = ["none", "small", "big"]
_AMOUNT = {"none": 0, "small": 2, "big": 4}
_LEVEL_FIELDS = ("human_moment", "acted_as_machine")
_HARA_OBJECTIVE = "Owe Old Hara a favor"
_SYSTEM = (
    "You are a strict referee for a tabletop RPG. Read the player's action and the narration, "
    "then answer each question about what actually happened in the narration. "
    "When unsure, answer none or false."
)


def build_questions(session: Session, player_id: str) -> dict[str, str]:
    c = session.characters[player_id]
    name = c.name
    questions = {
        "human_moment": f"none/small/big: did {name} share a genuinely human moment (a kindness, a shared meal, "
                        "being thanked, keeping a promise, choosing restraint)?",
    }
    if is_tsukumogami(c):
        questions["acted_as_machine"] = (f"none/small/big: did {name} act as a pure machine (cold calculation, "
                                         "following an owner's script, treating people as inputs)?")
    if c.pending_repo:
        questions["gave_up_repo_item"] = (f"true/false: did {name} hand over or lose their "
                                          f"{repo_target_name(c.pending_repo)} to the repo crew?")
    if c.installments_owed > 0 and not c.bodiless:
        questions["gig_paid_out"] = f"true/false: did {name} get paid for finished work?"
    if c.bodiless:
        questions["got_new_shell"] = f"true/false: did {name} get a new utsusemi shell?"
    if c.throttled:
        questions["hara_unlocked_chrome"] = (f"true/false: did Old Hara unlock {name}'s throttled "
                                             f"{CHROME[c.throttled].name}?")
    return questions


def build_schema(questions: dict[str, str]) -> dict:
    properties = {
        k: ({"type": "string", "enum": _LEVELS} if k in _LEVEL_FIELDS else {"type": "boolean"})
        for k in questions
    }
    return {"type": "object", "properties": properties, "required": list(questions), "additionalProperties": False}


def validate_verdict(verdict: dict, questions: dict[str, str]) -> None:
    if not isinstance(verdict, dict) or set(verdict) != set(questions):
        raise ValueError(f"referee answered {sorted(verdict) if isinstance(verdict, dict) else verdict!r}, "
                         f"expected {sorted(questions)}")
    for key, value in verdict.items():
        ok = value in _LEVELS if key in _LEVEL_FIELDS else isinstance(value, bool)
        if not ok:
            raise ValueError(f"bad referee value for {key}: {value!r}")


def _state_line(session: Session, player_id: str) -> str:
    c = session.characters[player_id]
    parts = [f"{c.name}: {'tsukumogami' if is_tsukumogami(c) else 'human'}"]
    if c.installments_owed > 0:
        parts.append(f"owes {c.installments_owed}")
    if c.pending_repo:
        parts.append(f"repo pending: {repo_target_name(c.pending_repo)}")
    if c.throttled:
        parts.append(f"throttled: {CHROME[c.throttled].name}")
    if c.bodiless:
        parts.append("bodiless")
    return ", ".join(parts)


def _messages(session, player_id, action_text, narration_text, questions) -> list[dict]:
    lines = "\n".join(f"- {k}: {q}" for k, q in questions.items())
    user = (f"State: {_state_line(session, player_id)}\nAction: {action_text}\n"
            f"Narration: {narration_text}\nQuestions:\n{lines}")
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def apply_verdict(session: Session, player_id: str, verdict: dict) -> None:
    c = session.characters[player_id]
    name = c.name
    delta = _AMOUNT[verdict.get("human_moment", "none")] - _AMOUNT[verdict.get("acted_as_machine", "none")]
    if delta:
        before = c.humanity
        session.pending_world_events.extend(change_humanity(c, delta))
        if is_tsukumogami(c) and c.humanity != before:
            session.log.append(f"[selfhood: {c.humanity - before:+d}]")
    # Same order as 17b's tool path: repo and unthrottle before payment, which clears both.
    if verdict.get("gave_up_repo_item") and c.pending_repo:
        removed = repossess(c)
        if removed == SHELL:
            session.log.append(f"[torite: Saeko's crew took {name}'s shell - {name} drops into the nearest machine]")
        else:
            session.log.append(f"[torite: Saeko's crew took {name}'s {CHROME[removed].name}]")
    if verdict.get("hara_unlocked_chrome") and c.throttled:
        unthrottle(c)
        if _HARA_OBJECTIVE not in session.active_objectives:
            session.active_objectives.append(_HARA_OBJECTIVE)
    if verdict.get("got_new_shell") and c.bodiless:
        new_shell(c)
        session.log.append(f"[utsusemi: {name} wakes in a new shell]")
    if verdict.get("gig_paid_out") and c.installments_owed > 0:
        pay_installment(c, 1)


async def run_referee(session: Session, client, player_id: str, action_text: str, narration_text: str) -> None:
    if player_id not in session.characters:
        return
    questions = build_questions(session, player_id)
    try:
        verdict = await client.judge(_messages(session, player_id, action_text, narration_text, questions),
                                     build_schema(questions))
        validate_verdict(verdict, questions)
    except Exception as e:  # a failed referee must never break the turn
        session.log.append(f"[referee error: {e}]")
        return
    apply_verdict(session, player_id, verdict)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/referee.py tests/test_referee.py
git commit -m "feat(18): referee module - per-turn questions, schema, verdict application"
```

---

### Task 4: The narrator gives up the referee's fields

**Files:**
- Modify: `narrator/tools.py`, `server/__main__.py`
- Test: `tests/test_narrator_tools.py`, `tests/test_server_main.py`

**Interfaces:**
- Consumes: nothing new. After this task the referee (Task 3) is the only code path that triggers humanity/selfhood gains and losses outside chrome and overclock, plus repossess, unthrottle, new_shell and installment payments.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narrator_tools.py`:

```python
@pytest.mark.parametrize("field", ["humanity_delta", "selfhood_loss", "repossess", "installments_paid", "new_shell", "unthrottle"])
def test_narrator_can_no_longer_set_referee_fields(field):
    from pydantic import ValidationError
    from narrator.tools import ApplyCharacterUpdate
    value = True if field in ("repossess", "new_shell", "unthrottle") else 1
    with pytest.raises(ValidationError):
        ApplyCharacterUpdate(player_id="p1", **{field: value})
```

Append to `tests/test_server_main.py`:

```python
def test_system_prompt_no_longer_tells_narrator_to_set_referee_fields():
    from server.__main__ import build_system_prompt
    prompt = build_system_prompt()
    for field in ("humanity_delta", "selfhood_loss", "installments_paid", "new_shell", "unthrottle", "set repossess"):
        assert field not in prompt
    for staging in ("Arakawa", "Saeko", "Old Hara", "bodiless", "Appliance"):
        assert staging in prompt
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narrator_tools.py tests/test_server_main.py -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

`narrator/tools.py`:
- Remove the fields `humanity_delta`, `installments_paid`, `repossess`, `unthrottle`, `selfhood_loss`, `new_shell` (and their comments) from `ApplyCharacterUpdate`.
- In `_execute_apply_character_update`, remove: the validate-before-mutation checks for those fields, the humanity/selfhood block, the repossess block, the unthrottle block, the new_shell block and the payment line. Keep health, armor, points, conditions and inventory exactly as they are.
- Remove imports that become unused (`change_humanity`, `pay_installment`, `repossess`, `unthrottle`, `new_shell`, `SHELL`, `is_tsukumogami`, and `CHROME` if no longer used — check each with a grep before deleting).

`server/__main__.py`, rewrite the sentences that instruct setting these fields so they only describe staging. Replace exactly:
- `"For therapy or a real human moment (a friend, a meal, choosing restraint), you may set apply_character_update's humanity_delta to 1-5; never for routine scenes."` → `"Give characters real human moments - a friend, a meal, choosing restraint - when the story allows."`
- `"when a gig pays out, set apply_character_update's installments_paid to 1."` → `"when a gig pays out, say so plainly."`
- `"stage Saeko Kirigaya's crew; set repossess to true only if the character loses or gives the chrome up."` → `"stage Saeko Kirigaya's crew; the character may fight, flee, pay or give the chrome up."`
- `"he can - set unthrottle to true - but they'll owe him."` → `"he can, but they'll owe him."`
- In the tsukumogami sentence: replace `"For a tsukumogami, humanity_delta 1-5 is a selfhood gain for human moments (being thanked, sharing food, keeping a promise, an unprompted kindness, a choice made for no reason); set selfhood_loss 1-5 when they act as a pure machine (cold calculation, following an owner's script, treating people as inputs). Never for routine scenes."` with `"A tsukumogami grows through human moments (being thanked, sharing food, keeping a promise, an unprompted kindness) and fades when acting as a pure machine."`; replace `"set new_shell to true when they get one."` with `"narrate it plainly when they get one."`

The exact current wording may be split across string literals; edit the literal pieces so the resulting prompt text matches the replacements above. Read the whole `rules` string first.

Then delete or rewrite existing tests in `tests/test_narrator_tools.py` and `tests/test_server_main.py` that exercise the removed fields through `apply_character_update` (the 17b/17c installments/repossess/unthrottle/selfhood/new_shell tool tests, and prompt tests asserting `selfhood_loss`/`new_shell` text). Their behaviour is now covered by `tests/test_referee.py` (Task 3) and `tests/test_debt.py`; delete a test only when an equivalent referee or debt test exists, otherwise port it to call `apply_verdict` in `tests/test_referee.py`. List every deleted or ported test in your report.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/tools.py server/__main__.py tests/
git commit -m "feat(18): narrator stages state scenes; referee owns the state fields"
```

---

### Task 5: Turn wiring — voice filter, redo, referee

**Files:**
- Modify: `server/narration.py` (`_hold_roll`, `_run_turn`)
- Test: `tests/test_narration.py`

**Interfaces:**
- Consumes: `run_referee(session, client, player_id, action_text, narration_text)` (Task 3); `NarratorClient.judge` / no-op judge on scripted clients (Task 2).
- Produces: `_hold_roll(...) -> str | None` (the refusal message, or None); the redo and voice-filter behaviour.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narration.py`:

```python
def _scripted_client(responses: list[dict], judge_answers: list[dict] | None = None, seen: list | None = None) -> NarratorClient:
    state = {"i": 0, "j": 0}

    async def chat_fn(*, model, messages, format):
        if seen is not None:
            seen.append(messages)
        payload = responses[min(state["i"], len(responses) - 1)]
        state["i"] += 1
        return {"message": {"content": json.dumps(payload)}}

    async def judge_fn(*, model, messages, format):
        if judge_answers is None:
            answer = {k: ("none" if "enum" in v else False) for k, v in format["properties"].items()}
        else:
            answer = judge_answers[state["j"]]
            state["j"] += 1
        return {"message": {"content": json.dumps(answer)}}

    async def generate_fn(**kwargs):
        pass

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn, judge_fn=judge_fn)


def _say(text, tool=None, tool_args=None, speaker="narrator"):
    tool_call = {"tool": tool} if tool is None else {"tool": tool, "tool_args": tool_args}
    return {"narration": [{"speaker": speaker, "text": text}], "tool_call": tool_call}


async def test_segment_spoken_as_the_player_character_is_dropped(tmp_path):
    session = _session_with_character()
    client = _scripted_client([{"narration": [
        {"speaker": "Rook", "text": "I'll take the job."},
        {"speaker": "Mama Sato", "text": "Eat first, child."},
    ], "tool_call": {"tool": None}}])
    await _call(session, client, "p1", {"text": "I sit down."}, tmp_path, tts_backend=FakeTTSBackend())
    assert "Rook: I'll take the job." not in session.log
    assert "Mama Sato: Eat first, child." in session.log
    assert "[voice filtered: Rook]" in session.log


async def test_refused_roll_redoes_the_turn_once_with_the_engine_fact(tmp_path):
    session = _session_with_character()
    session.characters["p1"].lifepath = "tsukumogami"
    session.characters["p1"].bodiless = True
    seen = []
    climb = {"player_id": "p1", "attribute": "body", "skill": "athletics", "stakes": "normal", "reason": "climb"}
    client = _scripted_client([
        _say("You haul yourself up the fire escape.", "request_roll", climb),
        _say("The vending machine's speaker crackles: you have no hands to climb with."),
    ], seen=seen)
    await _call(session, client, "p1", {"text": "I climb the fire escape."}, tmp_path, tts_backend=FakeTTSBackend())
    assert "You haul yourself up the fire escape." not in session.log
    assert "The vending machine's speaker crackles: you have no hands to climb with." in session.log
    assert session.log.count("p1: I climb the fire escape.") == 1
    assert any(line.startswith("[redo: Rook has no body]") for line in session.log)
    assert "Engine: Rook has no body. That does not happen" in seen[1][-1]["content"]
    assert len(seen) == 2


async def test_redo_does_not_loop(tmp_path):
    session = _session_with_character()
    session.characters["p1"].bodiless = True
    climb = {"player_id": "p1", "attribute": "body", "skill": "athletics", "stakes": "normal", "reason": "climb"}
    seen = []
    client = _scripted_client([_say("You climb.", "request_roll", climb)], seen=seen)
    await _call(session, client, "p1", {"text": "I climb."}, tmp_path, tts_backend=FakeTTSBackend())
    assert len(seen) == 2
    assert sum(line.startswith("[redo: ") for line in session.log) == 1
    assert "p1" not in session.pending_rolls


async def test_redo_removes_the_discarded_audio(tmp_path):
    session = _session_with_character()
    session.characters["p1"].bodiless = True
    climb = {"player_id": "p1", "attribute": "body", "skill": "athletics", "stakes": "normal", "reason": "climb"}
    client = _scripted_client([_say("You climb.", "request_roll", climb), _say("You can't.")])
    store = await _call(session, client, "p1", {"text": "I climb."}, tmp_path, tts_backend=FakeTTSBackend())
    audio_lines = [l for l in session.log if l.startswith("[audio: ")]
    assert len(audio_lines) == 1
    files = list((store.directory / "audio" / session.session_id).glob("*.wav"))
    assert len(files) == 1


async def test_referee_runs_on_action_turns_and_applies(tmp_path):
    session = _session_with_character()
    session.characters["p1"].humanity = 50
    client = _scripted_client([_say("Mama Sato laughs and refills your bowl.")], judge_answers=[{"human_moment": "big"}])
    await _call(session, client, "p1", {"text": "I share a meal."}, tmp_path, tts_backend=FakeTTSBackend())
    assert session.characters["p1"].humanity == 54


async def test_referee_skipped_on_turn_that_opens_a_roll(tmp_path):
    session = _session_with_character()
    leap = {"player_id": "p1", "attribute": "reflexes", "skill": "athletics", "stakes": "normal", "reason": "leap"}
    client = _scripted_client([_say("You eye the ledge.", "request_roll", leap)], judge_answers=[])
    await _call(session, client, "p1", {"text": "I leap."}, tmp_path, tts_backend=FakeTTSBackend())
    assert "p1" in session.pending_rolls
    # judge_answers=[] makes any referee call fail, which run_referee would log.
    assert not any(line.startswith("[referee error") for line in session.log)


async def test_referee_runs_on_roll_resolution(tmp_path):
    from server.narration import handle_roll
    session = _session_with_character()
    session.characters["p1"].installments_owed = 3
    session.pending_rolls["p1"] = {"player_id": "p1", "attribute": "reflexes", "skill": "athletics", "stakes": "normal",
                                   "difficulty": "moderate", "reason": "the job", "dc": 9, "name": "Rook"}
    client = _scripted_client([_say("Arakawa counts out your pay.")],
                              judge_answers=[{"human_moment": "none", "gig_paid_out": True}])
    store = JSONFileSessionStore(tmp_path)
    await handle_roll(session, client, store, _UnusedImageBackend(), FakeTTSBackend(), "p1")
    assert session.characters["p1"].installments_owed == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration.py -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement in `server/narration.py`**

Import `run_referee` from `narrator.referee`.

`_hold_roll` returns the refusal message (still logging it):

```python
def _hold_roll(session: Session, player_id: str, tool_args: dict) -> str | None:
    tool_args["player_id"] = player_id
    try:
        request = RequestRoll(**tool_args)
    except (ValueError, TypeError) as e:
        session.log.append(f"[tool error: {e}]")
        return str(e)
    character = session.characters.get(player_id)
    if character is None:
        session.log.append(f"[tool error: unknown player_id: {player_id!r}]")
        return f"unknown player_id: {player_id!r}"
    if character.bodiless and SKILLS[request.skill].governing_attribute in (Attribute.BODY, Attribute.REFLEXES):
        message = f"{character.name} has no body"
        session.log.append(f"[tool error: {message}]")
        return message
    ...  # pending/difficulty_for code from Task 1, unchanged
    return None
```

Split `_run_turn`'s narration logging and tool execution into helpers, and add the voice filter, redo and referee:

```python
def _is_player_voice(session: Session, speaker: str) -> bool:
    s = speaker.strip().lower()
    return any(s in (c.name.strip().lower(), c.player_id.strip().lower()) for c in session.characters.values())


async def _log_narration(session, response, store, tts_backend) -> tuple[list[Path], str]:
    """Logs and voices the response's segments; returns (audio files written, narration text)."""
    audio_paths: list[Path] = []
    texts: list[str] = []
    for i, segment in enumerate(response.narration):
        if segment.speaker != "narrator" and _is_player_voice(session, segment.speaker):
            session.log.append(f"[voice filtered: {segment.speaker}]")
            continue
        texts.append(segment.text)
        # ... the existing per-segment log + TTS body, unchanged, except:
        #     after output_path.write_bytes(audio_bytes): audio_paths.append(output_path)
    return audio_paths, " ".join(texts)


def _apply_tool(session, response, player_id, allow_roll) -> str | None:
    """Runs the narrator's tool call; returns the refusal message if the engine refused it."""
    if response.tool is None:
        return None
    tool_args = dict(response.tool_args)
    if response.tool == "request_roll":
        if allow_roll:
            return _hold_roll(session, player_id, tool_args)
        session.log.append("[tool error: no new rolls during a roll resolution]")
        return None
    try:
        result = execute_tool(session, response.tool, tool_args)
        session.log.append(f"[{response.tool}: {result}]")
        return None
    except (ValueError, TypeError) as e:
        session.log.append(f"[tool error: {e}]")
        return str(e)
```

(`Path` from `pathlib`. Keep the existing TTS body exactly; only add the `audio_paths.append` and the filter.)

New `_run_turn` body up to the image block:

```python
    shown_events = list(session.pending_world_events)
    messages = _build_messages(session, prompt_text, narrator_client.num_ctx)
    response = await narrator_client.respond(messages)
    del session.pending_world_events[:len(shown_events)]

    turn_start = len(session.log)
    if actor_line is not None:
        session.log.append(actor_line)
    audio_paths, narration_text = await _log_narration(session, response, store, tts_backend)
    refusal = _apply_tool(session, response, player_id, allow_roll)

    if refusal is not None and allow_roll:
        # Redo once (Phase 18): drop what was narrated and narrate again with the refusal as fact.
        for path in audio_paths:
            path.unlink(missing_ok=True)
        del session.log[turn_start:]
        session.pending_world_events[:0] = shown_events
        retry_prompt = f"{prompt_text}\n\nEngine: {refusal}. That does not happen - narrate the attempt failing or not being possible."
        messages = _build_messages(session, retry_prompt, narrator_client.num_ctx)
        response = await narrator_client.respond(messages)
        del session.pending_world_events[:len(shown_events)]
        if actor_line is not None:
            session.log.append(actor_line)
        session.log.append(f"[redo: {refusal}]")
        _, narration_text = await _log_narration(session, response, store, tts_backend)
        _apply_tool(session, response, player_id, allow_roll)  # a second refusal is only logged

    # Referee (Phase 18): not on the setup turn that opened a roll - the outcome isn't known yet.
    if player_id not in session.pending_rolls:
        await run_referee(session, narrator_client, player_id, prompt_text, narration_text)
```

The image block and compaction that follow stay as they are and use the final `response`.

Note: the original code deleted events with `del session.pending_world_events[:shown_events]` where `shown_events` was a count; it is now a copy of the list, so use `len(shown_events)`.

Existing tests: scripted `NarratorClient`s built without `judge_fn` get the no-op judge (Task 2), so the referee adds nothing for them. If an existing test fails only because it uses the Anthropic/OpenAI backend through `handle_action` and the referee now posts an extra request (producing a `[referee error: …]` line or an unexpected call count), update that test's assertion to account for the referee call and say so in your report. Do not change production code to special-case tests.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/narration.py tests/
git commit -m "feat(18): voice filter, redo refused turns once, referee after narration"
```

---

## Verification (controller, after the final review)

- **Live A/B** on `qwen3:8b` (GPU box `192.168.10.19`, 300 s client timeout), with `NIGHTWIRE_THINK` unset and then `off`:
  - human-moment turns (shared meal, being thanked) → referee gain;
  - a cold machine act as a tsukumogami → loss;
  - handing chrome, then the shell, to a pending repo crew → repossess;
  - an Arakawa job that pays → `installments_paid`;
  - 6+ risky actions → stakes and difficulty distribution;
  - a bodiless climb → redo, no success narration;
  - check every turn for a `[voice filtered:` line, and for player-voiced lines that got through.
  - Record referee latency, narrator time and JSON-error rate per think setting, plus n and errors.
- **Browser smoke:** a roll card still shows difficulty and DC.
- **Docs:** ROADMAP "18." entry before "### Candidate future phases", with the before/after table; set the `NIGHTWIRE_THINK` default recommendation in the README's configuration section if `off` wins.
