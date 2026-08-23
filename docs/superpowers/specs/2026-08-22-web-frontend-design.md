# Nightwire Web Frontend Design — Phase 4

Status: designed, not yet implemented. UI/UX layout was brainstormed and mockup-approved via visual comparison before this repo existed (see `ROADMAP.md`'s "Design already settled" for the full record) — carried forward here unchanged. The technical architecture below is newly, independently researched — no oracle-precedent citations.

## Stack

Vite + React 19 + TypeScript + Tailwind CSS (already decided — see `ROADMAP.md`'s Platform decision: no Next.js, since there's no SSR/API-route need when a real Python backend already exists).

## UI/UX (carried forward, unchanged)

- **Layout**: chat-bubble narration (dominant, top region) + a persistent compact vitals/party/objectives/combat band below it, always visible — no tab-switching hides your own HP + an input bar at the bottom.
- **Full character sheet**: on-demand overlay (e.g. `Ctrl+K`), laid out like a real physical tabletop sheet — boxed sections, minimal thin single-line rules between sections, no heavy box-drawing borders.
- **Character portrait**: a small pre-drawn art placeholder shown beside the sheet header, picked by character build.
- **Input composer**: Do / Say / Think mode toggle, client-side text formatting only (no protocol-level mode field — the same pattern verified in open-dungeon's own composer, a pure string transform before sending).
- **Secondary/utility commands**: stay as typed text for the first build, no command-palette widget yet.

## State architecture: split by state *kind*, not one library for everything

Real, researched finding: the "useState vs. Zustand vs. Redux" framing is the wrong question. **Server-pushed state and client-owned UI state are architecturally different problems**, and Nightwire's own state is overwhelmingly the former — character sheets, NPC list, world state, turn/combat state all arrive from the server over the WebSocket connection, none of it is genuinely client-owned.

- **Server-pushed state**: a thin WebSocket-message-to-state-update layer, keyed by envelope type (a `useReducer` at the app root dispatching on incoming message type is architecturally honest here — this state doesn't belong to any component, it belongs to the connection). **Not defaulting to Zustand for this** — reaching for a general client-state library for state that's actually server-authoritative is solving the wrong problem.
- **Client-only UI state** (which sheet tab is active, whether the sheet overlay is open, a connection-status banner): plain `useState`/local component state — reserve Zustand/Context only if genuinely global client-only state emerges that plain props can't reach cleanly.
- This directly supersedes the earlier "match open-dungeon's plain useState" note from before this repo existed — open-dungeon's simplicity worked *because* it has no live multiplayer state sync at all; Nightwire's real multiplayer sync is exactly the case that note itself flagged as needing revisiting.

## WebSocket connection management

- **`react-use-websocket`**, not a hand-rolled `useEffect`+`useRef` reconnect loop — current guidance consistently flags hand-rolled connection logic inside a mounting/unmounting component as the most common real mistake (duplicate connections). Used via its `share: true` option, wrapped in a single Context/provider at the app root — one persistent connection for the whole app, matching how a single client can only ever have one real connection to begin with.
- **Reconnection: exponential backoff with jitter**, not fixed-interval retry — fixed intervals cause every disconnected client to hammer the server simultaneously on a restart (a real, documented thundering-herd failure mode), not a theoretical concern.

## Protocol integration

A TypeScript module mirrors the envelope shapes the engine (Phase 2) and narrator backend (Phase 3) specs define — `{type, session_id, sender_id, payload}` — just types, generated/maintained alongside the actual protocol as it's built, not speculatively declared here.

## Testing

- **Vitest + React Testing Library** — confirmed the current (2026) standard for a Vite+React+TS project (State of JS 2025 survey: 52% adoption, up from 20% in 2023; shares Vite's config, no separate Jest setup).
- **MSW's `ws` namespace** for anything touching the live WebSocket connection — Mock Service Worker added first-class WebSocket mocking (a standards-first WHATWG-WebSocket-event model, intercepting both outgoing client messages and simulating incoming server events), a real current answer rather than a gap needing a bespoke mock.

## What's deliberately deferred

- Exact component boundaries beyond the layout regions already settled (StoryFeed, VitalsBar, PartyPanel/CombatPanel/ObjectivesPanel, Composer, CharacterSheetOverlay are the working names, not a finalized file-by-file breakdown) — implementation-phase work.
- The generated TypeScript protocol types themselves — depend on the engine's actual envelope catalog existing first (Phase 2's own deferred item).
- Exact Do/Say/Think formatting strings and command-palette scope-if-ever-needed — noted as open in the original design record, unchanged.
