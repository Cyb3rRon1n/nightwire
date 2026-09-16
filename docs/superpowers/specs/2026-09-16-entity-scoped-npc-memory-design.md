# Nightwire Entity-Scoped NPC Memory Design — Phase 12

Status: designed, not yet implemented. Second sub-phase of the "Long-session memory" candidate (`ROADMAP.md`'s Candidate future phases), following Phase 11's rolling narrative compaction. Grounded in `kiselyovd/dungeon-master-ai`'s real, shipped `remember_npc`/`recall_npc` pattern (independently verified 2026-09-15 research pass) and this project's own repeated, hard-won lessons about tool-firing reliability and context-budget bounding — not oracle-precedent (oracle's own "NPC notes field," per its ROADMAP, is not consulted here).

## The actual gap

Nightwire's narrative context today is either verbatim recent lines or a rolling prose summary (Phase 11) — nothing tracks durable facts about a *specific* NPC (a name, a promise, a debt, a distinguishing trait) in a form the narrator can reliably recall regardless of whether that NPC was mentioned in the last few turns or the summary happened to preserve them. A prose summary is lossy by nature (it's asked to compress, not index); an NPC introduced turn 3 and not mentioned again until turn 40 has no guaranteed path back into context.

## Architecture: no recall tool, no multi-round loop

**Decision: a `remember_npc` tool (write) plus always-injected context (read) — no `recall_npc` tool, no multi-round tool-calling loop.**

`kiselyovd/dungeon-master-ai`'s real architecture pairs `remember_npc` with `recall_npc`, and its `recall_npc` is a genuine tool the model calls to fetch information *before* producing its narration — which requires a multi-round tool-calling loop (call tool → see result → then narrate). Nightwire's turn structure is single-shot: one narration + at most one tool call per turn, full stop (`narrator/client.py`'s `NarratorResponse` — `narration` and `tool_call` are both produced in the same structured-output call). A `recall_npc` tool bolted onto this architecture would be silently useless: the model would have no way to see its own tool's result before finishing that turn's response.

Building a real multi-round loop to support genuine on-demand recall was considered and explicitly rejected for this phase — it's a much larger change touching the core turn-processing loop, the narrator client's structured-output contract, and every existing tool's assumptions about running exactly once per turn. That's a separate architectural project, not "entity-scoped memory" scope.

Instead: `remember_npc` writes a fact; every turn's context unconditionally includes a small "Known NPCs" block, the same passive-injection shape `Session.narrative_summary` (Phase 11) already uses. This also sidesteps a second, independently real problem this project has hit twice already: **relying on the model to reliably decide *when* to call a tool has a bad track record here.** `start_combat` had to be removed from the tool surface entirely after four separate prompt/sampling fixes failed to stop it over-firing (`ROADMAP.md`'s Phase 3 entry); `image_request` needed a structural per-turn cooldown, not just prompt wording, to stop firing on consecutive turns. A `recall_npc` tool would add a second surface with the exact same "will the model remember to call this" risk. Always-injecting sidesteps that risk class entirely for the read side — only the write side (`remember_npc`) carries any tool-firing-reliability risk at all, and that's a strictly smaller, better-understood problem this project has already solved for comparable low-frequency tools.

## Data model: storage keeps everything, context selection is bounded and adaptive

**Decision: separate "what the session knows" from "what fits in this turn's context,"** mirroring the exact split Phase 11 already established between `session.log` (full history, never pruned) and `_select_verbatim_narrative` (a bounded, token-budget-aware selection of it).

`Session.npc_memory: dict[str, list[str]]` — NPC name → an ordered list of remembered facts (oldest first). This is the storage layer: it keeps the fullest available history, not just what's recently relevant, so a future phase (the lorebook candidate, or a hypothetical keyword-relevance selector) has real data to search rather than an already-lossy LRU window. Two write-time sanity caps prevent pathological unbounded growth over a very long campaign, deliberately generous since they're a safety net, not the primary bounding mechanism: **50 total NPCs** (LRU-evicted by touch order once exceeded) and **5 facts per NPC** (oldest fact dropped once exceeded).

A new `_select_npc_memory_for_context(session, num_ctx) -> dict[str, list[str]]` function is the read-time bound — this is what actually decides what goes into a given turn's prompt, and it's a token-budget selection, not a fixed entry count, for the same reason Phase 11's verbatim window is budget-based rather than turn-count-based: it adapts if `num_ctx` ever changes (Phase 11's own design already anticipated a `6144` fallback), rather than silently becoming wrong. Walks `session.npc_memory` from most-recently-touched backward (same accumulate-and-break shape `_select_verbatim_narrative` uses), stopping once a small reserved budget is exhausted.

