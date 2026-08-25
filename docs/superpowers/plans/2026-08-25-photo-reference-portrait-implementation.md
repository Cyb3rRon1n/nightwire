# Photo-Reference Portrait Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a player optionally upload 1-2 photos of themselves in the existing "Approve & Generate Portrait" flow, forwarded in-memory to the FLUX image worker as reference images and never written to server disk — plus fix a real pre-existing bug in that same flow where a worker error leaves the "Generating…" button stuck forever.

**Architecture:** Backend first (widen `FluxWorkerBackend.generate_portrait` to accept inline base64 reference photos, then validate and wire them through `handle_approve_character`), then frontend (upload UI, client-side downscale, protocol wiring, and the stuck-button fix), then one live pass against the real running stack — same order Phase 5's own image-generation plan used.

**Tech Stack:** Python (FastAPI/pytest, existing `ImageBackend` protocol), TypeScript/React (existing `page.tsx`/`protocol.ts`), no new dependencies on either side.

**Spec:** `docs/superpowers/specs/2026-08-25-photo-reference-portrait-design.md` — read it first.

## Global Constraints

- Uploaded reference photos are never written to server disk at any point — validated in memory, forwarded to the image worker inline, discarded when the request completes.
- At most 2 reference photos per portrait request — matches `_MAX_REFERENCES` in `narrator/image_backend.py`, the FLUX worker's own hard cap (`prepare_reference_paths` only ever reads `references[:2]`).
- Each reference photo capped at 4MB decoded size; allowed types `image/png`, `image/jpeg`, `image/webp` — matches the existing `frontend/src/app/api/upload/route.ts` allowlist, reused for consistency rather than inventing a new one.
- No "your own face" verification of any kind — plain label copy only, per the spec's explicit scope decision. Do not add a checkbox or any enforcement.
- The upload is strictly optional — the existing text-only portrait flow (no photos, or "Skip for now") is unchanged.

---

## File Structure

