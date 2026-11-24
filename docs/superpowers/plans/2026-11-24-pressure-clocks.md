# Pressure Clocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three written, engine-owned clocks that fill from fights, misses, heat and nights, ease when their leads are
done, send portents and a full beat to the narrator, and show on the Status panel.

**Architecture:** One new module `narrator/clocks.py` reads `narrator/worlds/clocks.toml` and keeps state in a new
`Session.clocks` dict. The director's end-of-turn `tick` calls it; the narrator prompt gets one line, the state view
gets a `pressure` list, and the Status panel draws pips. No model calls.

**Tech Stack:** Python 3 (tomllib, pytest), Next.js/React (StatusPanel.tsx).

**Spec:** `docs/superpowers/specs/2026-11-24-pressure-clocks-design.md` (review card `pressure-clocks`, kept 2026-11-24
with no notes: all three clocks as written, the container clock hidden).

## Global Constraints

- Sizes are 4, 6 or 8. At most one segment per clock per turn, up or down; never below 0.
- Triggers are exactly `fight`, `miss`, `heat`, `night`, `lead_done`.
- Full: the `full` line goes to `session.pending_world_events`, the clock's `lead` goes through `promises.add_lead`,
  the log gets `[pressure: <id> full]`, the clock resets to 0 and rests 40 player turns (`director.NO_REPEAT`).
- A portent line is queued once each time the clock rises onto its stage; the log gets `[pressure: <id> <n>/<size>]`.
- Narrator line, shown clocks in the current district only: `Pressure: <name> <n>/<size>.`
- At most 2 shown clocks; hidden clocks never appear in the view or the prompt line.
- Old saves load with `clocks = {}`.

## Review Focus

- A turn with a fight AND a new night moves a clock one segment, not two (test in Task 1).
- A clock resting after full doesn't move at all, and `lead_done` during the rest doesn't take it below 0 (Task 1).
- A clock ticked from 0 straight across a stage queues its portent; easing back below and rising again queues it
  again (Task 1).
- A save from before clocks (no `clocks` key) loads and ticks (Task 1).
- The prompt line stays empty in a district with only a hidden clock (Task 2).

---

### Task 1: The clocks module and world file

**Files:**
- Create: `narrator/clocks.py`, `narrator/worlds/clocks.toml`, `tests/test_clocks.py`
- Modify: `engine/session.py` (field `clocks: dict[str, dict] = field(default_factory=dict)` next to `places`),
  `engine/persistence.py` (`clocks=data.get("clocks", {})`)

**Interfaces:**
- Produces:
  - `clocks.defs() -> tuple[dict, ...]` (cached, validated load; `defs.cache_clear()` usable in tests)
  - `clocks.validate(raw: list[dict]) -> None` raises `ValueError` naming the clock id
  - `clocks.tick(session, rolls: list[dict], heat_rose: bool) -> None`
  - `clocks.line(session) -> str` (`""` when nothing to say)
  - `clocks.view(session) -> list[dict]`, each `{"name", "district", "filled", "size"}`, shown clocks only
