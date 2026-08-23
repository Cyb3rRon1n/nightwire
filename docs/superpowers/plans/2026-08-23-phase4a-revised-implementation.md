# Phase 4a-revised: Frontend-on-open-dungeon-base Implementation Plan

> **For agentic workers:** the project's usual REQUIRED SUB-SKILL note (`superpowers:subagent-driven-development`) doesn't apply here — this plan was written and is being executed directly in an interactive session, not handed to a fresh subagent. If a future session picks this up cold, that skill is still the right way to execute the remaining tasks task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking; check them off as they land.

**Why this plan exists, and why it's dated after the code it documents:** every other phase in this project got a real implementation plan *before* code was written (`docs/superpowers/plans/2026-08-22-phase1-*` through `2026-08-23-phase4a-web-frontend-scaffold-implementation.md`). Phase 4a-revised broke that pattern — the open-dungeon-base pivot (`ROADMAP.md`'s "Superseded 2026-08-23" note) and everything built on top of it so far (the `/nightwire` connect+feed route, the Do/Say/Think composer) were built ad hoc, live, in-session, with no plan doc. This document is written retroactively to record what's already landed and to give the *remaining* work in this phase the same task-by-task structure every other phase got, per `CLAUDE.md`'s stated process (research → plan → execute).

**Goal:** Bring the `/nightwire` route on the open-dungeon Next.js base up to what `docs/superpowers/specs/2026-08-22-web-frontend-design.md` and `ROADMAP.md`'s "Design already settled" section actually specify — chat-bubble narration, a persistent vitals/party/objectives band, a character sheet overlay, and a character portrait placeholder — on top of the connect/join/composer wiring already proven live against a real GPU-backed narrator.

**Architecture:** Everything here is presentational, client-side work on `frontend/src/app/nightwire/page.tsx` and its supporting `frontend/src/lib/nightwire/*` modules. No backend or protocol changes — `StateView` (`protocol.ts`) already carries every field this plan renders (`characters`, `in_combat`, `current_turn`, `active_objectives`, `location`, `scene_mood`). Where a visual pattern already exists in open-dungeon's own `frontend/src/app/page.tsx` (chat bubble alignment, message styling), this plan reuses it directly rather than inventing a new one — the project's own standing rule is independent research over oracle-precedent, but open-dungeon is the frontend's actual adopted base, and reusing its already-verified patterns is exactly the "genuinely reusable code" the original platform decision called out, not a precedent to second-guess.

**Tech Stack:** unchanged from the current base — Next.js 16 + React 19 + Tailwind, `react-use-websocket`. No new dependencies for anything in this plan.

## Already landed (context, not tasks — do not redo)

- `9556cac` — open-dungeon adopted as the frontend base, replacing the from-scratch Vite scaffold.
- `6c50421` — minimal `/nightwire` route: connect form, join form, plain-text log feed, wired to the real Python WebSocket backend (`NEXT_PUBLIC_NIGHTWIRE_WS_URL`, default `ws://localhost:8000`). Verified live against a real `qwen3:8b` narrator turn, both on GPU-backed backends (`msi-laptop`, and `metta-desktop-gtr32bn` as a temporary stand-in while `msi-laptop` was rebuilt).
- **Do/Say/Think composer** (built and live-verified in the session that produced this plan, not yet committed): `ComposerMode = "do" | "say" | "think"`, a pure client-side text transform reusing open-dungeon's own `formatPlayerInput` pattern from `page.tsx` (`do` → `"> {text}"`, `say` → `'> You say "{text}"'`), extended with the same shape for `think` → `'> You think "{text}"'` — the design spec explicitly left this wording undecided; this is the concrete decision. A `sending` flag disables the composer and relabels the submit button while a turn is in flight, cleared on the next state broadcast (the protocol has no per-request ack, so "the next broadcast this connection sees" is the only real completion signal available).
  - **Currently blocked from landing in the real tree**: `nightwire/frontend` is root-owned on the dev machine this was built on; the diff lives in a sentinel-owned scratch copy pending a `chown` fix. **Task 1 below is porting it in**, once unblocked.
