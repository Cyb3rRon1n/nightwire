# Nightwire Phase 6 (Text-to-Speech) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the narrator character-distinct spoken voices — the narrator/DM and each in-fiction speaker sound different — delivered per narration segment, with a local Kokoro backend primary and an OpenAI TTS hosted fallback selectable at startup.

**Architecture:** `NarratorResponse.narration` becomes a list of speaker-tagged segments instead of one free-text string (the same discriminated-field treatment `tool_call` already got). `server/narration.py`'s `handle_action` flattens each segment to a log line, synthesizes its audio through a swappable `TTSBackend` Protocol (mirroring `ImageBackend`), and appends an `[audio: path]` tag line — same bracket-tag delivery convention `[image: path]` already uses, so the frontend and `_build_messages`' existing log filter need zero changes. NPC voices have no persistent record to live on (only player `CharacterSheet`s exist), so a new `Session.speaker_voices` dict tracks a session-scoped, gender-aware, first-appearance voice assignment.

**Tech Stack:** Python 3.11+, Pydantic v2 (schema), httpx (backend HTTP calls), pytest + pytest-asyncio (existing test stack, unchanged).

**Spec:** `docs/superpowers/specs/2026-08-23-tts-narration-design.md`

## Global Constraints

- Every backend HTTP call goes through an injectable function parameter (constructor-level, defaulting to a real implementation) — the existing `FluxWorkerBackend` convention (`http_fn` override), so every backend is testable without real network calls.
- Fail-soft per unit of work: a single segment's synthesis failure must not drop the rest of the turn's audio or narration. Catch `(ValueError, TypeError, OSError)` only — matches `server/narration.py`'s existing image-error handling exactly.
- No new environment variables or config files — this codebase has none today (model names, ports, and backend choice are all constructor defaults / call-site literals in `server/__main__.py`). Backend selection stays a `build_app()`-time choice, not a runtime toggle.
- Kokoro voice IDs verified against `hexgrad/Kokoro-82M`'s own `VOICES.md` (Apache 2.0) on 2026-08-23. OpenAI voice IDs and the `/v1/audio/speech` request shape verified against OpenAI's own API docs the same day — OpenAI does **not** publish gender labels for its voices (only tonal descriptors), so `OpenAITTSBackend`'s voice bank deliberately leaves `gender` unset rather than inventing a label with no source.

---

## File Structure

```
narrator/
├── client.py            # MODIFY: NarrationSegment model, NarratorResponse.narration becomes list[NarrationSegment]
├── tts_backend.py        # NEW: VoiceOption, TTSBackend Protocol, KokoroBackend, OpenAITTSBackend
└── voice_assignment.py   # NEW: assign_voice() - session-scoped, gender-aware, first-appearance voice pick
engine/
└── session.py            # MODIFY: Session.speaker_voices field
server/
├── narration.py          # MODIFY: flatten segments to log lines; synthesize + tag audio per segment
├── app.py                 # MODIFY: create_app() gains tts_backend param, passed through to handle_action
└── __main__.py             # MODIFY: build_app() constructs a KokoroBackend and passes it through
tests/
├── test_narrator_client.py   # MODIFY: payload fixtures use segment lists; new segment-parsing tests
├── test_harness.py            # MODIFY: payload fixtures use segment lists
├── test_narration.py          # MODIFY: fixtures + new multi-segment / audio-tag tests
├── test_app.py                 # MODIFY: payload fixture + tts_backend wiring in the shared test client helper
├── test_session.py             # MODIFY: speaker_voices field test
├── test_tts_backend.py         # NEW
└── test_voice_assignment.py    # NEW
```

---

### Task 1: Narration becomes a list of speaker-tagged segments

**Files:**
- Modify: `narrator/client.py`
- Modify: `tests/test_narrator_client.py`
- Modify: `tests/test_harness.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Produces: `NarrationSegment(BaseModel)` — `speaker: str`, `gender: Literal["male", "female"] | None = None`, `text: str`. `NarratorResponse.narration: list[NarrationSegment]` (was `str`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_narrator_client.py`:

```python
@pytest.mark.asyncio
async def test_respond_parses_narration_as_a_list_of_segments():
    client = NarratorClient(
        chat_fn=_fake_chat_returning({
            "narration": [
                {"speaker": "narrator", "text": "The alley is quiet."},
                {"speaker": "Jax", "gender": "male", "text": "You're late, choom."},
            ],
            "tool_call": {"tool": None},
        }),
    )
    response = await client.respond([{"role": "user", "content": "I look around."}])
    assert len(response.narration) == 2
    assert response.narration[0].speaker == "narrator"
    assert response.narration[0].gender is None
    assert response.narration[0].text == "The alley is quiet."
    assert response.narration[1].speaker == "Jax"
    assert response.narration[1].gender == "male"
    assert response.narration[1].text == "You're late, choom."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_narrator_client.py::test_respond_parses_narration_as_a_list_of_segments -v`
Expected: FAIL (`narration` is currently typed `str`; a list payload fails Pydantic validation, or `response.narration[0]` raises since a string indexes to a character, not a segment)

- [ ] **Step 3: Implement the schema change**

In `narrator/client.py`, add `NarrationSegment` right above `NarratorResponse` (after the existing `ImageRequest` class), and change `NarratorResponse.narration`'s type:

```python
class NarrationSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    speaker: str
    gender: Literal["male", "female"] | None = None
    text: str


class NarratorResponse(BaseModel):
    narration: list[NarrationSegment]
    tool_call: ToolCall
    ...
```

