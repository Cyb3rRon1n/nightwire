# Natural-looking loops from one anime still (researcher, 2026-11-27)

Asked by the owner on card `loops-realism` (verdict fix, 2026-11-27): "instead of staying with what rules we made, can i
see what animation can be done to make it look more natural? open research ideas or see what is popular."
"Checked" sources were opened by the researcher; "snippet" ones were seen only in search results.

## Top 3 by hardware

- **Now (CPU):** layered idle on the cut-out with spring physics; depth parallax drift; drawn-patch blinks plus gaze
  micro-saccades.
- **4070:** See-through layers plus mesh deform (and its depth for parallax); Wan 2.2 TI2V-5B/A14B GGUF loop as a motion
  reference with the face composited back; normal-map relighting.
- **Paid only:** Seedance-class I2V with first = last frame as a motion reference, face pasted back.

## Ranked ideas

1. **Layered idle on the cut-out: breath wave, weight shift, head sway, spring-physics hair and coat.** Breath travels
   as a wave belly → chest → shoulders → head with offset timing; soft parts follow through and settle (a "moving
   hold"); Live2D stacks deformers at different breath phases so nothing moves in lockstep; too many small motions hurt
   readability. Replace our sine hair warp with a damped spring/Verlet chain driven by body motion, made periodic by
   solving several cycles. Piecewise-affine or thin-plate warp of matte regions: torso rise, shoulder offset, head
   rotation 0.3–0.8° about the neck, a hip weight shift every 6–10 s. Face moves only rigidly (no new pixels); fill
   disocclusion from the plate. Wallpaper Engine's Shake effect (painted flow map + speed/strength/friction) is the same
   idea. Ours, CPU, no download, low risk, 1–2 days.
2. **Depth-based 2.5D camera drift.** Slow Lissajous drift of ~1–2% gives depth cues no 2D layer gives; the standard
   living-wallpaper move. Numpy warp by `depth * offset(t)` with periodic offset, disocclusions from the plate.
   Depth Anything V2 Small (Apache-2.0, ~25M params, runs once on CPU; Base/Large are CC-BY-NC-4.0). DepthFlow
   (AGPL-3.0, claims seamless loops, needs OpenGL — iGPU unconfirmed). Depth Pro: licence not named on its page. Low risk;
   keep drift under ~1.5% and cap her own parallax. 0.5–1 day.
3. **See-through layer split + mesh deformation** (arXiv 2602.03749, Feb 2026; checked). Splits one anime illustration
   into up to 23 inpainted semantic layers (hair, face, eyes, clothes…) with draw order and pseudo-depth, as a PSD;
   trained on Live2D models. Gives eyes/brows as separate layers (blinks without hand patches), hidden hair behind the
   neck, filled holes for larger motion. StretchyStudio (MIT) imports the PSD with auto-skeleton and Spine export; no
   video export seen. Repo Apache-2.0; weights' licences (three HF repos) not confirmed. 4070: 12–16 GB bf16, ~10 GB
   offload, ~8 GB NF4, once per image. Medium risk (inpainted pixels; always composite the original face). Authors call
   output a draft; untested on neon/rain plates. 1–2 days to test, a few more for a layer-mesh render path.
4. **Blinks and gaze micro-saccades.** Irregular blinks (fast close ~3 frames, slower open), 1–3 px gaze shifts with
   occasional larger glances (inference from practice, not one source). Our blink pipeline exists; patches are the
   blocker (SDXL inpaint on the 4070, or See-through eye layers). 0.5 day once patches exist.
5. **Relighting so neon colour moves across her.** Cheap: light-pulse masks multiplied/screened onto her matte with a hue
   per light (CPU, 0.5 day). Better: normals from depth or StableNormal (Apache-2.0) with a Lambert term per light
   (1–2 days). IC-Light (Apache-2.0, SD1.5) redraws pixels — not advised.
6. **Rain on her: wet sheen and drips.** Specular glints on shoulders/coat pulsing with passing light; slow drips off hair
   tips and sleeves; slight refraction as on the street. Ours, CPU, low risk off the face, 0.5–1 day.
7. **Wan 2.2 loop (first = last frame) as motion reference.** Apache-2.0. TI2V-5B: 24 GB at 720p per repo; community
   GGUF + 4-step LightX2V LoRA reports an 8 s loop in ~5 min on a 4070 12 GB (snippet). Colour burn-in at the loop
   point reported. Redraws her: use only as an optical-flow field applied to our layers, or paste her face back.
   1–3 days.
8. **FramePack** (Apache-2.0, ≥6 GB VRAM, RTX 30/40/50). Forward-only, no looping; would need cross-fade or Video
   Textures matching. Same redraw risk. 1 day to test.
9. **ToonCrafter** (Apache-2.0, 512×320 interpolation). Poor fit: low resolution, solves in-betweening not idle. Skip.
10. **Paid I2V (Seedance, Kling-class).** Best motion, but redraws and costs per clip; final polish or motion reference
    only.
11. **Live2D / Inochi2D by hand.** Gold standard but hours of rigging; See-through + StretchyStudio is the cheaper way in.

Also noted: Wallpaper Engine puppet warp uses a character cut-out and texture channels to swap eye states (snippet);
Animaze advises idles start and end neutral; community AI loops are mostly Wan 2.2 first/last-frame ComfyUI workflows.
LTX-2 weights are under separate community licences and ~66 GiB; not ranked. VTuber community and Kijai wrappers not
reviewed. Perception numbers are craft heuristics; tune by eye.

## Downloads (none fetched)

| Item | Size | Licence | For |
|---|---|---|---|
| Depth Anything V2 Small | ~25M params (~100 MB, not stated) | Apache-2.0 | 2 |
| See-through weights (3 HF repos) | not stated | repo Apache-2.0, weights unconfirmed | 3 (4070) |
| StretchyStudio | small | MIT | 3 |
| DepthFlow | pip | AGPL-3.0 | 2 (optional) |
| StableNormal | not stated | Apache-2.0 | 5 |
| Wan 2.2 GGUF | several GB | Apache-2.0 | 7 (4070) |
| FramePack | not stated | Apache-2.0 | 8 (4070) |

## Sources

Checked: [FramePack](https://github.com/lllyasviel/FramePack), [Depth-Anything-V2](https://github.com/DepthAnything/Depth-Anything-V2),
[Wan2.2](https://github.com/Wan-Video/Wan2.2), [See-through](https://github.com/shitagaki-lab/see-through),
[arXiv 2602.03749](https://arxiv.org/abs/2602.03749), [StretchyStudio](https://github.com/MangoLion/stretchystudio),
[Depth Pro](https://github.com/apple/ml-depth-pro), [ToonCrafter](https://github.com/Doubiiu/ToonCrafter),
[LTX-2](https://github.com/Lightricks/LTX-2), [DepthFlow](https://github.com/BrokenSource/DepthFlow),
[IC-Light](https://github.com/lllyasviel/IC-Light), [StableNormal](https://github.com/Stable-X/StableNormal).
Snippet only: [ComfyUI-See-through](https://github.com/jtydhr88/ComfyUI-See-through),
[Wallpaper Engine puppet warp](https://docs.wallpaperengine.io/en/scene/puppet-warp/introduction.html),
[Live2D HarmonicMotion](https://docs.live2d.com/en/cubism-sdk-manual/harmonicmotion/),
[Live2D auto sway](https://docs.live2d.com/en/cubism-editor-manual/auto-generation-of-sway-motion/),
[Follow through (Wikipedia)](https://en.wikipedia.org/wiki/Follow_through_and_overlapping_action),
[Wan 2.2 loops on a 4070](https://yanchen184.github.io/ai-lecturer-bob/blog/rtx-4070-wan22-i2v-loop),
[NextDiffusion Wan 2.2 loop tutorial](https://www.nextdiffusion.ai/tutorials/wan-2-2-looping-animations-in-comfyui).