**Budget**: a new `_NPC_MEMORY_BUDGET_FRACTION` of `num_ctx` (proposed starting value: 5% — at `num_ctx=8192`, roughly 410 tokens / ~1,640 characters), carved out of the same generation headroom Phase 11's final review measured at ~1,940 tokens free, *not* renegotiating the existing 65% verbatim-narrative fraction. This is deliberately conservative and, like every budget constant in this project so far, a starting value to live-verify, not a tuned optimum.

## Tool: schema-bounded, matching an existing precedent

```python
class RememberNPC(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., max_length=100)
    fact: str = Field(..., max_length=200)
```

The `max_length` bounds are a direct application of a precedent this exact file already establishes for `ApplyCharacterUpdate`'s `skill_points_delta`/`attribute_points_delta`: "bounded at the schema so one hallucinated large value can't permanently max a character in a single turn." An unbounded free-text field from an 8B model feeding directly into a context budget is exactly the scenario that convention exists for — without it, a single verbose `fact` could consume a large fraction of the already-small NPC memory budget on its own.

Joins the existing `TOOL_REGISTRY` (`narrator/tools.py`) and `ToolCall` discriminated union (`narrator/client.py`) exactly the way `request_roll`/`apply_character_update`/`update_world` already do — no changes to that established pattern.

**Executor** (`_execute_remember_npc`): appends `fact` to `session.npc_memory.setdefault(name, [])`, re-inserts `name` at the end of the dict (Python's insertion-ordering gives LRU-by-touch for free, no extra state), trims to the 5-facts-per-NPC cap (drop oldest), then trims the whole dict to the 50-NPC cap (drop least-recently-touched) if exceeded.

## Prompt guidance

`server/__main__.py`'s system prompt needs restraint guidance for `remember_npc`, following the same technique that fixed `image_request`'s original under-firing: a positive example (a genuinely durable, worth-remembering fact — a name, a promise, a debt) paired with a negative/counter-example (routine dialogue that doesn't warrant it). Exact wording is implementation-phase work, tuned against live probes the same way every other tool's prompt guidance in this project was — not written here.

## Fail-soft

No new failure surface at the write side beyond what `execute_tool`'s existing `(ValueError, TypeError)` catch in `server/narration.py` already handles (a malformed `tool_args` dict fails Pydantic validation the same way every other tool's does). The read side (`_select_npc_memory_for_context`) is pure, synchronous, and has no I/O — nothing to fail-soft around.

## Persistence

`Session.npc_memory` round-trips through `JSONFileSessionStore.save()`/`load()` with the same `.get("npc_memory", {})` legacy-file-defaulting pattern every prior `Session` field addition in this project uses (`speaker_voices`, `pending_initiative`, `narrative_summary`) — including a dedicated legacy-file test mirroring the established `test_load_defaults_*_when_missing_from_an_older_file` shape.

## Testing

- Unit tests for the executor: fact append, per-NPC fact cap (oldest dropped), total-NPC cap (least-recently-touched dropped), and touch re-ordering (an NPC touched again moves to the end, protecting it from eviction).
- Unit tests for `_select_npc_memory_for_context`: budget-respecting selection, most-recently-touched-first ordering, adapts to a different `num_ctx`.
- Unit tests for `_build_messages`'s injection: the "Known NPCs" block appears when `npc_memory` is non-empty, absent when empty (same shape as the existing `narrative_summary` injection tests).
- Persistence round-trip + legacy-file-defaulting tests.
- Live verification (this project's standing discipline): the combined real token budget (verbatim + summary + NPC memory) measured against the real deployed model, and a live reliability probe confirming `remember_npc` fires at reasonable, restrained rates — same technique already used to tune `image_request`'s and `start_combat`'s firing behavior.

## What's deliberately deferred

- `recall_npc` / any multi-round tool-calling loop — a real, separate architectural project if ever pursued, not in scope here.
- Keyword/relevance-filtered NPC selection (only showing NPCs relevant to the *current* scene rather than all recently-touched ones) — the future lorebook phase's territory; `_select_npc_memory_for_context`'s signature (`session, num_ctx`) is deliberately narrow enough that a relevance-aware version could replace it later without touching `_build_messages`'s call site.
- Any UI surface for players to view remembered NPCs.
- Cross-session NPC memory — stays session-scoped, matching every other piece of `Session` state.
- Tuning `_NPC_MEMORY_BUDGET_FRACTION`, the 50/5 sanity caps, or the exact prompt wording beyond a reasonable starting point — real measurement work for implementation phase and beyond.
