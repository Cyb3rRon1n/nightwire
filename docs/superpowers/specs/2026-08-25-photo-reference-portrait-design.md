# Nightwire Photo-Reference Portrait Design — Phase 8

Status: designed, not yet implemented. Extends Phase 5's image generation (`docs/superpowers/specs/2026-08-23-image-generation-design.md`) — same `ImageBackend`/`FluxWorkerBackend`, same reference-image mechanism, no new subsystem. Every choice below is grounded in independent external research — no oracle-precedent citations.

## The actual requirement

At character-approval time (the existing `approve_character` flow, Phase 5), a player can optionally upload 1-2 photos of themselves to guide the generated portrait's likeness, instead of relying on the text-only role/lifepath prompt alone. Stated directly by the project owner, with an explicit "I'm only speculating" framing that turned out to be a reasonable, buildable idea worth researching properly rather than dismissing.

This is additive, not a replacement: the existing text-prompt-only portrait flow (`_build_portrait_prompt` in `server/portrait.py`) is untouched for players who skip the upload.

## Fidelity: real limitation, not an implementation bug to chase

Research finding, load-bearing for the whole design: nightwire's backend does plain reference-image conditioning (`--input-images` on FLUX.2-klein, via `FluxWorkerBackend`) — not identity-lock, not compositing. This is architecturally the same class of mechanism as FLUX.1's IP-Adapter, which HuggingFace's own model card describes as carrying "a trade-off between content leakage and style transfer" and explicitly weaker than Kontext-style editing for character consistency ([HuggingFace](https://huggingface.co/InstantX/FLUX.1-dev-IP-Adapter)). Midjourney's `--oref` (omni-reference, their face-reference feature) documentation likewise states it "is not a guarantee of frame-perfect identity" ([Flowith](https://flowith.io/blog/midjourney-v7-consistent-characters-masterclass/)). A recent benchmark paper scores true Kontext-style editing far higher on "Character Preservation" than IP-Adapter-class conditioning ([arXiv:2506.15742](https://arxiv.org/pdf/2506.15742)) — nightwire's mechanism is the latter, not the former.

**Real precedent already ships this feature for TTRPG portraits specifically** — ImagineMe's D&D Portrait Generator, Bylo.ai's RPG Maker, CharGen, Fluxai.art's RPG Maker all exist today. ImagineMe notably asks for 10-20 photos per character, not one — a tell that single-photo fidelity is a known industry weak point, not a nightwire-specific risk.

**Design consequence**: expect "recognizable vibe," not a reliable likeness, and say so in the UI rather than overpromise. Two photos (the worker's hard cap — see below) is the ceiling this backend can use per generation; it is not expected to close the gap to Kontext-tier fidelity, just to give the model marginally more to work with.

## Retention: process-then-discard, never written to disk

Decision, confirmed with the project owner: uploaded photos are used once to generate the portrait, then discarded — never persisted, not even transiently on server disk.

Grounded in real precedent and its own gap: Lensa's privacy policy states "uploaded photos are automatically deleted after the AI avatars are generated, and face data is automatically deleted within 24 hours" ([Lensa privacy policy](https://legal.lensa.app/privacy-policy)), but third-party analysis notes Lensa's own broader retention language is looser than that specific marketing claim, and third-party processors "may temporarily retain photos according to their own policies" ([NordVPN](https://nordvpn.com/blog/is-lensa-safe/)). The academic literature on ephemeral sharing backs the general pattern — not retaining data reduces the surface for privacy concern outright ([SSRN:3740782](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3740782)) — but the credibility gap in Lensa's own stated-vs-actual retention is the specific failure mode to design around: **process-then-delete beats a stated TTL**, because a TTL is a promise about data that still exists somewhere for a while; never writing the file at all removes the promise-keeping problem entirely.

Consequence for architecture (see "Data flow" below): the photo must never touch server disk, not even in a directory that gets cleaned up later. It exists only as request payload, in memory, for the duration of one HTTP call to the image worker.

**Scope enforcement**: real precedent (Lensa, Midjourney, the TTRPG portrait tools above) does not technically verify "this is your own face" anywhere — it's stated policy, not identity verification, industry-wide. Nightwire matches that: plain label copy near the upload control states it's for the player's own likeness, no checkbox, no verification step. This is a scope decision the project owner made explicitly, not an oversight.

## Data flow: base64 in the websocket message, never a file

Three approaches were considered:

1. **(Chosen) Base64 data URLs inline in the `approve_character` websocket message.** The client reads the file(s) via `FileReader`, downscales to ~1024px longest side (fidelity doesn't benefit from more; message size does), and sends them as an optional field. `server/portrait.py` passes the data URLs straight through to `image_backend.generate_portrait(...)` and lets them go out of scope when the function returns — no disk write, so "process-then-discard" costs zero extra code.
2. **Reuse the existing `/api/upload` REST route** (`frontend/src/app/api/upload/route.ts`, inherited from `open-dungeon`, already functional — 8MB cap, PNG/JPEG/WebP allowlist via `zod`). Rejected: it writes to `frontend/public/uploads/` with no deletion mechanism at all, and the file would need to cross from the Next.js process to the Python server (different process, potentially different host in a real deployment) — honoring "never touch disk" here means adding a delete step across two processes, which is exactly the kind of two-places-touch-the-photo surface the Lensa retention-gap finding warns against.
3. **Client uploads directly to the FLUX worker's own HTTP endpoint**, bypassing the Python server entirely. Rejected: the worker (`127.0.0.1:7869`) is not meant to be browser-reachable — it's an implementation detail behind `ImageBackend`, matching the project's established "server owns all truth" boundary (the same reasoning that already keeps game state authority server-side). Building portrait-prompt construction and session/character validation client-side to make this work would duplicate real server logic for no benefit.

Approach 1 wins cleanly: smallest diff, matches the existing `_to_data_url`-and-send shape `FluxWorkerBackend` already uses for scene-generation references, and satisfies the retention decision as a natural consequence of the data flow rather than a bolted-on safeguard.

## Interface changes (shapes, not final signatures)

- **Protocol** (`frontend/src/lib/nightwire/protocol.ts`): `ApproveCharacterMessage` gains an optional `reference_photos?: string[]` — data URLs, capped at 2 entries.
- **Image backend** (`narrator/image_backend.py`): `generate_portrait` gains an optional reference-data-urls parameter. `_generate`'s internal reference-building needs to accept two kinds of reference: existing file-path references (scene generation, reusing the saved portrait) and new inline-data-url references (this feature) — both already end up as the same `{"dataUrl": ...}` shape the worker expects, so this is a small internal branch, not a protocol-shape change for `ImageBackend` consumers.
- **`server/portrait.py`**: `handle_approve_character` reads `reference_photos` off the incoming message (if present), passes it to `generate_portrait`, otherwise unchanged.
- **Size validation**: reject photos over ~4MB each server-side (generous margin over the ~1024px client-side downscale target), matching the existing upload route's validation pattern (type allowlist + size cap) rather than inventing a new one.

Exact field names, function signatures, and validation error shapes are implementation-phase work, same as every prior phase's spec has deferred them.

## UI flow

The upload control lives inside the existing post-join "Approve & Generate Portrait" banner (`page.tsx`) — that banner is already the one moment this decision gets made; no new screen or step. Label copy states the upload is optional, for the player's own likeness, and used once to generate the portrait without being stored — matching the "plain copy, no checkbox" scope decision above.

**Related fix folded into this pass**: live testing during this session's earlier work surfaced a real, pre-existing bug in this exact flow — if the image worker returns an error (observed live: a `500` from `/generate`), the "Generating…" button state never resolves; no error shown, no retry available, the banner is just stuck. Since this feature touches the same approve-portrait code path, fixing that failure state (show the error, let the player retry or fall back to text-only) is included here rather than left for a separate pass.

## Testing

- **Backend**: unit tests for the widened reference-building logic (data-url references vs. file-path references produce the same worker-facing shape), `handle_approve_character` with a mocked `ImageBackend` asserting it receives the uploaded photos, and a size-cap rejection test.
- **Frontend**: no existing test tooling for file-upload/`FileReader`/data-url flows in this repo — live verification against the real running stack (server + frontend + image worker), the same pattern every prior phase used, is the practical option here, not a gap unique to this feature.

## What's deliberately deferred

- Exact message/field names and validation error shapes — implementation-phase work.
- Any attempt to improve single-photo fidelity beyond "send up to 2 references" (e.g. multi-photo averaging, a dedicated face-embedding model) — the research is clear this backend's mechanism has a real ceiling here; chasing it further is a different, larger project (effectively building toward Kontext-tier editing or an IP-Adapter-FaceID-with-LoRA pipeline, both already rejected for the base portrait system in Phase 5's own spec for cost/hardware reasons that still apply).
- Reusing the uploaded photo for anything beyond the single portrait-generation call (e.g. as an ongoing scene-generation reference) — the "never persisted" retention decision makes this structurally impossible by design, not a feature gap.
- A "your own face" verification mechanism — explicitly out of scope; matches real-world precedent (nobody in this space verifies it) and the project owner's own scope decision.