(Only the `narration:` line's type changes — leave `tool_call`, `image_request`, and the `.tool`/`.tool_args` properties exactly as they are.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_narrator_client.py::test_respond_parses_narration_as_a_list_of_segments -v`
Expected: PASS

- [ ] **Step 5: Fix every existing test broken by the schema change**

Every other test in `tests/test_narrator_client.py` builds a payload with `"narration": "<some string>"` — that's no longer valid against the schema (a bare string doesn't parse as `list[NarrationSegment]`), so `client.respond(...)` will now raise `ValueError` on all of them. Replace every `"narration": "<TEXT>"` line in this file with `"narration": [{"speaker": "narrator", "text": "<TEXT>"}]`, and update the one direct string assertion. Concretely:

- `test_respond_returns_narration_only_when_no_tool_call`: change the payload's `"narration": "The alley is quiet."` to `"narration": [{"speaker": "narrator", "text": "The alley is quiet."}]`, and change the assertion `assert response.narration == "The alley is quiet."` to:
  ```python
  assert response.narration == [NarrationSegment(speaker="narrator", text="The alley is quiet.")]
  ```
  (add `NarrationSegment` to the `from narrator.client import ...` import line at the top of the file)
- `test_respond_returns_a_tool_call`: change `"narration": "You lunge for the ledge."` to `"narration": [{"speaker": "narrator", "text": "You lunge for the ledge."}]`
- `test_respond_rejects_a_tool_call_with_the_wrong_argument_shape`: change `"narration": "Combat breaks out!"` to `"narration": [{"speaker": "narrator", "text": "Combat breaks out!"}]`
- `test_respond_passes_the_structured_output_schema_to_chat_fn`: change `{"narration": "ok", "tool_call": {"tool": None}}` to `{"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}`
- `test_respond_prepends_the_system_prompt`: same change, `{"narration": "ok", "tool_call": {"tool": None}}` → `{"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}`
- `test_respond_raises_on_a_hallucinated_tool_name`: change `"narration": "You lunge for the ledge."` to `"narration": [{"speaker": "narrator", "text": "You lunge for the ledge."}]`
- `test_respond_parses_an_image_request`: change the payload's narration string to `"narration": [{"speaker": "narrator", "text": "The alley opens onto a rain-slicked plaza, neon bleeding into puddles."}]`
- `test_respond_image_request_defaults_to_none`: change `"narration": "The alley is quiet."` to `"narration": [{"speaker": "narrator", "text": "The alley is quiet."}]`

`test_respond_raises_on_malformed_model_output` and `test_unload_calls_generate_with_keep_alive_zero_and_no_prompt` don't touch `narration` — leave them as-is.

