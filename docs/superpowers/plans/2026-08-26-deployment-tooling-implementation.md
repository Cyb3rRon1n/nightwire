# Deployment Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `nightwire-deploy` CLI that detects hardware before acting — probing GPU/RAM, recommending an Ollama model tag and which optional backends (image-gen, TTS) to enable, confirming with the user, then installing/registering everything — for both the server (complex, hardware-aware) and the client (simple, Node + a URL).

**Architecture:** New `deploy/` Python package alongside `ruleset/`/`engine/`/`narrator/`/`server/`. Pure decision logic (`detect.py`, `tiers.py`) is unit-tested without any real hardware, subprocess/OS calls, or network access via dependency-injected runner callables (the same pattern `FluxWorkerBackend`'s `http_fn` and `KokoroBackend`'s `speech_fn` already use in this codebase). Orchestration (`server_install.py`, `client_install.py`, `services.py`, `cli.py`) is thin plumbing around those decisions, smoke-tested the same way.

**Tech Stack:** Python 3.11+, `psutil` (new dependency, for cross-platform RAM/CPU reads), stdlib `subprocess`/`platform`/`shutil`/`argparse`. No new frontend dependency — the client installer reuses `frontend`'s existing `NEXT_PUBLIC_NIGHTWIRE_WS_URL` convention.

**Spec:** `docs/superpowers/specs/2026-08-26-deployment-tooling-design.md` — read it first.

## Global Constraints

