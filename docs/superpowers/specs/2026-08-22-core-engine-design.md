# Nightwire Core Engine Design — Phase 2

Status: designed, not yet implemented. Builds on `2026-08-22-cyberpunk-ruleset-design.md`. New codebase throughout — no oracle files reused — but explicitly informed by which of oracle's engine patterns held up under research and which didn't.

## Turn model — the one deliberate improvement over oracle

**Free-flowing outside combat; strict initiative-gated turn order only once combat is formally declared.**

Oracle enforces a strict turn queue for the *entire* session, not just combat — every action, even casual roleplay, waits its turn. Research (real tabletop GMing convention, AI Dungeon's own multiplayer design, MUD architecture — see design-session notes) unanimously treats that as wrong: turn order is a combat-specific tool everywhere it was checked, never a whole-session rule. Outside combat there's no shared contested resource an out-of-turn action could corrupt, so a queue there is pure friction with no corresponding safety benefit.

- **Outside combat**: any joined player may send an action at any time; the engine processes them in real arrival order (same principle MUDs use — real-time events into a continuous simulation, not a queue). No `current_turn` concept applies.
- **Once combat is declared** (`start_combat`, same explicit-player-triggered event oracle already validated — not auto-detected from narration, matching oracle's own tool-calling-reliability finding that "did combat start" is a judgment call an LLM can't be trusted to make on its own): real initiative rolls (`1d10 + Reflexes`, ruleset spec), a `turn_order`/`current_turn` cycle applies, out-of-turn actions are rejected — this is where oracle's queue mechanism genuinely earns its keep (contested HP/damage state, ambiguous resolution order), so it's kept, just correctly scoped.
- **`end_combat`** returns to free-flowing mode.

## Session & character model

- **Session**: player roster, world state, NPC roster, combat state (`in_combat`, `turn_order`, `current_turn_index` — only meaningful while `in_combat`), narration log.
- **CharacterSheet**: name, role, the six attributes + derived modifiers, Health/max Health, Armor Rating, conditions, cyberware (equip slots + installed items with bonuses), inventory (structured items, same `{name, quantity, bonus}` shape as the ruleset spec), skills, level (milestone-driven, no XP counter needed), notes.
- **NPCs reuse the CharacterSheet shape** — same precedent oracle validated (a tracked NPC is a first-class sheet, not a separate lightweight type), still correct here.

## Multiplayer & privacy

- **Redacted public view / full owner view split carries over** — this is a proven, genre-agnostic pattern (what's fair for another player to see: name, role, Health/Armor, conditions; what stays private: inventory, exact stats, notes) — oracle's own reasoning here isn't oracle-specific, it's just correct, so it's kept.
- **Join/reconnect**: same shape as oracle (a real player identity persists across reconnects, a rejoining player gets a state snapshot, not a blank slate).

## Transport & protocol

- **WebSocket, JSON envelopes** — `{type, session_id, sender_id, payload}`, same shape as oracle's protocol, fresh implementation. No case yet for a different transport; narration streaming (token-by-token) and multiplayer broadcast both need a persistent connection, which rules out plain request/response HTTP the way open-dungeon uses it for its (solo-only) case.
- **Full envelope catalog is implementation-detail work**, not re-specified line-by-line here — it will cover the same categories oracle's protocol needs (join/session-lifecycle, player actions, narration streaming, character/NPC/world updates, dice results, combat start/end) with Nightwire's own field names, decided while building rather than pre-declared speculatively.

## AI GM / narrator backend

- **Swappable backend protocol** (local Ollama default, hosted API as a secondary option — per the ruleset spec's content/backend decision), same "one interface, multiple implementations" shape as oracle's `NarratorBackend`.
- **Structured JSON output preferred over native tool-calling** for the mechanical decision step, by default — oracle's own measured finding (roughly doubled real tool-call correctness on a 7B local model) adopted as the starting assumption here rather than rediscovered.
- **A real reliability-measurement harness from day one** (mirroring oracle's `--repeat N` live-scenario tooling) rather than retrofitted after informal testing — every reliability claim gets a live, repeatable measurement, never a single anecdotal run.

## Persistence

**JSON file-per-session**, same as oracle — zero new dependencies, proven, and nothing in Nightwire's scope (single/local/LAN play, no hosted multi-tenant service) needs SQL querying. A startup writability check (oracle's own real-incident-driven fix — a session store that silently failed mid-process) is worth carrying forward as a lesson, fresh implementation.

## Testing

Pytest, engine-level tests driven by a scripted/stub narrator (mirroring oracle's `StubDM`/`ScriptedNarrator` pattern) — no live-model dependency for unit tests. Applied from the first commit, not added after the fact.

## What's deliberately deferred

- The exact envelope/message catalog (see "Transport & protocol" above) — built alongside the features that need each one, same order oracle's own protocol grew in.
- Combat's NPC-turn-autonomy question (does an NPC ever get a real mechanical turn slot, or only get announced in initiative order) — oracle deferred this too, for the same reason: it's a genuinely bigger, separate mechanism, not a default to assume either way without its own design pass.
