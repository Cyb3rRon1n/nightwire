# Layered Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m tools.loop_still STILL` turns one approved scene still into a seamless loop where the city
moves (lights, rain, fog, splashes), the character barely moves (hair, coat, breathing, later blinks), and the
viewer can't tell it repeats.

**Architecture:** A `tools/loop_still/` package. Every effect is a pure function of the frame index `i` over `N`
frames, with whole cycles per loop, composed back to front: lights (the existing `tools.lights.Lights`), far rain,
fog, the character (warped hair and coat over an inpainted plate, blink patches), splashes, near rain. A lossless
FFV1 master is written first; checks run on the frames as they render and land in `meta.json`.

**Tech Stack:** numpy, OpenCV (`remap`, `distanceTransform`, `inpaint`), scipy, onnxruntime (matte, LaMa), SAM 2 on
CPU (masks only, optional extra), ffmpeg (FFV1, H.264 via `tools.shorts.remote.h264_encoder()`).

**Spec:** `docs/superpowers/specs/2026-11-25-layered-loop-design.md` (card `layered-loop` kept 2026-11-26, no note).

## Global Constraints

- CPU only. No step may need the GPU except making blink patches (`tools/fix_area.py`, 4U box, outside this plan).
- Every pixel of the character is the approved still, only displaced; the face mask is never warped. Only the blink
  patches may change it.
- Every effect is periodic in `i / N` with whole cycles per loop. Forward loops only, no ping-pong, no crossfade.
- Cycle counts of different effects share no common factor (helper `pick_cycles`, Task 2).
- Defaults: `--seconds 20`, `--fps 24`, `--size 1920x1338`, `--rain steady`, near rain in front ON, `--motion
  hair,coat,breath` when the masks exist, `--edge-tint` OFF (an option), `--blink` OFF unless both patches exist.
- Tips move 1–2% of image height at 0.2–0.5 Hz (start at 1.5% and 0.3 Hz); breathing 0.3–0.5% at about 0.25 Hz (start
  0.4%). The wind follows the rain slant.
- Checks: face frozen = exactly 0 difference; stretch (Jacobian determinant) within 0.9–1.1; seam step ≤ 1.25× the
  median step; halo ring mean within 4%; `repeat_score` ≥ 1.0 (Task 6 defines it).
- Seeded and deterministic: the same arguments give byte-identical frames.
- New heavy deps (torch, sam2) go in a new optional extra `loops` in `pyproject.toml`, never in `dependencies` or
  `dev`. Tests must not need them or any model file.
- Downloads (BiRefNet/ToonOut ONNX, LaMa ONNX, SAM 2.1 tiny): standing OK; check and record each licence in
  `tools/loop_still/MODELS.md`. No CC-BY-NC weights.
- Masks and plates are cached beside the still (`<still>.matte.png`, `.hair.png`, `.coat.png`, `.face.png`,
  `.blink-half.png`, `.blink-closed.png`) and never overwritten unless `--redo-matte` / `--redo-regions`.
- No commit trailers or AI attribution.

Not in this plan: the Inochi2D hand-rig benchmark (hours of manual rigging in a desktop app; do it after the owner
has seen the first loops), parallax, hair-only video (spec "Not doing").

## Review Focus

1. A still with no character (empty matte, no region masks) still renders: city only, checks that need a mask report
   `null`, not a crash. Pinned in Task 7.
2. Masks of a different size than the still (hand-fixed at another resolution) are resized with nearest/area, not
   rejected. Pinned in Task 3.
3. Hair reaching the frame edge: `remap` must use `BORDER_REFLECT`, so no black wedge pulls in. Pinned in Task 3.
4. `--seconds` values whose frame count isn't divisible by small numbers (e.g. 7 s → 168 frames, 10.5 s): splash
   periods and cycle counts still divide the loop. Pinned in Task 4.
5. A blink scheduled near the loop end must not straddle the seam. Pinned in Task 5.

---

### Task 1: Matte (cut-out), with the ToonOut vs BiRefNet A/B