Now do the identical replacement in `tests/test_harness.py` (it never asserts on `.narration`'s content, only builds payloads) — change every one of these five lines:
- `"narration": "You reach for your pistol.",` → `"narration": [{"speaker": "narrator", "text": "You reach for your pistol."}],`
- `"narration": "You wander off.", "tool_call": {"tool": None},` → `"narration": [{"speaker": "narrator", "text": "You wander off."}], "tool_call": {"tool": None},`
- `"narration": "The street is quiet tonight.", "tool_call": {"tool": None},` → `"narration": [{"speaker": "narrator", "text": "The street is quiet tonight."}], "tool_call": {"tool": None},`
- `"narration": "ok", "tool_call": {"tool": None},` → `"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None},`
- `"narration": "You lunge for the ledge.",` → `"narration": [{"speaker": "narrator", "text": "You lunge for the ledge."}],`

And in `tests/test_app.py`, the one occurrence:
```python
"narration": "The alley is quiet.", "tool_call": {"tool": None},
```
becomes:
```python
"narration": [{"speaker": "narrator", "text": "The alley is quiet."}], "tool_call": {"tool": None},
```

- [ ] **Step 6: Run the full test suite to verify everything passes**

Run: `pytest tests/test_narrator_client.py tests/test_harness.py tests/test_app.py -v`
Expected: all PASS (`test_app.py`'s other tests don't reach the narrator at all, so they're unaffected)

- [ ] **Step 7: Commit**

```bash
git add narrator/client.py tests/test_narrator_client.py tests/test_harness.py tests/test_app.py
git commit -m "feat: narration becomes a list of speaker-tagged segments"
```

---

### Task 2: Flatten segments into the session log

**Files:**
- Modify: `server/narration.py`
- Modify: `tests/test_narration.py`

**Interfaces:**
- Consumes: `NarratorResponse.narration: list[NarrationSegment]` (Task 1)
- Produces: `handle_action` appends one log line per segment — `segment.text` if `segment.speaker == "narrator"`, else `f"{segment.speaker}: {segment.text}"`. (This task does not touch audio at all — that's Task 6.)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_narration.py` (uses the existing `_fake_client`, `_session_with_character`, `_call` helpers already in the file):

```python
@pytest.mark.asyncio
async def test_handle_action_logs_one_line_per_narration_segment(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([
        {"speaker": "narrator", "text": "The alley reeks of ozone."},
        {"speaker": "Jax", "gender": "male", "text": "You're late, choom."},
    ])

    await _call(session, client, "p1", {"text": "I check the alley."}, tmp_path)

    assert session.log == [
        "p1: I check the alley.",
        "The alley reeks of ozone.",
        "Jax: You're late, choom.",
    ]
```

This needs a new helper alongside `_fake_client` in `tests/test_narration.py` — add it right after `_fake_client`:

```python
def _fake_client_with_segments(segments: list[dict], tool: str | None = None, tool_args: dict | None = None) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        tool_call = {"tool": tool} if tool is None else {"tool": tool, "tool_args": tool_args or {}}
        return {"message": {"content": json.dumps({"narration": segments, "tool_call": tool_call})}}

    async def generate_fn(**kwargs):
        pass

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_narration.py::test_handle_action_logs_one_line_per_narration_segment -v`
Expected: FAIL — `handle_action` still does `session.log.append(response.narration)`, which now appends the whole list object (or raises, since `.append` on a Pydantic list field works but produces a log entry that isn't a string), not per-segment lines.

- [ ] **Step 3: Implement the flattening**

In `server/narration.py`, replace this line in `handle_action`:

```python
    session.log.append(response.narration)
```

with:

```python
    for segment in response.narration:
        line = segment.text if segment.speaker == "narrator" else f"{segment.speaker}: {segment.text}"
        session.log.append(line)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_narration.py::test_handle_action_logs_one_line_per_narration_segment -v`
Expected: PASS

- [ ] **Step 5: Update every existing test's payload to the segment-list shape**

`_fake_client` in `tests/test_narration.py` currently takes `narration: str` and emits `{"narration": narration, ...}`. Change it to wrap the string as a single narrator segment:

```python
def _fake_client(narration: str, tool: str | None = None, tool_args: dict | None = None, image_prompt: str | None = None) -> NarratorClient:
    async def chat_fn(*, model, messages, format):
        tool_call = {"tool": tool} if tool is None else {"tool": tool, "tool_args": tool_args or {}}
        payload = {"narration": [{"speaker": "narrator", "text": narration}], "tool_call": tool_call}
        if image_prompt is not None:
            payload["image_request"] = {"prompt": image_prompt}
        return {"message": {"content": json.dumps(payload)}}

    async def generate_fn(**kwargs):
        pass

    return NarratorClient(chat_fn=chat_fn, generate_fn=generate_fn)
```

Every existing test that calls `_fake_client("some text", ...)` keeps working unchanged — a single narrator-only segment flattens back to the exact same unprefixed log line as before, which is why `test_handle_action_appends_the_players_action_and_the_narration_to_the_log` and `test_handle_action_with_no_tool_call_only_logs_narration` (both assert exact `session.log == ["p1: ...", "The alley is quiet."]`-style lists) don't need any change to their assertions.

- [ ] **Step 6: Run the full narration test file**

Run: `pytest tests/test_narration.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add server/narration.py tests/test_narration.py
git commit -m "feat: flatten narration segments into speaker-tagged log lines"
```

---

### Task 3: `Session.speaker_voices`

**Files:**
- Modify: `engine/session.py`
- Modify: `tests/test_session.py`

**Interfaces:**
- Produces: `Session.speaker_voices: dict[str, str]` (default `{}`) — maps a speaker name to the voice ID assigned to them for this session.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_session.py`:

```python
def test_session_speaker_voices_defaults_to_empty_and_is_independent_per_instance():
    session_a = Session(session_id="a")
    session_b = Session(session_id="b")

    assert session_a.speaker_voices == {}
    session_a.speaker_voices["Jax"] = "am_adam"

    assert session_b.speaker_voices == {}
```

(Check the top of `tests/test_session.py` for the existing `from engine.session import Session` import — reuse it, don't add a duplicate.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session.py::test_session_speaker_voices_defaults_to_empty_and_is_independent_per_instance -v`
Expected: FAIL with `AttributeError: 'Session' object has no attribute 'speaker_voices'`

- [ ] **Step 3: Implement**

In `engine/session.py`, add the field after `active_objectives`:

```python
    active_objectives: list[str] = field(default_factory=list)
    speaker_voices: dict[str, str] = field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_session.py::test_session_speaker_voices_defaults_to_empty_and_is_independent_per_instance -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/session.py tests/test_session.py
git commit -m "feat: add Session.speaker_voices for session-scoped TTS voice assignment"
```

---

### Task 4: `TTSBackend` protocol — Kokoro (local) and OpenAI TTS (hosted)

**Files:**
- Create: `narrator/tts_backend.py`
- Test: `tests/test_tts_backend.py`

**Interfaces:**
- Produces: `VoiceOption(BaseModel)` — `id: str`, `gender: Literal["male", "female"] | None = None`. `TTSBackend(Protocol)` — `voices: list[VoiceOption]` attribute, `async def synthesize(self, text: str, voice: str) -> bytes`. `KokoroBackend` and `OpenAITTSBackend`, both implementing `TTSBackend`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tts_backend.py`:

```python
import pytest

from narrator.tts_backend import KokoroBackend, OpenAITTSBackend


def _fake_speech_fn(response: bytes, seen: dict):
    async def speech_fn(text: str, voice: str) -> bytes:
        seen["text"] = text
        seen["voice"] = voice
        return response

    return speech_fn


@pytest.mark.asyncio
async def test_kokoro_backend_synthesize_calls_speech_fn_with_text_and_voice():
    seen = {}
    backend = KokoroBackend(speech_fn=_fake_speech_fn(b"fake-wav-bytes", seen))

    result = await backend.synthesize("You're late, choom.", "am_adam")

    assert result == b"fake-wav-bytes"
    assert seen["text"] == "You're late, choom."
    assert seen["voice"] == "am_adam"


def test_kokoro_backend_voices_are_gender_tagged():
    backend = KokoroBackend()
    genders = {v.gender for v in backend.voices}
    assert genders == {"male", "female"}
    assert all(v.id.startswith(("af_", "am_")) for v in backend.voices)


@pytest.mark.asyncio
async def test_openai_tts_backend_synthesize_calls_speech_fn_with_text_and_voice():
    seen = {}
    backend = OpenAITTSBackend(api_key="sk-test", speech_fn=_fake_speech_fn(b"fake-mp3-bytes", seen))

    result = await backend.synthesize("The alley is quiet.", "onyx")

    assert result == b"fake-mp3-bytes"
    assert seen["text"] == "The alley is quiet."
    assert seen["voice"] == "onyx"


def test_openai_tts_backend_voices_have_no_gender_label():
    # OpenAI does not publish gender labels for its TTS voices (verified
    # against its own API docs, 2026-08-23) - only tonal descriptors like
    # "deep" or "bright". Inventing male/female tags here would be an
    # unverified claim; leaving gender unset lets voice_assignment.py fall
    # back to its ungendered path for this backend instead.
    backend = OpenAITTSBackend(api_key="sk-test")
    assert all(v.gender is None for v in backend.voices)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.tts_backend'`

- [ ] **Step 3: Implement**

Create `narrator/tts_backend.py`:

```python
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel


class VoiceOption(BaseModel):
    id: str
    gender: Literal["male", "female"] | None = None


class TTSBackend(Protocol):
    voices: list[VoiceOption]

    async def synthesize(self, text: str, voice: str) -> bytes: ...


class KokoroBackend:
    """Talks to a local Kokoro server exposing an OpenAI-compatible
    /v1/audio/speech endpoint (the shape remsky/Kokoro-FastAPI and similar
    self-hosted wrappers use). base_url is a config default, not a protocol
    constant - point it at whatever the real deployment ends up running on.

    Voice IDs verified against hexgrad/Kokoro-82M's own VOICES.md
    (Apache 2.0), American English subset only, 2026-08-23.
    """

    voices = [
        VoiceOption(id="af_heart", gender="female"),
        VoiceOption(id="af_bella", gender="female"),
        VoiceOption(id="af_nova", gender="female"),
        VoiceOption(id="af_sarah", gender="female"),
        VoiceOption(id="am_adam", gender="male"),
        VoiceOption(id="am_michael", gender="male"),
        VoiceOption(id="am_onyx", gender="male"),
        VoiceOption(id="am_echo", gender="male"),
    ]

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8880",
        model: str = "kokoro",
        speech_fn: Callable[[str, str], Awaitable[bytes]] | None = None,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self._speech_fn = speech_fn or self._default_speech

    async def _default_speech(self, text: str, voice: str) -> bytes:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/v1/audio/speech",
                json={"model": self.model, "voice": voice, "input": text},
            )
            response.raise_for_status()
            return response.content

    async def synthesize(self, text: str, voice: str) -> bytes:
        return await self._speech_fn(text, voice)


class OpenAITTSBackend:
    """Hosted fallback: OpenAI's /v1/audio/speech endpoint. Voice IDs and
    the request shape verified against OpenAI's own API docs, 2026-08-23 -
    OpenAI publishes no gender label for these voices (tonal descriptors
    only), so VoiceOption.gender is deliberately left unset for all of them.
    """

    voices = [
        VoiceOption(id="alloy"),
        VoiceOption(id="echo"),
        VoiceOption(id="fable"),
        VoiceOption(id="onyx"),
        VoiceOption(id="nova"),
        VoiceOption(id="shimmer"),
    ]

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
        model: str = "tts-1",
        speech_fn: Callable[[str, str], Awaitable[bytes]] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._speech_fn = speech_fn or self._default_speech

    async def _default_speech(self, text: str, voice: str) -> bytes:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/v1/audio/speech",
                json={"model": self.model, "voice": voice, "input": text},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            return response.content

    async def synthesize(self, text: str, voice: str) -> bytes:
        return await self._speech_fn(text, voice)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts_backend.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add narrator/tts_backend.py tests/test_tts_backend.py
git commit -m "feat: add TTSBackend protocol with Kokoro and OpenAI TTS implementations"
```

---

### Task 5: Session-scoped, gender-aware voice assignment

**Files:**
- Create: `narrator/voice_assignment.py`
- Test: `tests/test_voice_assignment.py`

**Interfaces:**
- Consumes: `Session.speaker_voices` (Task 3), `VoiceOption` (Task 4)
- Produces: `assign_voice(session: Session, speaker: str, gender: Literal["male", "female"] | None, voices: list[VoiceOption]) -> str` — returns a voice ID, updating `session.speaker_voices` on a speaker's first appearance and reusing it on every later call for that speaker.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_voice_assignment.py`:

```python
from engine.session import Session
from narrator.tts_backend import VoiceOption
from narrator.voice_assignment import assign_voice

_BANK = [
    VoiceOption(id="af_heart", gender="female"),
    VoiceOption(id="af_bella", gender="female"),
    VoiceOption(id="am_adam", gender="male"),
    VoiceOption(id="am_michael", gender="male"),
]


def test_assign_voice_picks_the_first_matching_gender_for_a_new_speaker():
    session = Session(session_id="s1")

    voice = assign_voice(session, "Jax", "male", _BANK)

    assert voice == "am_adam"
    assert session.speaker_voices["Jax"] == "am_adam"


def test_assign_voice_reuses_the_stored_voice_for_a_returning_speaker_ignoring_gender():
    session = Session(session_id="s1")
    session.speaker_voices["Jax"] = "am_michael"

    voice = assign_voice(session, "Jax", "female", _BANK)

    assert voice == "am_michael"


def test_assign_voice_falls_back_to_the_full_bank_when_gender_is_none():
    session = Session(session_id="s1")

    voice = assign_voice(session, "narrator", None, _BANK)

    assert voice == "af_heart"


def test_assign_voice_gives_two_new_speakers_of_the_same_gender_different_voices():
    session = Session(session_id="s1")

    first = assign_voice(session, "Jax", "male", _BANK)
    second = assign_voice(session, "Chrome-9", "male", _BANK)

    assert first == "am_adam"
    assert second == "am_michael"
    assert first != second


def test_assign_voice_reuses_a_matching_voice_once_the_matching_pool_is_exhausted():
    session = Session(session_id="s1")
    assign_voice(session, "Jax", "male", _BANK)
    assign_voice(session, "Chrome-9", "male", _BANK)

    third = assign_voice(session, "Rook", "male", _BANK)

    assert third == "am_adam"  # both male voices already taken - reuse the first match


def test_assign_voice_falls_back_to_the_full_bank_when_no_voice_declares_that_gender():
    session = Session(session_id="s1")
    ungendered_bank = [VoiceOption(id="alloy"), VoiceOption(id="nova")]

    voice = assign_voice(session, "narrator", "male", ungendered_bank)

    assert voice == "alloy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_voice_assignment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.voice_assignment'`

- [ ] **Step 3: Implement**

Create `narrator/voice_assignment.py`:

```python
from typing import Literal

from engine.session import Session
from narrator.tts_backend import VoiceOption


def assign_voice(
    session: Session,
    speaker: str,
    gender: Literal["male", "female"] | None,
    voices: list[VoiceOption],
) -> str:
    if speaker in session.speaker_voices:
        return session.speaker_voices[speaker]

    candidates = [v for v in voices if v.gender == gender] if gender else []
    if not candidates:
        candidates = voices

    used = set(session.speaker_voices.values())
    unused = [v for v in candidates if v.id not in used]
    chosen = (unused or candidates)[0]

    session.speaker_voices[speaker] = chosen.id
    return chosen.id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_voice_assignment.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add narrator/voice_assignment.py tests/test_voice_assignment.py
git commit -m "feat: add session-scoped gender-aware voice assignment"
```

---

### Task 6: Wire TTS synthesis into `handle_action`

**Files:**
- Modify: `server/narration.py`
- Modify: `tests/test_narration.py`

**Interfaces:**
- Consumes: `TTSBackend` (Task 4), `assign_voice` (Task 5), the per-segment log-line loop (Task 2)
- Produces: `handle_action(session, narrator_client, store, image_backend, tts_backend, player_id, message)` — note the new `tts_backend` parameter, inserted right after `image_backend`. Each segment gets a synthesized `[audio: path]` (or `[audio error: ...]`) line immediately after its text line.

- [ ] **Step 1: Write the failing test**

Add `from narrator.tts_backend import VoiceOption` to `tests/test_narration.py`'s imports, then add:

```python
class FakeTTSBackend:
    # A 3-voice bank, deliberately ordered so a gender=None speaker
    # (narrator falls back to the full bank, picks index 0) and a
    # gender="male" speaker (candidates = [voice-a, voice-b]) land on
    # different voices rather than coincidentally colliding on a 2-voice
    # bank - see assign_voice's "unused, else first match" rule (Task 5).
    voices = [
        VoiceOption(id="voice-neutral", gender="female"),
        VoiceOption(id="voice-a", gender="male"),
        VoiceOption(id="voice-b", gender="male"),
    ]

    def __init__(self, audio_bytes: bytes = b"fake-wav-bytes"):
        self.audio_bytes = audio_bytes
        self.calls = []

    async def synthesize(self, text: str, voice: str) -> bytes:
        self.calls.append((text, voice))
        return self.audio_bytes


class _UnusedTTSBackend:
    # A single dummy voice, not an empty list - assign_voice() indexes
    # into whatever bank it's given, so an empty list would crash with
    # IndexError before synthesize()'s AssertionError ever fires.
    voices = [VoiceOption(id="unused", gender=None)]

    async def synthesize(self, text, voice):
        raise AssertionError("not exercised by this test")


@pytest.mark.asyncio
async def test_handle_action_synthesizes_audio_for_each_segment_and_tags_the_log(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([
        {"speaker": "narrator", "text": "The alley reeks of ozone."},
        {"speaker": "Jax", "gender": "male", "text": "You're late, choom."},
    ])
    tts_backend = FakeTTSBackend()

    store = await _call(session, client, "p1", {"text": "I check the alley."}, tmp_path, tts_backend=tts_backend)

    audio_lines = [line for line in session.log if line.startswith("[audio: ")]
    assert len(audio_lines) == 2
    for line in audio_lines:
        relative_path = line.removeprefix("[audio: ").removesuffix("]")
        assert (store.directory / relative_path).read_bytes() == b"fake-wav-bytes"
    assert tts_backend.calls == [
        ("The alley reeks of ozone.", "voice-neutral"),
        ("You're late, choom.", "voice-a"),
    ]


@pytest.mark.asyncio
async def test_handle_action_reuses_the_same_voice_for_a_returning_speaker(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([{"speaker": "Jax", "gender": "male", "text": "First line."}])
    tts_backend = FakeTTSBackend()
    await _call(session, client, "p1", {"text": "..."}, tmp_path, tts_backend=tts_backend)
    first_voice = tts_backend.calls[0][1]

    client2 = _fake_client_with_segments([{"speaker": "Jax", "text": "Second line, no gender given this time."}])
    await _call(session, client2, "p1", {"text": "..."}, tmp_path, tts_backend=tts_backend)

    assert tts_backend.calls[1][1] == first_voice


@pytest.mark.asyncio
async def test_handle_action_logs_an_audio_error_without_raising(tmp_path):
    session = _session_with_character()
    client = _fake_client_with_segments([{"speaker": "narrator", "text": "The scene shifts."}])

    class FailingTTSBackend:
        voices = [VoiceOption(id="unused", gender=None)]

        async def synthesize(self, text, voice):
            raise ValueError("tts server unreachable")

    await _call(session, client, "p1", {"text": "..."}, tmp_path, tts_backend=FailingTTSBackend())

    assert any("audio error" in line for line in session.log)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narration.py -k "audio or reuses_the_same_voice" -v`
Expected: FAIL — `_call`'s helper doesn't accept a `tts_backend` keyword yet, and `handle_action` doesn't synthesize anything.

- [ ] **Step 3: Update the `_call` test helper to pass a `tts_backend`**

In `tests/test_narration.py`, change the `_call` helper:

```python
async def _call(session, client, player_id, message, tmp_path, image_backend=None, tts_backend=None):
    store = JSONFileSessionStore(tmp_path)
    await handle_action(
        session, client, store, image_backend or _UnusedImageBackend(),
        tts_backend or _UnusedTTSBackend(), player_id, message,
    )
    return store
```

- [ ] **Step 4: Implement the TTS wiring**

In `server/narration.py`, add the new imports and parameter, and replace the segment-flattening loop from Task 2 with the full version that also synthesizes audio:

```python
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.client import NarratorClient
from narrator.image_backend import ImageBackend
from narrator.tools import execute_tool
from narrator.tts_backend import TTSBackend
from narrator.voice_assignment import assign_voice
```

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

    messages = _build_messages(session, action_text)
    response = await narrator_client.respond(messages)

    session.log.append(f"{player_id}: {action_text}")

    for i, segment in enumerate(response.narration):
        line = segment.text if segment.speaker == "narrator" else f"{segment.speaker}: {segment.text}"
        session.log.append(line)
        log_index = len(session.log)
        voice = assign_voice(session, segment.speaker, segment.gender, tts_backend.voices)
        try:
            audio_bytes = await tts_backend.synthesize(segment.text, voice)
            relative_path = f"audio/{session.session_id}/{log_index}-{i}.wav"
            output_path = store.directory / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_bytes)
            session.log.append(f"[audio: {relative_path}]")
        except (ValueError, TypeError, OSError) as e:
            session.log.append(f"[audio error: {e}]")

    if response.tool is not None:
        tool_args = dict(response.tool_args)
        if response.tool == "request_roll":
            tool_args["player_id"] = player_id
        try:
            result = execute_tool(session, response.tool, tool_args)
            session.log.append(f"[{response.tool}: {result}]")
        except (ValueError, TypeError) as e:
            session.log.append(f"[tool error: {e}]")

    if response.image_request is not None:
        character = session.characters.get(player_id)
        reference_paths = []
        if character is not None and character.portrait_path is not None:
            reference_paths.append(str(store.directory / character.portrait_path))
        try:
            await narrator_client.unload()
            image_bytes = await image_backend.generate_scene(response.image_request.prompt, reference_paths)
            relative_path = f"images/{session.session_id}/{len(session.log)}.png"
            output_path = store.directory / relative_path
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
            session.log.append(f"[image: {relative_path}]")
        except (ValueError, TypeError, OSError) as e:
            session.log.append(f"[image error: {e}]")
```

(Only the narration block changes — the tool-call and image-request blocks below it are unchanged, shown here in full so the file's final state is unambiguous.)

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `pytest tests/test_narration.py -v`
Expected: all PASS — this includes the Task 2 tests (`test_handle_action_appends_the_players_action_and_the_narration_to_the_log`, etc.), which now also get `_UnusedTTSBackend()` injected via `_call`'s default and continue to assert exact `session.log` equality on cases with zero segments needing audio verification... note the caveat in Step 6 below.

- [ ] **Step 6: Fix the Task 2 exact-equality assertions now that audio tags are interleaved**

Any test whose default path goes through a real `_fake_client(...)` call now hits the new synthesis loop, which calls `tts_backend.synthesize(...)` — but the default `_UnusedTTSBackend` raises `AssertionError` on any call, which is not one of the caught `(ValueError, TypeError, OSError)` types, so it will propagate and fail those tests. Every existing test in `tests/test_narration.py` that exercises `handle_action` through `_call` without passing `tts_backend=` must be updated to pass `tts_backend=FakeTTSBackend()`, and their `session.log` exact-equality assertions must include the resulting `[audio: ...]` line(s). Concretely, update these tests (all currently defined earlier in the file, from Task 2's work and the original pre-Phase-6 suite):

```python
@pytest.mark.asyncio
async def test_handle_action_appends_the_players_action_and_the_narration_to_the_log(tmp_path):
    session = _session_with_character()
    client = _fake_client("The alley is quiet.")
    tts_backend = FakeTTSBackend()

    await _call(session, client, "p1", {"text": "I look around."}, tmp_path, tts_backend=tts_backend)

    assert session.log[0] == "p1: I look around."
    assert session.log[1] == "The alley is quiet."
    assert session.log[2].startswith("[audio: ")
```

```python
@pytest.mark.asyncio
async def test_handle_action_with_no_tool_call_only_logs_narration(tmp_path):
    session = _session_with_character()
    client = _fake_client("The street is empty.")
    tts_backend = FakeTTSBackend()

    await _call(session, client, "p1", {"text": "I look around."}, tmp_path, tts_backend=tts_backend)

    assert session.log[0] == "p1: I look around."
    assert session.log[1] == "The street is empty."
    assert session.log[2].startswith("[audio: ")
```

Every other existing test in the file that calls `_call(...)` with a real narrator response needs `tts_backend=FakeTTSBackend()` added to its `_call(...)` invocation, so the default `_UnusedTTSBackend`'s `AssertionError` doesn't fire. None of these assert exact `session.log` equality (they use `any(...)` or `next(...)` lookups), so no other assertion changes are needed — only the one line inside each `_call(...)` shown below changes; everything else in each test is unchanged from its current form.

```python
@pytest.mark.asyncio
async def test_handle_action_executes_a_tool_call_and_logs_the_result(tmp_path):
    session = _session_with_character()
    client = _fake_client(
        "You lunge for the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill_mod": 1,
            "difficulty": "easy", "reason": "leap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    assert any("request_roll" in line for line in session.log)


@pytest.mark.asyncio
async def test_handle_action_overrides_the_models_player_id_for_request_roll(tmp_path):
    session = _session_with_two_characters()
    client = _fake_client(
        "You lunge for the ledge.", tool="request_roll",
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill_mod": 1,
            "difficulty": "easy", "reason": "leap",
        },
    )

    await _call(session, client, "p1", {"text": "I leap the gap."}, tmp_path, tts_backend=FakeTTSBackend())

    result_line = next(line for line in session.log if "request_roll" in line)
    assert "'attribute_mod': 2" in result_line
    assert "'attribute_mod': 5" not in result_line


@pytest.mark.asyncio
async def test_handle_action_logs_a_tool_error_without_raising(tmp_path):
    session = _session_with_character()
    client = _fake_client(
        "You reach for your gear.", tool="apply_character_update",
        tool_args={"player_id": "ghost"},
    )

    await _call(session, client, "p1", {"text": "I check my gear."}, tmp_path, tts_backend=FakeTTSBackend())

    assert any("tool error" in line for line in session.log)


@pytest.mark.asyncio
async def test_handle_action_generates_a_scene_image_and_logs_its_path(tmp_path):
    session = _session_with_character()
    client = _fake_client("The alley opens onto a neon plaza.", image_prompt="a neon cyberpunk plaza")

    class FakeImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            assert prompt == "a neon cyberpunk plaza"
            return b"fake-scene-bytes"

    store = await _call(
        session, client, "p1", {"text": "I step into the plaza."}, tmp_path,
        FakeImageBackend(), tts_backend=FakeTTSBackend(),
    )

    image_line = next(line for line in session.log if line.startswith("[image: "))
    image_path = image_line.removeprefix("[image: ").removesuffix("]")
    assert (store.directory / image_path).read_bytes() == b"fake-scene-bytes"


@pytest.mark.asyncio
async def test_handle_action_uses_the_actors_own_portrait_as_a_reference(tmp_path):
    session = _session_with_character()
    session.characters["p1"].portrait_path = "portraits/s1/p1.png"
    (tmp_path / "portraits" / "s1").mkdir(parents=True)
    (tmp_path / "portraits" / "s1" / "p1.png").write_bytes(b"portrait-bytes")
    client = _fake_client("A figure steps forward.", image_prompt="a scene")

    seen = {}

    class FakeImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            seen["reference_paths"] = reference_paths
            return b"x"

    await _call(
        session, client, "p1", {"text": "I step forward."}, tmp_path,
        FakeImageBackend(), tts_backend=FakeTTSBackend(),
    )

    assert seen["reference_paths"] == [str(tmp_path / "portraits" / "s1" / "p1.png")]


@pytest.mark.asyncio
async def test_handle_action_logs_an_image_error_without_raising(tmp_path):
    session = _session_with_character()
    client = _fake_client("The scene shifts.", image_prompt="a scene")

    class FailingImageBackend:
        async def generate_portrait(self, description):
            raise AssertionError("not exercised by this test")

        async def generate_scene(self, prompt, reference_paths):
            raise ValueError("worker unreachable")

    await _call(
        session, client, "p1", {"text": "I look up."}, tmp_path,
        FailingImageBackend(), tts_backend=FakeTTSBackend(),
    )

    assert any("image error" in line for line in session.log)
```

`test_handle_action_raises_on_missing_text` doesn't reach the narrator at all (it raises before `narrator_client.respond` is ever called) — leave it unchanged.

- [ ] **Step 7: Run the full narration test file**

Run: `pytest tests/test_narration.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add server/narration.py tests/test_narration.py
git commit -m "feat: synthesize per-segment audio and tag it into the session log"
```

---

### Task 7: Wire `TTSBackend` through the app and server entrypoint

**Files:**
- Modify: `server/app.py`
- Modify: `server/__main__.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: `handle_action`'s new `tts_backend` parameter (Task 6), `KokoroBackend` (Task 4)
- Produces: `create_app(store, narrator_client, image_backend, tts_backend)` — note the new 4th parameter.

- [ ] **Step 1: Add shared TTS fakes and write the failing test**

Add to `tests/test_app.py`, next to the existing `_UnusedImageBackend` class near the top of the file (needs `from narrator.tts_backend import VoiceOption` added to the imports):

```python
class _UnusedTTSBackend:
    # A single dummy voice, not an empty list - assign_voice() (Task 5)
    # indexes into whatever voice bank it's given, so an empty list would
    # crash with IndexError before synthesize()'s AssertionError ever
    # fires. This backend is only safe to use with tests that never send
    # an "action" message at all.
    voices = [VoiceOption(id="unused", gender=None)]

    async def synthesize(self, text, voice):
        raise AssertionError("tts backend should not be called by this test")


class FakeTTSBackend:
    voices = [VoiceOption(id="af_heart", gender="female")]

    async def synthesize(self, text, voice):
        return b"fake-wav-bytes"
```

Then add the new test:

```python
def test_action_message_with_a_narration_segment_synthesizes_audio(tmp_path):
    async def chat_fn(*, model, messages, format):
        return {"message": {"content": json.dumps({
            "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
            "tool_call": {"tool": None},
        })}}
    narrator_client = NarratorClient(chat_fn=chat_fn)

    client = _client(tmp_path, narrator_client, tts_backend=FakeTTSBackend())

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "action", "text": "I look around."})
        view = ws.receive_json()

    assert any(line.startswith("[audio: ") for line in view["log"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app.py::test_action_message_with_a_narration_segment_synthesizes_audio -v`
Expected: FAIL — `_client(...)` doesn't accept `tts_backend=` yet, and `create_app` doesn't have a 4th parameter to pass it through.

- [ ] **Step 3: Update `create_app` to accept and thread through a `tts_backend`**

In `server/app.py`, change the signature and the one call site:

```python
from narrator.tts_backend import TTSBackend


def create_app(
    store: JSONFileSessionStore,
    narrator_client: NarratorClient,
    image_backend: ImageBackend,
    tts_backend: TTSBackend,
) -> FastAPI:
```

and change:

```python
                    if message.get("type") == "action":
                        await handle_action(session, narrator_client, store, image_backend, tts_backend, player_id, message)
```

- [ ] **Step 4: Update `test_app.py`'s shared `_client` helper**

```python
def _client(tmp_path, narrator_client=None, image_backend=None, tts_backend=None):
    store = JSONFileSessionStore(tmp_path)
    client = narrator_client or NarratorClient(chat_fn=_unused_chat_fn, generate_fn=_unused_generate_fn)
    backend = image_backend or _UnusedImageBackend()
    tts = tts_backend or _UnusedTTSBackend()
    return TestClient(create_app(store, client, backend, tts))
```

- [ ] **Step 5: Fix the one pre-existing test that now reaches the TTS path**

`test_action_message_triggers_the_narrator_and_broadcasts_narration` sends a real "action" message and gets a real one-segment narration back, so with Task 6's wiring live it now reaches `assign_voice`/`synthesize` too — leaving it on the default `_UnusedTTSBackend` would fail it with the "should not be called" `AssertionError`. Change:

```python
    narrator_client = NarratorClient(chat_fn=chat_fn)
    client = _client(tmp_path, narrator_client)
```

to:

```python
    narrator_client = NarratorClient(chat_fn=chat_fn)
    client = _client(tmp_path, narrator_client, tts_backend=FakeTTSBackend())
```

(This is the only other test in the file that sends `{"type": "action", ...}` with a real chat_fn — `test_action_message_missing_text_sends_an_error` raises before `narrator_client.respond` is ever called, and `test_approve_character_*` go through `handle_approve_character`, a different function this plan doesn't touch — neither needs a change.)

- [ ] **Step 6: Wire the default backend in `server/__main__.py`**

```python
from narrator.tts_backend import KokoroBackend
```

```python
def build_app():
    store = JSONFileSessionStore("./sessions")
    system_prompt = (
        ...  # unchanged
    )
    narrator_client = NarratorClient(model="qwen3:8b", system_prompt=system_prompt)
    image_backend = FluxWorkerBackend()
    # KokoroBackend is the local-first default (coexists with qwen3:8b, no
    # GPU-swap cost) - swap to OpenAITTSBackend(api_key=...) here for the
    # hosted fallback; selection is a startup-time config choice, not a
    # runtime toggle (see docs/superpowers/specs/2026-08-23-tts-narration-design.md).
    tts_backend = KokoroBackend()
    return create_app(store, narrator_client, image_backend, tts_backend)
```

- [ ] **Step 7: Run the full test suite**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add server/app.py server/__main__.py tests/test_app.py
git commit -m "feat: wire TTSBackend through create_app and default to KokoroBackend"
```

---

## Self-Review Notes

- **Spec coverage**: `NarrationSegment` schema (Task 1), backend Protocol + Kokoro/OpenAI implementations (Task 4), session-scoped gender-aware assignment (Task 5), per-segment tag-in-log delivery (Task 2 + 6), fail-soft error handling (Task 6), startup-config backend selection (Task 7) — every section of the spec maps to a task. Deferred items (voice cloning, automatic failover, sentence-level streaming) have no task, matching the spec's own "What's deliberately deferred" section.
- **Voice bank honesty**: Kokoro and OpenAI voice IDs were verified against real sources during plan-writing (not left as a research step for the implementer, since the spec's deferred verification could be done immediately) — Kokoro's `VOICES.md` and OpenAI's own API docs, both fetched 2026-08-23. OpenAI's lack of published gender labels is carried through honestly (`gender=None` for all its voices) rather than inventing labels, with `assign_voice`'s fallback path exercising that exact case (`test_assign_voice_falls_back_to_the_full_bank_when_no_voice_declares_that_gender`).
- **Type consistency**: `TTSBackend.synthesize(text: str, voice: str) -> bytes` is identical across `KokoroBackend`, `OpenAITTSBackend`, every test fake, and `handle_action`'s call site. `assign_voice`'s signature matches its Task 5 definition everywhere it's called (Task 6). `handle_action`'s parameter order (`session, narrator_client, store, image_backend, tts_backend, player_id, message`) is consistent across `server/narration.py`, `server/app.py`, and every test helper.