- **A real reliability finding from live GPU testing, not part of this plan's scope but worth carrying forward**: a narrator turn can hang indefinitely (GPU idle, no error, no timeout) under real contention (observed with a game — Throne and Liberty — sharing the GPU with Ollama). A server restart cleared it. Nothing in this plan fixes that; it's server/narrator-side, out of scope for a frontend plan, but the eventual owner of Phase 3 hardening work should know about it.

## Global Constraints

- **No test framework** — per the commit that built the connect+feed route: "this app has none, and per project practice the real check here is against the live backend, not a mock." This plan follows that same convention: every task's verification step is a real live-browser check against a real running backend (GPU-backed where a narrator turn is involved), not a Vitest/RTL/MSW suite. This is a deliberate deviation from the original (scrapped) Phase 4a scaffold plan, which did use Vitest — that plan's own frontend was thrown away along with its test setup when open-dungeon became the base.
- Reuse open-dungeon's existing Tailwind classes/patterns wherever the visual need matches something already in `frontend/src/app/page.tsx`, rather than inventing new styling from scratch (ponytail: reuse before you write).
- Keep `/nightwire` isolated from open-dungeon's own routes/API — no changes to `frontend/src/app/page.tsx`, `frontend/src/app/api/*`, or the SQLite layer. Everything in this plan touches only `frontend/src/app/nightwire/` and `frontend/src/lib/nightwire/`.
- No combat/turn-order controls (`start_combat`/`advance_turn`/`end_combat` buttons) — out of scope. `view.in_combat` / `view.current_turn` are rendered read-only in Task 3's vitals band; per the design's own "Design already settled" note, secondary/utility commands stay as typed text for the first build, and combat controls were never in that settled list to begin with.
- No character-creation polish beyond what already exists (plain Name/Role/Lifepath text inputs) — a real picker is later scope, same deferral the original scaffold plan already made.

---

## File Structure

- Modify: `frontend/src/app/nightwire/page.tsx` — chat-bubble rendering, vitals band, `Ctrl+K` overlay toggle, portrait.
- Create: `frontend/src/lib/nightwire/portrait.ts` — deterministic placeholder-avatar helper (color + initials from role/name), pure function, no assets.
- Create: `frontend/src/app/nightwire/CharacterSheetOverlay.tsx` — the boxed-sections sheet component, split out since `page.tsx` is otherwise a single-file route.
- No changes to `frontend/src/lib/nightwire/protocol.ts`, `reducer.ts`, or `useNightwireSocket.ts` — this plan is pure rendering on top of state those already provide correctly.

---

### Task 1: Port the Do/Say/Think composer into the real tree

