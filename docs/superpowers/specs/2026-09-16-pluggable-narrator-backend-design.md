# Nightwire Pluggable Narrator Backend Design — Phase 12

Status: designed, not yet implemented. Sourced from `ROADMAP.md`'s "Candidate future phases" entry (surfaced 2026-09-15): `narrator/client.py` currently imports `ollama` directly, unlike `ImageBackend`/`TTSBackend` which already use a `Protocol` with a config-selectable factory. This closes that asymmetry, enabling real local-vs-hosted A/B reliability comparisons on the same `NarratorResponse` schema — the comparison itself is explicitly out of scope for this phase, see "What's deliberately deferred" below.

## The actual requirement

`ImageBackend` (Phase 5/10) and `TTSBackend` (Phase 3) both follow the same shape: a `Protocol`, one or more concrete implementations, a `create_X_backend()` factory reading an env var. `NarratorClient` never got this treatment — it's the one hardcoded integration point in the app, wrapping `ollama.AsyncClient` directly with no swap point. Adding a hosted fallback today would mean a second, parallel, ad-hoc code path rather than a real alternative behind the same interface every other backend already uses.

## Providers: both Anthropic and an OpenAI-compatible backend

**Decision: add both, not one.** The roadmap's own motivation is answering "local vs. hosted" — a single hosted option answers "local vs. one hosted vendor," a narrower question. Anthropic gives real schema-constrained output via forced tool-use (see below); an OpenAI-compatible backend covers OpenRouter, local vLLM/llama.cpp-server deployments, and any other provider a user already has infrastructure for — a materially different reach than Anthropic alone.

**No new dependencies.** `httpx>=0.27` is already a dependency, and every existing backend in this project (`ComfyUIBackend`, `FluxWorkerBackend`, `KokoroBackend`) talks to its API over raw HTTP rather than an official SDK. Both new narrator backends follow the same convention — no `anthropic`/`openai` packages added.

## Naming: `NarratorClient` keeps its name

**Decision: no rename.** `ImageBackend`/`TTSBackend`'s concrete implementations follow a `<Vendor>Backend` naming convention (`FluxWorkerBackend`, `KokoroBackend`), which `NarratorClient` doesn't match. Renaming it to `OllamaNarratorBackend` would touch every call site and roughly 100 existing test references for a purely cosmetic gain — `Protocol` conformance in Python is structural (duck typing), so the name mismatch costs nothing functionally. `NarratorClient` is left completely unchanged; it retroactively satisfies the new `NarratorBackend` Protocol as-is.

## Component: `NarratorBackend` Protocol

New `Protocol` in `narrator/client.py` (same file, next to the class it now sits alongside), covering exactly the three methods callers actually use — checked against every real call site in `server/narration.py` and `server/__main__.py`, not assumed:

```python
class NarratorBackend(Protocol):
    async def respond(self, messages: list[dict]) -> NarratorResponse: ...
    async def summarize(self, text: str) -> str: ...
    async def unload(self) -> None: ...
```

`NarratorClient` already implements all three. Two new sibling classes join it in new files:

### `narrator/anthropic_backend.py` — `AnthropicNarratorBackend`

**Schema enforcement: forced tool-use**, Anthropic's real documented mechanism for making the model call a schema-shaped tool — but not true constrained decoding the way Ollama's `format=` param is. Forced `tool_choice` only guarantees the model *calls* the declared tool; Anthropic's API does not itself validate that `input` conforms to the schema (that would need `strict: true` on the tool definition, not used here). One tool is declared per request, built from `NarratorResponse.model_json_schema()` as its `input_schema`, with `tool_choice={"type": "tool", "name": "narrator_response"}` forcing the model to call it. The response's `tool_use` content block's `input` is validated the same way `NarratorClient.respond()` already validates Ollama's JSON string — `NarratorResponse.model_validate(...)`, `ValidationError` re-raised as `ValueError`, identical to the existing pattern every caller already handles; this `model_validate` step is what actually catches non-conformance.

Note: forced `tool_choice` of type `tool` returns a 400 error on the `claude-fable-5-1` / `claude-mythos-5-1` model family — since `NARRATOR_ANTHROPIC_MODEL` is user-settable, pointing it at a Fable-family model fails hard with no hint why.

`summarize()` is a plain, unconstrained Messages API call (no forced tool-use needed — same shape as `NarratorClient._default_summarize`, which also skips the `format=` schema for the same reason: free prose, not structured data).

`unload()` is a no-op — nothing resident locally to free.

### `narrator/openai_compat_backend.py` — `OpenAICompatNarratorBackend`

**Schema enforcement: best-effort, not assumed universal.** OpenAI's own Structured Outputs (`response_format={"type": "json_schema", "json_schema": {..., "strict": true}}`) is requested when available, but "OpenAI-compatible" spans providers (OpenRouter, self-hosted vLLM/llama.cpp-server, etc.) with uneven support for strict mode. The backend always falls back to the same validation-after-the-fact path `NarratorClient.respond()` already uses (`NarratorResponse.model_validate_json()`, `ValidationError` → `ValueError`) regardless of whether the server actually enforced the schema — this makes the backend correct against a server that ignores `response_format` entirely, not just one that honors it, without needing to detect which case applies.