- Modify: `narrator/image_backend.py` — `ImageBackend` protocol + `FluxWorkerBackend.generate_portrait` accepts inline reference photos (data URLs), alongside the existing file-path references `generate_scene` already uses.
- Modify: `server/portrait.py` — `_validate_reference_photos` (new), `handle_approve_character` widened to read and forward them.
- Modify: `server/app.py` — pass the incoming `message` dict to `handle_approve_character` (currently doesn't).
- Modify: `frontend/src/lib/nightwire/protocol.ts` — `ApproveCharacterMessage` gains `reference_photos?: string[]`.
- Modify: `frontend/src/app/nightwire/page.tsx` — upload control in the portrait-approval banner, client-side downscale helper, wiring into `handleApprovePortrait`, and the stuck-button effect-dependency fix.
- Modify: `tests/test_image_backend.py`, `tests/test_portrait.py`, `tests/test_app.py`.

---

### Task 1: `FluxWorkerBackend` accepts inline reference photos for portraits

**Files:**
- Modify: `narrator/image_backend.py`
- Test: `tests/test_image_backend.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ImageBackend.generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes` — `reference_photos` is a list of already-formed data URL strings (e.g. `"data:image/png;base64,..."`), forwarded to the worker as-is (not read from disk, unlike `reference_paths`). Task 2 depends on this exact parameter name and shape.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_image_backend.py`, after the existing `test_generate_portrait_calls_http_fn_with_no_references` test:

```python
@pytest.mark.asyncio
async def test_generate_portrait_encodes_reference_photos_as_provided_data_urls(tmp_path):
    (tmp_path / "img4.png").write_bytes(b"fake-portrait-bytes")
    seen = {}
    backend = FluxWorkerBackend(
        output_dir=tmp_path,
        http_fn=_fake_http_fn({"id": "img4"}, seen),
    )

    result = await backend.generate_portrait(
        "a lean netrunner",
        reference_photos=["data:image/png;base64,QUJD"],
    )

    assert result == b"fake-portrait-bytes"
    assert seen["payload"]["references"] == [{"dataUrl": "data:image/png;base64,QUJD"}]


@pytest.mark.asyncio
async def test_generate_portrait_only_sends_the_first_two_reference_photos(tmp_path):
    (tmp_path / "img5.png").write_bytes(b"x")
    seen = {}
    backend = FluxWorkerBackend(output_dir=tmp_path, http_fn=_fake_http_fn({"id": "img5"}, seen))
    photos = [f"data:image/png;base64,PHOTO{i}" for i in range(3)]

    await backend.generate_portrait("a fixer", reference_photos=photos)

    assert seen["payload"]["references"] == [{"dataUrl": photos[0]}, {"dataUrl": photos[1]}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_image_backend.py -v`
Expected: the two new tests FAIL with `TypeError: generate_portrait() got an unexpected keyword argument 'reference_photos'`. All prior tests in the file still PASS unchanged.

- [ ] **Step 3: Implement**

In `narrator/image_backend.py`, replace the `ImageBackend` protocol's `generate_portrait` line:

```python
class ImageBackend(Protocol):
    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes: ...
    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes: ...
```

Replace `_generate`, `generate_portrait`, and `generate_scene` on `FluxWorkerBackend`:

```python
    async def _generate(
        self,
        prompt: str,
        aspect: str,
        reference_paths: list[str] | None = None,
        reference_photos: list[str] | None = None,
    ) -> bytes:
        from_paths = [self._to_data_url(p) for p in (reference_paths or [])]
        from_photos = [{"dataUrl": url} for url in (reference_photos or [])]
        references = (from_paths + from_photos)[:_MAX_REFERENCES]
        width, height = self._dimensions_for(aspect)
        payload = {
            "backend": self.backend,
            "prompt": prompt,
            "aspect": aspect,
            "width": width,
            "height": height,
            "references": references,
        }
        result = await self._http_fn(payload)
        return (self.output_dir / f"{result['id']}.png").read_bytes()

    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes:
        return await self._generate(description, aspect="portrait", reference_photos=reference_photos)

    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes:
        return await self._generate(prompt, aspect="square", reference_paths=reference_paths)
```

This is a pure widening: `reference_paths` (file paths, read from disk via `_to_data_url`) and `reference_photos` (already-formed data URLs, used as-is) are combined and truncated to `_MAX_REFERENCES` the same way scene generation's paths already were — `generate_scene`'s behavior and all its existing tests are unaffected, since it never passes `reference_photos`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_image_backend.py -v`
Expected: all tests PASS, including the two new ones and the three pre-existing ones (`test_generate_portrait_calls_http_fn_with_no_references`, `test_generate_scene_encodes_reference_files_as_data_urls`, `test_generate_scene_only_sends_the_first_two_references`).

- [ ] **Step 5: Commit**

```bash
git add narrator/image_backend.py tests/test_image_backend.py
git commit -m "feat: FluxWorkerBackend.generate_portrait accepts inline reference photos"
```

---

### Task 2: Validate and wire `reference_photos` through `approve_character`

**Files:**
- Modify: `server/portrait.py`
- Modify: `server/app.py`
- Test: `tests/test_portrait.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `ImageBackend.generate_portrait(description, reference_photos=...)` from Task 1.
- Produces: `_validate_reference_photos(raw: object) -> list[str]` (raises `ValueError` on any invalid input, returns `[]` for `None`) — a pure function, independently testable. `handle_approve_character` gains a required `message: dict` parameter (the raw incoming websocket message), matching the shape `server/narration.py`'s `handle_action` already receives.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_portrait.py` (add `import base64` and `pytest` at the top, and `_validate_reference_photos` to the import from `server.portrait`):

```python
import base64

import pytest

from engine.character import CharacterSheet
from server.portrait import _build_portrait_prompt, _validate_reference_photos


def _data_url(raw_bytes: bytes, media_type: str = "image/png") -> str:
    encoded = base64.b64encode(raw_bytes).decode()
    return f"data:{media_type};base64,{encoded}"


def test_no_reference_photos_returns_empty_list():
    assert _validate_reference_photos(None) == []


def test_valid_reference_photos_pass_through_unchanged():
    url = _data_url(b"fake-png-bytes")
    assert _validate_reference_photos([url]) == [url]


def test_more_than_two_reference_photos_is_rejected():
    urls = [_data_url(b"a"), _data_url(b"b"), _data_url(b"c")]
    with pytest.raises(ValueError, match="at most 2"):
        _validate_reference_photos(urls)


def test_non_list_reference_photos_is_rejected():
    with pytest.raises(ValueError, match="must be a list"):
        _validate_reference_photos("not-a-list")


def test_non_string_entry_is_rejected():
    with pytest.raises(ValueError, match="must be a string"):
        _validate_reference_photos([123])


def test_malformed_data_url_is_rejected():
    with pytest.raises(ValueError, match="base64 data URL"):
        _validate_reference_photos(["not-a-data-url"])


def test_disallowed_image_type_is_rejected():
    url = _data_url(b"fake-gif-bytes", media_type="image/gif")
    with pytest.raises(ValueError, match="unsupported image type"):
        _validate_reference_photos([url])


def test_invalid_base64_payload_is_rejected():
    with pytest.raises(ValueError, match="invalid base64"):
        _validate_reference_photos(["data:image/png;base64,not-valid-base64!!"])


def test_oversized_reference_photo_is_rejected():
    oversized = b"x" * (4 * 1024 * 1024 + 1)
    url = _data_url(oversized)
    with pytest.raises(ValueError, match="exceeds"):
        _validate_reference_photos([url])
```

(The two existing tests in this file, `test_known_role_and_lifepath_get_visual_tags` and `test_unknown_role_and_lifepath_fall_back_to_plain_description`, are untouched.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_portrait.py -v`
Expected: the new tests FAIL with `ImportError: cannot import name '_validate_reference_photos'`. The two pre-existing tests still PASS.

- [ ] **Step 3: Implement `_validate_reference_photos` and wire it into `handle_approve_character`**

In `server/portrait.py`, add `import base64` at the top, add these constants and function after `_LIFEPATH_VISUALS` and before `_build_portrait_prompt`:

```python
_MAX_REFERENCE_PHOTOS = 2
_MAX_REFERENCE_PHOTO_BYTES = 4 * 1024 * 1024
_ALLOWED_REFERENCE_PHOTO_TYPES = ("image/png", "image/jpeg", "image/webp")


def _validate_reference_photos(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"reference_photos must be a list, got {type(raw).__name__}")
    if len(raw) > _MAX_REFERENCE_PHOTOS:
        raise ValueError(f"reference_photos: at most {_MAX_REFERENCE_PHOTOS} photos allowed, got {len(raw)}")
    for photo in raw:
        if not isinstance(photo, str):
            raise ValueError(f"reference_photos: each entry must be a string, got {type(photo).__name__}")
        header, sep, encoded = photo.partition(",")
        if not sep or not header.startswith("data:") or ";base64" not in header:
            raise ValueError("reference_photos: each entry must be a base64 data URL (data:image/...;base64,...)")
        media_type = header[len("data:"):header.index(";")]
        if media_type not in _ALLOWED_REFERENCE_PHOTO_TYPES:
            raise ValueError(f"reference_photos: unsupported image type {media_type!r}")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except ValueError as e:
            raise ValueError(f"reference_photos: invalid base64 data: {e}") from e
        if not decoded:
            raise ValueError("reference_photos: image data is empty")
        if len(decoded) > _MAX_REFERENCE_PHOTO_BYTES:
            raise ValueError(
                f"reference_photos: image is {len(decoded)} bytes, exceeds {_MAX_REFERENCE_PHOTO_BYTES} byte limit"
            )
    return raw
```

Replace `handle_approve_character`'s signature and body:

```python
async def handle_approve_character(
    session: Session,
    store: JSONFileSessionStore,
    narrator_client: NarratorClient,
    image_backend: ImageBackend,
    player_id: str,
    message: dict,
) -> None:
    if player_id not in session.characters:
        raise ValueError(f"no joined character for player_id {player_id!r}")
    character = session.characters[player_id]
    reference_photos = _validate_reference_photos(message.get("reference_photos"))

    description = _build_portrait_prompt(character)
    await narrator_client.unload()
    image_bytes = await image_backend.generate_portrait(description, reference_photos=reference_photos)

    relative_path = f"portraits/{session.session_id}/{player_id}.png"
    output_path = store.directory / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image_bytes)

    character.portrait_path = relative_path
```

In `server/app.py`, update the call site (currently line 60) to pass `message`:

```python
                    elif message.get("type") == "approve_character":
                        await handle_approve_character(session, store, narrator_client, image_backend, player_id, message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_portrait.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 5: Update `tests/test_app.py` for the new signature, then write and verify its new tests**

`handle_approve_character` now always calls `image_backend.generate_portrait(description, reference_photos=...)` with a keyword argument, so every `ImageBackend`-shaped test stub needs to accept it. Widen both existing stubs' `generate_portrait` signature:

In `_UnusedImageBackend` (near the top of the file):
```python
class _UnusedImageBackend:
    async def generate_portrait(self, description, reference_photos=None):
        raise AssertionError("image backend should not be called by this test")

    async def generate_scene(self, prompt, reference_paths):
        raise AssertionError("image backend should not be called by this test")
```

In the local `FakeImageBackend` inside `test_approve_character_generates_and_broadcasts_a_portrait`:
```python
    class FakeImageBackend:
        async def generate_portrait(self, description, reference_photos=None):
            assert "Rook" in description
            return b"fake-portrait-bytes"

        async def generate_scene(self, prompt, reference_paths):
            raise AssertionError("not exercised by this test")
```

Add `import base64` near the top of `tests/test_app.py` (alongside the existing `import json`), then add these two new tests after `test_approve_character_without_a_joined_character_sends_an_error`:

```python
def test_approve_character_with_reference_photos_forwards_them_to_the_image_backend(tmp_path):
    generate_calls = []

    async def generate_fn(**kwargs):
        generate_calls.append(kwargs)

    narrator_client = NarratorClient(chat_fn=_unused_chat_fn, generate_fn=generate_fn)
    photo_url = "data:image/png;base64," + base64.b64encode(b"fake-face-bytes").decode()
    seen = {}

    class FakeImageBackend:
        async def generate_portrait(self, description, reference_photos=None):
            seen["reference_photos"] = reference_photos
            return b"fake-portrait-bytes"

        async def generate_scene(self, prompt, reference_paths):
            raise AssertionError("not exercised by this test")

    client = _client(tmp_path, narrator_client, FakeImageBackend())

    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "approve_character", "reference_photos": [photo_url]})
        view = ws.receive_json()

    assert seen["reference_photos"] == [photo_url]
    assert view["characters"]["p1"]["portrait_path"] is not None


def test_approve_character_with_too_many_reference_photos_sends_an_error(tmp_path):
    client = _client(tmp_path)  # default _UnusedImageBackend proves it's never called
    with client.websocket_connect("/ws/s1/p1") as ws:
        ws.send_json({
            "type": "join",
            "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
        })
        ws.receive_json()

        ws.send_json({"type": "approve_character", "reference_photos": ["a", "b", "c"]})
        error = ws.receive_json()

    assert error["type"] == "error"
    assert "at most 2" in error["message"]
```

- [ ] **Step 6: Run the full backend test suite**

Run: `pytest -q`
Expected: all tests pass (191 pre-existing + 2 from Task 1 + 10 from this task's `test_portrait.py` additions + 2 from this task's `test_app.py` additions = 205 total; exact pre-existing count may drift slightly from the codebase's current state, but there must be zero failures and zero errors).

- [ ] **Step 7: Commit**

```bash
git add server/portrait.py server/app.py tests/test_portrait.py tests/test_app.py
git commit -m "feat: validate and forward reference_photos through approve_character"
```

---

### Task 3: Frontend upload UI, protocol wiring, and the stuck-button fix

**Files:**
- Modify: `frontend/src/lib/nightwire/protocol.ts`
- Modify: `frontend/src/app/nightwire/page.tsx`

**Interfaces:**
- Consumes: the `reference_photos` field wired server-side in Task 2. No frontend automated test infrastructure exists for file-upload/`FileReader` flows in this repo (confirmed in the spec) — this task is verified live against the real running stack, the same pattern every prior phase in this project used (see `ROADMAP.md`'s Phase 4-7 entries).

This is a real, pre-existing bug in the exact flow this task touches: `page.tsx`'s effect that resets `approvingPortrait` (and `sending`/`combatActionPending`) back to `false` is keyed on `[view]` only. The socket reducer (`frontend/src/lib/nightwire/reducer.ts`) leaves `view` unchanged when an `error` message arrives — it only updates `state.error`. So if `approve_character` triggers a server-side error (e.g. the image worker returning a `500`), the error text renders (`page.tsx` already reads `error` from the hook and displays it), but the button stays stuck on "Generating…" forever, because the reset effect never re-fires. Live-verified during this project's own earlier session work.

- [ ] **Step 1: Add `reference_photos` to the protocol type**

In `frontend/src/lib/nightwire/protocol.ts`, replace:

```typescript
export interface ApproveCharacterMessage {
  type: 'approve_character'
}
```

with:

```typescript
export interface ApproveCharacterMessage {
  type: 'approve_character'
  reference_photos?: string[]
}
```

- [ ] **Step 2: Add the client-side downscale helper**

In `frontend/src/app/nightwire/page.tsx`, add this function near the other module-level pure helpers (e.g. right after `formatComposerInput`):

```typescript
// Downscales an uploaded reference photo client-side before sending it
// inline over the websocket - full phone-camera resolution buys nothing for
// a reference image and bloats the message (see docs/superpowers/specs/
// 2026-08-25-photo-reference-portrait-design.md).
async function fileToResizedDataUrl(file: File, maxDimension: number): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d context unavailable");
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", 0.85);
}
```

- [ ] **Step 3: Add state and handlers inside `NightwirePage`**

Add this state declaration right after the existing `const [portraitSkipped, setPortraitSkipped] = useState(false);` line:

```typescript
  const [referencePhotos, setReferencePhotos] = useState<string[]>([]);
```

Add these two functions right after `handleApprovePortrait`'s current definition (which you'll also modify in Step 4):

```typescript
  async function handleReferencePhotosSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []).slice(0, 2 - referencePhotos.length);
    event.target.value = "";
    for (const file of files) {
      try {
        const dataUrl = await fileToResizedDataUrl(file, 1024);
        setReferencePhotos((photos) => [...photos, dataUrl].slice(0, 2));
      } catch {
        // Unreadable/corrupt image - skip it, the upload is optional.
      }
    }
  }

  function handleRemoveReferencePhoto(index: number) {
    setReferencePhotos((photos) => photos.filter((_, i) => i !== index));
  }
```

- [ ] **Step 4: Wire `reference_photos` into `handleApprovePortrait`**

Replace the existing `handleApprovePortrait` function body:

```typescript
  function handleApprovePortrait() {
    send({
      type: "approve_character",
      ...(referencePhotos.length > 0 ? { reference_photos: referencePhotos } : {}),
    });
    setApprovingPortrait(true);
  }
```

- [ ] **Step 5: Fix the stuck-button bug**

Replace the effect's dependency array:

```typescript
  useEffect(() => {
    setSending(false);
    setApprovingPortrait(false);
    setCombatActionPending(false);
  }, [view, error]);
```

(This is the only change to this effect — `error` added to the dependency array so an error-only message, which leaves `view` unchanged per `reducer.ts`, still clears the pending states.)

- [ ] **Step 6: Add the upload control to the portrait-approval banner JSX**

Insert this block between the existing `<p className="nw-text-body">...Generate a portrait before playing?</p>` and the `<div className="flex gap-2">` button row (inside the portrait-approval banner's outer `<div className="nw-divider flex flex-col gap-2 rounded-lg border p-3 text-sm">`):

```jsx
                <div className="flex flex-col gap-1">
                  <label className="nw-hud text-xs nw-text-muted">
                    Optional — upload 1–2 photos of yourself to guide your portrait&apos;s likeness. Photos are sent once to generate your portrait and are not stored.
                  </label>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    multiple
                    onChange={handleReferencePhotosSelected}
                    disabled={approvingPortrait || referencePhotos.length >= 2}
                    className="nw-field text-xs"
                  />
                  {referencePhotos.length > 0 && (
                    <div className="flex gap-2">
                      {referencePhotos.map((photo, i) => (
                        <div key={i} className="relative">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={photo} alt="" className="size-14 rounded object-cover" />
                          <button
                            type="button"
                            onClick={() => handleRemoveReferencePhoto(i)}
                            className="nw-btn-ghost absolute -right-1 -top-1 flex size-4 items-center justify-center rounded-full p-0 text-[10px] leading-none"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
```

- [ ] **Step 7: Type-check and lint**

Run: `npx tsc --noEmit -p tsconfig.json` from `frontend/`
Expected: no output (clean).

Run: `npx eslint src/app/nightwire/page.tsx src/lib/nightwire/protocol.ts` from `frontend/`
Expected: only the pre-existing `react-hooks/set-state-in-effect` warning on the same effect (unrelated to this change, already present before this task) — no new errors.

- [ ] **Step 8: Live-verify against the real running stack**

Sync the three changed files to the GPU box, restart `nightwire-server` (backend changed in Tasks 1-2), leave the frontend dev server's hot-reload to pick up `page.tsx`/`protocol.ts` automatically:

```bash
scp -i ~/.ssh/nightwire_remote narrator/image_backend.py sentinel@100.67.87.32:~/projects/github/repos/nightwire/narrator/image_backend.py
scp -i ~/.ssh/nightwire_remote server/portrait.py sentinel@100.67.87.32:~/projects/github/repos/nightwire/server/portrait.py
scp -i ~/.ssh/nightwire_remote server/app.py sentinel@100.67.87.32:~/projects/github/repos/nightwire/server/app.py
ssh -i ~/.ssh/nightwire_remote sentinel@100.67.87.32 "systemctl --user restart nightwire-server"
scp -i ~/.ssh/nightwire_remote frontend/src/lib/nightwire/protocol.ts sentinel@100.67.87.32:~/projects/github/repos/nightwire/frontend/src/lib/nightwire/protocol.ts
scp -i ~/.ssh/nightwire_remote frontend/src/app/nightwire/page.tsx sentinel@100.67.87.32:~/projects/github/repos/nightwire/frontend/src/app/nightwire/page.tsx
```

(If the frontend dev server isn't already running, start it the same way established earlier this session: `nohup npm run dev > /tmp/nightwire-frontend.log 2>&1 &` from `~/projects/github/repos/nightwire/frontend`, and open an SSH tunnel `-L 3000:localhost:3000 -L 8000:localhost:8000` to reach it from the local browser.)

Using browser automation against the tunneled frontend, verify all of the following in one session:

1. Join a fresh character. The portrait-approval banner shows the new upload control and label copy, with no photos selected yet.
2. Select 2 valid image files (e.g. two small PNGs/JPEGs). Both thumbnails appear; the file input becomes disabled (2/2 already selected).
3. Remove one photo via its `×` button — one thumbnail remains, the file input re-enables.
4. Click "Approve & Generate Portrait" with 1 photo selected. Confirm (via `read_network_requests` or server-side `journalctl` on `nightwire-server`) the outgoing `approve_character` websocket message includes `reference_photos` with exactly one data URL, and that generation completes normally (portrait appears, same as the pre-existing text-only flow).
5. **Verify the stuck-button fix specifically**: trigger a real image-worker error (e.g. temporarily stop the `image-server` systemd unit on the GPU box, or reuse whatever produced the live `500` observed earlier this session) and click "Approve & Generate Portrait". Confirm the error text renders (as it already did before this change) **and** the button returns to "Approve & Generate Portrait" (not stuck on "Generating…"), re-enabled and clickable again. Restart `image-server` afterward if you stopped it.
6. Confirm the pre-existing skip-photos path still works unchanged: join a second character, click "Approve & Generate Portrait" with zero photos selected, confirm it succeeds exactly as before this change (no `reference_photos` field sent at all, per Step 4's spread-conditional).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/nightwire/protocol.ts frontend/src/app/nightwire/page.tsx
git commit -m "feat: optional photo-reference upload for portrait generation, fix stuck Generating… button on worker error"
```

---

## Self-review notes

- **Spec coverage**: fidelity/retention/scope decisions from the spec are all structural consequences of Task 1-2's design (data URLs only, never disk-written, capped at 2/4MB/allowed-types) — no separate task needed for them. UI placement (existing banner, no new screen) is Task 3. The folded-in bug fix is Task 3 Step 5.
- **Type consistency checked**: `reference_photos: list[str] | None = None` (Python, Task 1) ↔ `reference_photos?: string[]` (TypeScript, Task 3) ↔ `message.get("reference_photos")` read as `object` and validated (Task 2) — same field name end to end, matching this project's established pattern of keeping protocol field names identical across the Python/TypeScript boundary rather than translating them.
- **No placeholders**: every step above has real code, not a description of intent.