- Server hardware probing covers Linux, macOS, and Windows (spec's platform-scope decision).
- Detect → report → confirm → act, always in that order for `install`. Nothing that writes files, pulls models, or clones repos runs before a yes.
- `ultra-fast-image-gen` is a **private** repo — its clone URL is never hardcoded anywhere in this plan or the code it produces; it's always a value the user supplies at install time. (Confirmed in `docs/superpowers/plans/2026-08-23-phase5-image-generation-implementation.md` Task 7: "the clone URL had to come from the user directly, nothing in nightwire's checkout names it.")
- Model tag file sizes (`qwen3:8b` = 5.2GB, etc.) are sourced from `ollama.com/library/qwen3` (fetched 2026-08-26), not memory/assumption.
- `FLUX.2-klein-4B` needs 8GB VRAM at 512px (`docs/superpowers/specs/2026-08-23-image-generation-design.md`) — NVIDIA/CUDA (SDNQ) only, never recommended on Apple/CPU-only tiers.
- Kokoro-82M needs <2GB VRAM (`docs/superpowers/specs/2026-08-23-tts-narration-design.md`) and requires `ALLOW_DEV_UNLOAD=true` for `KokoroBackend.unload()` to work (verified against `remsky/Kokoro-FastAPI`'s own README, 2026-08-26).
- Windows gets no persistent service registration (spec's scope decision) — a generated PowerShell start script instead.
- No placeholder GitHub URLs, no invented PyTorch CUDA index tags (that tag drifts release to release — see Task 7).

---

### Task 1: Hardware detection (`deploy/detect.py`)

**Files:**
- Create: `deploy/__init__.py` (empty)
- Create: `deploy/detect.py`
- Modify: `pyproject.toml` — add `"psutil>=6.0"` to `dependencies`, add `"deploy"` to `tool.setuptools.packages.find.include`
- Test: `tests/test_deploy_detect.py`

**Interfaces:**
- Produces: `HardwareProfile(BaseModel)` with fields `os: Literal["linux","macos","windows"]`, `gpu_vendor: Literal["nvidia","apple","none"]`, `vram_gb: float | None`, `system_ram_gb: float`, `cpu_cores: int`. `probe(run: Callable[[list[str]], str] = <default>) -> HardwareProfile`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deploy_detect.py
import subprocess

import pytest

from deploy.detect import probe


def test_probe_detects_nvidia_gpu(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Linux")

    def fake_run(cmd):
        assert cmd[0] == "nvidia-smi"
        return "8192\n"

    profile = probe(run=fake_run)

    assert profile.os == "linux"
    assert profile.gpu_vendor == "nvidia"
    assert profile.vram_gb == 8.0


def test_probe_falls_back_to_apple_when_nvidia_smi_missing_on_mac(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Darwin")
    monkeypatch.setattr("deploy.detect.platform.machine", lambda: "arm64")

    def fake_run(cmd):
        raise FileNotFoundError("no nvidia-smi")

    profile = probe(run=fake_run)

    assert profile.os == "macos"
    assert profile.gpu_vendor == "apple"
    assert profile.vram_gb is None


def test_probe_falls_back_to_none_when_no_gpu_found(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Windows")

    def fake_run(cmd):
        raise FileNotFoundError("no nvidia-smi")

    profile = probe(run=fake_run)

    assert profile.os == "windows"
    assert profile.gpu_vendor == "none"
    assert profile.vram_gb is None


def test_probe_treats_nvidia_smi_command_error_as_no_gpu(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Linux")

    def fake_run(cmd):
        raise subprocess.CalledProcessError(1, cmd)

    profile = probe(run=fake_run)

    assert profile.gpu_vendor == "none"


def test_probe_reports_real_ram_and_cpu_cores():
    profile = probe()

    assert profile.system_ram_gb > 0
    assert profile.cpu_cores >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_detect.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deploy'`

- [ ] **Step 3: Add the dependency and package**

Add `"psutil>=6.0"` to `pyproject.toml`'s `dependencies` list, and `"deploy"` to `tool.setuptools.packages.find.include`. Create empty `deploy/__init__.py`.

- [ ] **Step 4: Implement `deploy/detect.py`**

```python
from __future__ import annotations

import platform
import subprocess
from typing import Callable, Literal

import psutil
from pydantic import BaseModel

CommandRunner = Callable[[list[str]], str]

_OS_MAP = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}


class HardwareProfile(BaseModel):
    os: Literal["linux", "macos", "windows"]
    gpu_vendor: Literal["nvidia", "apple", "none"]
    vram_gb: float | None
    system_ram_gb: float
    cpu_cores: int


def _default_run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return result.stdout


def _detect_gpu(run: CommandRunner, os_name: str) -> tuple[Literal["nvidia", "apple", "none"], float | None]:
    try:
        output = run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
        mib = float(output.strip().splitlines()[0])
        return "nvidia", round(mib / 1024, 1)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    if os_name == "macos" and platform.machine() == "arm64":
        return "apple", None
    return "none", None


def probe(run: CommandRunner = _default_run) -> HardwareProfile:
    os_name = _OS_MAP[platform.system()]
    gpu_vendor, vram_gb = _detect_gpu(run, os_name)
    return HardwareProfile(
        os=os_name,
        gpu_vendor=gpu_vendor,
        vram_gb=vram_gb,
        system_ram_gb=round(psutil.virtual_memory().total / (1024**3), 1),
        cpu_cores=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
    )
```

- [ ] **Step 5: Install the new dependency and run tests**

Run: `pip install -e ".[dev]"` then `pytest tests/test_deploy_detect.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml deploy/__init__.py deploy/detect.py tests/test_deploy_detect.py
git commit -m "feat: add cross-platform hardware detection for deployment tooling"
```

---

### Task 2: Tiering (`deploy/tiers.py`)

**Files:**
- Create: `deploy/tiers.py`
- Test: `tests/test_deploy_tiers.py`

**Interfaces:**
- Consumes: `HardwareProfile` (Task 1).
- Produces: `Recommendation(BaseModel)` with fields `tier: str`, `ollama_model: str`, `enable_image_gen: bool`, `tts_backend: Literal["kokoro","hosted","none"]`, `reasoning: str`. `recommend(profile: HardwareProfile) -> Recommendation`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deploy_tiers.py
from deploy.detect import HardwareProfile
from deploy.tiers import recommend


def test_confirmed_8gb_nvidia_tier_matches_real_deployment():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:8b"
    assert rec.enable_image_gen is True
    assert rec.tts_backend == "kokoro"


def test_higher_vram_gets_the_same_recommendation():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=24.0, system_ram_gb=64, cpu_cores=16)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:8b"
    assert rec.enable_image_gen is True


def test_mid_vram_disables_image_gen_but_keeps_local_tts():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=6.0, system_ram_gb=16, cpu_cores=8)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:4b"
    assert rec.enable_image_gen is False
    assert rec.tts_backend == "kokoro"


def test_low_vram_falls_back_to_hosted_tts():
    profile = HardwareProfile(os="windows", gpu_vendor="nvidia", vram_gb=2.5, system_ram_gb=16, cpu_cores=8)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:1.7b"
    assert rec.enable_image_gen is False
    assert rec.tts_backend == "hosted"


def test_apple_silicon_never_recommends_image_gen():
    profile = HardwareProfile(os="macos", gpu_vendor="apple", vram_gb=None, system_ram_gb=16, cpu_cores=8)

    rec = recommend(profile)

    assert rec.enable_image_gen is False
    assert rec.tier == "apple-unified"


def test_cpu_only_caps_model_size_even_with_huge_ram():
    profile = HardwareProfile(os="linux", gpu_vendor="none", vram_gb=None, system_ram_gb=256, cpu_cores=32)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:4b"
    assert rec.enable_image_gen is False
    assert rec.tier == "cpu-only"


def test_reasoning_is_a_nonempty_explanation():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)

    rec = recommend(profile)

    assert len(rec.reasoning) > 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_tiers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deploy.tiers'`

- [ ] **Step 3: Implement `deploy/tiers.py`**

```python
from __future__ import annotations

from pydantic import BaseModel

from deploy.detect import HardwareProfile

# ollama.com/library/qwen3 tags, default quantization, fetched 2026-08-26.
MODEL_SIZES_GB = {
    "qwen3:8b": 5.2,
    "qwen3:4b": 2.5,
    "qwen3:1.7b": 1.4,
    "qwen3:0.6b": 0.6,
}

# FLUX.2-klein-4B at 4-bit SDNQ: "8GB VRAM at 512px" - see
# docs/superpowers/specs/2026-08-23-image-generation-design.md. NVIDIA/CUDA
# (SDNQ) specific - never recommended on Apple/CPU-only tiers.
IMAGE_GEN_MIN_VRAM_GB = 8.0

# Kokoro-82M: "~300MB/<2GB VRAM" - see
# docs/superpowers/specs/2026-08-23-tts-narration-design.md.
KOKORO_VRAM_GB = 2.0

# The confirmed real deployment (RTX 2080). nvidia-smi sometimes reports a
# few hundred MB under the nominal 8192MiB due to reserved memory, so 7.5
# catches the real card without excluding it.
STANDARD_TIER_VRAM_GB = 7.5

# Apple unified memory and CPU-only RAM are shared with the OS and every
# other running app. No cited real-world number exists yet for a safe
# reserve on either (open item, see spec) - this flat reserve is a
# documented, disclosed estimate, not a verified measurement.
_UNIFIED_MEMORY_RESERVE_GB = 4.0


class Recommendation(BaseModel):
    tier: str
    ollama_model: str
    enable_image_gen: bool
    tts_backend: Literal["kokoro", "hosted", "none"]
    reasoning: str


def _pick_model(budget_gb: float) -> str:
    if budget_gb >= STANDARD_TIER_VRAM_GB:
        return "qwen3:8b"
    if budget_gb >= 3.0:
        return "qwen3:4b"
    if budget_gb >= 2.0:
        return "qwen3:1.7b"
    return "qwen3:0.6b"


def _tts_for(budget_gb: float, model: str) -> Literal["kokoro", "hosted"]:
    headroom = budget_gb - MODEL_SIZES_GB[model]
    return "kokoro" if headroom >= KOKORO_VRAM_GB else "hosted"


def recommend(profile: HardwareProfile) -> Recommendation:
    if profile.gpu_vendor == "nvidia" and profile.vram_gb is not None:
        budget = profile.vram_gb
        model = _pick_model(budget)
        enable_image_gen = budget >= IMAGE_GEN_MIN_VRAM_GB
        tts_backend = _tts_for(budget, model)
        tier = "standard" if enable_image_gen else ("lite" if model != "qwen3:0.6b" else "minimal")
        reasoning = (
            f"{budget:.1f}GB NVIDIA VRAM detected. Recommending {model} "
            f"({MODEL_SIZES_GB[model]}GB, leaves {budget - MODEL_SIZES_GB[model]:.1f}GB headroom). "
            + (
                "Image-gen fits (needs >= 8GB for FLUX.2-klein-4B at 512px)."
                if enable_image_gen
                else "Image-gen disabled - needs >= 8GB VRAM for FLUX.2-klein-4B at 512px."
            )
            + (
                " Kokoro (local TTS) fits alongside."
                if tts_backend == "kokoro"
                else " Recommending hosted TTS - not enough headroom left for Kokoro's <2GB alongside the model."
            )
        )
        return Recommendation(tier=tier, ollama_model=model, enable_image_gen=enable_image_gen, tts_backend=tts_backend, reasoning=reasoning)

    if profile.gpu_vendor == "apple":
        budget = max(profile.system_ram_gb - _UNIFIED_MEMORY_RESERVE_GB, 0.6)
        model = _pick_model(budget)
        tts_backend = _tts_for(budget, model)
        reasoning = (
            f"Apple Silicon detected, {profile.system_ram_gb:.1f}GB unified memory "
            f"(~{budget:.1f}GB assumed available after OS/app overhead - a documented estimate, "
            "not a verified number, since unified memory is shared with everything else running). "
            f"Recommending {model}. Image-gen disabled - FLUX.2-klein-4B's SDNQ quantization is "
            "NVIDIA/CUDA-specific and unverified on Metal."
            + (" Kokoro fits alongside." if tts_backend == "kokoro" else " Recommending hosted TTS.")
        )
        return Recommendation(tier="apple-unified", ollama_model=model, enable_image_gen=False, tts_backend=tts_backend, reasoning=reasoning)

    budget = max(profile.system_ram_gb - _UNIFIED_MEMORY_RESERVE_GB, 0.6)
    # Capped at qwen3:4b even with huge RAM headroom - CPU inference of
    # anything bigger is impractically slow without a GPU regardless of RAM.
    model = _pick_model(min(budget, 4.0))
    tts_backend = _tts_for(budget, model)
    reasoning = (
        f"No GPU detected. {profile.system_ram_gb:.1f}GB system RAM (~{budget:.1f}GB assumed "
        f"available). Recommending {model} for CPU inference - capped at qwen3:4b even with "
        "more RAM, since larger models are impractically slow without a GPU. Image-gen disabled "
        "- no CPU inference path for FLUX.2-klein-4B in this project."
        + (" Kokoro fits alongside." if tts_backend == "kokoro" else " Recommending hosted TTS.")
    )
    return Recommendation(tier="cpu-only", ollama_model=model, enable_image_gen=False, tts_backend=tts_backend, reasoning=reasoning)
```

Add `from typing import Literal` to the imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_deploy_tiers.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add deploy/tiers.py tests/test_deploy_tiers.py
git commit -m "feat: add hardware-tier to model/backend recommendation mapping"
```

---

### Task 3: Server config becomes environment-driven (`server/__main__.py`)

**Files:**
- Modify: `server/__main__.py`
- Modify: `tests/test_server_main.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks.
- Produces: `NullImageBackend`, `NullTTSBackend` (used only here); `build_app()` now reads `NIGHTWIRE_MODEL`, `NIGHTWIRE_IMAGE_BACKEND` (`flux`|`none`, default `flux`), `NIGHTWIRE_TTS_BACKEND` (`kokoro`|`openai`|`none`, default `kokoro`), `NIGHTWIRE_TTS_API_KEY` (required when `NIGHTWIRE_TTS_BACKEND=openai`) — this is what `deploy/server_install.py` (Task 5-7) writes into service files.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_server_main.py (replace the file's contents)
from fastapi import FastAPI


def test_build_app_returns_a_fastapi_app_with_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)


def test_build_app_reads_model_and_disables_optional_backends_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NIGHTWIRE_MODEL", "qwen3:4b")
    monkeypatch.setenv("NIGHTWIRE_IMAGE_BACKEND", "none")
    monkeypatch.setenv("NIGHTWIRE_TTS_BACKEND", "none")
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)


def test_build_app_wires_openai_tts_when_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NIGHTWIRE_TTS_BACKEND", "openai")
    monkeypatch.setenv("NIGHTWIRE_TTS_API_KEY", "sk-test")
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)


async def test_null_image_backend_fails_soft():
    from server.__main__ import NullImageBackend

    backend = NullImageBackend()

    try:
        await backend.generate_scene("prompt", [])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "disabled" in str(e)


async def test_null_tts_backend_fails_soft():
    from server.__main__ import NullTTSBackend

    backend = NullTTSBackend()

    try:
        await backend.synthesize("hi", "voice")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "disabled" in str(e)
    await backend.unload()  # no-op, must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server_main.py -v`
Expected: FAIL — `NullImageBackend`/`NullTTSBackend` don't exist yet, and the env-reading tests fail before assertions are even meaningful (they'll actually pass against the old hardcoded `build_app` since it ignores env vars entirely and always builds the same objects — but the import of `NullImageBackend`/`NullTTSBackend` in the last two tests fails with `ImportError`, which is the real signal here).

- [ ] **Step 3: Implement**

Replace `server/__main__.py`'s contents:

```python
import os

import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from narrator.image_backend import FluxWorkerBackend, ImageBackend
from narrator.tts_backend import KokoroBackend, OpenAITTSBackend, TTSBackend, VoiceOption
from server.app import create_app


class NullImageBackend:
    """No-op image backend for NIGHTWIRE_IMAGE_BACKEND=none. Attempts fail
    soft into an `[image error: ...]` log line via the existing
    `except (ValueError, TypeError, OSError)` handling in
    server/narration.py - same mechanism any other image-gen failure uses.
    """

    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes:
        raise ValueError("image generation disabled (NIGHTWIRE_IMAGE_BACKEND=none)")

    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes:
        raise ValueError("image generation disabled (NIGHTWIRE_IMAGE_BACKEND=none)")


class NullTTSBackend:
    """No-op TTS backend for NIGHTWIRE_TTS_BACKEND=none - same fail-soft shape as NullImageBackend."""

    voices: list[VoiceOption] = []

    async def synthesize(self, text: str, voice: str) -> bytes:
        raise ValueError("tts disabled (NIGHTWIRE_TTS_BACKEND=none)")

    async def unload(self) -> None:
        pass


def build_app():
    store = JSONFileSessionStore("./sessions")
    system_prompt = (
        "You are a cyberpunk tabletop game master. "
        "Most turns should set tool_call.tool to null - plain narration, dialogue, and "
        "exploration need no tool at all. Combat start/end is entirely player-controlled "
        "outside your tools - never mention or imply that you're starting or ending combat "
        "as a mechanical event, just narrate what's happening. "
        "You may optionally set image_request to generate a picture of the current scene. "
        "Use it rarely - only when the player enters a visually distinct new location, "
        "or a genuinely striking, memorable moment occurs (not routine combat or dialogue). "
        "Never two turns in a row. Example: player steps into a neon-lit rooftop bar for "
        "the first time -> set image_request.prompt to 'a rain-slicked rooftop bar, neon "
        "signs reflecting off wet concrete, city skyline behind'. Player orders a drink, "
        "asks a question, checks their own gear or inventory, or takes a routine combat "
        "action in a location already described this scene -> leave image_request unset, "
        "even if the action itself sounds visually interesting. When you do set it, the "
        "prompt should be a short, concrete visual description (setting, lighting, mood) - "
        "not a summary of the plot. "
        "Narration is a list of segments, each with a speaker. Use speaker 'narrator' for "
        "your own descriptive prose; use the exact same name every time a given character "
        "speaks (don't vary casing or spelling turn to turn). Set gender only the first "
        "time a new speaker appears - male or female, whichever fits the character. "
        "Characters have 100 max Health. Scale apply_character_update's health_delta to "
        "that pool: a grazing or minor hit is roughly -5 to -15, a solid hit -20 to -35, "
        "a devastating or critical hit -40 to -60. Don't default to small single-digit "
        "deltas from a d20-style game - a fight should plausibly end in a handful of hits."
    )
    model = os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b")
    narrator_client = NarratorClient(model=model, system_prompt=system_prompt)

    image_choice = os.environ.get("NIGHTWIRE_IMAGE_BACKEND", "flux")
    image_backend: ImageBackend = FluxWorkerBackend() if image_choice == "flux" else NullImageBackend()

    tts_choice = os.environ.get("NIGHTWIRE_TTS_BACKEND", "kokoro")
    tts_backend: TTSBackend
    if tts_choice == "openai":
        tts_backend = OpenAITTSBackend(api_key=os.environ["NIGHTWIRE_TTS_API_KEY"])
    elif tts_choice == "none":
        tts_backend = NullTTSBackend()
    else:
        tts_backend = KokoroBackend()

    return create_app(store, narrator_client, image_backend, tts_backend)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server_main.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full existing suite to check nothing else broke**

Run: `pytest -v`
Expected: PASS (this file is imported by nothing else in production code, but `server/app.py`'s own tests construct `FastAPI` apps directly with fakes, unaffected)

- [ ] **Step 6: Commit**

```bash
git add server/__main__.py tests/test_server_main.py
git commit -m "feat: make server backend/model selection environment-driven"
```

---

### Task 4: Per-OS service file writers (`deploy/services.py`)

**Files:**
- Create: `deploy/services.py`
- Test: `tests/test_deploy_services.py`

**Interfaces:**
- Produces: `write_systemd_unit(name, working_dir, exec_start, env, units_dir) -> Path`, `write_launchd_plist(name, working_dir, argv, env, plists_dir) -> Path`, `write_windows_start_script(entries, script_path) -> Path` where `entries: list[tuple[name, argv, working_dir, env]]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deploy_services.py
from pathlib import Path

from deploy.services import write_launchd_plist, write_systemd_unit, write_windows_start_script


def test_write_systemd_unit_contains_exec_and_env(tmp_path):
    path = write_systemd_unit(
        "nightwire-server", Path("/opt/nightwire"), "python -m server", {"NIGHTWIRE_MODEL": "qwen3:8b"}, tmp_path
    )

    content = path.read_text()
    assert path.name == "nightwire-nightwire-server.service"
    assert "ExecStart=python -m server" in content
    assert "WorkingDirectory=/opt/nightwire" in content
    assert "Environment=NIGHTWIRE_MODEL=qwen3:8b" in content
    assert "[Install]" in content


def test_write_launchd_plist_contains_program_args_and_env(tmp_path):
    path = write_launchd_plist(
        "nightwire-server", Path("/opt/nightwire"), ["python", "-m", "server"], {"NIGHTWIRE_MODEL": "qwen3:8b"}, tmp_path
    )

    content = path.read_text()
    assert path.name == "com.nightwire.nightwire-server.plist"
    assert "<string>python</string>" in content
    assert "<string>NIGHTWIRE_MODEL</string>" in content
    assert "<string>qwen3:8b</string>" in content


def test_write_windows_start_script_lists_every_entry(tmp_path):
    script_path = tmp_path / "start-all.ps1"
    entries = [
        ("nightwire-server", ["python", "-m", "server"], Path("C:/nightwire"), {"NIGHTWIRE_MODEL": "qwen3:8b"}),
        ("kokoro-server", ["bash", "start-gpu.sh"], Path("C:/Kokoro-FastAPI"), {"ALLOW_DEV_UNLOAD": "true"}),
    ]

    result_path = write_windows_start_script(entries, script_path)

    content = result_path.read_text()
    assert "nightwire-server" in content
    assert "kokoro-server" in content
    assert "NIGHTWIRE_MODEL" in content
    assert "ALLOW_DEV_UNLOAD" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_services.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deploy.services'`

- [ ] **Step 3: Implement `deploy/services.py`**

```python
from __future__ import annotations

from pathlib import Path

_SYSTEMD_UNIT_TEMPLATE = """[Unit]
Description=nightwire {name}
After=network.target

[Service]
WorkingDirectory={working_dir}
ExecStart={exec_start}
{env_lines}Restart=on-failure

[Install]
WantedBy=default.target
"""


def write_systemd_unit(name: str, working_dir: Path, exec_start: str, env: dict[str, str], units_dir: Path) -> Path:
    env_lines = "".join(f"Environment={key}={value}\n" for key, value in env.items())
    content = _SYSTEMD_UNIT_TEMPLATE.format(name=name, working_dir=working_dir, exec_start=exec_start, env_lines=env_lines)
    units_dir.mkdir(parents=True, exist_ok=True)
    path = units_dir / f"nightwire-{name}.service"
    path.write_text(content)
    return path


_LAUNCHD_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nightwire.{name}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}    </array>
    <key>WorkingDirectory</key>
    <string>{working_dir}</string>
    <key>EnvironmentVariables</key>
    <dict>
{env_entries}    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
"""


def write_launchd_plist(name: str, working_dir: Path, argv: list[str], env: dict[str, str], plists_dir: Path) -> Path:
    program_args = "".join(f"        <string>{arg}</string>\n" for arg in argv)
    env_entries = "".join(f"        <key>{k}</key>\n        <string>{v}</string>\n" for k, v in env.items())
    content = _LAUNCHD_PLIST_TEMPLATE.format(name=name, program_args=program_args, working_dir=working_dir, env_entries=env_entries)
    plists_dir.mkdir(parents=True, exist_ok=True)
    path = plists_dir / f"com.nightwire.{name}.plist"
    path.write_text(content)
    return path


def write_windows_start_script(entries: list[tuple[str, list[str], Path, dict[str, str]]], script_path: Path) -> Path:
    lines = ["# Generated by nightwire-deploy - starts each enabled service in its own window.", ""]
    for name, argv, working_dir, env in entries:
        env_assignments = "; ".join(f'$env:{k}="{v}"' for k, v in env.items())
        cmd = " ".join(argv)
        lines.append(
            f"Start-Process powershell -ArgumentList '-NoExit', '-Command', "
            f"\"{env_assignments}; cd \\\"{working_dir}\\\"; {cmd}\" -WindowStyle Normal  # {name}"
        )
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("\n".join(lines) + "\n")
    return script_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_deploy_services.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add deploy/services.py tests/test_deploy_services.py
git commit -m "feat: add per-OS service file generation (systemd, launchd, Windows)"
```

---

### Task 5: Server install — Ollama + nightwire-server unit (`deploy/server_install.py`)

**Files:**
- Create: `deploy/server_install.py`
- Test: `tests/test_deploy_server_install.py`

**Interfaces:**
- Consumes: `HardwareProfile` (Task 1), `Recommendation` (Task 2), `write_systemd_unit`/`write_launchd_plist`/`write_windows_start_script` (Task 4).
- Produces: `ollama_installed(which) -> bool`, `install_ollama(os_name, run) -> None`, `pull_model(model, run) -> None`, `run(profile, recommendation, siblings_dir, units_dir, run_cmd=..., which=..., image_gen_repo_url=None, tts_api_key=None) -> dict[str,str]` (returns the env dict written for `nightwire-server`; extended in Tasks 6-7). This first cut always sets `NIGHTWIRE_IMAGE_BACKEND=none` and `NIGHTWIRE_TTS_BACKEND=none`/`openai` regardless of the recommendation's `kokoro` choice — Task 6 wires Kokoro, Task 7 wires image-gen.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deploy_server_install.py
from pathlib import Path

from deploy.detect import HardwareProfile
from deploy.server_install import install_ollama, ollama_installed, pull_model, run
from deploy.tiers import Recommendation


def test_ollama_installed_true_when_on_path():
    assert ollama_installed(which=lambda name: "/usr/bin/ollama") is True


def test_ollama_installed_false_when_missing():
    assert ollama_installed(which=lambda name: None) is False


def test_install_ollama_runs_the_official_installer_per_os():
    calls = []
    install_ollama("linux", run=calls.append)
    assert calls[0][0] in ("sh", "curl")

    calls.clear()
    install_ollama("windows", run=calls.append)
    assert calls[0][0] == "winget"


def test_pull_model_calls_ollama_pull():
    calls = []
    pull_model("qwen3:8b", run=calls.append)
    assert calls == [["ollama", "pull", "qwen3:8b"]]


def test_run_installs_ollama_when_missing_and_pulls_model(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=False, tts_backend="none", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: None,
    )

    assert ["ollama", "pull", "qwen3:8b"] in calls
    assert env["NIGHTWIRE_MODEL"] == "qwen3:8b"
    unit_path = tmp_path / "units" / "nightwire-nightwire-server.service"
    assert unit_path.exists()
    assert "NIGHTWIRE_MODEL=qwen3:8b" in unit_path.read_text()


def test_run_skips_ollama_install_when_already_present(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=False, tts_backend="none", reasoning="test")

    run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: "/usr/bin/ollama",
    )

    assert not any(cmd[0] in ("winget", "brew") or "install.sh" in " ".join(cmd) for cmd in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_server_install.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deploy.server_install'`

- [ ] **Step 3: Implement `deploy/server_install.py`**

```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from deploy.detect import HardwareProfile
from deploy.services import write_launchd_plist, write_systemd_unit, write_windows_start_script
from deploy.tiers import Recommendation

CommandRunner = Callable[[list[str]], None]


def _default_run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ollama_installed(which: Callable[[str], str | None] = shutil.which) -> bool:
    return which("ollama") is not None


_OLLAMA_INSTALL_CMD = {
    "linux": ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
    "macos": ["brew", "install", "ollama"],
    "windows": ["winget", "install", "-e", "--id", "Ollama.Ollama"],
}


def install_ollama(os_name: str, run: CommandRunner = _default_run) -> None:
    run(_OLLAMA_INSTALL_CMD[os_name])


def pull_model(model: str, run: CommandRunner = _default_run) -> None:
    run(["ollama", "pull", model])


def run(
    profile: HardwareProfile,
    recommendation: Recommendation,
    siblings_dir: Path,
    units_dir: Path,
    run_cmd: CommandRunner = _default_run,
    which: Callable[[str], str | None] = shutil.which,
    image_gen_repo_url: str | None = None,
    tts_api_key: str | None = None,
) -> dict[str, str]:
    if not ollama_installed(which):
        install_ollama(profile.os, run_cmd)
    pull_model(recommendation.ollama_model, run_cmd)

    env = {
        "NIGHTWIRE_MODEL": recommendation.ollama_model,
        "NIGHTWIRE_IMAGE_BACKEND": "none",
        "NIGHTWIRE_TTS_BACKEND": "none",
    }

    server_argv = ["python", "-m", "server"]
    if profile.os == "linux":
        write_systemd_unit("nightwire-server", Path.cwd(), " ".join(server_argv), env, units_dir)
    elif profile.os == "macos":
        write_launchd_plist("nightwire-server", Path.cwd(), server_argv, env, units_dir)
    else:
        write_windows_start_script([("nightwire-server", server_argv, Path.cwd(), env)], units_dir / "start-all.ps1")

    return env
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_deploy_server_install.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add deploy/server_install.py tests/test_deploy_server_install.py
git commit -m "feat: add server installer core (Ollama check/install, model pull, service unit)"
```

---

### Task 6: Server install — Kokoro TTS

**Files:**
- Modify: `deploy/server_install.py`
- Modify: `tests/test_deploy_server_install.py`

**Interfaces:**
- Produces: `KOKORO_REPO_URL` constant, `setup_kokoro(repo_dir, device, run_cmd, which) -> None`, `kokoro_start_command(repo_dir, device, is_windows) -> list[str]`. `run()` gains: when `recommendation.tts_backend == "kokoro"`, clones+sets up Kokoro-FastAPI and writes its own service unit with `ALLOW_DEV_UNLOAD=true`; when `"hosted"`, sets `NIGHTWIRE_TTS_BACKEND=openai` and `NIGHTWIRE_TTS_API_KEY` in the nightwire-server env from the new `tts_api_key` parameter (already accepted by `run()`'s signature from Task 5, unused until now).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_deploy_server_install.py`:

```python
from deploy.server_install import kokoro_start_command, setup_kokoro


def test_setup_kokoro_installs_uv_when_missing(tmp_path):
    calls = []
    setup_kokoro(tmp_path / "Kokoro-FastAPI", device="cuda", run_cmd=calls.append, which=lambda name: None)
    assert any("astral.sh/uv" in " ".join(cmd) if isinstance(cmd, list) else "astral.sh/uv" in cmd for cmd in calls)


def test_setup_kokoro_skips_uv_install_when_present(tmp_path):
    calls = []
    setup_kokoro(tmp_path / "Kokoro-FastAPI", device="cuda", run_cmd=calls.append, which=lambda name: "/usr/bin/uv")
    assert calls == []


def test_kokoro_start_command_picks_gpu_or_cpu_script():
    assert kokoro_start_command(Path("/x/Kokoro-FastAPI"), device="cuda", is_windows=False) == ["bash", "/x/Kokoro-FastAPI/start-gpu.sh"]
    assert kokoro_start_command(Path("/x/Kokoro-FastAPI"), device="cpu", is_windows=False) == ["bash", "/x/Kokoro-FastAPI/start-cpu.sh"]
    assert kokoro_start_command(Path("C:/Kokoro-FastAPI"), device="cuda", is_windows=True) == [
        "powershell", "-File", "C:/Kokoro-FastAPI/start-gpu.ps1",
    ]


def test_run_with_kokoro_tts_clones_and_writes_its_own_unit(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=False, tts_backend="kokoro", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: "/usr/bin/ollama" if name == "ollama" else "/usr/bin/uv",
    )

    assert env["NIGHTWIRE_TTS_BACKEND"] == "kokoro"
    assert any(cmd[:2] == ["git", "clone"] for cmd in calls)
    kokoro_unit = tmp_path / "units" / "nightwire-kokoro-server.service"
    assert kokoro_unit.exists()
    assert "ALLOW_DEV_UNLOAD=true" in kokoro_unit.read_text()


def test_run_with_hosted_tts_sets_openai_env_and_api_key(tmp_path):
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=2.5, system_ram_gb=16, cpu_cores=8)
    recommendation = Recommendation(tier="lite", ollama_model="qwen3:1.7b", enable_image_gen=False, tts_backend="hosted", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: None, which=lambda name: "/usr/bin/ollama", tts_api_key="sk-test",
    )

    assert env["NIGHTWIRE_TTS_BACKEND"] == "openai"
    assert env["NIGHTWIRE_TTS_API_KEY"] == "sk-test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_server_install.py -v`
Expected: FAIL — `setup_kokoro`/`kokoro_start_command` don't exist; the kokoro/hosted `run()` tests fail their new assertions since `run()` currently hardcodes `NIGHTWIRE_TTS_BACKEND=none`.

- [ ] **Step 3: Implement**

Add to `deploy/server_install.py` (device parameter type: `Literal["cuda", "cpu", "mps"]`, add `from typing import Literal`):

```python
KOKORO_REPO_URL = "https://github.com/remsky/Kokoro-FastAPI.git"


def _is_windows() -> bool:
    import platform

    return platform.system() == "Windows"


def clone_repo(repo_url: str, dest: Path, run_cmd: CommandRunner = _default_run) -> None:
    if not dest.exists():
        run_cmd(["git", "clone", repo_url, str(dest)])


def setup_kokoro(repo_dir: Path, device: Literal["cuda", "cpu", "mps"], run_cmd: CommandRunner = _default_run, which: Callable[[str], str | None] = shutil.which) -> None:
    # Kokoro-FastAPI's own start-gpu/start-cpu scripts manage their own
    # uv-installed deps on first run (verified against its README,
    # 2026-08-26) - the only prerequisite this installer owns is uv itself.
    if which("uv") is None:
        if _is_windows():
            run_cmd(["powershell", "-c", "irm https://astral.sh/uv/install.ps1 | iex"])
        else:
            run_cmd(["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])


def kokoro_start_command(repo_dir: Path, device: Literal["cuda", "cpu", "mps"], is_windows: bool) -> list[str]:
    script = "start-cpu" if device == "cpu" else "start-gpu"
    if is_windows:
        return ["powershell", "-File", f"{repo_dir}/{script}.ps1"]
    return ["bash", f"{repo_dir}/{script}.sh"]


_DEVICE_BY_OS = {"macos": "mps", "linux": "cuda", "windows": "cuda"}
```

Rewrite `run()`'s TTS handling (replace the hardcoded `"NIGHTWIRE_TTS_BACKEND": "none"` line and add after the `env = {...}` block, before writing the nightwire-server unit):

```python
    device = "cpu" if profile.gpu_vendor == "none" else _DEVICE_BY_OS[profile.os]

    if recommendation.tts_backend == "kokoro":
        kokoro_dir = siblings_dir / "Kokoro-FastAPI"
        clone_repo(KOKORO_REPO_URL, kokoro_dir, run_cmd)
        setup_kokoro(kokoro_dir, device, run_cmd, which)
        kokoro_env = {"ALLOW_DEV_UNLOAD": "true"}
        kokoro_argv = kokoro_start_command(kokoro_dir, device, profile.os == "windows")
        if profile.os == "linux":
            write_systemd_unit("kokoro-server", kokoro_dir, " ".join(kokoro_argv), kokoro_env, units_dir)
        elif profile.os == "macos":
            write_launchd_plist("kokoro-server", kokoro_dir, kokoro_argv, kokoro_env, units_dir)
        env["NIGHTWIRE_TTS_BACKEND"] = "kokoro"
    elif recommendation.tts_backend == "hosted":
        env["NIGHTWIRE_TTS_BACKEND"] = "openai"
        if tts_api_key:
            env["NIGHTWIRE_TTS_API_KEY"] = tts_api_key
    else:
        env["NIGHTWIRE_TTS_BACKEND"] = "none"
```

Remove the now-redundant `"NIGHTWIRE_TTS_BACKEND": "none"` default from the initial `env = {...}` dict (keep `NIGHTWIRE_MODEL` and `NIGHTWIRE_IMAGE_BACKEND` there). On Windows, `kokoro-server` doesn't get its own unit from this block (no persistent service on Windows per the global constraint) — its entry gets folded into the shared `start-all.ps1` alongside `nightwire-server` in Task 7's final wiring pass; note this explicitly with a comment `# Windows: kokoro-server entry added to start-all.ps1 below, not here` and leave the `write_windows_start_script` call in the Task 5 code as-is for now — Task 7 restructures it to collect every service into one list before writing the one script.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_deploy_server_install.py -v`
Expected: PASS (11 tests total)

- [ ] **Step 5: Commit**

```bash
git add deploy/server_install.py tests/test_deploy_server_install.py
git commit -m "feat: wire Kokoro local TTS and hosted TTS into the server installer"
```

---

### Task 7: Server install — image-gen (private repo, user-supplied URL)

**Files:**
- Modify: `deploy/server_install.py`
- Modify: `tests/test_deploy_server_install.py`

**Interfaces:**
- Produces: `setup_image_gen(repo_dir, device, run_cmd, which) -> None`. `run()` gains an `image_gen_repo_url: str | None = None` parameter (already in the Task 5 signature, unused until now): when `recommendation.enable_image_gen` is true AND `image_gen_repo_url` is given, clones+sets up `ultra-fast-image-gen` there and writes an `image-server` unit that runs nightwire's own `frontend/scripts/start-image-server.mjs`; when `enable_image_gen` is true but no URL was given, `enable_image_gen` is treated as false for the rest of `run()` (nothing to clone) and this is reflected in the returned env. Windows service writing is restructured here into one list, since this task is what makes 3 possible services (`nightwire-server`, `kokoro-server`, `image-server`) real.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_deploy_server_install.py`:

```python
from deploy.server_install import setup_image_gen


def test_setup_image_gen_creates_venv_and_installs_requirements(tmp_path):
    calls = []
    repo_dir = tmp_path / "ultra-fast-image-gen"
    repo_dir.mkdir()

    setup_image_gen(repo_dir, device="cuda", run_cmd=calls.append, which=lambda name: "/usr/bin/python")

    assert any(cmd[:3] == ["python", "-m", "venv"] for cmd in calls)
    assert any("requirements.txt" in cmd[-1] for cmd in calls if cmd)


def test_setup_image_gen_cpu_uses_stable_cpu_wheel_index(tmp_path):
    calls = []
    repo_dir = tmp_path / "ultra-fast-image-gen"
    repo_dir.mkdir()

    setup_image_gen(repo_dir, device="cpu", run_cmd=calls.append, which=lambda name: "/usr/bin/python")

    assert any("download.pytorch.org/whl/cpu" in " ".join(cmd) for cmd in calls)


def test_run_with_image_gen_clones_when_url_given(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="none", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: "something",
        image_gen_repo_url="git@example.com:private/ultra-fast-image-gen.git",
    )

    assert env["NIGHTWIRE_IMAGE_BACKEND"] == "flux"
    assert ["git", "clone", "git@example.com:private/ultra-fast-image-gen.git", str(tmp_path / "siblings" / "ultra-fast-image-gen")] in calls
    image_unit = tmp_path / "units" / "nightwire-image-server.service"
    assert image_unit.exists()
    assert "ULTRA_FAST_IMAGE_GEN_DIR" in image_unit.read_text()


def test_run_disables_image_gen_when_no_url_given_even_if_recommended(tmp_path):
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="none", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: None, which=lambda name: "something", image_gen_repo_url=None,
    )

    assert env["NIGHTWIRE_IMAGE_BACKEND"] == "none"
    assert not (tmp_path / "units" / "nightwire-image-server.service").exists()


def test_run_on_windows_writes_one_start_script_for_every_enabled_service(tmp_path):
    profile = HardwareProfile(os="windows", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="kokoro", reasoning="test")

    run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: None, which=lambda name: "something",
        image_gen_repo_url="https://example.com/private.git",
    )

    content = (tmp_path / "units" / "start-all.ps1").read_text()
    assert "nightwire-server" in content
    assert "kokoro-server" in content
    assert "image-server" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_server_install.py -v`
Expected: FAIL — `setup_image_gen` doesn't exist; `run()` still ignores `image_gen_repo_url` and always writes `NIGHTWIRE_IMAGE_BACKEND=none`; Windows only writes `nightwire-server` today.

- [ ] **Step 3: Implement**

Add to `deploy/server_install.py`:

```python
def setup_image_gen(repo_dir: Path, device: Literal["cuda", "cpu", "mps"], run_cmd: CommandRunner = _default_run, which: Callable[[str], str | None] = shutil.which) -> None:
    venv_dir = repo_dir / ".venv"
    if not venv_dir.exists():
        run_cmd(["python", "-m", "venv", str(venv_dir)])
    venv_python = str(venv_dir / ("Scripts/python.exe" if _is_windows() else "bin/python"))
    if device == "cpu":
        # The CPU wheel index is stable and safe to hardcode. The CUDA case
        # deliberately does NOT pin a specific index here: PyTorch's CUDA
        # wheel tag (cuXXX) changes release to release, and a version pinned
        # today would silently go stale. Plain `pip install torch` resolves
        # a working GPU-enabled wheel for the common case; a user on an
        # unusual CUDA version should install their own torch build into
        # this venv first.
        run_cmd([venv_python, "-m", "pip", "install", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu"])
    else:
        run_cmd([venv_python, "-m", "pip", "install", "torch", "torchvision"])
    run_cmd([venv_python, "-m", "pip", "install", "-r", str(repo_dir / "requirements.txt")])
```

Rewrite `run()` fully to collect service entries once and write them together at the end (replacing the earlier per-service `if profile.os == "linux": write_systemd_unit(...)` calls scattered through Tasks 5-6):

```python
def run(
    profile: HardwareProfile,
    recommendation: Recommendation,
    siblings_dir: Path,
    units_dir: Path,
    run_cmd: CommandRunner = _default_run,
    which: Callable[[str], str | None] = shutil.which,
    image_gen_repo_url: str | None = None,
    tts_api_key: str | None = None,
) -> dict[str, str]:
    if not ollama_installed(which):
        install_ollama(profile.os, run_cmd)
    pull_model(recommendation.ollama_model, run_cmd)

    device: Literal["cuda", "cpu", "mps"] = "cpu" if profile.gpu_vendor == "none" else _DEVICE_BY_OS[profile.os]
    env = {"NIGHTWIRE_MODEL": recommendation.ollama_model}
    services: list[tuple[str, list[str], Path, dict[str, str]]] = []

    if recommendation.tts_backend == "kokoro":
        kokoro_dir = siblings_dir / "Kokoro-FastAPI"
        clone_repo(KOKORO_REPO_URL, kokoro_dir, run_cmd)
        setup_kokoro(kokoro_dir, device, run_cmd, which)
        kokoro_argv = kokoro_start_command(kokoro_dir, device, profile.os == "windows")
        services.append(("kokoro-server", kokoro_argv, kokoro_dir, {"ALLOW_DEV_UNLOAD": "true"}))
        env["NIGHTWIRE_TTS_BACKEND"] = "kokoro"
    elif recommendation.tts_backend == "hosted":
        env["NIGHTWIRE_TTS_BACKEND"] = "openai"
        if tts_api_key:
            env["NIGHTWIRE_TTS_API_KEY"] = tts_api_key
    else:
        env["NIGHTWIRE_TTS_BACKEND"] = "none"

    if recommendation.enable_image_gen and image_gen_repo_url:
        image_gen_dir = siblings_dir / "ultra-fast-image-gen"
        clone_repo(image_gen_repo_url, image_gen_dir, run_cmd)
        setup_image_gen(image_gen_dir, device, run_cmd, which)
        image_env = {"ULTRA_FAST_IMAGE_GEN_DIR": str(image_gen_dir)}
        services.append(("image-server", ["npm", "run", "image:server"], Path.cwd() / "frontend", image_env))
        env["NIGHTWIRE_IMAGE_BACKEND"] = "flux"
    else:
        env["NIGHTWIRE_IMAGE_BACKEND"] = "none"

    services.append(("nightwire-server", ["python", "-m", "server"], Path.cwd(), env))

    if profile.os == "linux":
        for name, argv, working_dir, service_env in services:
            write_systemd_unit(name, working_dir, " ".join(argv), service_env, units_dir)
    elif profile.os == "macos":
        for name, argv, working_dir, service_env in services:
            write_launchd_plist(name, working_dir, argv, service_env, units_dir)
    else:
        write_windows_start_script(services, units_dir / "start-all.ps1")

    return env
```

Remove the now-duplicated per-service unit-writing code left over from Tasks 5-6 (the old `if profile.os == "linux": write_systemd_unit("nightwire-server", ...)` block and the Task 6 kokoro-specific `if profile.os == "linux": write_systemd_unit("kokoro-server", ...)` block) — this task's `run()` replaces both wholesale with the single loop above.

- [ ] **Step 4: Run the full server_install test file to verify everything passes**

Run: `pytest tests/test_deploy_server_install.py -v`
Expected: PASS (16 tests total)

- [ ] **Step 5: Commit**

```bash
git add deploy/server_install.py tests/test_deploy_server_install.py
git commit -m "feat: wire image-gen (private repo, user-supplied URL) into the server installer"
```

---

### Task 8: Client install (`deploy/client_install.py`)

**Files:**
- Create: `deploy/client_install.py`
- Test: `tests/test_deploy_client_install.py`

**Interfaces:**
- Produces: `node_version_ok(run) -> tuple[bool, str]` (returns whether Node >=22 and the raw version string), `run(server_url, frontend_dir, run_cmd=...) -> None` (writes `frontend/.env.local` and runs `npm ci`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deploy_client_install.py
from deploy.client_install import node_version_ok, run


def test_node_version_ok_true_for_22_plus():
    ok, version = node_version_ok(lambda cmd: "v22.4.0\n")
    assert ok is True
    assert version == "v22.4.0"


def test_node_version_ok_false_for_below_22():
    ok, version = node_version_ok(lambda cmd: "v20.11.0\n")
    assert ok is False
    assert version == "v20.11.0"


def test_node_version_ok_false_when_node_missing():
    def fake_run(cmd):
        raise FileNotFoundError("no node")

    ok, version = node_version_ok(fake_run)
    assert ok is False
    assert version == "not found"


def test_run_writes_env_local_and_runs_npm_ci(tmp_path):
    calls = []
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    run("ws://192.168.1.10:8000", frontend_dir, run_cmd=calls.append)

    env_file = frontend_dir / ".env.local"
    assert env_file.read_text().strip() == "NEXT_PUBLIC_NIGHTWIRE_WS_URL=ws://192.168.1.10:8000"
    assert calls == [["npm", "ci"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_client_install.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deploy.client_install'`

- [ ] **Step 3: Implement `deploy/client_install.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

CommandRunner = Callable[[list[str]], str]


def _default_run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return result.stdout


def node_version_ok(run: CommandRunner = _default_run) -> tuple[bool, str]:
    try:
        output = run(["node", "--version"]).strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False, "not found"
    major = int(output.lstrip("v").split(".")[0])
    return major >= 22, output


def run(server_url: str, frontend_dir: Path, run_cmd: Callable[[list[str]], None] = lambda cmd: subprocess.run(cmd, check=True, cwd=frontend_dir)) -> None:
    (frontend_dir / ".env.local").write_text(f"NEXT_PUBLIC_NIGHTWIRE_WS_URL={server_url}\n")
    run_cmd(["npm", "ci"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_deploy_client_install.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add deploy/client_install.py tests/test_deploy_client_install.py
git commit -m "feat: add client installer (Node version check, server URL, npm ci)"
```

---

### Task 9: CLI (`deploy/cli.py`) + entry point

**Files:**
- Create: `deploy/cli.py`
- Modify: `pyproject.toml` — add `[project.scripts]` with `nightwire-deploy = "deploy.cli:main"`
- Test: `tests/test_deploy_cli.py`

**Interfaces:**
- Consumes: `probe` (Task 1), `recommend` (Task 2), `server_install.run`/`client_install.run` (Tasks 5-8).
- Produces: `confirm(recommendation, input_fn=input) -> Recommendation`, `main(argv=None, input_fn=input) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_deploy_cli.py
from deploy.cli import confirm, main
from deploy.tiers import Recommendation


def _rec(**overrides):
    defaults = dict(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="kokoro", reasoning="test reasoning")
    defaults.update(overrides)
    return Recommendation(**defaults)


def test_confirm_accepts_default_on_enter():
    result = confirm(_rec(), input_fn=lambda prompt: "")
    assert result.ollama_model == "qwen3:8b"


def test_confirm_raises_systemexit_on_no():
    try:
        confirm(_rec(), input_fn=lambda prompt: "n")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_confirm_customize_overrides_model():
    inputs = iter(["customize", "qwen3:4b", "n", "hosted"])
    result = confirm(_rec(), input_fn=lambda prompt: next(inputs))
    assert result.ollama_model == "qwen3:4b"
    assert result.enable_image_gen is False
    assert result.tts_backend == "hosted"


def test_main_detect_prints_and_returns_zero(capsys):
    code = main(["detect"])
    captured = capsys.readouterr()
    assert code == 0
    assert "gpu_vendor" in captured.out


def test_main_install_client_calls_client_install(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("deploy.cli.run_client_install", lambda server_url, frontend_dir=None: calls.append(server_url))
    inputs = iter(["ws://localhost:8000"])

    code = main(["install", "--role", "client"], input_fn=lambda prompt: next(inputs))

    assert code == 0
    assert calls == ["ws://localhost:8000"]


def test_main_install_server_skips_image_gen_when_no_url_and_calls_server_install(monkeypatch):
    captured = {}

    def fake_server_install(profile, recommendation, siblings_dir, units_dir, **kwargs):
        captured["recommendation"] = recommendation
        captured["kwargs"] = kwargs
        return {"NIGHTWIRE_MODEL": recommendation.ollama_model}

    monkeypatch.setattr("deploy.cli.run_server_install", fake_server_install)
    inputs = iter(["", "", ""])  # confirm default, blank image-gen url, (no tts prompt since kokoro)

    code = main(["install", "--role", "server"], input_fn=lambda prompt: next(inputs))

    assert code == 0
    assert captured["kwargs"]["image_gen_repo_url"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_deploy_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deploy.cli'`

- [ ] **Step 3: Implement `deploy/cli.py`**

```python
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from deploy.client_install import run as run_client_install
from deploy.detect import probe
from deploy.server_install import run as run_server_install
from deploy.tiers import Recommendation, recommend

InputFn = Callable[[str], str]


def confirm(recommendation: Recommendation, input_fn: InputFn = input) -> Recommendation:
    print(f"\nDetected tier: {recommendation.tier}")
    print(recommendation.reasoning)
    print(f"\n  model:      {recommendation.ollama_model}")
    print(f"  image-gen:  {'on' if recommendation.enable_image_gen else 'off'}")
    print(f"  tts:        {recommendation.tts_backend}")
    choice = input_fn("\nProceed with this configuration? [Y/n/customize]: ").strip().lower()
    if choice in ("", "y", "yes"):
        return recommendation
    if choice in ("n", "no"):
        raise SystemExit("Install cancelled.")

    model = input_fn(f"Ollama model [{recommendation.ollama_model}]: ").strip() or recommendation.ollama_model
    image_raw = input_fn(f"Enable image-gen? [{'Y/n' if recommendation.enable_image_gen else 'y/N'}]: ").strip().lower()
    enable_image_gen = image_raw.startswith("y") if image_raw else recommendation.enable_image_gen
    tts_raw = input_fn(f"TTS backend (kokoro/hosted/none) [{recommendation.tts_backend}]: ").strip() or recommendation.tts_backend
    return Recommendation(tier=recommendation.tier, ollama_model=model, enable_image_gen=enable_image_gen, tts_backend=tts_raw, reasoning=recommendation.reasoning)


def _install_server(input_fn: InputFn) -> int:
    profile = probe()
    recommendation = recommend(profile)
    confirmed = confirm(recommendation, input_fn)

    image_gen_repo_url = None
    if confirmed.enable_image_gen:
        image_gen_repo_url = input_fn(
            "Git URL for the (private) ultra-fast-image-gen repo [blank to skip image-gen]: "
        ).strip() or None

    tts_api_key = None
    if confirmed.tts_backend == "hosted":
        tts_api_key = input_fn("OpenAI API key for hosted TTS: ").strip()

    run_server_install(
        profile,
        confirmed,
        siblings_dir=Path.cwd().parent,
        units_dir=Path.home() / ".config" / "systemd" / "user",
        image_gen_repo_url=image_gen_repo_url,
        tts_api_key=tts_api_key,
    )
    print("Server install complete.")
    return 0


def _install_client(input_fn: InputFn) -> int:
    server_url = input_fn("Nightwire server WebSocket URL [ws://localhost:8000]: ").strip() or "ws://localhost:8000"
    run_client_install(server_url, Path.cwd() / "frontend")
    print("Client install complete.")
    return 0


def main(argv: list[str] | None = None, input_fn: InputFn = input) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="nightwire-deploy")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("detect")
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--role", choices=["server", "client"], required=True)

    args = parser.parse_args(argv)

    if args.command == "detect":
        profile = probe()
        recommendation = recommend(profile)
        print(profile.model_dump_json(indent=2))
        print(recommendation.reasoning)
        return 0

    if args.role == "server":
        return _install_server(input_fn)
    return _install_client(input_fn)


if __name__ == "__main__":
    sys.exit(main())
```

Note: `client_install.run`'s signature from Task 8 is `run(server_url, frontend_dir, run_cmd=...)` — `_install_client` calls it with just the first two positional args, relying on `run_cmd`'s default. Match the `test_main_install_client_calls_client_install` test's monkeypatched signature `(server_url, frontend_dir=None)` exactly when patching.

Add to `pyproject.toml`:

```toml
[project.scripts]
nightwire-deploy = "deploy.cli:main"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pip install -e ".[dev]"` then `pytest tests/test_deploy_cli.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the entire test suite**

Run: `pytest -v`
Expected: PASS (every test in `tests/`, old and new)

- [ ] **Step 6: Verify the entry point actually resolves**

Run: `nightwire-deploy detect`
Expected: prints a `HardwareProfile` JSON blob and a reasoning string for the real machine, no crash

- [ ] **Step 7: Commit**

```bash
git add deploy/cli.py pyproject.toml tests/test_deploy_cli.py
git commit -m "feat: add nightwire-deploy CLI entry point"
```

---

### Task 10: Docs — README rewrite + `docs/deployment.md`

**Files:**
- Modify: `README.md` (the "Running it" section)
- Create: `docs/deployment.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Rewrite `README.md`'s "Running it" section**

Replace the current section (lines 31-44) with:

```markdown
## Running it

**Server** (detects your GPU/RAM, recommends a model tag and which optional backends fit, confirms before touching anything):

```bash
pip install -e ".[dev]"
nightwire-deploy install --role server
```

**Client** (checks Node, asks which server to connect to):

```bash
nightwire-deploy install --role client
cd frontend && npm run dev   # http://localhost:3000/nightwire
```

See `docs/deployment.md` for what detection checks, the tier table, and troubleshooting.

<details>
<summary>Manual / advanced (no installer)</summary>

```bash
# server
pip install -e ".[dev]"
python -m server                     # ws://localhost:8000

# web frontend (development)
cd frontend && npm ci && npm run dev # http://localhost:3000/nightwire
```

Image generation additionally needs a running `ultra-fast-image-gen` worker (`open-dungeon`'s `image_server/`) on `http://127.0.0.1:7869` — optional; without it, everything except scene/portrait images works normally. Backend/model selection is environment-driven: `NIGHTWIRE_MODEL`, `NIGHTWIRE_IMAGE_BACKEND` (`flux`/`none`), `NIGHTWIRE_TTS_BACKEND` (`kokoro`/`openai`/`none`), `NIGHTWIRE_TTS_API_KEY`.

</details>
```

- [ ] **Step 2: Write `docs/deployment.md`**

```markdown
# Deploying Nightwire

`nightwire-deploy` detects your hardware before it acts: it probes, recommends a configuration with the reasoning behind it, waits for you to confirm (or customize), and only then pulls models, clones sibling services, and registers anything.

## Server

```bash
pip install -e ".[dev]"
nightwire-deploy install --role server
```

What it checks: OS, GPU vendor + VRAM (`nvidia-smi`; Apple Silicon uses unified system RAM instead since there's no discrete VRAM to query), total RAM, CPU cores.

What it recommends, by tier:

| Tier | Hardware | Ollama model | Image-gen | TTS |
|---|---|---|---|---|
| `standard` | NVIDIA, ≥7.5GB VRAM | `qwen3:8b` | on | Kokoro (local) |
| `lite` | NVIDIA, 3-7.5GB VRAM | `qwen3:4b` | off | Kokoro (local) |
| `minimal` | NVIDIA, 2-3GB VRAM | `qwen3:1.7b` | off | hosted (OpenAI TTS) |
| `apple-unified` | Apple Silicon | sized off unified RAM | off (SDNQ is CUDA-only, unverified on Metal) | Kokoro if RAM allows, else hosted |
| `cpu-only` | no GPU | capped at `qwen3:4b` | off (no CPU path for FLUX.2-klein-4B) | Kokoro if RAM allows, else hosted |

The `standard` tier is the one real, live-verified configuration (the project's own RTX 2080 deployment — see `ROADMAP.md`'s Phase 3/5/6 entries). Everything else follows the same arithmetic (`docs/superpowers/specs/2026-08-26-deployment-tooling-design.md` has the full reasoning and citations) but hasn't been run on real hardware at that tier yet — if something doesn't fit, `customize` at the confirm prompt to override any field.

**Image generation needs a private repo.** `ultra-fast-image-gen` isn't public — the installer will ask for its git URL when you confirm image-gen. Leave it blank to skip image-gen even on hardware that could run it.

**Hosted TTS needs an API key.** You'll be prompted for an OpenAI API key when the recommended (or customized) TTS backend is `hosted`.

Services register as systemd --user units on Linux, launchd agents on macOS, and as a generated `start-all.ps1` on Windows (no persistent service on Windows yet — there's no real Windows deployment to design a service story against).

## Client

```bash
nightwire-deploy install --role client
cd frontend && npm run dev
```

Checks Node ≥22, asks for the server's WebSocket URL (default `ws://localhost:8000`), writes `frontend/.env.local`. No hardware detection — the client never runs a model.

## Troubleshooting

**`CUDA out of memory` during scene-image generation, even though the model fit fine on its own.** This happened for real on the reference 8GB deployment: Kokoro's resident footprint (~1GB) plus FLUX's peak VAE-decode allocation together exceeded 8GB, even though each fit individually. Fixed upstream by `KokoroBackend.unload()` — `server/narration.py` unloads TTS (and the narrator model) before every image generation. If you see this on a customized/non-standard tier, the fix is the same class of problem: something resident is eating headroom FLUX needs at its peak. Lower the model tier or disable a resident backend rather than assuming the VRAM math from the tier table alone.

**`git pull` looks like a no-op after a fresh clone.** A real incident, not hypothetical (see `ROADMAP.md`'s Phase 5 entry, "Deploy-path bug"): if the target directory has no `.git` of its own, git commands silently walk up to an ancestor repo. Confirm with `git rev-parse --show-toplevel` before assuming a checkout is tracking what you think it is.

**`nightwire-deploy install --role server` says Ollama isn't found even though it's running.** The installer checks `PATH`, not whether the Ollama service is reachable. If you installed Ollama in a non-standard location, add it to `PATH` before re-running, or run `ollama pull <model>`/register services yourself using the env vars the installer would have written (see `README.md`'s manual/advanced section).
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/deployment.md
git commit -m "docs: rewrite Running It around nightwire-deploy, add deployment guide"
```

---

### Task 11: `Cyb3rRon1n.github.io` nightwire card

**Files:**
- Modify: `../Cyb3rRon1n.github.io/index.html` (sibling repo/submodule, not nightwire itself)

**Interfaces:** none.

- [ ] **Step 1: Find the existing project-card markup**

Read `index.html` and locate the repeated markup for the existing Vulcan/Anvil/Atlas/Oracle cards (same list the repo's own `README.md` names). Note the exact tag structure, class names, and any icon/badge convention used per card.

- [ ] **Step 2: Add a matching nightwire card**

Insert a new card immediately after Oracle's (before the `dojo` "start here" band, per `README.md`'s description of dojo's own special placement), using the exact same markup shape as the existing cards — same classes, same structural elements (title, one-line description, link). Description text: something in the site's existing voice, one line, e.g. "A cyberpunk tabletop RPG with an AI game master — playable solo or with friends, in a browser." (reusing nightwire's own README tagline verbatim). Link target: `https://github.com/Cyb3rRon1n/nightwire`.

- [ ] **Step 3: Open `index.html` directly in a browser and confirm the new card renders correctly**

Since this is a self-contained static file with no build step (per its own `README.md`), open it directly (`file://` path) or via a quick local static server, and visually confirm: the new card matches the others' layout/spacing, the link is correct, and no existing card broke.

- [ ] **Step 4: Commit**

```bash
cd ../Cyb3rRon1n.github.io
git add index.html
git commit -m "feat: add nightwire project card"
```

Note: if `Cyb3rRon1n.github.io` is registered as a git submodule of the outer `repos` checkout (it is, per `.gitmodules`), this commit happens inside the submodule's own repo — the outer repo will then show the submodule pointer as changed, which is a separate, deliberate commit in the outer repo if the user wants that pointer bumped (not part of this task).

---

## Self-Review Notes

- **Spec coverage**: CLI shape (Task 9), server detect→tier→confirm→act (Tasks 1,2,5-7,9), client flow (Tasks 8-9), docs (Task 10), github.io (Task 11), testing approach (pure logic unit-tested throughout, orchestration smoke-tested via injected runners) — every spec section has a task.
- **Corrections made during planning, not in the spec**: `ultra-fast-image-gen`'s clone URL is user-supplied, never hardcoded (confirmed private in this project's own Phase 5 plan). The image-server service launches via nightwire's own already-working `frontend/scripts/start-image-server.mjs`, not a guessed raw command. PyTorch's CUDA wheel index is deliberately left unpinned (drifts per release) while the CPU index (stable) is hardcoded. Ollama's own official installer already manages its own system service, so no separate `ollama` unit is generated by this plan.
- **Type/signature consistency checked**: `Recommendation.tts_backend` is `Literal["kokoro","hosted","none"]` throughout; `HardwareProfile` fields match between Task 1's definition and every later task's usage; `server_install.run()`'s signature is introduced once in Task 5 and only extended (never renamed) through Tasks 6-7.
