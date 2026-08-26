# Nightwire Deployment Tooling Design — Phase 7

Status: designed, not yet implemented. Every real deployment so far (msi-laptop, this machine) was done by hand — manual `git clone`, manual `pip install -e`, hand-written systemd --user units per service, VRAM budgeting worked out live via trial and error (see `ROADMAP.md`'s Phase 3/5/6 entries for the real OOM incident between Kokoro and the image backend on an 8GB card). This phase turns that hand-rolled process into a "detect before acting" installer: probe the machine, recommend a configuration with real numbers behind it, confirm with the user, then act.

## The actual requirement

Two separable installs, not one:

- **Server**: needs hardware detection, because the right configuration (which Ollama model tag, whether image-gen fits, which TTS backend) depends on what GPU/RAM is actually there. This is the complex half.
- **Client**: the Next.js frontend never runs a model — it just needs Node present and a server URL to point at. No hardware logic at all.

Both ship as one CLI, `nightwire-deploy`, added to the existing Python project rather than as separate shell/PowerShell scripts — the project is already Python, and detection logic (parse GPU output → pick a tier) is the same code on every OS; only the last mile (service registration) forks per platform.

## CLI shape

New `[project.scripts]` entry point, `deploy/` package alongside `ruleset/`, `engine/`, `narrator/`, `server/`:

```
nightwire-deploy install --role server
nightwire-deploy install --role client
nightwire-deploy detect          # report only, no prompts, no changes — for debugging/CI
```

`install` always runs detect → report → confirm → act, in that order, for both roles. `detect` alone is the escape hatch for "just tell me what you'd do" without any prompt loop, useful for scripting and for verifying the probe itself works on a new machine before trusting it to act.

## Server: detect

```python
class HardwareProfile(BaseModel):
    os: Literal["linux", "macos", "windows"]
    gpu_vendor: Literal["nvidia", "apple", "none"]
    vram_gb: float | None       # None when gpu_vendor == "none"
    system_ram_gb: float
    cpu_cores: int
```

- **NVIDIA**: `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits` — present and on PATH the same way on Linux, macOS (rare, eGPU), and Windows once drivers are installed, so one code path covers all three OSes for the vendor real deployments actually use.
- **Apple Silicon**: no discrete VRAM — Ollama's Metal backend shares unified system RAM with everything else running. Reported as `gpu_vendor="apple"`, `vram_gb=None`, and the tiering step below uses `system_ram_gb` as the budget signal instead, with a documented haircut for OS/app overhead (see open item below).
- **Anything else** (no NVIDIA GPU found, not Apple Silicon — includes AMD, which no real deployment targets today): `gpu_vendor="none"`. Tiering falls back to CPU inference sized off `system_ram_gb`.
- `system_ram_gb` / `cpu_cores`: `psutil` — already a transitive dependency of nothing currently in `pyproject.toml`, so this is the one new runtime dependency this phase adds (stdlib's own `os.cpu_count()` covers cores, but total RAM cross-platform without `psutil` means hand-rolling three separate `/proc/meminfo` / `sysctl` / WMI paths, which is exactly the kind of already-solved problem the ladder says to reach for a dependency over).

## Server: tier → recommendation

```python
class Recommendation(BaseModel):
    tier: str
    ollama_model: str
    enable_image_gen: bool
    tts_backend: Literal["kokoro", "hosted", "none"]
    reasoning: str          # shown to the user verbatim in the confirm prompt
```

One tier is real and confirmed, not estimated: **8GB NVIDIA VRAM** → `qwen3:8b` resident + Kokoro resident + on-demand image-gen via the existing unload/reload dance in `server/narration.py` — this is exactly the RTX 2080 configuration already live-verified in Phase 3/5/6. Everything above 8GB gets the same recommendation (headroom only helps). Below 8GB, and the CPU-only / Apple-unified-RAM tiers, need their own thresholds.

**Open item, deliberately not invented here**: the smaller-tag VRAM footprints (`qwen3:4b`, `qwen3:1.7b`, `qwen3:0.6b`) and the exact cutoff where image-gen/Kokoro stop being worth recommending are real numbers to pull from Ollama's own model library pages and llama.cpp GGUF sizing tables during implementation — not memory/assumption, per this project's standing research rule (`CLAUDE.md`). Same for the Apple-unified-RAM haircut. The implementation plan carries this as its own research task before the tier table is filled in; this design fixes the *shape* of the tiering (an ordered table from most to least capable, each row a `Recommendation`), not the exact numbers.

## Server: report → confirm → act

Report prints the detected `HardwareProfile` and the `Recommendation.reasoning` in full, then prompts `[Y/n/customize]`. `customize` drops into per-field prompts (override the model tag, force image-gen/TTS on or off) seeded with the recommended values as defaults — never a blank form. Nothing below this line runs before a yes.

**Act**, in order:
1. Check `ollama` is on PATH and its service answers (`ollama list`). If missing: confirm, then run the official install path per OS (`winget install Ollama.Ollama` / official install script) rather than a bespoke download-and-run — reuses upstream's own installer instead of reimplementing it.
2. `ollama pull <chosen tag>`.
3. If image-gen is enabled: clone `ultra-fast-image-gen` (path configurable, default a sibling directory next to `nightwire`), create its venv, install its deps — same shape whether image-gen is on or off, just skipped when off.
4. If TTS is `kokoro`: same clone/venv/install for `Kokoro-FastAPI`. If `hosted`: no clone, just prompts for an API key and writes it to config — no local process to manage.
5. Write configuration as **environment variables**, not a new file format — today there's no config file at all: `server/__main__.py`'s `build_app()` hardcodes `NarratorClient(model="qwen3:8b", ...)`, `FluxWorkerBackend()`, and `KokoroBackend()` directly, swapped by hand-editing the file per its own comment. `build_app()` changes to read `NIGHTWIRE_MODEL`, `NIGHTWIRE_IMAGE_BACKEND` (`flux`/`none`), `NIGHTWIRE_TTS_BACKEND` (`kokoro`/`openai`/`none`) and `NIGHTWIRE_TTS_API_KEY` via `os.environ.get(...)`, defaulting to today's exact hardcoded values when unset — so an un-installed dev checkout behaves identically to today. The installer doesn't need a `.env`-parsing dependency: it writes these variables directly into whatever already carries them per platform — `Environment=` lines in the systemd unit, `EnvironmentVariables` in the launchd plist, `$env:` assignments in the Windows start script — so `os.environ` is all `build_app()` ever needs.
6. Register services:
   - **Linux**: systemd --user units for `ollama`, `image-server` (if enabled), `kokoro-server` (if local), `nightwire-server` — same shape as the hand-written units already running on both real Fedora boxes today, just templated instead of hand-typed.
   - **macOS**: equivalent launchd plists (`~/Library/LaunchAgents/`), same four services conditionally.
   - **Windows**: no service registration — there's no real Windows deployment to design a service story against yet (matches the earlier scope decision). Instead, write a `start-all.ps1` that launches each enabled process in its own window/job, printed at the end with instructions to run it.

## Client: detect → confirm → act

No `HardwareProfile`, no tiers. Detect step checks `node --version` against the README's stated `Node 22+` requirement. Report is just "Node 20.x found, need 22+" or "Node 22.4.0 OK" — no reasoning paragraph needed, there's only one fact being checked. Confirm/prompt asks for the nightwire server's WebSocket URL (default `ws://localhost:8000`, matching the README's own documented default). Act writes `frontend/.env.local` with that URL and runs `npm ci`.

## Docs

- **`nightwire/README.md`**: "Running it" section rewritten around the two installer commands as the primary path, with the current manual `pip install -e` / `npm ci` steps kept as a "manual/advanced" fallback immediately below rather than deleted — some contributors will want to skip the installer.
- **`nightwire/docs/deployment.md`** (new): prerequisites, what detection actually checks and why, the tier table once real numbers land, the manual-override flags, and a troubleshooting section built directly from the real incidents already on record in `ROADMAP.md` (the Kokoro/Flux VRAM collision, the msi-laptop no-`.git` deploy-path bug) — real incidents this project already paid for, turned into documentation instead of tribal knowledge.
- **`Cyb3rRon1n.github.io/index.html`**: one new project card for nightwire, matching the existing Vulcan/Anvil/Atlas/Oracle card markup exactly, linking to the nightwire repo. No install instructions duplicated on the site — the card is a pointer, not a mirror.

## Testing

The detection/tiering functions are pure (probe output in, `HardwareProfile`/`Recommendation` out) and branchy — exactly what gets a real test: `tests/test_deploy_detect.py` feeds fixture `nvidia-smi` output (and the "not found" case, and a fixture Apple/`psutil` RAM reading) through the parser and asserts the resulting tier, no live GPU needed to run the suite. The install orchestration itself (subprocess calls to `ollama pull`, `npm ci`, writing service files) is thin plumbing around already-tested decisions — verified live per OS the same way this project verifies everything else (real terminal, real service file, real `systemctl --user status`), not mocked.

## What's deliberately deferred

- Exact VRAM/RAM thresholds for every tier below the confirmed 8GB-NVIDIA row — real research task for implementation, not invented here (see "Server: tier → recommendation" above).
- AMD GPU detection (`rocm-smi` or equivalent) — no real deployment targets AMD today; falls into the generic CPU-only tier until that changes.
- Windows service registration (Task Scheduler / NSSM-style wrapping) — foreground start script only, per the earlier scope decision; revisit if a real Windows deployment ever happens.
- Automatic hardware re-detection / re-tiering after install (e.g. on GPU upgrade) — `install` is a one-time setup flow; re-running it re-detects and re-confirms from scratch, no separate "update my tier" command.
- A packaged desktop client — the client installer targets the existing Next.js web frontend only.
