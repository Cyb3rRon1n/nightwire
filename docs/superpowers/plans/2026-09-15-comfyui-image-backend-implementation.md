# ComfyUI Image Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second `ImageBackend` implementation that talks to a real ComfyUI instance over HTTP, selectable via `IMAGE_BACKEND=comfyui`, so nightwire's Docker/Linux deployment (its primary shape) has a working image-generation path — `FluxWorkerBackend` is MLX-only and cannot run there at all.

**Architecture:** New `narrator/comfyui_backend.py` implements the existing `ImageBackend` Protocol by submitting a ComfyUI workflow graph (`POST /prompt`), polling `GET /history/{prompt_id}` until the generation completes, then fetching the image bytes (`GET /view`). A new `create_image_backend()` factory in `narrator/image_backend.py` selects between `FluxWorkerBackend` and `ComfyUIBackend` from the `IMAGE_BACKEND` env var, replacing the hardcoded construction in `server/__main__.py`.

**Tech Stack:** Python 3.11+, `httpx` (already a dependency — no new dependency needed; see Global Constraints).

**Spec:** `docs/superpowers/specs/2026-09-15-comfyui-image-backend-design.md`

## Global Constraints

- `IMAGE_BACKEND` env var: `flux_worker` (default, preserves current behavior) or `comfyui`. Unknown values raise `ValueError`.
- `COMFYUI_URL` default `http://192.168.10.19:8188` — sentinel's real, live-verified address. **DHCP-assigned, has already changed once** — must stay a config default, never hardcoded elsewhere.
- `COMFYUI_CHECKPOINT` default `v1-5-pruned-emaonly-fp16.safetensors` — the real checkpoint confirmed loaded on sentinel's instance.
- Resolution: 512×768 for `generate_portrait`, 512×512 for `generate_scene` (oracle's own proven-working defaults for an 8GB card at SD1.5).
- `ComfyUIBackend` must implement `narrator.image_backend.ImageBackend` exactly: `generate_portrait(description: str, reference_photos: list[str] | None = None) -> bytes`, `generate_scene(prompt: str, reference_paths: list[str]) -> bytes`.
- **No IPAdapter/reference-photo support.** `reference_photos`/`reference_paths` are accepted (protocol compliance) but never used — sentinel's real ComfyUI install has no face-consistency custom node (confirmed live). This must be visible in code as a comment, not silent.
- **No new dependency.** Oracle's own `ComfyUIBackend` uses `websockets` for real-time progress — nightwire's `ImageBackend` protocol has no progress-callback parameter at all (confirmed: neither `generate_portrait` nor `generate_scene` takes one), so there's nothing to feed real-time progress into. Poll `GET /history/{prompt_id}` on a plain interval instead — `httpx` alone covers it, no new dependency earns its place here (ladder rung 5: don't add a dependency for what a few lines of polling already does).
- Every constructor argument that varies by test (HTTP client, sleep function) must be injectable, matching `FluxWorkerBackend`'s existing `http_fn` DI pattern in this same file — keeps unit tests free of real network calls or real sleeps.

---

## File Structure

- **Create** `narrator/comfyui_backend.py` — `ComfyUIBackend` class: workflow-graph construction, submit/poll/fetch cycle.
- **Modify** `narrator/image_backend.py` — add `import os`, import `ComfyUIBackend`, add `create_image_backend()` factory function at the bottom.
- **Modify** `server/__main__.py` — replace the hardcoded `FluxWorkerBackend(...)` construction with `create_image_backend()`.
- **Create** `tests/test_comfyui_backend.py` — unit tests for `ComfyUIBackend` against a fake HTTP client.
- **Modify** `tests/test_image_backend.py` — add tests for `create_image_backend()`.

---

### Task 1: ComfyUIBackend

**Files:**
- Create: `narrator/comfyui_backend.py`
- Test: `tests/test_comfyui_backend.py`

**Interfaces:**
- Produces: `ComfyUIBackend` class in `narrator/comfyui_backend.py`, constructor `ComfyUIBackend(base_url: str = "http://127.0.0.1:8188", checkpoint: str = "v1-5-pruned-emaonly-fp16.safetensors", timeout: float = 120.0, poll_interval: float = 1.0, client: httpx.AsyncClient | None = None, sleep_fn: Callable[[float], Awaitable[None]] | None = None)`, methods `async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes` and `async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes`.

- [ ] **Step 1: Write the failing tests for the happy path**

