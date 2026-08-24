# Nightwire Text-to-Speech Design — Phase 6

Status: designed, not yet implemented. Builds on the narrator backend (Phase 3), web frontend (Phase 4a-revised), and image generation (Phase 5) specs — reuses their established patterns directly rather than inventing new ones. Research (backend survey, licenses, hardware fit) is recorded in `ROADMAP.md`'s Phase 6 entry and not repeated here.

## The actual requirement

Spoken narration with **character-distinct voices** — the narrator/DM voice and each in-fiction speaker (player, NPCs) should sound different from each other, not one flat narrator voice reading everything. This is a real structural requirement, not just "run TTS on the narration text": today's `NarratorResponse.narration` is a single undifferentiated string with no speaker attribution at all, so voice-per-speaker requires a schema change before any audio backend matters.

## Backend: Kokoro-82M (local) + OpenAI TTS (hosted, config-selectable)

**Local primary: Kokoro-82M.** Apache 2.0, ~300MB / <2GB VRAM — coexists with the resident `qwen3:8b` on the 8GB RTX 2080 without contention (unlike Phase 5's image backend, no unload/swap dance needed). Its built-in voice bank supplies multiple distinct preset voices at zero added VRAM cost. Alternatives ruled out in the research pass: Coqui XTTS-v2 (CPML non-commercial license, vendor defunct since Jan 2024); F5-TTS/Fish-Speech S2 Pro (real reference-clip cloning, but ~8GB VRAM each — the same GPU-swap cost Phase 5 pays for images — and unverified licenses); Piper (license unverified/contradictory across sources).

**Hosted secondary: OpenAI TTS.** Simplest and cheapest of the surveyed hosted options (~$0.015/min) — chosen as the fallback tier specifically because it's *only* a fallback, not the primary voice experience, so cloning/realism quality matters less than simplicity here. ElevenLabs and Cartesia were surveyed and are better on realism/latency but add cost and complexity with no clear need once they're not the primary path.

**Selection is startup-time config, not automatic failover** — matching `FluxWorkerBackend`'s `base_url`/`backend` constructor params. No "detect local failure, fall back automatically" logic: simpler, and avoids having to define what counts as a failure worth swapping backends mid-session. A user picks one backend when the server starts; switching requires a restart.

```python
class TTSBackend(Protocol):
    async def synthesize(self, text: str, voice: str) -> bytes: ...
```

One implementation per backend (`KokoroBackend`, `OpenAITTSBackend`), same shape as `ImageBackend`/`FluxWorkerBackend`. Voice-ID namespace is backend-specific (Kokoro's own preset names vs. OpenAI's own preset names) — not unified, since backend choice is fixed for the life of a session.

## Speaker attribution: `narration` becomes segments

`NarratorResponse.narration: str` → `narration: list[NarrationSegment]`, where:

```python
class NarrationSegment(BaseModel):
    speaker: str            # "narrator" or an in-fiction name
    gender: Literal["male", "female"] | None = None  # only meaningful on a speaker's first appearance this session
    text: str
```

This is the same kind of change `tool_call` already went through (a discriminated/structured field the model fills per turn, not free prose) — no new mechanism, applied to a second field. The system prompt needs updating to instruct the model to tag each line's speaker (and gender, on first appearance). `_build_messages` in `server/narration.py` flattens segments back to `"Speaker: text"` lines (`"text"` alone for `narrator`, to match today's unprefixed style) for both the session log and the recent-context feed — a format change, not a new mechanism, since the log is already a flat `list[str]`.

## Voice assignment: gender-aware, session-scoped auto-assignment

NPCs have **no persistent record anywhere in the codebase** — only player `CharacterSheet`s exist (`engine/character.py`); NPCs are invented in prose with no stable identity to hang a pre-configured voice mapping on. So assignment happens dynamically, at the `Session` level:

- `Session` gains `speaker_voices: dict[str, str] = field(default_factory=dict)`.
- The first time a speaker name appears in a session's narration, the server assigns it the next unused voice from the active backend's bank, **filtered by the model-tagged `gender`** where given, and records the mapping. Every later segment from that speaker reuses the stored voice — no re-tagging needed, no drift turn to turn.
- Gender is the only characteristic honored. Kokoro's (and OpenAI's) preset voice banks are small fixed sets distinguished mainly by gender/accent — there's no parameter for age, species, or "synthetic/augmented" timbre. Matching on gender is a real, honest improvement over blind round-robin; claiming to account for age/race/being would overpromise what a preset voice bank can represent. Reference-clip cloning (F5-TTS class) is the backend that could actually hit those axes, and it's explicitly out of scope for this phase (see Deferred).
- Exact Kokoro preset names/gender tags need a direct source check against the real voice-bank listing before implementation, per this project's standing rule to ground decisions in verified sources, not memory — the research pass that selected Kokoro didn't enumerate the bank itself.

## Delivery: per-segment audio, same tag-in-log pattern as images

Because narration is now segmented and each segment has exactly one speaker, synthesis runs **per segment**, not per turn and not sentence-streamed — each segment is already the natural unit. No new WebSocket message type: this follows the existing image pattern exactly, where delivery is a bracket-tag embedded in the plain-text log rather than a separate structured push.

For each segment: append its `"Speaker: text"` log line, then synthesize its audio and save to `{store.directory}/audio/{session_id}/{log_index}-{segment_index}.wav`, where `log_index = len(session.log)` at the moment that text line was appended (same derivation Phase 5 uses for `images/{session_id}/{len(session.log)}.png`) and `segment_index` is that segment's position within the turn's `narration` list. Append an `[audio: audio/{session_id}/{log_index}-{segment_index}.wav]` tag line immediately after the text line — mirroring `[image: {relative_path}]` from `server/narration.py`. The frontend already renders whatever it finds in the raw log (`views.py` broadcasts `log[-50:]` verbatim) and `_build_messages`' existing `not line.startswith("[")` filter already excludes bracket-tagged lines from the narrative context fed back to the model — both work unchanged, no new plumbing.

## Error handling

Each segment's `synthesize()` call is wrapped independently, matching the image backend's fail-soft shape (`except (ValueError, TypeError, OSError)`): a failure on one segment logs `[audio error: ...]` for that segment only and moves on — it doesn't drop the rest of the turn's audio or the turn itself. No GPU-unload retry logic is needed since Kokoro doesn't contend for VRAM with the narrator model in the first place.

## What's deliberately deferred

- Reference-clip voice cloning (F5-TTS / Fish-Speech) — real scope (unverified licenses, a third GPU-swap participant alongside narrator/image backends) parked for if/when age-, species-, or identity-specific voices are actually needed beyond what gender-matched presets deliver.
- Automatic local→hosted failover — backend choice is startup config only; detecting "local TTS failed, switch to hosted mid-session" is real added logic not built now.
- Exact Kokoro voice-bank preset names and their gender tags — needs a direct check against the real bank listing before the implementation plan can reference specific voice IDs.
- Sentence-level streaming within a segment — segments are already turn-sub-divided by speaker, which was the main latency concern; further chunking is an optimization to revisit only if per-segment latency is actually a problem once measured.
- The persistent visual-style-consistency and talking-portrait ideas noted in `ROADMAP.md`'s Phase 6 entry — explicitly out of scope for this design, tracked there as forward-looking, not designed.