**Blocked on:** `nightwire/frontend` ownership fix (currently root-owned; sudo access to fix it was broken as of this plan's writing).

**Files:**
- Modify: `frontend/src/app/nightwire/page.tsx` (real tree) — apply the diff already built and live-verified in the sentinel-owned scratch copy.

**Steps**

- [x] **Step 1:** Ownership fixed (`sudo chown -R sentinel:sentinel`) once the machine's sudo/PAM issue (a fingerprint-auth-before-password PAM stack ordering problem, unrelated to this project) was diagnosed and worked around.
- [x] **Step 2:** Composer diff applied to the real file — as its own isolated commit (a first attempt accidentally bundled Task 2's bubble diff in too, since it had already been applied to the working file before committing; caught immediately and split via `git reset --soft HEAD~1` + re-commit in two passes, safe since neither commit had been pushed).
- [x] **Step 3:** N/A in practice — verification used a second `next dev` instance on a fresh port rather than restarting the pre-existing root-owned `:3002` instance (still running, not killable as `sentinel`); the real committed files were confirmed byte-identical to the already-live-verified scratch copy instead.
- [x] **Step 4: Live-verify.** Full pass done in Task 6's final port-verification below, against the real committed tree.
- [x] **Step 5: Commit** — `feat: Do/Say/Think composer on the /nightwire route`.
- [x] **Step 6:** Scratch copy retired after the final verification pass confirmed the real tree.

---

### Task 2: Chat-bubble narration layout

**Goal:** Replace the current flat `<p>` list (every log line styled identically) with the ROADMAP's actual spec: the viewer's own lines right-aligned in a bubble, everything else (narrator prose, other players) left-aligned as plain text — reusing open-dungeon's own pattern verbatim, not a new bubble system.

**Reuse source:** `frontend/src/app/page.tsx` lines ~1597–1620 — player/user messages get `<div className="ml-auto max-w-[92%] sm:max-w-2xl">` wrapping `<div className="rounded-2xl rounded-br-md border border-stone-800/70 bg-stone-900/60 px-4 py-3 text-sm leading-6 text-stone-300">`; narrator messages get no bubble at all, just `<p className="text-pretty whitespace-pre-wrap">` prose. This is exactly the "no bubble component library needed, plain flexbox/margin alignment" pattern `ROADMAP.md` already cites as verified.

**A real gap this task has to close that open-dungeon's own version doesn't:** nightwire's `log` is `list[str]` server-authored lines like `"player-composer-2: > I check the terminal."` for player turns and bare narration text for the narrator — there's no `role: "user" | "assistant"` field to branch on the way open-dungeon's `StoryMessage` has. The client-side classifier for this task: a line matching `^${playerId}: ` (the *viewer's own* id, from `useNightwireSocket`'s `playerId` argument) is the viewer's own line → bubble, right-aligned. Everything else (narrator prose, or another player's `"other-id: ..."` line) → left-aligned prose, no bubble. This deliberately doesn't distinguish "other player" from "narrator" yet — that's a real simplification, acceptable because nightwire's current sessions are single-player in practice; note it as a known gap if multiplayer testing surfaces it as wrong.

**Files:**
- Modify: `frontend/src/app/nightwire/page.tsx`

**Steps**

- [x] **Step 1:** Write a small `isOwnLine(line: string, playerId: string): boolean` helper (`line.startsWith(\`${playerId}: \`)`).
- [x] **Step 2:** Replace the log's `.map` with a branch: own lines get the bubble wrapper (reused classes above, minus the `MessageActions`/edit affordance — that's chat-editing, not in scope here), everything else gets left-aligned prose (`font-serif text-stone-100`, matching open-dungeon's own narrator styling — nightwire's narrator prose deserves the same treatment, not a plain `<p>`).
- [x] **Step 3: Live-verify.** Done against the real GPU backend: player's own line rendered as a right-aligned bubble with the `> ` prefix visible inside it, narrator reply rendered as left-aligned prose below it, no console errors. Also surfaced a real, unrelated backend finding while verifying: a narrator turn attempted a `start_combat` tool call with malformed args, producing `[tool error: 5 validation errors for StartCombat ...]` — a raw pydantic `ValidationError` dump landed in `session.log` and rendered as narrator prose (correctly, by this task's own classifier — the *content* being a technical error dump is a Phase 3 narrator/tool-schema concern, out of scope here, but worth fixing eventually so players never see a stack-trace-shaped message).
- [x] **Step 4: Commit** — `feat: chat-bubble narration layout on the /nightwire route`.

---

### Task 3: Persistent vitals/party/objectives band

**Goal:** A compact, always-visible strip between the feed and the composer — own HP/armor/conditions, other characters' redacted vitals, current location/scene mood, and active objectives. Per the spec: "always visible — no tab-switching hides your own HP."

**Files:**
- Modify: `frontend/src/app/nightwire/page.tsx`

**Steps**

- [x] **Step 1:** Render a `<div>` band reading directly off `view.characters[playerId]` (own `FullCharacter`: `health`/`max_health`/`armor`/`conditions`) and the remaining entries in `view.characters` (each a `RedactedCharacter` when not the viewer — same fields minus `attributes`/`inventory`/`player_id`/`lifepath`).
- [x] **Step 2:** Render `view.location` and `view.scene_mood` (both nullable — render nothing, not an empty label, when null) and `view.active_objectives` as a short inline list.
- [x] **Step 3:** Minimal single-line-rule styling, matching the spec's "minimal thin single-line rules between sections, no heavy box-drawing borders" language (`border-t border-stone-800`, not a boxed panel).
- [x] **Step 4: Live-verify.** Joined with a real character, confirmed the band renders immediately from the join broadcast (`Doc · 10/10 HP`). Sent an action; HP/armor stayed unchanged (no successful `apply_character_update`/damage this turn) and `location`/`scene_mood`/`active_objectives` correctly rendered nothing rather than empty labels — `OLLAMA_WORLD_UPDATES` defaults off per `ROADMAP.md`, so those fields not populating is expected on this deployment, not a bug. The update-on-change path itself (band re-rendering after a real stat change) is still unverified — no test turn actually changed a stat.
  - **Same recurring backend finding as Task 2**, now seen twice independently: the narrator attempted a `start_combat` tool call with malformed args again (`[tool error: 3 validation errors for StartCombat ...]`), same shape as before. Two independent live turns hitting the identical failure mode is a real, reproducible pattern — likely a narrator system-prompt or tool-schema issue in Phase 3, not a one-off model hiccup. Flagging for whoever picks up Phase 3 hardening next.
- [x] **Step 5: Commit** — `feat: persistent vitals/party/objectives band on the /nightwire route`.

---

### Task 4: Character portrait placeholder

**Goal:** A small, deliberately-cheap placeholder avatar next to the sheet header — per ROADMAP, "not photorealistic, not AI-generated yet... a real visual touch that ships before Phase 5's real image generation exists."

**Files:**
- Create: `frontend/src/lib/nightwire/portrait.ts`

**Steps**

- [x] **Step 1:** Write a pure function `portraitFor(role: string, name: string): { initials: string; colorClass: string }` — initials from the name, a Tailwind background color class picked deterministically from a small fixed palette by hashing `role` (so every character of a given role reads consistently, not randomly per render). No image assets, no generation call.
- [x] **Step 2:** Render it as a small rounded square (`size-5` inline in the vitals band, `size-10` in the sheet header) next to the character name in Task 3's vitals band and Task 5's sheet header.
- [x] **Step 3: Live-verify.** Joined as "Zeke" (role Fixer) — rendered a `ZE` badge, amber, in both the vitals band and the sheet header. Only one role tested live (a second role's distinct color wasn't independently re-verified in a second session — the hash function itself is deterministic and trivial enough that this is a low-risk gap, but noting it rather than claiming full verification).
- [x] **Step 4: Commit** — `feat: deterministic placeholder portrait for character avatars`.

---

### Task 5: Character sheet overlay (`Ctrl+K`)

**Goal:** On-demand full sheet, laid out like a physical tabletop sheet — boxed sections for core stats, skills-equivalent, equipped vs. carried gear, features/abilities. Toggled via `Ctrl+K`, not a permanently-visible panel.

**Files:**
- Create: `frontend/src/app/nightwire/CharacterSheetOverlay.tsx`
- Modify: `frontend/src/app/nightwire/page.tsx` — keybind wiring, overlay open/closed state.

**Steps**

- [x] **Step 1:** `CharacterSheetOverlay` takes the viewer's own `FullCharacter` (typed as `CharacterSheet`) and an `onClose` callback. Sections: header (portrait from Task 4 + name/role/lifepath), attributes (`Record<string, number>` — renders whatever keys are actually present, doesn't hardcode the six-attribute list since that's the ruleset's concern, not the frontend's — confirmed live as "None set." for a join with no attributes), health/armor/conditions, inventory. Thin single-line rules between sections, no heavy borders.
- [x] **Step 2:** `useEffect` keydown listener for `Ctrl+K` in `page.tsx`, toggling a local `sheetOpen` boolean, `event.preventDefault()`'d so it doesn't hit the browser's own address-bar shortcut. Rendered only once `view` exists and the viewer's own entry in `view.characters` is narrowed to `CharacterSheet` via a `"player_id" in ...` check (the map's value type is `CharacterSheet | RedactedCharacter`).
- [x] **Step 3: Live-verify.** Joined, pressed `Ctrl+K` — overlay opened showing the real joined character's data (name, role, lifepath, HP, empty attributes/inventory correctly rendered as "None set."/"Empty." rather than blank). Clicked the explicit close button — overlay closed cleanly, feed underneath still intact.
- [x] **Step 4: Commit** — `feat: on-demand character sheet overlay (Ctrl+K)`.

---

### Task 6: Whole-phase live verification pass

**Goal:** One end-to-end pass through everything this plan built, together, against a real GPU-backed backend — matching how prior phases closed with "one final whole-branch review" before considering the phase done.

**Steps**

- [x] **Step 1:** Fresh browser session against `metta-desktop-gtr32bn` (the current GPU stand-in while msi-laptop rebuilds). Connected, joined as "Marrow" (Solo/Corpo) — portrait (`MA`, Task 4) and vitals band (`Marrow · 10/10 HP`, Task 3) both rendered correctly from the join broadcast alone, before any action was sent. Bubble layout (Task 2) has nothing to show yet at this point, by design — confirmed in Step 2 instead.
- [x] **Step 2:** Sent one real action in each composer mode against the live backend, all three round-tripped and rendered correctly composed with the bubble layout: `Do` → `player-final: > I slip through the service entrance.` (bubble, right-aligned), `Say` → `player-final: > You say "Anyone else in here?"`, `Think` → `player-final: > You think "This whole job feels wrong."` — narrator prose rendered left-aligned after each.
- [x] **Step 3:** Opened the sheet overlay (`Ctrl+K`) while a narrator turn was in flight (`sending` state active), confirmed the underlying feed's prior narration was still present in the DOM the whole time the overlay was open, closed the overlay via `Ctrl+K` again (not just the button — confirmed the keybind toggles both directions), fed continued live-updating normally afterward. No desync.
- [x] **Step 4:** Checked browser console for errors across the entire pass (console tracking armed from before the first navigate) — **zero errors**, entire pass clean.
- [x] **A decisive version of the recurring finding from Tasks 2/3**: every single one of the four real narrator turns in this final pass — not most, all four — produced a `[tool error: N validation errors for StartCombat ...]` line. What looked like an intermittent quirk across Tasks 2-3 is, based on this pass, closer to "the narrator attempts `start_combat` with malformed args on nearly every turn regardless of content." This is now the single most important finding to hand off to whoever picks up Phase 3 hardening next — it's not a rare edge case.
- [x] **Step 5:** `ROADMAP.md`'s Phase 4 entry rewritten to reflect what's actually built vs. still deferred.
- [x] **Step 6: Commit** — `docs: close out Phase 4a-revised - open-dungeon frontend, composer, bubbles, vitals, portrait, sheet`.

**Final port-verification pass, once ownership was actually fixed:** all five frontend tasks applied to the real tree as five separate commits (mirroring this plan's own task boundaries, including one self-correction: the first composer commit accidentally bundled the bubble diff too, caught and split via `git reset --soft` before anything was pushed). Every file diffed byte-identical against the already-live-verified scratch copy before committing. A second live pass, this time against the real committed code (not the scratch copy) and the *rebuilt* `msi-laptop` (`100.67.87.32`, GPU confirmed live post-rebuild - `NVIDIA GeForce RTX 2080 with Max-Q Design`, same card): join → portrait + vitals rendered from the broadcast alone, a live `Do`-mode action round-tripped and rendered as a bubble + narrator prose, the narrator called `end_combat` this time (not `start_combat` - confirms the schema fix generalizes across all five tools, not just the one that surfaced it) with valid args and zero tool errors, `Ctrl+K` opened/closed the sheet overlay correctly (the automated key-press needed a `KeyboardEvent` dispatched directly at the page rather than the browser-automation `key` action, which Chrome's own address-bar shortcut was intercepting first when no real input had focus - a test-tooling quirk, not a code issue), zero console errors across the whole pass.

## Out-of-scope fix landed alongside this plan: the `start_combat` narrator bug

Not a Phase 4a-revised task (this is Phase 3, `narrator/client.py` and `narrator/harness.py`), but built, tested, and live-verified in the same session that closed Task 6, since Task 6 is what surfaced it as decisive rather than intermittent (4/4 real turns hit it).

**Root cause** (confirmed by reading the actual code, not guessed): `NarratorResponse.tool_args` was a bare `dict` — Ollama's structured-output `format` schema constrained the model to a valid `tool` *name* but gave it nothing to constrain `tool_args`'s shape, so the model free-generated a plausible-looking-but-wrong shape for `start_combat` (`scene`/`enemies`/action-lists) instead of the real `{"reason": str}`. The system prompt (`server/__main__.py`: `"You are a cyberpunk tabletop game master."`) also never documents any tool's argument shape.

**Real fix implemented**: `NarratorResponse.tool_call` is now a Pydantic discriminated union (`Annotated[Union[_NoTool, _RequestRollCall, ..., _StartCombatCall, ...], Field(discriminator="tool")]`), each variant embedding the *actual* tool argument model from `narrator/tools.py` (`RequestRoll`, `StartCombat`, etc.) rather than a loose dict. `.tool`/`.tool_args` kept as properties returning the same flat shape every existing caller already expected, so `server/narration.py` needed zero changes. `narrator/harness.py`'s `run_harness` needed one real follow-on fix: with strict validation, a malformed tool call now raises inside `client.respond()` itself rather than surviving to be scored later, so the harness loop needed a `try/except ValueError: continue` around each `respond()` call to keep scoring failures instead of crashing — `_scores_as_pass`'s own redundant re-validation was deleted as dead code, since an invalid shape can no longer reach it.

**Verified two ways, not just unit-tested:**
- `pytest`: 117 passed locally (116 baseline + one new test asserting a wrong-shape `start_combat` call now raises `ValueError` at parse time), 115 passed + 2 skipped on the Windows deployment (same suite, platform-skipped tests).
- **Live against the real GPU-backed `qwen3:8b`**, three real turns specifically chosen to reliably trigger `start_combat` (matching the exact kind of prompt that hit the bug 4/4 times in Task 6's own verification pass): **zero `tool error` lines**, all three `start_combat` calls succeeded with valid `{"reason": ...}` args. Response times also dropped (~9s vs. 17-30s+ before) — likely because the model no longer wastes generation on a shape that then fails validation.

**What's still open, now cleanly separated from the bug this fixed**: the narrator still calls `start_combat` on nearly every turn regardless of whether the scene actually escalates to violence — a real over-triggering/prompt-tuning issue, but now a low-severity one (it succeeds harmlessly with `{"acknowledged": true, ...}` instead of erroring). Worth a system-prompt pass on *when* to call it, separate from this fix.

**Files changed, now committed to the real tree**: `narrator/client.py`, `narrator/harness.py`, `tests/test_narrator_client.py`, `tests/test_narration.py`, `tests/test_app.py`, `tests/test_harness.py` — one commit, `fix: constrain tool_args to a real per-tool schema, not a loose dict`. Also deployed directly (fix included from the start, no separate port needed) to the rebuilt `msi-laptop`, alongside a fresh `dojo` bootstrap and a full `~/projects/github/repos` clone there for future direct-on-machine work.

**Phase 4a-revised status: done.** All six tasks landed in the real `nightwire` repo as separate commits (7 total: 5 frontend tasks + the out-of-scope narrator fix + this doc), each live-verified against a real GPU-backed backend - first in a sentinel-owned scratch copy (while the real tree was root-owned and sudo was broken), then confirmed byte-identical and re-verified live against the real committed code once ownership was fixed. `ROADMAP.md` updated. Nothing left blocked.

**Still open, deliberately out of this plan's scope, for whoever picks up next:**
- The narrator's `start_combat`/`end_combat` over-triggering (fires almost every turn regardless of content) - now harmless post-fix, but still a real prompt-tuning gap.
- Combat/turn-order controls, other-player-vs-narrator bubble distinction, and real character creation - all explicitly deferred per this plan's own Global Constraints.
- A narrator turn hanging indefinitely under real GPU contention (observed once, cleared by a server restart) - server-side, Phase 3 territory.