Create `tests/test_comfyui_backend.py`:

```python
import pytest

from narrator.comfyui_backend import ComfyUIBackend


class _FakeResponse:
    def __init__(self, json_data=None, content=b""):
        self._json_data = json_data
        self.content = content

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _FakeComfyClient:
    """Stands in for httpx.AsyncClient - only the methods ComfyUIBackend
    actually calls (post, get), duck-typed to httpx's own response shape."""

    def __init__(self, prompt_id="abc123", history=None, image_bytes=b"fake-comfyui-png"):
        self.prompt_id = prompt_id
        self.history = history if history is not None else {
            "abc123": {
                "outputs": {
                    "9": {"images": [{"filename": "nightwire_00001_.png", "subfolder": "", "type": "output"}]}
                }
            }
        }
        self.image_bytes = image_bytes
        self.calls = []

    async def post(self, url, json=None):
        self.calls.append(("post", url, json))
        return _FakeResponse(json_data={"prompt_id": self.prompt_id})

    async def get(self, url, params=None):
        self.calls.append(("get", url, params))
        if url.startswith("/history/"):
            return _FakeResponse(json_data=self.history)
        if url == "/view":
            return _FakeResponse(content=self.image_bytes)
        raise AssertionError(f"unexpected GET {url}")


async def _no_sleep(seconds):
    pass


@pytest.mark.asyncio
async def test_generate_portrait_returns_fetched_image_bytes():
    client = _FakeComfyClient(image_bytes=b"portrait-bytes")
    backend = ComfyUIBackend(checkpoint="v1-5-pruned-emaonly-fp16.safetensors", client=client, sleep_fn=_no_sleep)

    result = await backend.generate_portrait("a lean netrunner in a rain-slicked jacket")

    assert result == b"portrait-bytes"


@pytest.mark.asyncio
async def test_generate_portrait_builds_correct_workflow_graph():
    client = _FakeComfyClient()
    backend = ComfyUIBackend(checkpoint="v1-5-pruned-emaonly-fp16.safetensors", client=client, sleep_fn=_no_sleep)

    await backend.generate_portrait("a lean netrunner")

    submit_calls = [c for c in client.calls if c[0] == "post"]
    assert len(submit_calls) == 1
    _, url, payload = submit_calls[0]
    assert url == "/prompt"
    nodes = payload["prompt"]
    assert nodes["4"]["class_type"] == "CheckpointLoaderSimple"
    assert nodes["4"]["inputs"]["ckpt_name"] == "v1-5-pruned-emaonly-fp16.safetensors"
    assert nodes["6"]["inputs"]["text"] == "a lean netrunner"
    assert nodes["5"]["inputs"]["width"] == 512
    assert nodes["5"]["inputs"]["height"] == 768
    assert nodes["9"]["class_type"] == "SaveImage"


@pytest.mark.asyncio
async def test_generate_scene_uses_square_dimensions():
    client = _FakeComfyClient()
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep)

    await backend.generate_scene("a rain-slicked alley, neon signs", reference_paths=[])

    submit_calls = [c for c in client.calls if c[0] == "post"]
    nodes = submit_calls[0][2]["prompt"]
    assert nodes["5"]["inputs"]["width"] == 512
    assert nodes["5"]["inputs"]["height"] == 512
    assert nodes["6"]["inputs"]["text"] == "a rain-slicked alley, neon signs"


@pytest.mark.asyncio
async def test_generate_portrait_fetches_the_view_with_history_image_info():
    client = _FakeComfyClient(
        prompt_id="xyz",
        history={
            "xyz": {"outputs": {"9": {"images": [{"filename": "shot.png", "subfolder": "sub", "type": "output"}]}}}
        },
    )
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep)

    await backend.generate_portrait("a fixer")

    view_calls = [c for c in client.calls if c[0] == "get" and c[1] == "/view"]
    assert len(view_calls) == 1
    assert view_calls[0][2] == {"filename": "shot.png", "subfolder": "sub", "type": "output"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_comfyui_backend.py -v`
Expected: `FAIL` / `ERROR` — `ModuleNotFoundError: No module named 'narrator.comfyui_backend'`

- [ ] **Step 3: Implement `ComfyUIBackend`**

Create `narrator/comfyui_backend.py`:

```python
import time
import uuid
from collections.abc import Awaitable, Callable

import httpx

_NEGATIVE_PROMPT = "blurry, deformed, extra limbs, bad anatomy, watermark, text, low quality"
_STEPS = 20
_CFG = 7.0
_SAMPLER = "euler"
_SCHEDULER = "normal"
_PORTRAIT_SIZE = (512, 768)
_SCENE_SIZE = (512, 512)


class ComfyUIBackend:
    """Talks to a real ComfyUI instance's HTTP API - workflow-graph shape
    (CheckpointLoaderSimple -> two CLIPTextEncode -> EmptyLatentImage ->
    KSampler -> VAEDecode -> SaveImage) and the submit/fetch sequence are a
    technical reference from oracle's own working ComfyUIBackend (the same
    external tool's API, not a design decision being copied).

    Polls GET /history instead of the websocket progress stream oracle's
    version uses - nightwire's ImageBackend protocol has no progress
    callback to feed, so there's nothing to stream to; polling avoids a
    new dependency (websockets) for a capability nothing would use.

    No reference-photo/img2img support - the real ComfyUI instance this
    targets (sentinel, verified live) has no IPAdapter/InstantID custom
    node installed. reference_photos/reference_paths are accepted (protocol
    compliance) and silently ignored - a known, documented limitation
    (see the Phase 10 design spec), not an oversight.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        checkpoint: str = "v1-5-pruned-emaonly-fp16.safetensors",
        timeout: float = 120.0,
        poll_interval: float = 1.0,
        client: httpx.AsyncClient | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.checkpoint = checkpoint
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=30.0)
        if sleep_fn is not None:
            self._sleep = sleep_fn
        else:
            import asyncio

            self._sleep = asyncio.sleep

    def _build_workflow(self, prompt: str, seed: int, width: int, height: int, filename_prefix: str) -> dict:
        return {
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self.checkpoint}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": _NEGATIVE_PROMPT, "clip": ["4", 1]}},
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": _STEPS,
                    "cfg": _CFG,
                    "sampler_name": _SAMPLER,
                    "scheduler": _SCHEDULER,
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}},
        }

    async def _generate(self, prompt: str, width: int, height: int, filename_prefix: str) -> bytes:
        seed = uuid.uuid4().int & 0xFFFFFFFF
        workflow = self._build_workflow(prompt, seed, width, height, filename_prefix)

        submit = await self._client.post("/prompt", json={"prompt": workflow})
        submit.raise_for_status()
        prompt_id = submit.json()["prompt_id"]

        deadline = time.monotonic() + self.timeout
        history: dict = {}
        while time.monotonic() < deadline:
            response = await self._client.get(f"/history/{prompt_id}")
            response.raise_for_status()
            history = response.json()
            if prompt_id in history:
                break
            await self._sleep(self.poll_interval)
        else:
            raise TimeoutError(f"ComfyUI didn't finish generating within {self.timeout}s")

        outputs = history[prompt_id]["outputs"]
        image_info = next(image for node_output in outputs.values() for image in node_output.get("images", []))

        view = await self._client.get(
            "/view",
            params={
                "filename": image_info["filename"],
                "subfolder": image_info.get("subfolder", ""),
                "type": image_info.get("type", "output"),
            },
        )
        view.raise_for_status()
        return view.content

    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes:
        width, height = _PORTRAIT_SIZE
        return await self._generate(description, width, height, "nightwire_portrait")

    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes:
        width, height = _SCENE_SIZE
        return await self._generate(prompt, width, height, "nightwire_scene")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_comfyui_backend.py -v`
Expected: `4 passed`

- [ ] **Step 5: Write the failing test for the timeout path**

Append to `tests/test_comfyui_backend.py`:

```python
@pytest.mark.asyncio
async def test_generate_portrait_raises_timeout_error_when_never_ready():
    client = _FakeComfyClient(history={})  # prompt_id never appears
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep, timeout=0.05, poll_interval=0.01)

    with pytest.raises(TimeoutError):
        await backend.generate_portrait("a fixer")
```

- [ ] **Step 6: Run it to verify it passes (implementation already handles this)**

Run: `pytest tests/test_comfyui_backend.py -v`
Expected: `5 passed` — the `while`/`else` deadline loop already raises `TimeoutError`, so no implementation change needed; this step just confirms it.

- [ ] **Step 7: Commit**

```bash
git add narrator/comfyui_backend.py tests/test_comfyui_backend.py
git commit -m "feat: add ComfyUIBackend implementing ImageBackend protocol"
```

---

### Task 2: `create_image_backend()` factory, wired into `__main__.py`