- State per clock id: `{"filled": int, "night": int, "rest_until": int}` (`night` is the last night seen, starting
  at the session's night when first seen, so the first tick never counts a night).

**World file.** Each `[[clock]]`: `id`, `name`, `size`, `shown`, `where` (district names), `ticks`, `eases`,
`eases_leads` (optional list), `portents` (table of stage -> line, keys are segment numbers as strings),
`full`, `lead`. Write the three clocks from the spec, wording below:

| id | name | size | shown | where | ticks | eases | eases_leads |
|---|---|---|---|---|---|---|---|
| `ogane-docks` | Ōgane crackdown on the Docks | 6 | true | Kuroshio Docks | fight, heat, night | lead_done | the crane-jam event's lead, copied exactly from events.toml |
| `container` | The no-manifest container | 4 | false | Kuroshio Docks | night | (none) | |
| `kuze-ikebe` | Kuze-gumi squeeze on Ikebe Low | 6 | true | Ikebe Low | miss, night | lead_done | (none: any done lead naming the district) |

- ogane-docks: 2 "Extra Ōgane drones hang over the gantry cranes, sweeping the container canyons with light." 4
  "Ōgane checkpoints go up at the Docks gates, fining everyone who passes." full "An Ōgane armored response team
  sweeps the container canyons, kicking open doors and billing every crew it finds." lead "Find out who sold the
  Docks out to Ōgane".
- container: 2 "The no-manifest container's light flickers in a pattern, as if something inside is counting." 3 "A
  crane lifts the no-manifest container to the outbound stack on its own, with no operator in the cab." full "The
  no-manifest container ships out on the night tide; whatever was running inside is gone." lead "Find out where the
  no-manifest container went".
- kuze-ikebe: 2 "Shop shutters in Ikebe Low carry fresh Kuze-gumi protection stickers." 4 "A chrome-ya clinic behind
  a noren curtain closes \"for renovation\", a Kuze-gumi lantern at its door." full "The Kuze-gumi takes over a block of
  Ikebe Low, and two men in suits pay Mama Sato's izakaya a polite visit." lead "Find out who in Ikebe Low is paying
  the Kuze-gumi".

**Tick rules** (the algorithm the tests pin):
- District = `_where(kuroshio(), session.location)[1]`. `fight`: a roll with skill in `places._FIGHT_SKILLS`, or
  `session.in_combat`, while in the clock's district. `miss`: an outcome `failure` or `complication` there.
  `heat`: `heat_rose` there. `night`: `session.night` > the stored `night` (anywhere; always update the stored night).
- `lead_done`: a journal entry this turn (`kind == "done"`, `turn == _player_turns(session)`) whose text is the
  clock's `lead`, or is in `eases_leads`, or — only when the clock has no `eases_leads` — names its district
  (`_where(kuroshio(), text)[1]` is in `where`).
- `up = any tick trigger fired`, `down = any eases trigger fired`; move `up - down` (so both = no move).
- While `_player_turns(session) < rest_until`: no move.
- Rising onto a stage in `portents` queues that line (`pending_world_events`) and logs it. Reaching `size` fires
  full instead.

- [ ] **Step 1: Write failing tests** in `tests/test_clocks.py` (use `tests.test_referee._session`; put a roll in
  the log as `[roll: {...}]` the way `director._rolls_this_turn` reads it, or pass `rolls` directly):
  - `test_world_file_loads`: `{c["id"] for c in clocks.defs()} == {"ogane-docks", "container", "kuze-ikebe"}` and
    at most 2 have `shown`.
  - `test_validate_rejects` (parametrized): size 5; unknown trigger `"riot"`; unknown district; portent stage 6 on a
    size-4 clock; missing `full`. Each raises `ValueError`.
  - `test_fight_in_district_moves_one`: in "Kuroshio Docks", a melee roll + `heat_rose=True` -> ogane-docks filled 1,
    kuze-ikebe 0.
  - `test_fight_and_new_night_still_one`: same turn also `session.night += 1` -> ogane-docks 1 (and container 1).
  - `test_first_tick_counts_no_night`: fresh session at night 3 -> container 0.
  - `test_portent_queued_on_stage`: ogane-docks at 1, a fight -> 2, its stage-2 line is in
    `pending_world_events`, and `[clock: ogane-docks 2/6]` in the log.
  - `test_ease_then_rise_requeues_portent`: at 2, a done journal entry with the crane-jam lead this turn -> 1; a
    fight next turn -> 2 and the portent queued again.
  - `test_kuze_eases_on_any_ikebe_lead`: kuze at 3; a done entry "Ask at the Low-city shrine who cut Ikebe Low's
    power" this turn -> 2.
  - `test_full_fires_lead_and_rests`: container at 3, new night -> filled 0, its full line queued, its lead in
    `active_objectives`, `[clock: container full]` logged; next night inside 40 turns -> still 0.
  - `test_never_below_zero`: kuze at 0 with an Ikebe done lead -> 0.
  - `test_line_and_view`: in Ikebe Low with kuze at 4 -> `line == "Pressure: Kuze-gumi squeeze on Ikebe Low 4/6."`;
    in Kuroshio Docks with only the container moved -> `line == ""` (shown clocks at 0 and hidden clocks say
    nothing); `view` never includes `container`.
  - `test_old_save_loads`: a session dict without `clocks` loads through `JSONFileSessionStore` with `clocks == {}`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_clocks.py -q` -> fails (no module).
- [ ] **Step 3:** Implement the module, world file, session field and persistence line. Line rule: shown clocks in
  the current district with `filled > 0`, joined with "; " after `Pressure: `, ending in ".". View: every shown
  clock, `filled` from state (0 if unseen).
- [ ] **Step 4:** Tests pass; full suite `.venv/bin/python -m pytest tests/ -q` passes.
- [ ] **Step 5:** Commit "Pressure clocks: engine-owned clocks with portents (spec 2026-11-24)".

### Task 2: Wire it in

**Files:**
- Modify: `narrator/director.py` (`tick`), `server/narration.py` (prompt, after `places.line`), `server/views.py`
  (`"pressure": clocks.view(session)`), `frontend/src/app/nightwire/play/StatusPanel.tsx` (+ its view type),
  `tools/soak_test.py` (summary key `clocks`), `tools/soak_score.py` (two probes), `ROADMAP.md`, tests.

**Interfaces:**
- Consumes: Task 1's `clocks.tick`, `clocks.line`, `clocks.view`.

- [ ] **Step 1: Failing tests:**
  - `tests/test_director.py::test_tick_moves_pressure_clocks`: player in Kuroshio Docks, a melee roll logged this
    turn, `director.tick` -> `session.clocks["ogane-docks"]["filled"] == 1`. `heat_rose` = the current place's heat
    after `places.heat` is above its value before.
  - `tests/test_views.py` (or where `build_view` is tested): `"pressure"` lists ogane-docks and kuze-ikebe, never
    container.
  - Prompt test next to the existing `places.line` prompt test: in Ikebe Low with kuze at 2 the prompt contains
    `Pressure: Kuze-gumi squeeze on Ikebe Low 2/6.`; in Kuroshio Docks with only the container moved, no
    `Pressure:` line.
  - `tests/test_soak_score.py`: probes `clock_moved` (any clock filled > 0, or any `[clock: ... full]`… use
    `events`-free summary: any `summary["clocks"]` value with `filled > 0` or `rest_until > 0`) and `clock_portent`
    (summary key `clock_portent`: soak_test sets it True when any log line starts with `[clock: ` and isn't `full`
    or a night-clock line — night-clock lines are `[clock: night ...`).
- [ ] **Step 2:** Run them; they fail.
- [ ] **Step 3:** Wire: in `director.tick`, read the place heat before `places.heat`, then call
  `clocks.tick(session, rolls, heat_rose)` after the lockdown block. Prompt line after `here`. View key. Status
  panel: a "Pressure" section under "Here", one row per clock: name, then `●`/`○` pips like the repo clock in
  `CharacterSheetOverlay.tsx`, with `role="img"` and `aria-label="<name> <filled> of <size>"`; hide the section
  when the list is empty. Soak: add `"clocks"` to the summary keys and set `summary["clock_portent"]`. Roadmap: a
  "Pressure clocks" bullet under Built.
- [ ] **Step 4:** Full pytest passes; `cd frontend && npx tsc --noEmit && npx eslint src/app/nightwire/play/StatusPanel.tsx`
  clean.
- [ ] **Step 5:** Commit "Pressure clocks: director, prompt, status panel and soak probes".
