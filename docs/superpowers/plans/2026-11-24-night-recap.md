# Night Recap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pick 3 to 12 panels from a played session and write them out as an HTML sheet and a silent animatic.

**Architecture:** `narrator/recap.py` is pure and deterministic. It turns a Session into Panels plus facts.
`tools/recap.py` renders those to `recap.html` (with images copied beside it) and to `recap.mp4`, reusing
`tools/shorts/animatic.py`'s `_fit`, `_camera` and `zoom_pan` and `remote.h264_encoder`. The soak test saves its
session and calls it.

**Spec:** `docs/superpowers/specs/2026-11-24-night-recap-design.md` (approved 2026-11-24).

## Global Constraints

- Panels: at least 3 (or every turn, if there are fewer), at most 12, held 3.5 s each, with 0.5 s fades.
- Scores:
  - clean success or failure 2, complication 1
  - `[promise: ` / `[promise kept: ` / `[promise broken: ` 3
  - `[director: <id>]` (not `breather`) 2, `[pressure: ` 2
  - `[person: ` and `[director: comeback]` 2
  - `[rated: like]` 3
  - `[mark: ` 1
- Always keep the first turn, the last turn and the first turn in each new district. A scene holds panels in proportion to its turns,
  at least 3 (build ruling, see the spec).
- Art, in order: the turn's `[image: x]`, then `location_art(place)`, then `district_art(place)`, then None (a dark
  card).
- Speech: an NPC line of 4 to 20 words, the shortest one, with `character-art/<slug>.jpg` when it exists. Otherwise
  the first sentence of the narration, capped at 160 characters.
- The action line reads "<player name>: <action>". Nothing in brackets reaches a panel.

## Review Focus

- A roll turn (the set-up, then the resolution, with no new action line) stays one turn (Task 1).
- A session with fewer than 3 turns shows every turn and never crashes on 0 turns (Task 1).
- Party play: several player ids, each action line is its own turn, and the right name shows (Task 1).
- A missing image file on disk falls back to a dark card instead of crashing the renderer (Task 2).

### Task 1: The engine

**Files:**
- `engine/session.py` and `persistence.py`: `trail: list[str]`.
- `narrator/director.py`: `tick` appends `session.location or ""`.
- `narrator/ratings.py`: `rate` logs `[rated: like]` or `[rated: dislike]`.
- `narrator/places.py`: `mark` logs `[mark: <text>]` when it adds one.
- New `narrator/recap.py` and `tests/test_recap.py`.

**Produces:**
- `recap.turns(session) -> list[dict]`, each `{n, player, action, place, lines, notes, image}`.
- `recap.panels(session) -> list[dict]`, each `{n, place, caption, art, speaker, portrait, text, action}`.
- `recap.facts(session) -> dict`, with `{people, promises_open, promises_done, leads, night}`.

- [ ] Tests:
  - a quiet 2-turn session gives 2 panels
  - the first, last and new-district turns are kept
  - a 30-turn session gives 12 panels or fewer
  - never more than 3 in a row in one place
  - a speech panel takes the shortest line of 4 to 20 words and its portrait
  - no bracket text ever appears
  - a roll's set-up and resolution form one turn
  - party names are right
  - an old save with no trail works
  - the `[rated: like]` and `[mark: ]` log lines are written
- [ ] Implement, run the full suite, commit.

### Task 2: The renderer and the soak hook

**Files:** new `tools/recap.py` and `tests/test_recap_render.py`. Change `tools/soak_test.py` so it saves the session
JSON next to the soak file and builds the recap into `design-data/soak/<stamp>-recap/`.

- [ ] Tests:
  - the HTML holds every panel's text and the facts
  - images are copied, and a missing one becomes the dark card
  - with ffmpeg present, the mp4 lasts 3.5 s × panels within 0.3 s (ffprobe)
- [ ] Run `python -m tools.recap <session.json> --out DIR` on a seeded session.
- [ ] Commit, push, then run it on soak 17.