**Files:**
- Modify: `narrator/image_backend.py`
- Modify: `server/__main__.py`
- Test: `tests/test_image_backend.py`

**Interfaces:**
- Consumes: `ComfyUIBackend` from `narrator/comfyui_backend.py` (Task 1), `FluxWorkerBackend` (already in `narrator/image_backend.py`).
- Produces: `create_image_backend() -> ImageBackend` in `narrator/image_backend.py`, reading `IMAGE_BACKEND`/`FLUX_WORKER_URL`/`IMAGE_OUTPUT_DIR`/`COMFYUI_URL`/`COMFYUI_CHECKPOINT` from `os.environ`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_image_backend.py`:

```python
from narrator.comfyui_backend import ComfyUIBackend
from narrator.image_backend import create_image_backend


def test_create_image_backend_defaults_to_flux_worker(monkeypatch):
    monkeypatch.delenv("IMAGE_BACKEND", raising=False)

    backend = create_image_backend()

    assert isinstance(backend, FluxWorkerBackend)


def test_create_image_backend_selects_comfyui(monkeypatch):
    monkeypatch.setenv("IMAGE_BACKEND", "comfyui")
    monkeypatch.setenv("COMFYUI_URL", "http://192.168.10.19:8188")
    monkeypatch.setenv("COMFYUI_CHECKPOINT", "v1-5-pruned-emaonly-fp16.safetensors")

    backend = create_image_backend()

    assert isinstance(backend, ComfyUIBackend)
    assert backend.checkpoint == "v1-5-pruned-emaonly-fp16.safetensors"


