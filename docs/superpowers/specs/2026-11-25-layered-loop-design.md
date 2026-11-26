# Layered loop: the city moves, the character stays frozen

Status: draft for the owner (card `layered-loop`). The owner liked the CPU spike (2026-11-25,
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
3. **The character:** the original still's pixels inside the matte, unchanged.
4. **Front layers:**
   - Street splashes on the ground area behind and around the feet, each on a 3-frame cycle at a random phase.
   - Near rain: sparse, longer and brighter streaks across the whole frame, including in front of her.
5. **Loop rule:** every effect is a function of `i / N` with whole cycles per loop. Particles wrap by modulo on a
   travel of whole screen heights, and the noise is tiled. The lossless check (below) is the proof.
6. **Output:** a lossless master (FFV1 `.mkv`), an H.264 `.mp4` for viewing, a 3× looped preview and a poster
   frame, written to `design-data/loops/<still-stem>/<preset>/` with a `meta.json` (options, seed, matte model,
   check numbers).

### Checks (run on the lossless master, saved in meta.json)

- **Frozen:** with no front rain, the matte core (alpha 255, shrunk 3 px) differs from the still by exactly 0. With
  front rain, it differs only where a rain or splash pixel was drawn.
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
- **Lip-sync or any face or body motion** (owner rule).
- **Video models.** Wan, AniSora, LTX and Seedance stay in the 4U loop plan as the fallback.

## Testing

- Unit tests: periodic particles land in the same place at frame 0 and frame N; the matte cache is reused and
  never overwritten; a still with no character (empty matte) still renders; option parsing; the three checks
  catch a planted seam, a changed character pixel and a halo.
- End to end: 3 stills × 2 presets. The checks pass, and ffprobe reads the outputs. The owner reviews them on the
  Loops page.

## Owner questions

1. **Near rain in front of the character:** OK? It falls across her but never changes her. My pick is yes. Adobe
   and Clip Studio both layer rain in front, and without it she looks pasted on.
2. **Light on her:** let the neon's breathing tint her a little (a faint glow on her edge that pulses with the
   sign)? Research flags a frozen figure under moving light as the main "pasted on" risk, but this bends "perfectly
   frozen". My pick is no for now; try it as an option later.
3. **Length:** 10 s loops by default, or longer for the shorts?
