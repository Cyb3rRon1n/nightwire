# Pluggable Narrator Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the narrator a `Protocol`-based swap point (matching `ImageBackend`/`TTSBackend`) with two new hosted implementations (Anthropic, OpenAI-compatible) alongside the existing Ollama one, selected via `NARRATOR_BACKEND`.

**Architecture:** A `NarratorBackend` Protocol (`respond`/`summarize`/`unload`) that `NarratorClient` already satisfies structurally, no rename. Two new sibling classes (`AnthropicNarratorBackend`, `OpenAICompatNarratorBackend`) implement the same three methods over raw `httpx`, no new dependencies. A `create_narrator_backend()` factory mirrors `create_image_backend()` exactly. `server/__main__.py` calls the factory instead of constructing `NarratorClient` directly.

**Tech Stack:** Python 3.11+, `httpx` (already a dependency), `pydantic` v2, `pytest`/`pytest-asyncio`.

**Spec:** `docs/superpowers/specs/2026-09-16-pluggable-narrator-backend-design.md`

## Global Constraints

- No new dependencies (`anthropic`/`openai` SDKs) — raw `httpx`, matching `ComfyUIBackend`/`FluxWorkerBackend`/`KokoroBackend`.
- `NarratorClient` is not renamed and not modified — it satisfies the new Protocol as-is (except Task 5's `system_prompt` gap, scoped to the two new backends only).
- Both new backends raise only `ValueError` (schema/validation failure) or let `httpx.HTTPError` propagate (request failure) — no new exception types.
- Both new backends' `unload()` is a no-op.
- Env var names for the OpenAI-compatible backend are `NARRATOR_OPENAI_COMPAT_*`, never bare `OPENAI_COMPAT_*` — those names are already used by an unrelated frontend feature (`frontend/.env.example`).
- Default `NARRATOR_BACKEND=ollama` preserves current behavior unchanged.

---

### Task 1: `NarratorBackend` Protocol

**Files:**
- Modify: `narrator/client.py` (add near the top, after the existing model classes, before `class NarratorClient`)
- Test: `tests/test_narrator_client.py` (append)

**Interfaces:**
- Produces: `NarratorBackend` (a `Protocol`, `@runtime_checkable`) with `async def respond(self, messages: list[dict]) -> NarratorResponse`, `async def summarize(self, text: str) -> str`, `async def unload(self) -> None`. Every later task's backend class implements exactly this shape.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_narrator_client.py`:

```python
def test_narrator_client_satisfies_the_narrator_backend_protocol():
    from narrator.client import NarratorBackend
    client = NarratorClient()
    assert isinstance(client, NarratorBackend)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_narrator_client.py::test_narrator_client_satisfies_the_narrator_backend_protocol -v`
Expected: FAIL with `ImportError: cannot import name 'NarratorBackend'`

- [ ] **Step 3: Add the Protocol**

In `narrator/client.py`, add `Protocol` and `runtime_checkable` to the existing `from typing import ...` line at the top of the file (it currently imports `Annotated, Literal, Union` — extend that same import, don't add a second `typing` import line). Then add this class immediately before `class NarratorClient:`:

```python
@runtime_checkable
class NarratorBackend(Protocol):
    async def respond(self, messages: list[dict]) -> NarratorResponse: ...
    async def summarize(self, text: str) -> str: ...
    async def unload(self) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_narrator_client.py::test_narrator_client_satisfies_the_narrator_backend_protocol -v`
Expected: PASS

- [ ] **Step 5: Run the full test file to confirm nothing else broke**

Run: `pytest tests/test_narrator_client.py -v`
Expected: all pass (adding a Protocol and an import touches nothing else in this file)

- [ ] **Step 6: Commit**

```bash
git add narrator/client.py tests/test_narrator_client.py
git commit -m "feat: add NarratorBackend protocol, satisfied by the existing NarratorClient"
```

---

### Task 2: `AnthropicNarratorBackend`

**Files:**
- Create: `narrator/anthropic_backend.py`
- Test: `tests/test_anthropic_backend.py`

**Interfaces:**
- Consumes: `NarratorResponse`, `NarrationSegment` from `narrator.client` (existing, unchanged).
- Produces: `AnthropicNarratorBackend(api_key: str, model: str = "claude-sonnet-5", client: httpx.AsyncClient | None = None)`, satisfying `NarratorBackend` from Task 1. Task 4's factory constructs this exact class with these exact constructor parameter names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_anthropic_backend.py`:

```python
import json

import httpx
import pytest

from narrator.anthropic_backend import AnthropicNarratorBackend


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _FakeAnthropicClient:
    """Stands in for httpx.AsyncClient - only the method
    AnthropicNarratorBackend actually calls (post), duck-typed to httpx's
    own response shape."""

    def __init__(self, response_json):
        self.response_json = response_json
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        return _FakeResponse(self.response_json)


def _tool_use_response(tool_input: dict):
    return {
        "content": [
            {"type": "tool_use", "name": "narrator_response", "input": tool_input},
        ],
    }


@pytest.mark.asyncio
async def test_respond_forces_tool_use_and_parses_the_tool_input():
    payload = {
        "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
        "tool_call": {"tool": None},
    }
    fake_client = _FakeAnthropicClient(_tool_use_response(payload))
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    response = await backend.respond([{"role": "user", "content": "I look around."}])

    assert response.narration[0].text == "The alley is quiet."
    assert response.tool is None
    # Forced tool-use is the whole point - assert the actual request shape,
    # not just that a request happened.
    _, body, headers = fake_client.calls[0]
    assert body["tool_choice"] == {"type": "tool", "name": "narrator_response"}
    assert body["tools"][0]["name"] == "narrator_response"
    assert headers["x-api-key"] == "test-key"


@pytest.mark.asyncio
async def test_respond_raises_value_error_on_missing_tool_use_block():
    fake_client = _FakeAnthropicClient({"content": [{"type": "text", "text": "oops, no tool call"}]})
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    with pytest.raises(ValueError, match="no tool_use block"):
        await backend.respond([{"role": "user", "content": "I look around."}])


@pytest.mark.asyncio
async def test_respond_raises_value_error_on_schema_mismatch():
    # tool_input is missing the required "narration" field entirely.
    fake_client = _FakeAnthropicClient(_tool_use_response({"tool_call": {"tool": None}}))
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    with pytest.raises(ValueError):
        await backend.respond([{"role": "user", "content": "I look around."}])


@pytest.mark.asyncio
async def test_summarize_sends_a_plain_unconstrained_request():
    fake_client = _FakeAnthropicClient({"content": [{"type": "text", "text": "  A short summary.  "}]})
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)

    result = await backend.summarize("Some session events.")

    assert result == "A short summary."
    _, body, _ = fake_client.calls[0]
    assert "tools" not in body
    assert "tool_choice" not in body


@pytest.mark.asyncio
async def test_unload_is_a_noop():
    backend = AnthropicNarratorBackend(api_key="test-key", client=_FakeAnthropicClient({}))
    await backend.unload()  # must not raise, must not call the fake client
    assert len(backend._client.calls) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_anthropic_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.anthropic_backend'`

- [ ] **Step 3: Write the implementation**

Create `narrator/anthropic_backend.py`:

```python
"""AnthropicNarratorBackend - forced tool-use for schema-constrained
output, the real Anthropic-API equivalent of Ollama's format= JSON-schema
param NarratorClient.respond() already relies on. Raw httpx, no anthropic
SDK dependency - matches every other backend in this project
(ComfyUIBackend, FluxWorkerBackend, KokoroBackend)."""

import httpx
from pydantic import ValidationError

from narrator.client import NarratorResponse

_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_TOOL_NAME = "narrator_response"


class AnthropicNarratorBackend:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.system_prompt = ""
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._tool_schema = NarratorResponse.model_json_schema()

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    async def respond(self, messages: list[dict]) -> NarratorResponse:
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
            "tools": [
                {
                    "name": _TOOL_NAME,
                    "description": "Respond with the narrator's structured turn output.",
                    "input_schema": self._tool_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": _TOOL_NAME},
        }
        if self.system_prompt:
            body["system"] = self.system_prompt
        result = await self._client.post(_API_URL, json=body, headers=self._headers())
        result.raise_for_status()
        data = result.json()
        tool_use = next(
            (block for block in data.get("content", []) if block.get("type") == "tool_use"),
            None,
        )
        if tool_use is None:
            raise ValueError("Anthropic response had no tool_use block")
        try:
            return NarratorResponse.model_validate(tool_use["input"])
        except ValidationError as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e

    async def summarize(self, text: str) -> str:
        body = {
            "model": self.model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": text}],
            "system": (
                "Summarize the following tabletop RPG session events in 2-3 sentences. "
                "Preserve named characters, promises, and key decisions made. Prose only, no lists."
            ),
        }
        result = await self._client.post(_API_URL, json=body, headers=self._headers())
        result.raise_for_status()
        data = result.json()
        text_block = next(block for block in data["content"] if block.get("type") == "text")
        return text_block["text"].strip()

    async def unload(self) -> None:
        # No local resources to free - a hosted API has nothing resident here.
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_anthropic_backend.py -v`
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
git add narrator/anthropic_backend.py tests/test_anthropic_backend.py
git commit -m "feat: add AnthropicNarratorBackend with forced tool-use"
```

---

### Task 3: `OpenAICompatNarratorBackend`

**Files:**
- Create: `narrator/openai_compat_backend.py`
- Test: `tests/test_openai_compat_backend.py`

**Interfaces:**
- Consumes: `NarratorResponse` from `narrator.client` (existing, unchanged).
- Produces: `OpenAICompatNarratorBackend(base_url: str, model: str, api_key: str | None = None, client: httpx.AsyncClient | None = None)`, satisfying `NarratorBackend`. Task 4's factory constructs this exact class with these exact constructor parameter names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_openai_compat_backend.py`:

```python
import pytest

from narrator.openai_compat_backend import OpenAICompatNarratorBackend


class _FakeResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _FakeOpenAIClient:
    """Stands in for httpx.AsyncClient - only the method
    OpenAICompatNarratorBackend actually calls (post)."""

    def __init__(self, response_json):
        self.response_json = response_json
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        return _FakeResponse(self.response_json)


def _chat_response(content_str: str):
    return {"choices": [{"message": {"content": content_str}}]}


@pytest.mark.asyncio
async def test_respond_requests_strict_json_schema_and_parses_it():
    import json
    payload = json.dumps({
        "narration": [{"speaker": "narrator", "text": "The alley is quiet."}],
        "tool_call": {"tool": None},
    })
    fake_client = _FakeOpenAIClient(_chat_response(payload))
    backend = OpenAICompatNarratorBackend(
        base_url="http://localhost:8080/v1", model="test-model", api_key="test-key", client=fake_client,
    )

    response = await backend.respond([{"role": "user", "content": "I look around."}])

    assert response.narration[0].text == "The alley is quiet."
    url, body, headers = fake_client.calls[0]
    assert url == "http://localhost:8080/v1/chat/completions"
    assert body["response_format"]["type"] == "json_schema"
    assert headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_respond_works_even_if_the_server_ignores_response_format():
    # A server that doesn't honor response_format at all - the schema
    # request was sent (asserted above), but this proves the fallback
    # validate-after-the-fact path is real, not just theoretical, for a
    # server that returns valid JSON without ever enforcing the schema.
    import json
    payload = json.dumps({
        "narration": [{"speaker": "narrator", "text": "Free-form but valid."}],
        "tool_call": {"tool": None},
    })
    fake_client = _FakeOpenAIClient(_chat_response(payload))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    response = await backend.respond([{"role": "user", "content": "hi"}])

    assert response.narration[0].text == "Free-form but valid."


@pytest.mark.asyncio
async def test_respond_raises_value_error_on_malformed_json():
    fake_client = _FakeOpenAIClient(_chat_response("not json at all"))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    with pytest.raises(ValueError):
        await backend.respond([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_respond_works_without_an_api_key():
    # A local vLLM/llama.cpp-server deployment needs no key at all.
    import json
    payload = json.dumps({"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}})
    fake_client = _FakeOpenAIClient(_chat_response(payload))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    await backend.respond([{"role": "user", "content": "hi"}])

    _, _, headers = fake_client.calls[0]
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_summarize_sends_a_plain_chat_completion():
    fake_client = _FakeOpenAIClient(_chat_response("  A short summary.  "))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)

    result = await backend.summarize("Some session events.")

    assert result == "A short summary."
    _, body, _ = fake_client.calls[0]
    assert "response_format" not in body


@pytest.mark.asyncio
async def test_unload_is_a_noop():
    fake_client = _FakeOpenAIClient({})
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)
    await backend.unload()
    assert len(fake_client.calls) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_openai_compat_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.openai_compat_backend'`

- [ ] **Step 3: Write the implementation**

Create `narrator/openai_compat_backend.py`:

```python
"""OpenAICompatNarratorBackend - talks to any OpenAI-compatible chat
completions endpoint (OpenRouter, a local vLLM/llama.cpp-server, etc.).
Requests OpenAI's own Structured Outputs (response_format=json_schema),
but never assumes the server actually enforces it - "OpenAI-compatible"
spans providers with uneven strict-mode support, so every response is
validated the same way regardless of whether the server honored the
schema or just happened to return valid JSON. Raw httpx, no openai SDK
dependency - matches every other backend in this project."""

import json

import httpx
from pydantic import ValidationError

from narrator.client import NarratorResponse

_SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following tabletop RPG session events in 2-3 sentences. "
    "Preserve named characters, promises, and key decisions made. Prose only, no lists."
)


class OpenAICompatNarratorBackend:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.system_prompt = ""
        self._client = client or httpx.AsyncClient(timeout=60.0)
        self._response_schema = NarratorResponse.model_json_schema()

    def _headers(self) -> dict:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def respond(self, messages: list[dict]) -> NarratorResponse:
        full_messages = messages
        if self.system_prompt:
            full_messages = [{"role": "system", "content": self.system_prompt}] + messages
        body = {
            "model": self.model,
            "messages": full_messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "narrator_response", "schema": self._response_schema},
            },
        }
        result = await self._client.post(
            f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
        )
        result.raise_for_status()
        content = result.json()["choices"][0]["message"]["content"]
        try:
            return NarratorResponse.model_validate_json(content)
        except (ValidationError, json.JSONDecodeError) as e:
            raise ValueError(f"model returned invalid structured output: {e}") from e

    async def summarize(self, text: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        result = await self._client.post(
            f"{self.base_url}/chat/completions", json=body, headers=self._headers(),
        )
        result.raise_for_status()
        return result.json()["choices"][0]["message"]["content"].strip()

    async def unload(self) -> None:
        # No local resources to free - a hosted API has nothing resident here.
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_openai_compat_backend.py -v`
Expected: all 6 PASS

- [ ] **Step 5: Commit**

```bash
git add narrator/openai_compat_backend.py tests/test_openai_compat_backend.py
git commit -m "feat: add OpenAICompatNarratorBackend"
```

---

### Task 4: `create_narrator_backend()` factory

**Files:**
- Modify: `narrator/client.py` (append after `NarratorClient`)
- Test: `tests/test_narrator_client.py` (append)

**Interfaces:**
- Consumes: `NarratorClient` (existing), `AnthropicNarratorBackend` (Task 2), `OpenAICompatNarratorBackend` (Task 3).
- Produces: `create_narrator_backend() -> NarratorBackend`. Task 5 calls this exact function name from `server/__main__.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narrator_client.py`:

```python
def test_create_narrator_backend_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("NARRATOR_BACKEND", raising=False)
    from narrator.client import create_narrator_backend

    backend = create_narrator_backend()

    assert isinstance(backend, NarratorClient)


def test_create_narrator_backend_selects_anthropic(monkeypatch):
    monkeypatch.setenv("NARRATOR_BACKEND", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from narrator.client import create_narrator_backend
    from narrator.anthropic_backend import AnthropicNarratorBackend

    backend = create_narrator_backend()

    assert isinstance(backend, AnthropicNarratorBackend)
    assert backend.api_key == "test-key"


def test_create_narrator_backend_selects_openai_compat(monkeypatch):
    monkeypatch.setenv("NARRATOR_BACKEND", "openai_compat")
    monkeypatch.setenv("NARRATOR_OPENAI_COMPAT_BASE_URL", "http://localhost:8080/v1")
    monkeypatch.setenv("NARRATOR_OPENAI_COMPAT_MODEL", "local-model")
    from narrator.client import create_narrator_backend
    from narrator.openai_compat_backend import OpenAICompatNarratorBackend

    backend = create_narrator_backend()

    assert isinstance(backend, OpenAICompatNarratorBackend)
    assert backend.base_url == "http://localhost:8080/v1"
    assert backend.model == "local-model"


def test_create_narrator_backend_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("NARRATOR_BACKEND", "not-a-real-backend")
    from narrator.client import create_narrator_backend

    with pytest.raises(ValueError, match="not-a-real-backend"):
        create_narrator_backend()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_narrator_client.py -k create_narrator_backend -v`
Expected: FAIL with `ImportError: cannot import name 'create_narrator_backend'`

- [ ] **Step 3: Write the factory**

Add `import os` to `narrator/client.py`'s top-of-file imports (its current imports are `collections.abc`, `typing`, `ollama`, `pydantic`, and `narrator.tools` — `os` needs adding, it's not there yet). Append this function at the end of the file, after the `NarratorClient` class:

```python
def create_narrator_backend() -> NarratorBackend:
    # NARRATOR_BACKEND selects the narrator backend at startup - config, not
    # a runtime toggle, same shape IMAGE_BACKEND/create_image_backend already
    # use. Defaults to ollama (current behavior, unchanged for existing
    # deployments). Imports are local to avoid a hard import-time dependency
    # from every narrator/client.py user onto the hosted-backend modules.
    backend = os.environ.get("NARRATOR_BACKEND", "ollama").strip().lower()
    if backend == "ollama":
        return NarratorClient(model=os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b"))
    if backend == "anthropic":
        from narrator.anthropic_backend import AnthropicNarratorBackend
        return AnthropicNarratorBackend(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            model=os.environ.get("NARRATOR_ANTHROPIC_MODEL", "claude-sonnet-5"),
        )
    if backend == "openai_compat":
        from narrator.openai_compat_backend import OpenAICompatNarratorBackend
        return OpenAICompatNarratorBackend(
            base_url=os.environ["NARRATOR_OPENAI_COMPAT_BASE_URL"],
            model=os.environ["NARRATOR_OPENAI_COMPAT_MODEL"],
            api_key=os.environ.get("NARRATOR_OPENAI_COMPAT_API_KEY"),
        )
    raise ValueError(f"Unknown NARRATOR_BACKEND {backend!r}. Valid backends: 'ollama', 'anthropic', 'openai_compat'.")
```

Note: this factory doesn't take `system_prompt` — callers that need one (see Task 5) set it as an attribute after construction, same as today's direct `NarratorClient(...)` call site's replacement will do explicitly in Task 5.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_narrator_client.py -v`
Expected: all pass, including the 4 new ones

- [ ] **Step 5: Run the full test suite**

Run: `pytest -q`
Expected: all pass (this task only adds code, doesn't touch `server/__main__.py` yet)

- [ ] **Step 6: Commit**

```bash
git add narrator/client.py tests/test_narrator_client.py
git commit -m "feat: add create_narrator_backend() factory"
```

---

### Task 5: Wire `server/__main__.py`, docs, final verification

**Files:**
- Modify: `server/__main__.py:1-45` (the `NarratorClient` import and construction)
- Modify: `README.md` (env var / setup section — find where `IMAGE_BACKEND` is documented and add a matching paragraph)
- Modify: `ROADMAP.md` (mark Phase 12 built, mirroring how other shipped candidate-phase bullets are annotated)
- Check for `CHANGELOG.md` — only edit it if it already exists

**Interfaces:**
- Consumes: `create_narrator_backend()` (Task 4).

- [ ] **Step 1: Update `server/__main__.py`**

Change the import line:

```python
from narrator.client import NarratorClient
```

to:

```python
from narrator.client import create_narrator_backend
```

Change the construction line:

```python
    narrator_client = NarratorClient(model=os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b"), system_prompt=system_prompt)
```

to:

```python
    narrator_client = create_narrator_backend()
    narrator_client.system_prompt = system_prompt
```

- [ ] **Step 2: Add regression tests proving the system prompt reaches both new backends**

This closes a real gap: without it, switching `NARRATOR_BACKEND` to `anthropic`/`openai_compat` would silently drop the entire game-master system prompt, since Task 2/3's `respond()` implementations already read `self.system_prompt` (set in each backend's `__init__` to `""`) but nothing yet proves it's wired end to end from a caller setting the attribute post-construction, the way Step 1 now does.

Append to `tests/test_anthropic_backend.py`:

```python
@pytest.mark.asyncio
async def test_respond_sends_system_prompt_as_top_level_system_field():
    payload = {"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}}
    fake_client = _FakeAnthropicClient(_tool_use_response(payload))
    backend = AnthropicNarratorBackend(api_key="test-key", client=fake_client)
    backend.system_prompt = "You are a cyberpunk GM."

    await backend.respond([{"role": "user", "content": "hi"}])

    _, body, _ = fake_client.calls[0]
    assert body["system"] == "You are a cyberpunk GM."
    assert all(m["role"] != "system" for m in body["messages"])
```

Append to `tests/test_openai_compat_backend.py`:

```python
@pytest.mark.asyncio
async def test_respond_prepends_system_prompt_as_a_message():
    import json
    payload = json.dumps({"narration": [{"speaker": "narrator", "text": "ok"}], "tool_call": {"tool": None}})
    fake_client = _FakeOpenAIClient(_chat_response(payload))
    backend = OpenAICompatNarratorBackend(base_url="http://localhost:8080/v1", model="test-model", client=fake_client)
    backend.system_prompt = "You are a cyberpunk GM."

    await backend.respond([{"role": "user", "content": "hi"}])

    _, body, _ = fake_client.calls[0]
    assert body["messages"][0] == {"role": "system", "content": "You are a cyberpunk GM."}
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: all pass, including the 2 new system-prompt tests

- [ ] **Step 4: Update README.md**

Find the existing config/env-var mention of `IMAGE_BACKEND` in README.md. Add a matching short paragraph immediately after it:

```markdown
The narrator itself is also swappable: the default (`NARRATOR_BACKEND=ollama`) is local Ollama; set `NARRATOR_BACKEND=anthropic` (needs `ANTHROPIC_API_KEY`) or `NARRATOR_BACKEND=openai_compat` (needs `NARRATOR_OPENAI_COMPAT_BASE_URL` and `NARRATOR_OPENAI_COMPAT_MODEL`, e.g. for OpenRouter or a local vLLM/llama.cpp-server) for a hosted alternative — same `NarratorResponse` schema either way, so behavior is directly comparable across backends.
```

- [ ] **Step 5: Update ROADMAP.md**

In the "Candidate future phases" section, find the bullet starting "**Pluggable narrator backend**" and prepend a "Built" note to it, matching the exact phrasing style the "Long-session memory" bullet above it already uses for its own "First sub-phase... shipped" note:

```
- **Pluggable narrator backend** (Ollama + a hosted fallback) — **Built 2026-09-16**: `NarratorBackend` protocol + `AnthropicNarratorBackend`/`OpenAICompatNarratorBackend`, selected via `NARRATOR_BACKEND`. See `docs/superpowers/specs/2026-09-16-pluggable-narrator-backend-design.md`. The actual local-vs-hosted A/B reliability comparison this enables is still open, deliberately deferred per that spec.
```

- [ ] **Step 6: Check for and update CHANGELOG.md**

Run: `ls CHANGELOG.md 2>&1`

If it exists, add an entry at the top following its existing format (check its most recent entry for the exact style before writing yours). If it doesn't exist, skip this step — don't create one speculatively.

- [ ] **Step 7: Full test suite + lint one more time**

Run: `pytest -q && cd frontend && npm run lint`
Expected: all pass. (This task doesn't touch `frontend/`, so `npm run lint` passing confirms nothing was accidentally broken there.)

- [ ] **Step 8: Manual sanity check against a real hosted API (optional but recommended per spec)**

If an `ANTHROPIC_API_KEY` is available in this environment, run a quick real call to confirm the forced tool-use shape actually works against the real API (not just mocks) — e.g. a short Python script constructing `AnthropicNarratorBackend(api_key=os.environ["ANTHROPIC_API_KEY"])` with a real `httpx.AsyncClient()` and calling `respond()` with a one-line test message. This is a manual check, not a new automated test — the spec explicitly doesn't require live-API verification to call this phase done (see spec's Testing section), but a quick real check is worth doing if a key is on hand.

- [ ] **Step 9: Commit**

```bash
git add server/__main__.py narrator/anthropic_backend.py narrator/openai_compat_backend.py tests/test_anthropic_backend.py tests/test_openai_compat_backend.py README.md ROADMAP.md
git commit -m "feat: wire create_narrator_backend() into server startup; docs"
```
