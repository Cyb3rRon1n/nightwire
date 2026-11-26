# Layered loop: the city moves, and the character barely does

Status: draft for the owner (card `layered-loop`). Widened 2026-11-25: the owner said "do not need restrict to still
and background animation ... minimal animation, aesthetics, like hair wind", so the character gets small idle motion
too (section "Character motion"). There is still no lip-sync, and the face stays still until the owner decides. The owner liked the CPU spike (2026-11-25,
https://claude.ai/artifact/A8SCvcVTFHhiE45fvm9Yia) and asked for a real workflow, researched first. The idea came from a
clip the owner shared ("animation with Claude, no video-generation AI": a background layer and character layers put
together in code). We take the layers and leave out its mouth-swap lip-sync (owner rule: no face animation).

## Why

The shorts goal is local stills with looping background motion, and Seedance only for final polish
(`nightwire_local_video_goal`). Video models (Wan 2.2, AniSora, LTX) need the 4U box and still change the character.
A layered loop runs on the CPU, costs nothing, and keeps the character exactly as approved, pixel for pixel. It
becomes the first step for background loops; a video model is used only for shots this can't do.

## Prior art (researcher 2026-11-25; checked = page opened)

- **Rain in front and behind** (Adobe, "Add rain to video", checked). One rain layer sits in front. A duplicate,
  masked around the subject, sits behind, with the mask feathered. Lesson: two rain layers, and the back one
  masked by the character.
- **Rain depth and cycles** (Clip Studio tip 7699, checked, a general frame-by-frame tutorial). Three frames are
  enough for drawn rain. The layers behind are thinner, smaller and fainter. Splashes are redrawn over about 3
  frames. Lesson: far rain is thin and faint, near rain is sparse and longer, and splashes run on a short cycle.
- **Anime matting: ToonOut** (Muratori and Seytre, arXiv 2509.06839, checked; weights MIT, dataset CC-BY 4.0). A
  BiRefNet fine-tune on 1,228 anime images. Pixel accuracy rose from 95.3% to 99.5%, on the authors' own test set.
  Lesson: likely better hair edges than plain BiRefNet. We A/B it on our stills, not on their numbers.
- **Cinemagraph loops** (Adobe, Vamp, the ffmpeg xfade wiki; snippets only, unverified). One or a few things
  move and the rest is locked. A loop can repeat or bounce, and a crossfade hides a seam. Our own choice is
  stronger: every effect is periodic in the loop length, so the last frame leads into the first by construction
  and nothing needs a crossfade.
- **Moving the camera from one still** (Shih et al., "3D Photography using Context-aware Layered Depth
  Inpainting", CVPR 2020, checked). Warping by depth opens holes behind the subject that must be filled. LaMa
  inpainting is Apache-2.0 (repo LICENSE, checked). Depth Anything V2 Small is Apache-2.0, but Base, Large and
  Giant are CC-BY-NC-4.0 (repo README, checked), so only Small is usable. Both are kept for later (see Not doing).
- **The shared clip's own post** could not be found. Pages about "Claude writes the animation code, ffmpeg
  encodes" match the approach, but they are not the source.

## Prior art for character motion (researcher 2026-11-25, second pass; checked = page opened)

- **Animation principles** (Wikipedia, "Twelve basic principles of animation", checked). In follow-through and
  overlapping action, loose parts keep moving and move at different rates. Secondary action supports the main
  action and is cut if it distracts. Lesson: hair tips lag their roots, and there are two or three rates per region.
- **Rigging tools.** Live2D Cubism (comparison and download pages, checked): the FREE edition has 50 deformers and
  9×9 warps, commercial use is free below 10M yen of sales a year, and it runs on Windows and macOS only. Inochi2D
  and Inochi Creator (GitHub, checked) are BSD-2 and open source, but Creator is still pre-1.0. Both need hours of
  hand rigging per character. Lesson: they are a benchmark, not the default.
- **See-through** (shitagaki-lab, GitHub, checked, Apache-2.0). It splits one illustration into up to 23 layers
  (hair, face, clothes and so on) and fills in what each covers, as a PSD. It needs about 12–16 GB of VRAM (about
  10 GB with offload). It does not rig anything. Lesson: on the 4070 it solves the "what is behind moving hair"
  problem.
- **Video and cinemagraph models.** Text2Cinemagraph (MIT) and Eulerian Motion Fields (Holynski et al. 2021,
  project page) target water and smoke, not hair. LivePortrait (checked) animates faces only. Wan 2.2 (checked,
  Apache-2.0) lists 24 GB or more for its 5B model; a 12 GB GGUF fit is only a snippet. No masked, hair-only Wan
  2.2 5B workflow was found. Lesson: generated pixels drift off-model, which is why video was rejected for faces. A
  hair-only paste-back on the 4070 is an experiment, not the plan.
- **Hair and clothes masks.** anime-seg (PyPI, hair, clothes and face classes) was seen in snippets only, and its
  licence is unchecked. SAM 2 with point prompts is the checked alternative.

## Design

`python -m tools.loop_still STILL [--seconds 10] [--size 1920x1338] [--rain none|drizzle|steady|heavy]
[--lights] [--train ... --passes ...] [--sweeps ...] [--fog] [--out DIR]`

1. **Matte.** The character's cut-out is made once and saved beside the still as `<still>.matte.png`. It is
   reused, and it can be fixed by hand. The model is ToonOut (ONNX, via onnxruntime) or BiRefNet, whichever wins
   the A/B on 3 of our stills (Task 1). The edge is feathered by 2 px. Bright neon behind hair is pulled back
   (edge colour decontamination), so no halo shows when rain passes behind.
2. **Back layers,** all masked by the matte:
   - `tools/lights.py` breathing and flicker, with an optional train and headlight sweeps. It already exists and
     loops; the matte replaces its hand-drawn `--exclude`.
   - Far rain: thin, faint and slow, over the whole frame.
   - Optional fog drift: a periodic noise field that scrolls a whole tile per loop.
3. **The character,** from the original still's pixels. The face is never moved. The other parts move only as set
   out in "Character motion" below; with `--still-character` she stays exactly as approved.
4. **Front layers:**
   - Street splashes on the ground area behind and around the feet, each on a 3-frame cycle at a random phase.
   - Near rain: sparse, longer and brighter streaks across the whole frame, including in front of her.
5. **Loop rule:** every effect is a function of `i / N` with whole cycles per loop. Particles wrap by modulo on a
   travel of whole screen heights, and the noise is tiled. The lossless check (below) is the proof.
6. **Output:** a lossless master (FFV1 `.mkv`), an H.264 `.mp4` for viewing, a 3× looped preview and a poster
   frame, written to `design-data/loops/<still-stem>/<preset>/` with a `meta.json` (options, seed, matte model,
   check numbers).

### Character motion (`--motion hair,coat[,breath]`)

The approach is procedural and needs no model. Every pixel is still the approved art, only displaced a little:

- **Regions.** Hair and coat masks are made once with SAM 2 point prompts (or anime-seg if its licence checks
  out) and saved beside the still as `<still>.hair.png` and `<still>.coat.png`, so they can be fixed by hand.
  The face mask comes from the same step and is a hard "never move" area.
- **Roots stay put.** Each region's weight grows with distance from its attachment: the scalp edge next to the
  face for hair, the shoulder line for a coat. Roots move 0 and tips move most.
- **Wind.** A smooth displacement field, the sum of 2–3 sines with whole cycles per loop and a phase delayed from
  root to tip, so tips lag (follow-through). It is applied with OpenCV `remap`. Starting values (our call, not
  sourced): tips at 1–2% of image height, 0.2–0.5 Hz. The wind blows the same way as the rain slant.
- **Breathing** (optional): 0.3–0.5% scale on chest and shoulders at about 0.25 Hz.
- **What shows behind moving hair.** Where a strand moves off the background, the pixels behind it would still be
  hair. Phase 1 fills a thin band behind each region's edge with LaMa (Apache-2.0, runs on CPU) and keeps
  amplitudes small. Phase 2 uses See-through's filled layers on the 4070.
- **Benchmark.** One character is rigged by hand in Inochi Creator, once, to compare the look and the hours.

### Checks (run on the lossless master, saved in meta.json)

- **Face frozen:** the face mask differs from the still by exactly 0, apart from rain drawn in front. With
  `--still-character`, the whole matte core is held to the same rule.
- **No rubber:** the displacement field's local stretch (its Jacobian determinant) stays between 0.9 and 1.1, so
  line art never visibly shears.
- **Seam:** the step from the last frame to the first is at most 1.25× the median step between neighbouring frames.
- **Halo:** the mean brightness of a 3 px ring outside the matte, against the same ring in the still, stays within
  4%. This catches leaks at the edge.

### Review

Each run adds its clips to one "Loops" artifact page (the spike page grows into it), with videos side by side
and the check numbers. Verdicts go on Nightwire Reviews inbox cards, as with every review. Liked presets become
the defaults.

## Not doing (yet)

- **Parallax camera drift.** It needs an empty background behind the character (LaMa inpainting, or a plate
  rendered on the 4U box), plus Depth Anything V2 Small. This is phase 2, after the owner likes phase 1.
- **Lip-sync** (owner rule). Face motion such as blinks waits for the owner's answer.
- **Hair-only video generation** (Wan 2.2 5B with the hair pasted back): an experiment for the 4070, after phase 1.
- **Video models.** Wan, AniSora, LTX and Seedance stay in the 4U loop plan as the fallback.

## Testing

- Unit tests: the displacement at frame 0 equals frame N; roots and the face move 0; stretch stays within bounds;
  periodic particles land in the same place at frame 0 and frame N; the matte cache is reused and
  never overwritten; a still with no character (empty matte) still renders; option parsing; the three checks
  catch a planted seam, a changed character pixel and a halo.
- End to end: 3 stills × 2 presets. The checks pass, and ffprobe reads the outputs. The owner reviews them on the
  Loops page.

## Owner questions

1. **Near rain in front of the character:** OK? It falls across her but never changes her. My pick is yes. Adobe
   and Clip Studio both layer rain in front, and without it she looks pasted on.
2. **Light on her:** let the neon's breathing tint her a little (a faint glow on her edge that pulses with the
   sign)? Research flags a still figure under moving light as the main "pasted on" risk. Now that she may move a
   little, my pick is yes, as a faint option you judge on the first clips.
3. **Length:** 10 s loops by default, or longer for the shorts?
4. **Face:** completely still, or are small things like blinks OK? My pick is still for now; blinks would need
   drawn closed-eye frames (from the expression renders), not warping.
5. **Breathing:** include it by default, or hair and coat only?
