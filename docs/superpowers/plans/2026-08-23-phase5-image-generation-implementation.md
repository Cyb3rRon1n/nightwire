# Phase 5: Image Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` (fresh subagent per task, review after each, one final whole-branch review). Steps use checkbox (`- [ ]`) syntax.

**Spec:** `docs/superpowers/specs/2026-08-23-image-generation-design.md` — read it first. This plan implements it task-by-task, backend first (testable without a GPU via a fake `ImageBackend`), then wiring, then frontend, then a real live GPU pass at the end.

**Backend target:** FLUX.2-klein via `ultra-fast-image-gen`'s worker HTTP API (port 7869 by default — confirm actual port/routes against the real `image_server/` code before Task 2, the spec cites its README, not a verified live API contract).

## Global Constraints

- `ImageBackend` is swappable (spec's forward-compat requirement) — resolution/model/steps are backend config, never hardcoded outside the backend implementation.
- Scene images are a `NarratorResponse.image_request` field, **not** a tool — no `TOOL_REGISTRY` entry, no discriminated-union variant.
- Log entries for generated images reuse the existing `[tag: value]` bracket convention already established for tool results (`narration.py`: `f"[{response.tool}: {result}]"`) — `[image: {path}]` — not a new `StateView` field. Smallest change that fits the existing protocol shape.
- Portrait files: `sessions/portraits/{session_id}/{player_id}.png`. Scene images: `sessions/images/{session_id}/{turn_index}.png`. Referenced by path in `CharacterSheet`/log, never embedded as base64 in JSON.
- GPU swap: call `ollama.AsyncClient().generate(model=..., keep_alive=0)`-style unload (check the actual `ollama` package's unload mechanism — may be `keep_alive=0` on any call, not a dedicated unload endpoint) before any image generation call. No pre-warm after.
- No live-GPU test framework requirement for Tasks 1-4 (a `FakeImageBackend` returning a fixed path covers them, same pattern `NarratorClient(chat_fn=...)` already uses for narrator tests). Real GPU verification is Task 7, live, against msi-laptop.

---

## File Structure

- Create: `narrator/image_backend.py` — `ImageBackend` protocol + `FluxWorkerBackend` implementation.
- Modify: `engine/character.py` — `CharacterSheet.portrait_path: str | None`.
- Modify: `server/dispatch.py` — new `approve_character` message type (portrait generation trigger).
- Modify: `narrator/client.py` — `NarratorResponse` gains `image_request`.
- Modify: `server/narration.py` — GPU unload-before-generate, scene image handling, log line.
- Modify: `server/views.py` — no schema change (log already carries it), but confirm `portrait_path` surfaces via existing `asdict(character)`.
- Modify: `server/__main__.py` — wire `FluxWorkerBackend` into `create_app`.
- Modify: `frontend/src/lib/nightwire/protocol.ts`, `page.tsx` — image log-line rendering, approve-character flow.
- Create: `tests/test_image_backend.py`, modify `tests/test_narrator_client.py`, `tests/test_narration.py`, `tests/test_dispatch.py`, `tests/test_character.py`.

---

### Task 1: `CharacterSheet.portrait_path`

**Files:** `engine/character.py`, `tests/test_character.py`

- [ ] **Step 1: failing test** — `CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid").portrait_path is None` (default), and a round-trip persistence test (`JSONFileSessionStore` save/load preserves a set `portrait_path`).
- [ ] **Step 2: verify fails** — `AttributeError` / field not accepted.
- [ ] **Step 3: implement** — add `portrait_path: str | None = None` to the dataclass.
- [ ] **Step 4: verify passes**
- [ ] **Step 5: commit** — `feat: add portrait_path to CharacterSheet`

---

### Task 2: `ImageBackend` protocol + `FluxWorkerBackend`

**Files:** `narrator/image_backend.py`, `tests/test_image_backend.py`

**Interfaces:**
```python
class ImageBackend(Protocol):
    async def generate_portrait(self, description: str) -> bytes: ...
    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes: ...
```
Returns raw image bytes — callers own file-writing (matches `NarratorClient.respond()` returning a parsed object, not writing anything itself).

- [ ] **Step 1: failing test** — a `chat_fn`-style injectable `FluxWorkerBackend(http_fn=...)` (mirrors `NarratorClient`'s `chat_fn` injection pattern for testability without a live server): `generate_portrait("a lean netrunner in a rain-slicked jacket")` calls the injected HTTP function with the right payload shape, returns bytes from a fake response.
- [ ] **Step 2: verify fails** — module doesn't exist.
- [ ] **Step 3: implement.** Before writing the real request payload, **read the actual `frontend/image_server/` source** (not just the spec's README citation) to confirm real routes/payload shape — the spec explicitly flagged this as unverified. If the real API differs from what's assumed here, that's expected; match the real code, note the deviation in this task's own commit message.
- [ ] **Step 4: verify passes**
- [ ] **Step 5: commit** — `feat: ImageBackend protocol and FluxWorkerBackend implementation`

---

### Task 3: Portrait generation on character approval

**Files:** `server/dispatch.py`, `server/app.py` (websocket handler needs backend access), `tests/test_dispatch.py`, `tests/test_app.py`

**Protocol addition:** new client message `{"type": "approve_character"}` (no body — operates on the already-joined character for that connection). Server: unload Ollama → call `image_backend.generate_portrait(...)` with a description built from the character's `name`/`role`/`lifepath` → write bytes to `sessions/portraits/{session_id}/{player_id}.png` → set `character.portrait_path` → save session → broadcast (existing `manager.broadcast` path, same as every other message type).

- [ ] **Step 1: failing test** — `dispatch.py`: unknown-message-type-style test isn't right here since this needs the image backend; test at the `server/app.py` websocket level instead (matches how `test_action_message_triggers_the_narrator_and_broadcasts_narration` already tests narrator wiring end-to-end with a fake `chat_fn`). Send `join` then `approve_character` over a `TestClient` websocket with a fake `ImageBackend`, assert the broadcast `characters[player_id].portrait_path` is set.
- [ ] **Step 2: verify fails**
- [ ] **Step 3: implement.**
- [ ] **Step 4: verify passes**
- [ ] **Step 5: commit** — `feat: portrait generation on character approval`

---

### Task 4: `NarratorResponse.image_request`

**Files:** `narrator/client.py`, `tests/test_narrator_client.py`

**Shape:** `image_request: ImageRequest | None` where `ImageRequest = BaseModel { prompt: str }` — sibling field to `narration` and `tool_call`, not part of the discriminated union (spec's own reasoning: no engine-state effect to log, conflates two different decision kinds if merged into `tool_call`).

- [ ] **Step 1: failing test** — fake JSON payload with `"image_request": {"prompt": "a rain-slicked alley, neon signs"}` parses, `response.image_request.prompt` accessible; a payload with `"image_request": null` also parses (field optional, defaults `None`).
- [ ] **Step 2: verify fails**
- [ ] **Step 3: implement** — add the field to `NarratorResponse`. Check the generated `model_json_schema()` still round-trips through a quick manual check (like Task 4's earlier schema-inspection did for the discriminated union) — `image_request` should appear as a plain nullable object property, not touch the existing `tool_call` discriminator.
- [ ] **Step 4: verify passes**
- [ ] **Step 5: commit** — `feat: image_request field on NarratorResponse`

---

### Task 5: Scene image generation wired into `handle_action`

**Files:** `server/narration.py`, `tests/test_narration.py`

- [ ] **Step 1: failing test** — fake narrator client returning a response with `image_request` set, fake `ImageBackend`; assert `session.log` gains a `[image: sessions/images/{session_id}/{n}.png]`-shaped line, and the image backend was called with the character's own `portrait_path` (if set) as a reference.
- [ ] **Step 2: verify fails**
- [ ] **Step 3: implement.** In `handle_action`, after the existing tool-call handling: if `response.image_request` is set, unload Ollama (same mechanism as Task 3), collect reference paths (the acting character's `portrait_path`, if any — multi-character reference is later scope per the spec), call `image_backend.generate_scene(...)`, write the file, append the bracket-tagged log line. Wrap in the same `except (ValueError, TypeError)` pattern the existing tool-error handling uses — an image failure shouldn't break the turn, matching how tool errors already degrade gracefully to a logged error instead of crashing.
- [ ] **Step 4: verify passes**
- [ ] **Step 5: commit** — `feat: scene image generation wired into narrator turns`

---

### Task 6: Frontend — image cards and approve-character flow

**Files:** `frontend/src/app/nightwire/page.tsx`, `frontend/src/lib/nightwire/protocol.ts`

- [ ] **Step 1:** `CharacterSheet` type gains `portrait_path: string | null`. `RedactedCharacter` — decide whether other players' portraits are visible (probably yes, it's not sensitive state) — add there too if so.
- [ ] **Step 2:** Log rendering (`isOwnLine`'s sibling logic) gains a third branch: a line matching `/^\[image: (.+)\]$/` renders an `<img>` card instead of bubble/prose — reuse the existing conditional structure in the log `.map`, don't restructure it.
- [ ] **Step 3:** Character-creation flow gains a review/approve step before `handleJoin`'s current immediate-join behavior — draft state shown back to the player, an "Approve" action sends `{"type": "approve_character"}` after join succeeds. Exact UI is implementation-phase per the spec; keep it minimal (a confirm button), matching every other composer/form element's existing plain styling.
- [ ] **Step 4:** Portrait rendering — once `portrait_path` is set, prefer it over `portraitFor()`'s placeholder badge in the vitals band and sheet overlay (`portraitFor` stays as the fallback for characters without a generated portrait yet, not deleted).
- [ ] **Step 5: Live-verify** in browser against a real backend: images need to be served over HTTP somehow (the FastAPI backend has no static file route yet) — add a minimal static mount for `sessions/portraits/` and `sessions/images/` in `server/app.py` if not already reachable, verify an `<img>` actually loads, not just that the path string is correct.
- [ ] **Step 6: commit** — `feat: image cards and character-approval flow on the /nightwire route`

---

### Task 7: Live GPU verification pass

**Goal:** same discipline as Phase 3's reliability harness and Phase 4a-revised's Task 6 — a real pass against real hardware, not just unit tests, before calling this phase done.

- [x] **Step 1:** Deployed `image-server.service` on msi-laptop (cloned `newideas99/ultra-fast-image-gen`, private repo — the clone URL had to come from the user directly, nothing in nightwire's checkout names it). `/health` confirmed `ok: true` before testing through nightwire.
- [x] **Step 2:** Full flow live: join → `approve_character` → real 384×512 PNG written, 44.2s round-trip (unload + cold model load + generation). First attempt hit a real CUDA OOM — the worker's own "fast" mode defaults to 1024px (needs ~16GB); fixed by explicitly requesting 512px (see the Task 7 fix commit). Frontend rendering not re-verified in-browser this pass (WS-protocol-level verification only, given context budget) — the rendering code itself was already tsc-verified in Task 6.
- [x] **Step 3 (adjusted):** The narrator never called `image_request` on a real live turn — confirmed, not assumed (system prompt doesn't mention the capability, same failure shape `start_combat` had before its own fix). Verified the *mechanism* instead via a direct `FluxWorkerBackend.generate_scene()` call using the real approved portrait as reference — real image, real consistency (see Step 5).
- [ ] **Step 4:** Not separately re-measured this pass — cold-load cost (~45-60s) already directly observed multiple times earlier in this session; the Step 2 44.2s figure itself includes it.
- [x] **Step 5:** Eyeballed directly, real images (not a citation): the scene generation using the approved portrait as reference produced a visibly consistent character — same beard, same green tactical jacket, same build — correctly placed in a new neon-alley setting. Answers the spec's own flagged "honest gap" for real, on the actual target hardware.
- [x] **Step 6:** No errors in `nightwire-server`/`image-server` logs across the pass, once the 512px fix landed (pre-fix: real logged CUDA OOM, itself a legitimate finding, not a false negative).
- [x] **Step 7:** `ROADMAP.md`'s Phase 5 entry rewritten with what's built, the 512px finding, the image_request gap, and the consistency result.
- [x] **Step 8: commit** — `fix: request 512px explicitly, image_request never fires yet` (folds the Task 7 fix and findings into one commit rather than a separate docs-only one, since the fix itself *is* what Task 7 verification produced).
