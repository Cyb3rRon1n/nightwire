# Nightwire Rolling Narrative Compaction Design — Phase 11

Status: designed, not yet implemented. First sub-phase of the "Long-session memory" candidate (`ROADMAP.md`'s Candidate future phases, added after Phase 10). Grounded in two independently-verified external sources — `open-dungeon`'s real, shipped context-compaction pattern and Ollama's own documented `num_ctx`/truncation behavior — plus a concrete, confirmed gap in nightwire's own current code. No oracle-precedent reasoning: oracle's own "rebuilt every ten resolved turns" campaign-summary shape is cited below only as a converging data point (a second independent project reaching a similar "summary of old + verbatim recent" shape), not as the source of any decision here.

## The actual gap, confirmed in nightwire's own code

`server/narration.py:12-30`'s `_build_messages` sends the narrator exactly `narrative[-10:]` every turn — a hardcoded, fixed 10-line slice of `session.log`, regardless of how much context budget is actually available. Everything before those 10 lines is not summarized, not stored anywhere the narrator can see it — it is simply gone. By turn 15 of any session, turn 1 no longer exists as far as the model is concerned.

This compounds with a second, separate, confirmed gap: nightwire has never set `num_ctx` anywhere in `narrator/client.py`'s Ollama call (`options={"temperature": 0.3}` only). Ollama's own documentation states the effective default context window for an 8GB-class card is around 4K tokens (docs are inconsistent — 2048 in the Modelfile reference, 4096 in the FAQ, VRAM-scaled in the context-length page: 4k below 24GiB, which covers this project's target RTX 2080 8GB either way) — and **Ollama silently truncates a request that exceeds it, from the beginning, with no error and no warning** ([Ollama context-length docs discussion](https://www.ssdnodes.com/learn/ollama-context-length-num-ctx), [Serverman: Ollama Context Window](https://www.serverman.co.uk/ai/ollama/ollama-context-window/)). Because nightwire has never pinned this, its actual effective context budget today is whatever Ollama's undocumented default happens to resolve to on the deployment hardware — not a number anyone chose. A compaction system that triggers relative to "the context budget" needs that budget to be a real, known number first.

## Pinning `num_ctx`: a prerequisite, not a separate phase

**Decision: pin `num_ctx=8192` on the Ollama call** (`narrator/client.py`'s `_default_chat`, `options={"temperature": 0.3, "num_ctx": 8192}`), roughly doubling the likely current ~4096 default. This is a real, measurable VRAM cost on the target hardware (RTX 2080 8GB, already resident with qwen3:8b, with Kokoro TTS and on-demand FLUX/ComfyUI image generation sharing the same card via the unload/reload dance Phase 6 already built) — not a free change. **Must be live-verified for VRAM headroom on the real deployment box before this phase is called done**, the same discipline Phase 6 used when it found Kokoro's own resident footprint conflicting with FluxWorkerBackend's peak transient VRAM need (`ROADMAP.md`'s Phase 6 entry, "A new, real VRAM conflict, found live and fixed same day").

8192 is a starting value, not a tuned optimum — chosen as a reasonable doubling to create real headroom for the compaction work below without first needing a dedicated VRAM-budgeting research pass. If live verification finds it doesn't fit alongside the other resident services, the fallback is a smaller value (e.g. 6144), not abandoning the pin entirely — running with an unpinned, undocumented, silently-truncating budget is strictly worse than any explicitly-chosen smaller number.

## Trigger: token-budget-aware, not turn-count

**Decision: compact based on actual estimated token usage against the real (now-pinned) `num_ctx`, not a fixed turn count.** This is `open-dungeon`'s real, shipped pattern — its README describes history filling the model's context window, with older passages auto-compacting into a rolling summary once the window fills, rather than a naive sliding window or a fixed cadence. Oracle's own "rebuilt every ten resolved turns" is a fixed-turn-count trigger instead; independently evaluated and not chosen here, because it doesn't adapt to how verbose a given session's narration actually is — a fixed count either compacts too early on terse sessions (wasted LLM calls) or too late on verbose ones (still silently losing history before the trigger fires).

**Token estimate**: no tokenizer dependency — `len(text) // 4` (a standard rough chars-per-token heuristic) is sufficient for a "getting close to budget" trigger, not an exact accounting requirement. This is a threshold signal, not a billing calculation.

**Budget split**: verbatim recent narrative gets ~60–70% of `num_ctx`, leaving room for the system prompt (a substantial multi-paragraph block, see `server/__main__.py`), the party roster line, the player's current action, and space for the model's own response generation. A precise percentage is implementation-phase tuning, not fixed here.

## Mechanism: full-rebuild summary, not incremental

**Decision: when the verbatim window can no longer fit all of `session.log`'s narrative lines, the lines that fall out get folded into `Session.narrative_summary: str` via one dedicated, full-rebuild summarization LLM call** — a separate, simple call (system prompt: summarize the given prior events in 2-3 sentences, preserving named characters, promises, and key decisions; no tool schema, no structured output needed) — not the main narrator call, and not an incremental patch appended to the previous summary each time.

Full rebuild (regenerate the summary from the complete set of now-excluded lines each time compaction fires) was chosen over incremental patching (append new material onto the existing summary text) because: oracle's own "rebuilt every ten turns" is also a full rebuild, a second independent data point for this shape; and incremental patching risks compounding drift across repeated edits (each edit's own errors/omissions persist and stack), while a full rebuild starts fresh from the real source lines every time, at the cost of a bigger prompt per compaction call — an acceptable tradeoff since compaction is infrequent by design (it only fires once the budget is actually threatened).

**Correction, 2026-09-15 (found in this phase's own final whole-branch review)**: the "compaction is infrequent by design" claim above was wrong without a further mechanism. Without hysteresis, `excluded_count` grows by roughly the number of lines appended per turn (~2+) once past the budget threshold, so the naive guard (`excluded_count <= narrative_summary_line_count`) only suppressed genuinely no-op turns — in steady-state play past the threshold, compaction fired on nearly every turn. Fixed with `_RECOMPACT_LINE_THRESHOLD` (`server/narration.py`): compaction now only re-fires once at least 8 additional lines have been excluded since the last firing, restoring the intended infrequent-by-design behavior. Also found in the same review and fixed: the full-rebuild summarization input itself was unbounded and would eventually exceed its own context budget and silently truncate — capped via `_MAX_SUMMARIZE_INPUT_CHARS` (24,000 chars, Task 4's own live-verified session size).

`_build_messages` prepends `session.narrative_summary` (when non-empty) ahead of the verbatim recent-lines block — the same "summary of old material + verbatim recent material" shape both `open-dungeon` (described above) and oracle (`ROADMAP.md`'s "a rolling summary rebuilt every ten resolved turns keeps early-session plot alive") independently arrived at. Two unrelated projects converging on the same shape is treated here as confirmation the shape itself is sound, not as oracle-precedent reasoning for adopting it.

## Fail-soft

If the summarization call errors (model error, malformed response, network issue against the Ollama backend), log `session.log.append(f"[summary error: {e}]")` and keep the previous `narrative_summary` value unchanged rather than blocking the player's turn — the same convention `[image error: ...]`/`[audio error: ...]`/`[tool error: ...]` already establish throughout nightwire's turn-handling code.

## Where this runs

Compaction is a post-turn check, not a pre-turn one — it happens in `server/narration.py`'s `handle_action`, after the turn's narration/tool/image/TTS work completes (mirroring where those other post-processing steps already live), checking whether the updated `session.log` now exceeds the verbatim budget and triggering the summarization call if so.

## Testing

- Unit tests for the trigger threshold: given a fake history length and a fake/injected token-budget constant, does compaction fire at the right point and not before?
- Unit tests for the compaction call itself: a fake summarizer response correctly updates `session.narrative_summary`; a fake summarizer error correctly logs `[summary error: ...]` and leaves the prior summary untouched.
- Live verification (this project's standing discipline, independently re-affirmed, not cited from oracle): the `num_ctx=8192` VRAM check against the real deployment box's other resident services (qwen3:8b, Kokoro, image-gen), and a real, long synthetic session run against the live model confirming the summary is actually generated and appears in later turns' context.

## What's deliberately deferred

- Entity-scoped memory (`remember_npc`/`recall_npc`-style tool calls) — a separate candidate sub-phase (`kiselyovd/dungeon-master-ai`'s pattern), addressing a different problem (specific fact/NPC recall via explicit model-invoked tools) than this phase's general narrative continuity.
- Keyword-triggered lorebook — a separate candidate sub-phase; nightwire has no authored setting/lore content yet at all (unlike oracle's `world_context/Aetherfall`), a real prerequisite gap before this would even have anything to inject.
- Tuning the verbatim/summary budget split beyond a reasonable starting guess (~60–70%) — real measurement work for a later pass once this phase's basic mechanism is live and observable.
- Incremental (non-full-rebuild) summarization — not ruled out permanently, just not chosen for this first cut.
- Any change to `num_ctx` beyond the initial 8192 pin — a live-verified starting value, not a tuned optimum.