`summarize()` is a plain chat-completion call, no `response_format`. `unload()` is a no-op.

## Selection: `create_narrator_backend()` factory

New factory in `narrator/client.py`, mirroring `create_image_backend()`'s shape exactly:

```python
def create_narrator_backend() -> NarratorBackend:
    backend = os.environ.get("NARRATOR_BACKEND", "ollama").strip().lower()
    if backend == "ollama":
        return NarratorClient(model=os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b"), ...)
    if backend == "anthropic":
        return AnthropicNarratorBackend(...)
    if backend == "openai_compat":
        return OpenAICompatNarratorBackend(...)
    raise ValueError(f"Unknown NARRATOR_BACKEND {backend!r}. Valid backends: 'ollama', 'anthropic', 'openai_compat'.")
```

`server/__main__.py` calls this factory instead of constructing `NarratorClient` directly. Default `ollama` preserves current behavior for existing deployments unchanged.

## Config

| Variable | Default | Purpose |
|---|---|---|
| `NARRATOR_BACKEND` | `ollama` | `ollama` \| `anthropic` \| `openai_compat` |
| `NIGHTWIRE_MODEL` | `qwen3:8b` | Ollama model (existing var, unchanged) |
| `ANTHROPIC_API_KEY` | — | Standard Anthropic SDK-convention env var name (shared, not project-specific — fine to reuse) |
| `NARRATOR_ANTHROPIC_MODEL` | `claude-sonnet-5` | Model id for the Anthropic backend |
| `NARRATOR_OPENAI_COMPAT_BASE_URL` | — | Required when `NARRATOR_BACKEND=openai_compat` |
| `NARRATOR_OPENAI_COMPAT_MODEL` | — | Required when `NARRATOR_BACKEND=openai_compat` |
| `NARRATOR_OPENAI_COMPAT_API_KEY` | — | Optional (a local vLLM/llama.cpp-server needs none) |

**Deliberately separate names from `frontend/.env.example`'s existing `OPENAI_COMPAT_*`/`OPENROUTER_*` vars.** Those configure the open-dungeon template's own unrelated built-in text-generation feature in the Next.js frontend — a completely different subsystem from this game backend's narrator. Reusing the same env var names would silently cross-wire two unrelated features the moment someone sets one expecting it to affect both. The `NARRATOR_` prefix makes the boundary explicit.

## Error handling

No new error-handling surface. Both new backends raise the same two exception classes every existing caller (`server/narration.py`, `_maybe_compact`) already handles identically regardless of which backend is active: `ValueError` for a schema/validation failure, `httpx.HTTPError` for a request failure. This was true before this phase and stays true after — the whole point of the Protocol is that callers don't need to know or care which backend is behind it.

## Testing

Unit tests per backend, same fake/mock shape the test suite already uses everywhere (`_fake_client`'s `chat_fn`/`generate_fn` injection points, `FakeTTSBackend`) — no real API calls in tests:
- `AnthropicNarratorBackend`: a fake HTTP client returning a `tool_use` block, asserting the request body actually sets forced `tool_choice` and the right schema; a malformed/missing `tool_use` block raising `ValueError`.
- `OpenAICompatNarratorBackend`: a fake response validating correctly; a separate case where the fake server ignores `response_format` and returns free-form JSON that still validates (proving the fallback path is real, not just theoretical); a genuinely malformed response raising `ValueError`.
- `create_narrator_backend()`: one test per valid `NARRATOR_BACKEND` value, one for the unknown-value `ValueError`, mirroring `create_image_backend`'s existing test shape exactly.

**No live-hosted-API verification required for this phase** — unlike the ComfyUI backend (Phase 10), which needed a real GPU to prove real image generation happened, this phase's correctness is entirely about request/response shape and schema handling, which mocked tests cover completely. A live call to a real hosted API is a reasonable manual sanity check before calling the phase done, but isn't the same "no live-hardware-verification bar" the ComfyUI phase needed to clear — there's no local hardware behavior at stake here.

## What's deliberately deferred

- **The actual A/B reliability comparison** (local Ollama vs. either hosted backend, on the same scenario) — this phase only builds the capability to run one. Measuring and comparing is separate, focused follow-up scope, explicitly chosen this way per project discussion.
- Streaming responses — both new backends make single blocking requests, matching `NarratorClient`'s own current behavior exactly. Not a regression, not an enhancement.
- Retry/backoff logic for hosted API rate limits or transient failures — out of scope; a caller-level concern if it ever becomes a real problem, not designed speculatively here.
- Per-backend cost tracking/budgeting — no such feature exists for any backend in this project today; not introduced here either.
- Any change to `NarratorClient`/the Ollama path itself.
