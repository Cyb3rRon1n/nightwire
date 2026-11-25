# Last Night Recap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A "Last night" chip in the Status panel that opens last night's recap panels in the game.

**Architecture:** `narrator/recap.py` tags turns with their night and picks one night's panels; `server/views.py`
sends `last_night`; a new `LastNightOverlay.tsx` (Radix dialog, like the gallery) shows it from a chip in
`StatusPanel.tsx`.

**Tech Stack:** Python/pytest, Next.js/React, node:test.

**Spec:** `docs/superpowers/specs/2026-11-24-last-night-recap-design.md` (approved: chip only).

## Global Constraints

- Nothing opens by itself; the chip is "new" (cyan dot, `aria-label` "Last night, new") during the new night's first
  stretch until this player opens it; seen night saved per game in localStorage (`safeStorage` helpers).
- `last_night` is `None` on night 1 or when last night had no turns.
- Panel art paths are servable from the server root: `place-art/…` and `character-art/…` as is, scene images as
  `media/<path>`.
- A turn's night is the one current when its action line came (the sleep turn stays in the old night).

## Review Focus

- An old save with no `[clock:` lines: every turn is night 1 (Task 1).
- A night with fewer than 3 turns shows every turn (Task 1).
- Night 3: only night 2's turns, never night 1's (Task 1).
- Opening the overlay from the chip returns focus to the chip on close (Task 2, browser check).
- 390 px: the grid is one column and the chip doesn't wrap the Now line badly (Task 2, browser check).

---

### Task 1: engine and view

**Files:** modify `narrator/recap.py`, `server/views.py`; tests in `tests/test_recap.py`, `tests/test_views.py`.

**Produces:** `recap.turns(session)` dicts gain `"night": int`; `recap.panels(session, night: int | None = None)`;
`recap.last_night(session) -> dict | None` = `{"night", "panels" (art/portrait servable), "open": [str]}`;
`build_view(...)["last_night"]`.

- [ ] Tests: night tags incl. sleep turn; `panels(night=1)` excludes night 2; no clock lines -> night 1;
  `last_night` None on night 1, filled on night 2 with `media/` scene art; view key present.
- [ ] Implement; `pytest tests/test_recap.py tests/test_views.py` then the full suite.
- [ ] Commit "Last night: one night's panels in the view (spec 2026-11-24)".

### Task 2: chip and overlay

**Files:** create `frontend/src/app/nightwire/play/LastNightOverlay.tsx`; modify `StatusPanel.tsx`,
`protocol.ts` (`last_night` type), `play.css`.

- [ ] Chip beside "Night N · stretch"; new-dot rule from Global Constraints; overlay grid (art, portrait inset,
  caption, line, action), then "Still open".
- [ ] `npx tsc --noEmit`, `npx eslint` on touched files, `node --test` pass.
- [ ] Browser check at 1280 and 390 px against a saved soak session on night 3.
- [ ] Commit "Last night: chip and overlay".