def test_create_image_backend_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("IMAGE_BACKEND", "not-a-real-backend")

    with pytest.raises(ValueError, match="not-a-real-backend"):
        create_image_backend()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_image_backend.py -v`
Expected: `FAIL` — `ImportError: cannot import name 'create_image_backend'`

- [ ] **Step 3: Add the factory to `narrator/image_backend.py`**

Add `import os` to the top of `narrator/image_backend.py` (alongside the existing `base64`/`Path`/`Protocol`/`httpx` imports), add `from narrator.comfyui_backend import ComfyUIBackend` there too, and append this function at the end of the file:

```python
def create_image_backend() -> ImageBackend:
    """IMAGE_BACKEND selects the image backend at startup - config, not a
    runtime toggle, same shape TTSBackend selection already uses. Defaults
    to flux_worker (current behavior, unchanged for existing deployments)."""
    backend = os.environ.get("IMAGE_BACKEND", "flux_worker").strip().lower()
    if backend == "flux_worker":
        return FluxWorkerBackend(
            base_url=os.environ.get("FLUX_WORKER_URL", "http://127.0.0.1:7869"),
            output_dir=os.environ.get("IMAGE_OUTPUT_DIR", "frontend/public/generated"),
        )
    if backend == "comfyui":
        return ComfyUIBackend(
            base_url=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"),
            checkpoint=os.environ.get("COMFYUI_CHECKPOINT", "v1-5-pruned-emaonly-fp16.safetensors"),
        )
    raise ValueError(f"Unknown IMAGE_BACKEND {backend!r}. Valid backends: 'flux_worker', 'comfyui'.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_image_backend.py -v`
Expected: all tests pass, including the 3 new ones and the existing `FluxWorkerBackend` tests (unchanged).

- [ ] **Step 5: Wire the factory into `server/__main__.py`**

In `server/__main__.py`, replace:

```python
from narrator.image_backend import FluxWorkerBackend
```

with:

```python
from narrator.image_backend import create_image_backend
```

and replace this block:

```python
    # output_dir default (frontend/public/generated) matches
    # image_server/optimized_image_server.py's own OUT_DIR default,
    # assuming both processes run from the repo root - still true when
    # FLUX_WORKER_URL points elsewhere (a container split needs a shared
    # volume mounted at this same path in both containers).
    image_backend = FluxWorkerBackend(
        base_url=os.environ.get("FLUX_WORKER_URL", "http://127.0.0.1:7869"),
        output_dir=os.environ.get("IMAGE_OUTPUT_DIR", "frontend/public/generated"),
    )
```

with:

```python
    # IMAGE_BACKEND selects flux_worker (default, MLX-only) or comfyui
    # (Docker/Linux-friendly, no reference-photo support) - see
    # docs/superpowers/specs/2026-09-15-comfyui-image-backend-design.md.
    image_backend = create_image_backend()
```

- [ ] **Step 6: Run the full existing test suite to confirm nothing broke**

Run: `pytest tests/ -v`
Expected: all tests pass, including `tests/test_server_main.py::test_build_app_returns_a_fastapi_app` (still exercises the flux_worker default path since `IMAGE_BACKEND` is unset in that test's environment).

- [ ] **Step 7: Commit**

```bash
git add narrator/image_backend.py server/__main__.py tests/test_image_backend.py
git commit -m "feat: add create_image_backend factory, wire IMAGE_BACKEND=comfyui into __main__"
```

---

### Task 3: Live verification against sentinel's real ComfyUI instance

**Files:** none (verification only — no code changes).

- [ ] **Step 1: Confirm sentinel's ComfyUI is still reachable at the configured default**

Run: `curl -s http://192.168.10.19:8188/system_stats`
Expected: a JSON response with real GPU/RAM stats. If this fails (IP drift — sentinel's address is DHCP-assigned and has changed before), find the current address and either pass `COMFYUI_URL` explicitly in the next step or update the default in `narrator/image_backend.py`/the spec.

- [ ] **Step 2: Run one real generation against it**

From the nightwire repo root, with the venv active:

```bash
python3 -c "
import asyncio
from narrator.comfyui_backend import ComfyUIBackend

async def main():
    backend = ComfyUIBackend(base_url='http://192.168.10.19:8188')
    image_bytes = await backend.generate_portrait('a lean netrunner in a rain-slicked jacket, cyberpunk noir')
    with open('/tmp/comfyui-verify.png', 'wb') as f:
        f.write(image_bytes)
    print(f'wrote {len(image_bytes)} bytes')

asyncio.run(main())
"
```

Expected: prints a real byte count (a valid SD1.5 PNG at 512×768 is typically a few hundred KB), no exception. Confirm `/tmp/comfyui-verify.png` is a real, openable image (open it, or run `file /tmp/comfyui-verify.png` and confirm it reports PNG image data with the right dimensions).

- [ ] **Step 3: Record the result in ROADMAP.md**

Update the Phase 10 entry in `nightwire/ROADMAP.md` (added in the design-spec commit) to note live verification: what generated, how long it took, and the real ComfyUI/checkpoint versions confirmed — matching the "real GPU, not just mocks" verification note every other image-generation phase in this roadmap already carries. Commit this update separately.

```bash
git add ROADMAP.md
git commit -m "docs: record live verification of ComfyUI image backend against sentinel"
```

---

## Self-Review

**Spec coverage:**
- Config-selectable, not a replacement → Task 2 (`create_image_backend`, `IMAGE_BACKEND` default `flux_worker`). ✓
- `ComfyUIBackend` implementing the existing `ImageBackend` protocol, zero changes to `server/narration.py`/`portrait.py` → Task 1 (protocol-matching signatures), confirmed no other files touched. ✓
- Real, live-verified target (sentinel, DHCP caveat) → `COMFYUI_URL` default + Task 3's reachability check before trusting it. ✓
- Checkpoint matching what's actually loaded → `COMFYUI_CHECKPOINT` default, asserted in Task 2's test. ✓
- No reference-photo support, documented not silent → docstring + comment in `ComfyUIBackend`, called out in Global Constraints. ✓
- Workflow-graph shape (oracle as technical reference) → Task 1 Step 3. ✓
- Resolution 512×768 portrait / 512×512 scene → `_PORTRAIT_SIZE`/`_SCENE_SIZE`, tested in Task 1. ✓
- Unit tests mocking the HTTP layer → Task 1's `_FakeComfyClient`. ✓
- Live verification before calling the phase done → Task 3. ✓
- Deferred items (IPAdapter, quality passes, hosted backend, FluxWorkerBackend changes) → none touched by any task; confirmed no task modifies `FluxWorkerBackend`. ✓

**Placeholder scan:** No TBD/TODO/"add appropriate" phrasing found; every step has real, runnable code or an exact command.

**Type consistency:** `ComfyUIBackend.__init__` signature in Task 1 matches the constructor call in Task 2's factory (`base_url`, `checkpoint` passed by keyword — `timeout`/`poll_interval`/`client`/`sleep_fn` left at their defaults, which is correct for production use). `generate_portrait`/`generate_scene` signatures match `ImageBackend` protocol exactly (`narrator/image_backend.py`'s existing definition, unchanged). `create_image_backend() -> ImageBackend` return type covers both concrete classes since both structurally satisfy the Protocol.
