# District Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A subway-diagram map of Kuroshio's 7 districts in the World panel that shows engine state and fills the
action box with a travel line.

**Architecture:** `narrator/citymap.py` derives the map from session state and becomes `view["map"]`. A new
`play/CityMap.tsx` draws an `aria-hidden` SVG with real `<button>`s on top and a card below. A "Go" button lifts the
travel line to `PlayScreen`, which hands it to `FeedPanel`'s composer.

**Tech Stack:** Python/pytest, Next.js/React, node:test.

**Spec:** `docs/superpowers/specs/2026-11-24-district-map-design.md` (card `district-map`, kept 2026-11-24. Owner
said "go with what you think is right": the station order stays as drawn, and the Yomi Line is always shown).

## Global Constraints

- There are 7 districts, in this order: Tenjō Heights, Hanabira-chō, Ikebe Low, Kuroshio Docks, Ring Line, The Loop,
  Yomi Line.
- At most two marks per district: `here`, plus one of the clock's pips or a mood word that isn't "calm".
- The travel lines, copied exactly:
  - Ring Line district: "I take the Ring Line to <d>."
  - No trains (`clock.NO_TRAINS`): "I take a taxi to <d>."
  - Tenjō Heights: "I ride a maglev pod up to Tenjō Heights."
  - Yomi Line: "I head down into the sealed Yomi Line."
  - The Loop: "I ride up onto the Loop."
  - The current district: none.
- Go fills the action box. It never sends.
- Each button is at least 24 px, and 44 px under `pointer: coarse`. There is a `<figure>` with a `<figcaption>`.

## Ruling against the spec

The travel line is chosen in Python, as `go` on each district, not in the frontend. The engine owns the night clock,
so its tests live there. Cost if wrong: one small function moves to TypeScript.

## Review Focus

- A place key that is a district itself, such as "Ikebe Low", counts toward that district's mood (Task 1 test).
- The Ring Line district while you are on it: `here` is true and `go` is None (Task 1).
- A Go during your own pending roll: the composer is disabled, so the filled text waits there (Task 2: no send).
- In narrow mode, Go switches to the FEED tab, so the filled box can be seen (Task 2).
- A session with no location: nothing is `here`, and every district has a `go` (Task 1).

---

### Task 1: `narrator/citymap.py` and the view

**Files:** create `narrator/citymap.py` and `tests/test_citymap.py`. Modify `server/views.py` (`"map":
citymap.view(session)`).

**Produces:** `citymap.view(session) -> dict`, which is `{"districts": [ {name, here, mood, clock, people, places,
art, go} ×7 ], "trains": bool, "caption": str}`.
- `mood` is the worst `places.mood` word among `session.places` keys in that district (by `_where`), or "calm".
- `clock` is `{filled, size}` from the district's shown pressure clock, or None.
- `people` are the names in `session.people` whose `district` is this one.
- `places` are world place names in that district that are keys of `session.places`, or that `movement.places_in`
  finds in `active_objectives` or journal text.
- `art` is `place_art.location_art(name)`.
- `caption` reads "Kuroshio. You are in <d>. <n> districts under pressure.", with "You are in" left out when there is
  no location and "under pressure" counting clocks above 0. It says "1 district" for one.

- [ ] Tests: here and go for the current district; mood is the worst of two places, wary over calm; a shown clock
  appears but a hidden one never does; people by district; places known by visit and by objective text only; the
  taxi line in "small hours"; Tenjō, Yomi and Loop lines; no location means none is here; the caption counts; the
  view has a `map` key.
- [ ] Implement, then run `pytest tests/test_citymap.py` and the full suite.
- [ ] Commit "District map: engine view (spec 2026-11-24)".

### Task 2: The map component

**Files:** create `frontend/src/app/nightwire/play/CityMap.tsx`. Modify `WorldPanel.tsx` (a collapsible Map section
at the top, open state saved under `nightwire-map-open` with `readFlag`/`writeFlag`), `PlayScreen.tsx` (draft state
`{text, seq}`; on narrow screens Go also switches to the feed tab; the rail label becomes "Map"), `FeedPanel.tsx`
(prop `draft`; a `useEffect` on `seq` sets the composer text, sets mode "do", and focuses the box), `protocol.ts`
(`map` type), and `play.css`.

- [ ] Positions in a 300×320 viewBox:
  - Tenjō (150,20)
  - Hanabira (150,96)
  - Ikebe (234,166)
  - Docks (150,236)
  - Ring Line hub (66,166)
  - Loop (255,285)
  - Yomi (54,300)
- [ ] The inner ring is a 45° octagon through the four Ring stations. The outer Loop ring is an octagon about 30
  units outside it. Tenjō is a dashed spur to Hanabira. Yomi is a grey dashed line along the bottom.
- [ ] Buttons are placed by percentage, with the name on one line and the mark on a second small line. `here` gets
  `aria-current="location"`. The selected district's card sits below and has Go.
- [ ] `npx tsc --noEmit`, `npx eslint` on the touched files, and `node --test` all pass.
- [ ] Browser check at 1280 and 390 px against a local server, with screenshots.
- [ ] Commit "District map: diagram, card and Go".
