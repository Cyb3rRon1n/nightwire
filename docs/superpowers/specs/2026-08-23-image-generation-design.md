# Nightwire Image Generation Design — Phase 5

Status: designed, not yet implemented. Builds on the narrator backend (Phase 3) and web frontend (Phase 4a-revised) specs. Every choice below is grounded in independent external research — no oracle-precedent citations (oracle has no image generation at all).

## The actual requirement

Not "generate a picture per turn" in isolation. The real shape, stated directly by the project owner: a player creates a character, reviews it, and once approved, a portrait is generated and saved with that character (shown on their sheet). That same portrait is then used as a **reference image** for later scene/event generation featuring that character — the character should look recognizably like themselves across separate generations, not a new face each time. Priority: fast, without sacrificing quality or immersion.

This is meaningfully harder than open-dungeon's own image feature (plain per-turn text-to-image, no character-identity requirement at all) — it's specifically about maintaining visual identity across generations from a single reference image, zero-shot (no per-character training step; a player approving a portrait and immediately playing can't wait for a LoRA training run).

## Backend: FLUX.2-klein via `ultra-fast-image-gen`

**Decision: reuse open-dungeon's existing FLUX worker (`image_server/`, wrapping the separate `ultra-fast-image-gen` repo), not ComfyUI, not a hosted API.** Real grounding, not a guess:

- **It already does reference-image editing today.** `ultra-fast-image-gen`'s own README: "Upload up to 6 reference images... write a prompt describing the changes." This isn't a capability to build — it's already there, wired into the codebase family nightwire's frontend is built on.
- **Fits the target hardware today, with real numbers.** FLUX.2-klein-4B at 4-bit SDNQ quantization: 8GB VRAM at 512px, ~3s per image on an RTX 3090 (4 steps) per the repo's own README. The current dev hardware (RTX 2080, Turing architecture, 8GB) is older/slower than that benchmark card, so expect somewhat longer — realistically 6-15s at 512px — but the model genuinely fits, unlike the alternatives below.
- **FLUX.1 Kontext** (Black Forest Labs) has the single best *documented* consistency number found — 92% identity match from one reference image ([BFL](https://bfl.ai/models/flux-kontext), [arXiv:2506.15742](https://arxiv.org/html/2506.15742v2)) — but its fast/quantized (FP8/FP4) speed numbers are reported against Ada/Blackwell tensor cores specifically ([NVIDIA blog](https://developer.nvidia.com/blog/optimizing-flux-1-kontext-for-image-editing-with-low-precision-quantization)); the dev GPU is Turing, and no source verifies that quantization path is actually fast on Turing. Real risk of falling back to slow CPU-offload behavior on exactly the hardware this needs to run on today.
- **SDXL + IP-Adapter FaceID** reaches the highest reported consistency (80-95%) but only with a per-character LoRA training step stacked on top ([HF IP-Adapter docs](https://huggingface.co/docs/diffusers/using-diffusers/ip_adapter)) — directly conflicts with "approve a portrait, play immediately." Without the LoRA step, consistency drops. Also carries real OOM risk on 8GB once ControlNet/upscaler are added to the same stack ([AUTOMATIC1111 discussion #11713](https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/11713)).
- **Hosted APIs** (Replicate/fal.ai, InstantID/PhotoMaker-class endpoints) are genuinely competitive on latency once local swap overhead (below) is counted, and cost is low ($0.003-$0.12/image, per [teamday.ai](https://www.teamday.ai/blog/ai-api-pricing-comparison-2026)) — but break the project's local-first stance for no forced reason yet, and add an external dependency/API-key surface this project has deliberately avoided for the narrator itself except as an opt-in secondary. Not ruled out permanently (see "What's deliberately deferred").

**Honest gap in this research, stated plainly**: no source directly benchmarks *reference-editing-mode consistency* on Turing-class 8GB cards specifically. The 92/100 multi-pose consistency number for FLUX.2 is a general benchmark, not measured in this exact reference-editing configuration on this exact card. This is a real, testable hypothesis going into implementation, not a settled fact — the reliability-measurement discipline this project already applies to the narrator (Phase 3's harness) should apply here too: verify on the real hardware before trusting the claim.

## Forward compatibility: better hardware is coming

The project owner is acquiring better GPU hardware down the road. **This design must not hardcode today's 8GB/512px ceiling into the architecture.** Concretely:

- `ImageBackend` is a swappable interface (mirroring `NarratorBackend`'s already-established pattern) — resolution, step count, and model variant are backend *configuration*, not protocol-level constants. Bumping resolution or swapping FLUX.2-klein-4B for FLUX.2-klein-9B (or a future model entirely) on better hardware is a config change, not a redesign.
- The reference-image mechanism (upload reference photos, get a consistent output) is a property of the backend implementation, not the `ImageBackend` protocol's own shape — the protocol just says "generate an image, optionally given reference images." A future backend swap (e.g. to FLUX.1 Kontext once faster hardware makes its quantization path viable, or to a hosted API) doesn't change how the rest of the system calls it.
- No code path should assume 512px specifically — treat it as this backend's current configured value, not a constant baked into image-storage or frontend-rendering logic.

## Trigger mechanism: two different problems, two different triggers

**Scene/event images are a narration-time, per-turn decision — a new field on `NarratorResponse`, not a new tool.** Reusing open-dungeon's own proven shape directly (ROADMAP.md already commits to this: "a generated image as a field on the message/turn object itself, rendered inline under that turn"): `NarratorResponse` gains `image_request: ImageRequest | None` as a sibling to `narration` and `tool_call` — the model decides per turn whether a scene visually warrants an image, same as open-dungeon's `imageRequest.needed`/`imageRequest.prompt`. This is deliberately **not** shaped as a sixth tool alongside `request_roll`/`apply_character_update`/etc. — those tools all have a real mechanical *execution result* the engine applies and logs (a die roll, a stat change); an image request has no engine-state effect at all, it's a presentation decision layered on top of narration. Forcing it into the tool-call discriminated union would conflate two different kinds of decision the schema is supposed to keep separate.

**Character portraits are not a narration-time decision at all** — they happen once, at character-approval time, before any narration exists to make a decision about. This needs new protocol surface: character creation currently sends a single `join` message with plain fields (name/role/lifepath) and no approval step. This design adds a review/approval step to that flow — the client shows the drafted character back to the player, and only on explicit approval does a new message trigger portrait generation server-side. Exact message shape is implementation-phase work (see deferred section) but the sequencing is a real design commitment: draft → review → approve → generate portrait → persist → broadcast.

## Persistence: portraits are files, referenced by path

Character sheets currently persist as JSON (`engine/persistence.py`, one file per session). Embedding generated images as base64 in that JSON would bloat every session file with binary data on every save. Instead: portraits save to disk as real image files (e.g. `sessions/portraits/{session_id}/{player_id}.png`), and `CharacterSheet` gains a `portrait_path` (or `portrait_url`, once the frontend needs to fetch it) field referencing the file — the same "attachment as a reference, not inline data" shape open-dungeon already uses for its own character portraits (`Attachment` objects with a `.url`). Scene images attached to a turn follow the same pattern rather than inflating `session.log` (a `list[str]`) with binary data.

## GPU orchestration: the swap cost is real, name it explicitly

**On-demand, unload-and-swap** (the chosen strategy): before an image generation runs, Ollama's resident model is force-unloaded (Ollama supports `keep_alive=0` to unload immediately after — no new mechanism needed, just a parameter on the existing narrator client's own calls, or an explicit unload call before triggering an image). The image backend then gets the full 8GB. After generation, Ollama is *not* pre-warmed back up — the next narrator turn just pays the normal cold-load penalty this project already measured directly (~55-60s first call, then warm at the speeds already seen live: 7-15s per turn).

**This is a real, accepted cost, not a hidden one**: any turn that generates a scene image makes the *next* narration turn slow (a full model reload), exactly the same cold-start cost already documented from live testing earlier this session. Worth surfacing to the player somehow (a loading state that explains why, not silence) — implementation-phase UX work, not blocking this design.

## What's deliberately deferred

- Exact `ImageBackend` protocol method signatures and the `ImageRequest`/portrait message schemas — implementation-phase work, same as Phase 3's tool schemas were.
- The character-creation review/approval UI flow itself — this design commits to the *sequencing* (draft → approve → generate), not the concrete UI.
- A hosted-API `ImageBackend` implementation — not ruled out, explicitly parked as a real future option (matching the narrator's own local-first-with-hosted-secondary policy) once local generation is live and its real speed/consistency on this hardware is actually measured, not assumed.
- A reliability/consistency measurement pass on the real hardware, mirroring Phase 3's narrator harness — needed before trusting any specific consistency number cited above as more than a hypothesis for *this* project's actual setup.
- Resolution/model-tier bump once better hardware arrives — deliberately left as a config change for that day, not designed now against hardware that doesn't exist yet.
- What "a scene visually warrants an image" actually means in the system prompt — prompt-engineering work, needs a real model to test against, not speculative text written here.
