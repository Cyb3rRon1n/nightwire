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
