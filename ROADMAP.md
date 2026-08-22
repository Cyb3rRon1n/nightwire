# Nightwire — Roadmap

A cyberpunk tabletop RPG with an AI game master, playable solo or with friends, in a real browser. A ground-up sibling project to `oracle` (the owner's D&D-flavored AI-DM project) — same underlying idea (an LLM running a real, rules-grounded tabletop game), different genre, different platform, built fresh rather than adapted, deliberately.

This file is the durable source of truth for project state and decisions, same convention `oracle/ROADMAP.md` already established — kept thorough enough that picking this repo up cold (a new machine, a new AI coding session) is enough to continue without re-deriving context.

## Why a fresh project, not an oracle fork

Oracle's engine, protocol, and reliability-tested narrator patterns are genre-agnostic in principle, but the owner chose a full rebuild over reusing that plumbing — a deliberate call, not an oversight, made explicitly during this project's design conversation (2026-08-22). The stated reasoning: a from-scratch build lets nightwire's architecture serve its own identity rather than carrying oracle's D&D-shaped decisions forward, and doing it this way is itself part of what makes the project worth building.

**What still carries over is lessons, not code:**
- Structured JSON output beat native tool-calling for local-model reliability on the mechanical decision step (roughly doubled real tool-call correctness in oracle's own testing) — worth trying first here rather than re-discovering it.
- A silent self-correction pass (the DM gets one quiet chance to fix a narration that should have changed game state before a player-visible advisory fires) was a real, validated pattern worth carrying forward conceptually.
- Every reliability claim in oracle was backed by a live, repeatable measurement harness (`--repeat N` against a real model), never a single anecdotal run — the same discipline applies here.
- Real infrastructure verification (a live model, a live browser, a live multiplayer session) over mocked-only claims of "done."

## Platform decision (2026-08-22)

A pure terminal client cannot deliver this project's stated destination (real character art, TTS narration, a rich visual tabletop-style sheet) — no reliable inline-image support across terminals, and critically, **a remote/SSH terminal session has no channel to play audio on the user's own machine at all**. Confirmed against four comparable open-source AI-DM projects (`dungeon-ultimate`, `open-dungeon`, `skeinkeeper`, `dungeon-master-ai`) — all four independently left the terminal for a browser or desktop-web frontend once they wanted the same things; none stayed TUI-only for this feature set.

**Decision: a real browser-based web client from the start**, talking to a Python backend over WebSocket (same transport shape oracle already uses successfully) or an equivalent — no terminal client planned for this project.

**Primary reference: `open-dungeon`** (github.com/newideas99/open-dungeon, MIT, 216 stars) — chosen by the owner as the closest match to the desired feel. Concretely useful, verified patterns worth building on (not forking the repo itself — see "What we're not doing" below):
- **Do/Say/Story-style input composer**: a three-way mode toggle that formats the player's text client-side before sending (`"do"` → `"> draw my sword"`, `"say"` → `'> You say "..."'`) — no protocol-level mode field, just a text transform. Nightwire's own version drops "Story" (co-writing narration isn't part of the current design) in favor of **Do / Say / Think**.
- **Chat-bubble narration** via plain flexbox alignment (player right-aligned, GM/NPC left-aligned) — no bubble component library needed.
- **A generated image as a field on the message/turn object itself**, rendered inline under that turn by the message component — the shape nightwire's own future image-gen phase should copy.
- **Per-stage swappable local/cloud backends** (narration/image/audio each independently local-or-hosted) — the same shape as oracle's own `NarratorBackend` protocol, generalized across all three media types from day one instead of retrofitted later.

**What we're not doing**: cloning open-dungeon's actual repository as scaffolding. Its genuinely reusable code (the composer's format function, a few div/flexbox patterns) is small enough to reimplement directly; its Next.js API routes, SQLite backend, and 3,991-line single-file monolith are baggage nightwire doesn't want. Framework choice: **Vite + React + TypeScript**, not Next.js — nightwire's backend already exists as a separate Python service (mirroring oracle's split), so there's no use for Next.js's own API-route/SSR machinery.

## Ruleset decision (2026-08-22)

**Homebrew original cyberpunk ruleset, not adapted from an existing system.** Researched real alternatives first, same diligence oracle's own `ATTRIBUTION.md` applies to the D&D SRD:
- No dedicated open-licensed "cyberpunk SRD" exists as its own project.
- **Cypher System Open License (CSOL)**, Monte Cook Games — a real, verified, CC-BY-equivalent right to reproduce Cypher System rules text in a derivative product. Legally solid, but Cypher is a genre-agnostic light system (Might/Speed/Intellect pools) — would need a full reskin into cyberpunk flavor, not cyberpunk out of the box.
- **CY_BORG** (a MÖRK BORG hack) has real cyberpunk flavor and a real third-party license permitting derivative products, but whether that license actually grants reproduction of its core rules TEXT (vs. only permission to make a referencing/compatible product) could not be confirmed from the public license pages alone — an unresolved, unverified risk.
- **Cyberpunk RED/2020** (R. Talsorian) confirmed not openly licensed at all — ruled out.

Given the owner's own stated motivation ("that in itself will make this unique"), homebrew was chosen over the CSOL reskin path or the unverified CY_BORG path — zero licensing risk, and originality is treated as a real feature here, not just a fallback. This means nightwire's core mechanics (dice system, attributes, roles/classes, gear/cyberware, hacking resolution, combat resolution, NPC stat blocks, advancement) are **not yet designed** — this is real, first-priority design work, tracked as Phase 1 below, not something this roadmap resolves on its own.

## Phases

Each phase gets its own brainstorming pass (questions → approaches → design → spec) and its own implementation plan when its turn comes — this roadmap sequences them, it doesn't pre-design them.

1. **Cyberpunk ruleset design** (not started) — the new "SRD": core dice/resolution mechanic, attributes, roles/classes, cyberware/gear system, hacking mechanics, combat resolution, NPC/enemy stat blocks, advancement. Pure design, no code. Gates everything below — the engine's data model and the sheet UI both need real mechanics to model before they can be built.
2. **Core engine** (not started) — session/turn model, character/NPC data model (per the ruleset above), WebSocket protocol, persistence, solo + multiplayer join/turn-order/reconnect. New build, not adapted from oracle's — see "Why a fresh project" above for the reasoning, and the lessons-carried-forward list for what still transfers conceptually.
3. **AI GM / narrator backend** (not started) — local-first (Ollama), tool-calling for mechanical resolution, structured-output-over-native-tool-calling as the starting assumption (see lessons above), a real reliability-measurement harness from the start rather than retrofitted.
4. **Web frontend** (design done, 2026-08-22 — not yet built) — Vite + React + TypeScript. Layout, composer, and character-sheet-overlay design were brainstormed and mocked up in oracle's own repo before this project existed as a separate one (see "Design already settled" below); this phase ports that approved design into real components once phases 1-3 give it real data to render.
5. **Image generation** (not started) — swappable `ImageBackend`, portrait/scene cards attached to a turn (per open-dungeon's message-field pattern above). Expect "card under the relevant turn," not full scene-art compositing — even the most advanced comparable project researched (`dungeon-master-ai`) hasn't solved that yet either.
6. **Text-to-speech** (not started) — swappable narration-voice backend, same shape as image generation.

## Design already settled (carried over from the brainstorming session that spawned this project)

These were brainstormed and mockup-approved before nightwire had its own repo — captured here so they survive the move rather than needing to be re-decided:

- **Layout**: chat-bubble narration (dominant, top region) + a persistent compact vitals/party/objectives/combat band below it (always visible — no tab-switching hides your own HP) + an input bar at the bottom. A hybrid of two directions explored, not a copy of any single reference.
- **Full character sheet**: an on-demand overlay (opened via a keybind, e.g. `Ctrl+K`), laid out like a real physical tabletop sheet — boxed sections for core stats, saves/skills-equivalent, equipped vs. carried gear, features/abilities — not a flat scrolling list. Border/panel style: minimal thin single-line rules between sections, no heavy box-drawing borders, whitespace doing most of the separating.
- **Character portrait**: a small pre-drawn art placeholder (not photorealistic, not AI-generated yet) shown beside the sheet header, picked by character build — a real visual touch that ships before Phase 5's real image generation exists, deliberately cheap.
- **Input composer**: Do / Say / Think mode toggle, client-side text formatting only (see "Platform decision" above) — confirm exact formatting/labels during Phase 4's own design pass, since it was scoped conceptually here but not pixel/wording-finalized.
- **Secondary/utility commands** (equivalent to oracle's `/equip`, `/export`, etc.): stay as typed text for now, no command-palette widget in the first build — added only if it turns out to matter in practice.

## Explicitly not doing (yet)

- Reusing oracle's Python engine/protocol code directly — see "Why a fresh project" above.
- A terminal/TUI client — see "Platform decision" above.
- Adapting an existing ruleset (Cypher/CSOL, CY_BORG) — homebrew chosen instead, see "Ruleset decision" above.
- Full scene-image compositing (image drawn into a live map/scene) — even peer projects researched haven't solved this; Phase 5 targets per-turn cards instead.
