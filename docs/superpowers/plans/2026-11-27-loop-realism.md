# Loop Realism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rippling wet street, neon bloom, rain lit by the lights, one passing car per loop and light film grain
to `tools/loop_still`, all on by default, all periodic, with the face still exact.

**Architecture:** One new module `tools/loop_still/realism.py` (`Ripples`, `Bloom`, `light_map`, `rain_tint`,
`grain`); `render.py` wires them into the existing back-to-front loop; `__main__.py` gains on/off flags.

**Tech Stack:** numpy, OpenCV, pytest (venv `.venv`).

**Spec:** `docs/superpowers/specs/2026-11-26-loop-realism-design.md` (approved 2026-11-27).

## Global Constraints

- CPU only; no new models or dependencies.
- Every layer is periodic in the frame index i with period N (frame N == frame 0), except grain, which is fresh per
  frame and seeded by (seed, i).
- Face pixels stay exact: `face_max_diff == 0`. Grain and ripples never touch the held mask.
- Existing checks keep passing on the three test stills: stretch 0.9–1.1, seam ≤ 1.25, halo 0.96–1.04, repeat ≥ 1.0.
- New meta check `ripples_on_her` must be 0 (no ripple or mirror change inside her hard matte).
- Seam and repeat are measured on frames before grain.
- Defaults on: `--ripples`, `--bloom`, `--lit-rain`, `--car`, `--grain`; `--mirror` off. Each has a `--no-` form.
- Commits carry no AI-attribution trailers.

## Review Focus

1. A still with no character (empty matte): ripples, bloom and grain still work; no crash.
2. `--rain none`: no ripples, no car-dependent crash; lit rain is a no-op.
3. Short loops (e.g. 3 s) where the default car sweep can't fit: the car is skipped with a note, not an assert.
4. `--no-lights`: the car needs lights; it is skipped with a note, and bloom uses the static plate.
5. Ground line at the very bottom (`--ground 1.0`): ripples have no area and must not crash.

---

### Task 1: `realism.py` — ripples, bloom, light map, grain

**Files:**
- Create: `tools/loop_still/realism.py`
- Test: `tests/test_loop_realism.py`

**Interfaces:**
- Produces:
  - `Ripples(size, frames, fps, ground, seed, preset, avoid=None)` with `.area` (H×W float32 0..1, zero above the
    ground line and inside `avoid >= 0.5` grown 9 px), `.apply(img, i) -> img` (resamples `img` through the ripple
    gradient inside `.area`, adds lit rings), `.empty` (bool).
    Drop count per loop: `{"none": 0, "drizzle": 60, "steady": 160, "heavy": 320} * W/1920`; life 0.8 s; each drop
    active at frames `(t0 + age) % N`, so the field is periodic by construction. Height
    `A·sin(k·r − ω·age)·exp(−r/σ)·exp(−age/τ)` drawn on a half-size grid in a local patch per drop. Offset
    = gradient × 10 px × perspective (0.3 at the ground line → 1.0 at the bottom). Ring light = positive part of h ×
    blurred plate brightness × 0.25.
  - `Bloom(base, strength=0.22)`: `.mask` from `base` once (luma > 0.55 and saturation > 0.3, soft); `.apply(img)`
    screen-adds three blurs (σ ≈ 6, 24, 80 px at 1920 wide, done at quarter size), the widest warm-tinted.
  - `light_map(img) -> (H, W, 3)` float32: the image blurred at 1/8 size, upscaled.
  - `rain_tint(lmap) -> (H, W, 3)`: `clip(0.35·RAIN_TINT + 1.6·lmap, 0, 1.6)`.
  - `grain(shape, seed, i, amount=0.012) -> (H, W, 1)` float32, gaussian, same for the same (seed, i).
