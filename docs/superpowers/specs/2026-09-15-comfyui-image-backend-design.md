# Nightwire ComfyUI Image Backend Design — Phase 10

Status: designed, not yet implemented. Builds on the image-generation spec (Phase 5, `2026-08-23-image-generation-design.md`) and its already-established `ImageBackend` protocol. Sourced from independent verification of nightwire's own documented gap plus real, live testing against actual ComfyUI infrastructure — not from oracle-as-precedent. Oracle's own `server/image_backend.py` was read as a technical reference for ComfyUI's HTTP+WebSocket API shape (workflow-graph submission, progress polling, output fetch) — the same external tool's API regardless of which project calls it, not a design/ruleset decision being copied. Explicitly approved by the project owner for this one case (README's Docker-deployment section and its own documented "no shared-volume wiring" gap already name the underlying problem independently).

## The actual requirement

`FluxWorkerBackend` (Phase 5) is MLX-based — Apple Silicon only. Nightwire's own README says so plainly: "Image generation is not part of the Docker stack... there's no shared-volume wiring here for its output image files, so generated images won't reach the containerized web frontend without more plumbing." This is a real, currently-open deployment gap, not a hypothetical one — nightwire runs as a Docker stack (this project's primary deployment shape per its own `docker-compose.yml` and `CLAUDE.md`), and MLX cannot run in a Linux container at all.

The fix: a second `ImageBackend` implementation that talks to a real ComfyUI instance over plain HTTP/WebSocket — cross-platform, Docker-reachable, no MLX dependency.

## Backend: ComfyUI, config-selectable alongside FluxWorkerBackend

**Decision: add, don't replace.** `IMAGE_BACKEND` env var (`flux_worker` default, preserving current behavior; `comfyui` as the new option) selects between them at `server/__main__.py`'s startup, via a new `create_image_backend()` factory in `narrator/image_backend.py`. Mac/MLX users keep `FluxWorkerBackend`; Linux/Docker users (this project's primary deployment target) get a working alternative. Nothing about `FluxWorkerBackend` changes.

**Real, live-verified target**: `sentinel` (a LAN machine, RTX 2080 8GB) already runs a real ComfyUI 0.35.0 instance via an Anvil-generated stack, confirmed live at time of writing (`/system_stats` responded 200, real GPU/RAM figures returned) at `192.168.10.19:8188`. **This IP is DHCP-assigned and has already changed once** — `COMFYUI_URL` is a config default, not a hardcoded assumption; verify reachability before relying on it, same caution already on file for this machine elsewhere in the owner's infrastructure notes.

**Checkpoint**: `v1-5-pruned-emaonly-fp16.safetensors` — the one real checkpoint actually loaded on sentinel's instance right now (confirmed via `/object_info`'s `CheckpointLoaderSimple` input list), not assumed from documentation. `COMFYUI_CHECKPOINT` env var, defaulting to this value.

## Known, deliberate limitation: no reference-image support

**Sentinel's real ComfyUI install has no IPAdapter, InstantID, or any face-consistency custom node** — confirmed directly against its live `/object_info` (953 nodes enumerated, zero IPAdapter/InstantID/FaceID matches). This means `ComfyUIBackend.generate_portrait`/`generate_scene` will be **text-prompt-only**, same limitation oracle's own `ComfyUIBackend` documents for the identical reason ("needs IPAdapter, a real custom-node dependency a bare install doesn't have").

This is a real regression relative to `FluxWorkerBackend`, which nightwire's Phase 8 already built real reference-photo support for (`reference_photos`/`reference_paths` params on the `ImageBackend` protocol) — nightwire's own stated differentiator ("a character looks like themselves across turns"). Accepted here because:
- The protocol already supports the parameters optionally (`reference_photos: list[str] | None`) — `ComfyUIBackend` simply never uses them, same as oracle's version never receiving them at all. No protocol change needed.
- This is config-selectable, not a replacement — anyone who needs reference consistency stays on `FluxWorkerBackend`.
- Installing IPAdapter and re-verifying consistency on this specific card/checkpoint is real, separate scope (a follow-up phase, not blocking this one) — not designed here.

## Component

New `narrator/comfyui_backend.py`. Implements the existing `ImageBackend` protocol (`generate_portrait`, `generate_scene`) — `server/narration.py` and `server/portrait.py` need zero changes, same as adding any other protocol implementation.

**Workflow-graph shape** (technical reference: oracle's `ComfyUIBackend`, a real working integration against this same tool): `CheckpointLoaderSimple` → two `CLIPTextEncode` (positive/negative) → `EmptyLatentImage` → `KSampler` → `VAEDecode` → `SaveImage`. Submitted via `POST /prompt` with a `client_id`; progress tracked over `GET /ws?clientId=...`; final image fetched via `GET /history/{prompt_id}` then `GET /view`. `generate_scene` reuses the identical graph-building code as `generate_portrait` with a different prompt string and no reference conditioning (matching the "no reference support" limitation above) — the two methods differ only in prompt content and output naming (`filename_prefix`), not in graph shape.

**Resolution**: 512×768 for `generate_portrait`, 512×512 for `generate_scene` — oracle's own defaults, fits comfortably on an 8GB card at SD1.5. These don't need to match `FluxWorkerBackend`'s own aspect numbers (384×512 portrait / 512×512 square, `_dimensions_for`) pixel-for-pixel — it's a different model (FLUX vs. SD1.5) with its own reasonable defaults, not a shared constant; both independently respect the same "long side around 512px, fits an 8GB card" ceiling Phase 5 already established. No hires-fix/LoRA/face-detail quality passes in this first cut — oracle's `ComfyUIOptions` shows the extension points exist if wanted later, but nothing here requires them yet.

## Config

| Variable | Default | Purpose |
|---|---|---|
| `IMAGE_BACKEND` | `flux_worker` | `flux_worker` \| `comfyui` |
| `COMFYUI_URL` | `http://192.168.10.19:8188` | Real, currently-live sentinel address — DHCP, verify before trusting |
| `COMFYUI_CHECKPOINT` | `v1-5-pruned-emaonly-fp16.safetensors` | Must match a real checkpoint loaded on the target instance |

## Testing

Unit tests mocking `httpx`/`websockets` (oracle's `tests/test_image_backend.py` shape: fake `/prompt` submit, fake ws progress/executing messages, fake `/history`+`/view` responses) — verifies workflow-graph construction and the submit→poll→fetch sequence without needing a real GPU for CI.

**Live verification** (this project's standing discipline — Phase 5's own "real GPU, not just mocks" precedent, independently re-affirmed here, not cited from oracle): one real portrait generation against sentinel's actual running instance before calling this phase done, same as every other nightwire phase's live-verification bar.

## What's deliberately deferred

- IPAdapter/InstantID reference-image support for the ComfyUI path — real follow-up scope, only worth doing if the text-prompt-only version proves insufficient in practice.
- Quality passes (hires-fix, LoRA, face-detail) — oracle's `ComfyUIOptions` shows the shape if ever wanted; not built here.
- Any change to `FluxWorkerBackend` or its Apple Silicon deployment path.
- A hosted image-API backend (oracle also has `OpenAIImageBackend`/`PollinationsImageBackend`) — not ruled out, not designed here; this phase is specifically about closing the Docker/Linux gap, not adding a third tier.
- Scene-image compositing into a live map — already explicitly out of scope project-wide (ROADMAP.md's "Explicitly not doing (yet)").