**Files:**
- Create: `tools/loop_still/__init__.py` (empty), `tools/loop_still/matte.py`, `tools/loop_still/MODELS.md`
- Modify: `pyproject.toml` (add `loops = ["onnxruntime", "torch", "sam2"]` to optional deps)
- Test: `tests/test_loop_matte.py`

**Interfaces:**
- Produces: `load_or_make_matte(still: Path, model: Path | None, redo: bool = False) -> np.ndarray` (float32 HxW
  0..1, still's size); `feather(matte, px=2) -> np.ndarray`; `decontaminate(img_bgr_f32, matte, ring_px=3) ->
  np.ndarray` (edge pixels' colour pulled toward the inner colour where the background was bright);
  `MATTE_SUFFIX = ".matte.png"`.

- [x] **Step 1: Tests** — `test_cached_matte_is_reused_and_never_overwritten` (write a fake matte file, call with a
  model path that doesn't exist: returns the cached one, file mtime unchanged); `test_redo_without_model_raises`;
  `test_feather_keeps_core_and_background` (core pixels stay 1.0, far background 0.0, edge strictly between);
  `test_decontaminate_only_touches_the_edge_ring` (pixels farther than `ring_px` from the edge unchanged exactly).
- [x] **Step 2:** Run `.venv/bin/python -m pytest tests/test_loop_matte.py -v` → FAIL (module missing).
- [x] **Step 3: Implement.** Model inference via onnxruntime, 1024×1024 input, ImageNet mean/std, sigmoid output
  resized back (BiRefNet's ONNX contract, as rembg uses it). Saved matte is 8-bit PNG.
- [x] **Step 4:** Tests pass.
- [x] **Step 5: A/B (manual, recorded).** Download BiRefNet-general ONNX and ToonOut weights (export ToonOut to
  ONNX if only a checkpoint ships; give up after one hour and record why). Run both on 3 stills
  (`design-data/scenes/rin-kageyama--alley.png` plus two other night scenes with hair against neon). Save edge crops
  side by side to `design-data/loops/_matte-ab/`. Default model = the one with fewer halo/hole errors by eye; write
  the choice, licences and URLs in `MODELS.md`.
- [x] **Step 6: Commit** `Loop still: matte with cache, feather and edge decontamination (+ model A/B notes)`.

### Task 2: Periodic building blocks

**Files:** Create `tools/loop_still/periodic.py`; Test `tests/test_loop_periodic.py`

**Interfaces:**
- Produces: `pick_cycles(hz: float, seconds: float, taken: set[int]) -> int` (nearest count ≥ 1 to `hz*seconds`
  sharing no factor > 1 with any in `taken`; adds it to `taken`); `divisors_between(n: int, lo: int, hi: int) ->
  list[int]`; `tile_noise(h, w, cell, rng) -> np.ndarray` (wrap-around smooth noise, 0..1).

- [x] **Step 1: Tests** — `test_pick_cycles_shares_no_factor` (`taken={4}`, `pick_cycles(0.3, 20, taken)` → 5 or 7,
  not 6); `test_pick_cycles_never_zero` (`pick_cycles(0.01, 10, set()) == 1`); `test_tile_noise_wraps` (left column
  ≈ continuation of right column: `abs(n[:,0]-n[:,-1]).max()` below the median neighbour step × 2).
- [x] **Step 2–4:** fail, implement, pass.
- [x] **Step 5: Commit** `Loop still: periodic helpers (coprime cycle counts, wrapping noise)`.

### Task 3: Character motion (hair, coat, breathing)

**Files:** Create `tools/loop_still/motion.py`, `tools/loop_still/regions.py`; Test `tests/test_loop_motion.py`

**Interfaces:**
- Consumes: `pick_cycles` (Task 2).
- Produces:
  - `Motion(regions: dict[str, np.ndarray], face: np.ndarray, size: tuple[int, int], frames: int, seconds: float,
    wind: tuple[float, float], seed: int, taken: set[int], amp=0.015, hz=0.3, breath=0.004)` with
    `.field(i) -> tuple[np.ndarray, np.ndarray]` (dx, dy in pixels) and `.warp(img, i) -> np.ndarray`.
  - `weights(region, root) -> np.ndarray`: 0 at the root, 1 at the farthest tip (`cv2.distanceTransform` from the
    root pixels, normalised, then `** 1.5`).
  - `stretch(dx, dy) -> tuple[float, float]`: min and max Jacobian determinant of `(x+dx, y+dy)`.
  - `regions.py`: CLI `python -m tools.loop_still.regions STILL --hair X,Y[;X,Y] --coat X,Y --face X,Y` (fractions of
    width/height) running SAM 2.1 hiera-tiny on CPU, writing `<still>.hair.png`, `.coat.png`, `.face.png`; hair
    and coat have the face subtracted and are clipped to the matte. Pure `clean_regions(hair, coat, face, matte)`
    holds that logic, for tests.

Roots: hair root = hair pixels within 6 px of the dilated face mask; coat root = the top 8% rows of the coat mask.
Displacement = `w(x) * amp * H * Σ a_k sin(2π(c_k i/N − 0.25 w(x)) + θ_k)` along the wind direction (unit vector of
the rain slant), plus 30% of that across it; 2 terms for hair, 2 for coat, cycle counts from `pick_cycles`, weights
`a = (0.7, 0.3)`. Breathing: vertical displacement of the coat region, `breath * coat_height * w_breath(y) *
sin(2π c_b i/N)` where `w_breath` is 0 at the matte's bottom row and 1 at the coat root (shoulders). The face mask,
dilated by 2 px, is forced to 0 displacement and the field is smoothed (Gaussian, σ = 3 px) before clamping it there
again. `warp` uses `cv2.remap(..., INTER_LINEAR, borderMode=BORDER_REFLECT)`.

- [x] **Step 1: Tests** — `test_field_at_frame_0_equals_frame_N` (`field(0) == field(N)` to 1e-6);
  `test_roots_and_face_move_zero` (exactly 0 on face pixels and root pixels, every 10th frame);
  `test_tips_move_most` (max |d| on tip pixels ≥ 0.9 × `amp*H`·Σa over the loop, root pixels 0);
  `test_stretch_stays_in_bounds` (synthetic blob hair, default amp: 0.9 ≤ min, max ≤ 1.1);
  `test_masks_of_another_size_are_resized` (Review Focus 2); `test_hair_at_frame_edge_reflects_not_black` (Review
  Focus 3: a hair region touching x=0; warped frame has no new pixel darker than the input's minimum);
  `test_clean_regions_subtracts_face_and_clips_to_matte`; `test_no_regions_is_identity` (`warp(img, i) is` equal to
  img).
- [x] **Step 2–4:** fail, implement, pass.
- [x] **Step 5: Commit** `Loop still: hair, coat and breathing motion with roots and face held still`.

### Task 4: City layers (rain, splashes, fog)

**Files:** Create `tools/loop_still/layers.py`; Test `tests/test_loop_layers.py`

**Interfaces:**
- Consumes: `pick_cycles`, `divisors_between`, `tile_noise` (Task 2).
- Produces: `RAIN = {"none": 0, "drizzle": 250, "steady": 600, "heavy": 1200}` (drops per 1920 px width);
  `Rain(size, frames, preset, seed, slant=0.12, near=False)` with `.layer(i) -> np.ndarray` (float HxW 0..1 alpha)
  and `.slant`; `Splashes(size, frames, ground: float, seed, count)` with `.layer(i)`; `Fog(size, frames, seed,
  taken)` with `.layer(i)`.

Far rain: the preset count, 5–9 screen heights per loop per drop (from the spike: `ys = (y0 + laps*(h+40)*t) %
(h+40) - 20`), 1 px, alpha 0.10–0.22. Near rain: 12% of the count, 10–14 laps, 2 px, longer (30–60 px), alpha
0.25–0.4. Splashes: sites in the band from `ground` (fraction of height, default 0.8) to the bottom, outside the
matte core; each site's period is a divisor of N between 6 and 48 frames; a splash is a small ellipse ring drawn
over 3 frames (growing, then fading) at a site position that changes each occurrence (from the seed and occurrence
index modulo the occurrences per loop). Fog: `tile_noise` scrolled by exactly 1 tile width per loop, alpha ≤ 0.08.

- [x] **Step 1: Tests** — `test_rain_frame_0_equals_frame_N` for far and near; `test_splash_periods_divide_N` for N in
  (480, 168, 252) (Review Focus 4); `test_splash_lasts_three_frames`; `test_fog_frame_0_equals_frame_N`;
  `test_rain_none_is_empty`; `test_same_seed_same_layers`.
- [x] **Step 2–4:** fail, implement, pass.
- [x] **Step 5: Commit** `Loop still: periodic rain (far and near), splashes and fog`.

### Task 5: Blinks

**Files:** Create `tools/loop_still/blink.py`; Test `tests/test_loop_blink.py`

**Interfaces:**
- Produces: `schedule(frames: int, fps: int, seed: int) -> list[tuple[int, list[str]]]` (start frame, per-frame
  patch names); `Blinks(half: np.ndarray, closed: np.ndarray, frames, fps, seed)` (RGBA patches the still's size)
  with `.apply(img, i) -> np.ndarray` and `.mask` (union of the patches' alpha, which the face check exempts);
  `load_blinks(still: Path, size, frames, fps, seed) -> Blinks | None` (None unless both patch files exist).

Shapes (24 fps, Bloop Animation): regular `["half","closed","closed","half","half"]`, fast
`["half","closed","half","half"]`, slow `["half","half","closed","closed","half","half","half"]`; 1 in 5 blinks is
fast or slow, 1 in 6 is followed 6 frames later by a second regular blink. Gaps uniform 3–8 s. No blink starts in the
first 0.5 s, and none may end later than 0.5 s before the loop end. Times scale with `fps`.

- [x] **Step 1: Tests** — `test_gaps_are_uneven_and_3_to_8_s` (over seeds 1–20: every gap within 3–8 s plus the double
  blink's 6 frames; not all gaps equal); `test_no_blink_straddles_the_seam` (Review Focus 5, seeds 1–50, N=480 and
  N=168); `test_apply_changes_only_patch_pixels`; `test_load_blinks_needs_both_patches`.
- [x] **Step 2–4:** fail, implement, pass.
- [x] **Step 5: Commit** `Loop still: subtle blinks from drawn eye patches on an uneven schedule`.

### Task 6: Checks

**Files:** Create `tools/loop_still/checks.py`; Test `tests/test_loop_checks.py`

**Interfaces:**
- Produces: `Checks(still_f32, face, matte, frames)` fed frame by frame: `.character(i, char_img)` (the composited
  character before front layers), `.back(i, back_img)` (back layers + character, before front layers), `.final(i,
  small_gray)`; `.stretch(lo, hi)` per frame; `.result() -> dict` with keys `face_max_diff`, `stretch_min`,
  `stretch_max`, `seam_ratio`, `halo_ratio`, `repeat_score`, `passed` (bool), `failed` (list of names).

Definitions: face = max abs difference on face pixels minus the blink mask (must be 0). Seam = step(N−1→0) /
median step(i→i+1) on 160 px-wide grayscale finals (≤ 1.25). Halo = mean over the loop of the 3 px ring just
outside the matte in `back` frames, divided by the same ring in the still (within 0.96–1.04). Repeat:
`D(k)` = mean over i of mean |f(i) − f((i+k) mod N)| on the small finals; `repeat_score` = min over k in
[fps, N−fps] of D(k) / median step (≥ 1.0: no shorter lag looks more alike than neighbouring frames). Checks that
need a mask return `None` and are skipped when the mask is empty.

- [x] **Step 1: Tests** — `test_planted_seam_fails` (a jump between the last and first frame); `test_changed_face_pixel_fails`;
  `test_blink_pixels_are_exempt`; `test_halo_fails_on_a_bright_ring`; `test_hidden_half_loop_fails_repeat`
  (sequence whose second half copies the first); `test_clean_periodic_sequence_passes`; `test_empty_matte_gives_none_not_crash`.
- [x] **Step 2–4:** fail, implement, pass.
- [x] **Step 5: Commit** `Loop still: face, stretch, seam, halo and repeat checks`.

### Task 7: Render and CLI

**Files:** Create `tools/loop_still/__main__.py`, `tools/loop_still/render.py`; Test `tests/test_loop_render.py`

**Interfaces:**
- Consumes: everything above; `tools.lights.Lights` (pass the feathered matte as `exclude`, its `frame(i)` as the
  back plate) and `tools.lights.cover`; `tools.shorts.remote.h264_encoder`.
- Produces: `render(opts: Options) -> Path` (the output dir); `Options` dataclass mirroring the CLI; CLI
  `python -m tools.loop_still STILL [--seconds 20] [--fps 24] [--size 1920x1338] [--rain none|drizzle|steady|heavy]
  [--no-near-rain] [--lights] [--train ... --floor ... --passes ...] [--sweeps ...] [--sign-blink POLY] [--fog]
  [--ground 0.8] [--motion hair,coat,breath | --still-character] [--blink] [--edge-tint] [--plate lama|telea]
  [--matte-model PATH] [--redo-matte] [--seed 1] [--preset NAME] [--out DIR] [--frames-only K]`.
  (`--sign-blink` is `Lights`' sign blink, renamed so `--blink` means eyes.)

Per frame: `back = lights.frame(i)` (or the still) `+ far rain + fog` (rain and fog scaled by `1 − matte`); the
character = the plate (the still with the moving regions' band, dilated by the max displacement, inpainted once with
LaMa ONNX, or `cv2.inpaint` Telea when `--plate telea` / no LaMa model) with the warped regions over it, then blink
patches; composite `char` over `back` with the warped feathered matte; optional edge tint (the 3 px rim inside the
matte gets 0.35 × the blurred light change `lights.frame(i) − still` there); then splashes and near rain over
everything. Output to `design-data/loops/<stem>/<preset>/` (preset = `--preset` or `rain-<rain>`): `master.mkv`
(FFV1, `-g N`), `loop.mp4` (H.264, `-g N`, yuv420p), `preview3x.mp4` (`-stream_loop 2` of loop.mp4), `poster.jpg`
(frame 0), `meta.json` (all options, seed, matte model, cycle counts, check results, seconds taken). The process exits
1 when a check fails, after writing everything. `--frames-only K` renders K frames to PNG for quick looks.

- [x] **Step 1: Tests** (small: 160×112, 2 s, 12 fps, `--plate telea`, synthetic still and masks in `tmp_path`) —
  `test_render_writes_all_outputs_and_ffprobe_reads_them`; `test_still_character_holds_the_whole_matte_core`;
  `test_no_character_still_renders` (Review Focus 1); `test_same_args_same_frames` (frame hashes equal over two
  runs); `test_meta_has_check_results_and_cycles`; `test_blink_flag_without_patches_warns_and_continues`.
- [x] **Step 2–4:** fail, implement, pass. Full suite: `.venv/bin/python -m pytest tests/ -q` all pass.
- [x] **Step 5: Commit** `Loop still: render, outputs and CLI`.

### Task 8: End to end, review page, docs

**Files:** Modify `docs/image-generation-guide.md` (a short "Loops" section); data under `design-data/loops/`.

- [x] **Step 1:** Make region masks for the 3 A/B stills (`python -m tools.loop_still.regions ...`), check them by eye
  at full size, hand-fix if needed.
- [x] **Step 2:** Render 3 stills × 2 presets (`--rain steady --lights --fog`, and `--rain heavy --lights
  --edge-tint`). All checks pass; `ffprobe` reads every output; note render times in `meta.json`.
- [x] **Step 3:** Watch each loop 3× back to back at full size and on a 390 px-wide view (the researcher's "watch
  several cycles" rule). Note anything that repeats visibly or looks rubbery; fix the defaults and re-render.
- [x] **Step 4:** Grow the spike page into the "Loops" artifact (same URL as the spike, A8SCvcVTFHhiE45fvm9Yia): the
  clips side by side, the check numbers, the matte A/B crops. Add one inbox card per preset for verdicts.
- [x] **Step 5: Commit and push** `Loop still: first loops, guide section`.