- [x] **Step 1: Write the failing tests.**
  `test_ripples_are_periodic_and_stay_off_her`: `apply(img, 0) == apply(img, N)`; frames differ at some i;
  pixels above the ground line and inside `avoid` are unchanged.
  `test_ripples_none_preset_is_empty`: preset "none" → `.empty` and `apply` returns the image unchanged.
  `test_ripples_with_ground_at_bottom_does_not_crash`.
  `test_bloom_only_near_bright_neon`: black image with one bright saturated square → brighter just outside the
  square, unchanged far away; an all-grey image is unchanged.
  `test_rain_is_brighter_under_light`: `rain_tint` larger where the light map is bright.
  `test_grain_is_fresh_per_frame_and_reproducible`.
- [x] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_loop_realism.py -q` → FAIL (module missing).
- [x] **Step 3: Implement `realism.py`.**
- [x] **Step 4: Run them.** Expected: PASS.
- [x] **Step 5: Commit.** `loop_still: ripples, bloom, lit rain and grain layers`

### Task 2: Wire into `render.py` and the CLI

**Files:**
- Modify: `tools/loop_still/render.py` (Options, render loop), `tools/loop_still/__main__.py`,
  `tools/loop_still/checks.py` (pre-grain `final`, `ripples_on_her`)
- Test: `tests/test_loop_render.py`

**Interfaces:**
- Consumes: Task 1's classes and functions.
- Order per frame: `city = lights.frame(i)` → bloom → ripples (and mirror) → far rain × tint and fog × (0.5 + lmap)
  → body, hair, coat, blinks → face check → edge tint → splashes, near rain × tint → final check (pre-grain) → grain
  × (1 − held) → encode.
- Car: when `o.car` and `o.lights` and no `o.sweeps`, sweep at `round(0.45·seconds, 2)` s when it fits
  (`p + 2.6·fps + 1.5·fps < N`), else note "car: loop too short".
- Mirror: flipped, blurred (σ 6 px) copy of `frame` above the ground line, × 0.18, inside `ripples.area`, drawn
  through the ripple offsets.
- `meta.checks.ripples_on_her`: max |change| that the ripple and mirror layers make inside the hard matte, over all
  frames; failing if > 0.
- [x] **Step 1: Write failing tests.** `test_realism_defaults_on` (parse defaults); `test_render_with_realism_passes_checks`
  (synthetic still with a character and a bright patch: checks pass, `ripples_on_her == 0`, `face_max_diff == 0`);
  `test_car_skipped_on_short_loop` (3 s loop renders and notes the skip); `test_no_character_renders`.
- [x] **Step 2: Run them.** Expected: FAIL.
- [x] **Step 3: Implement.**
- [x] **Step 4: Run the full suite.** `.venv/bin/python -m pytest tests/ -q` → all pass.
- [x] **Step 5: Commit.** `loop_still: realism layers on by default (ripples, bloom, lit rain, car, grain)`

### Task 3: Render the three test stills, measure, publish

- [x] Render rin-kageyama--alley, ayame-tsuda--city and yuki-shirasagi--city with defaults (`--preset realism`), one at a time.
- [x] All checks pass; record seconds per clip and per-layer cost in the ledger, then compare with the spec's estimate.
- [x] Look at frames: ripples visible but subtle, bloom stays anime, rain darkens in shadow, car once. Tune values, then re-render.
- [x] Update the Loops page with before/after pairs, add card `loops-realism` to the inbox, update the guide's loop section.
- [x] Commit, push and tick the plan.

## Result (2026-11-27)

- All three test stills pass every check (face 0, ripples on her 0; seam 0.88–0.99; repeat 2.8–5.1). About 530 s per
  20 s clip, against 6–7 min before.
- Measured per frame at 1920×1338 after review fixes: ripples 53 ms, bloom 81 ms, lit rain 50 ms, grain 41 ms (spec
  guessed less for ripples and bloom).
- Review fixes: bloom ignores her; `--mirror` alone doesn't ripple; ripples only on street rows, clamped and kept
  clear of her, with a real leak check; the missing no-character and ground-at-bottom render test was added.
- Owner card `loops-realism` asks: more real or just busier, ripple strength, keep the car, keep grain.
