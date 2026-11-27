# Loop idle, camera drift and wet light — design

Status: approved 2026-11-27. The owner's verdict on card `loops-natural` was "yes, yes, yes" to all three questions:
- build ideas 1–3 on the CPU, with the face rule relaxed;
- download Depth Anything V2 Small;
- queue See-through and Wan 2.2 for the 4070.

## Why

On `loops-realism` the owner said the realism pass was "better". They then asked to go beyond our own rules for a
more natural look (research: `docs/superpowers/research/2026-11-27-natural-loop-animation.md`). The city moves but
she stands frozen, apart from a little hair and coat. That stillness is now the main thing that reads as fake.

## Rule change

Old rule: "the face never changes". New rule: **her face moves only as a whole**. Whole means a rigid shift and
rotation, with no pixel redrawn. Light may fall on the face at half strength. Lip-sync is still out. Blinks still wait
for drawn eye patches, which come on the 4U box.

## Goals (all on by default, all periodic, CPU only)

1. **Idle** (`--idle`). This is a body field: one displacement field over her whole cut-out. It is drawn as its own
   layer under the coat and hair layers, and those layers add their own wind fields on top. The field has three
   parts, all measured against her figure height Hf:
   - **Breath**: a rise of 0.25% Hf at about 0.25 Hz. It starts at the hips and grows to full at the shoulder line,
     and the head rides on it. The wave travels upward: the shoulders lag the belly by 0.12 of a cycle.
   - **Weight shift**: a sideways sway of 0.4% Hf at about 0.07 Hz, so about one cycle per 20 s loop. The feet stay
     planted. The sway eases in from the feet to the hips, and everything above the hips moves as one.
   - **Head sway**: a rotation about the neck point (the bottom centre of the face). It has two terms, 0.5° at about
     0.15 Hz and 0.25° at about 0.23 Hz. The rotation is full above the chin and eases out by the shoulder line. For
     hair, the rotation stays full over the whole hair mask, because hair hangs from the head.

   Every term takes a cycle count from `pick_cycles`, so no two parts share a beat. Over the face the field is
   affine with rotation only. Idle replaces the old coat-only breath term.

   **Springs**: hair and coat tips follow the body as damped springs. Each idle term on a tip gets the steady-state
   response of a damped oscillator:

   H = ω0² / (ω0² − ω² + 2iζω0ω)

   - hair: f0 = 0.9 Hz, ζ = 0.3
   - coat: f0 = 0.6 Hz, ζ = 0.4

   The tip gets the extra part (H − 1)·body, scaled by the tip weight, so roots get none of it. This is linear and
   uses the same cycle counts, so it stays exactly periodic. The tips trail and overshoot a little, which is the
   follow-through the research describes.
2. **Camera drift** (`--drift`).
   - **Depth**: Depth Anything V2 Small (Apache-2.0, 94.6 MB, `~/models/loop_still/depth-anything-v2-small`) runs
     once on the CPU, about 1 s. The disparity is saved beside the still as `<still>.depth.png` (16-bit), so it can be
     fixed by hand like the matte.
   - **Her area**: the disparity inside her matte is filled from around her, so the background behind her moves like
     the background. The disparity is then blurred by 0.4% of width, so depth edges stretch rather than tear.
   - **Focus**: the median disparity of her matte, so she and the street at her feet stay put. Everything else
     shifts by (disparity − focus) × offset(t). The offset is an x and y Lissajous of 0.7% and 0.3% of width, at about
     0.05 Hz and 0.08 Hz. Any shift is capped at 1.2% of width.
   - **What it moves**: it warps the city (lights, bloom and ripples) before the far rain. She is not warped, rain
     stays in screen space, and nothing touches the face.
   - **Without a character**: the focus is the median of the whole frame.
   - **Model missing**: drift is skipped, with a note.
3. **Wet light on her** (`--wet`).
   - **Light wash**: the change the lights make (city − plate, signed, blurred by 2% of width) is added over her
     current cut-out at 0.3, and at half that on the face. So the car's light and the neon's flicker cross her, not
     just her rim. This comes after the face check.
   - **Wet sheen**: her own highlights (luma minus its blur, which picks out the painted specular areas) brighten
     where light grows, tinted by the local light colour. The sheen covers her coat, hair and body, never the face,
     and moves with her.
   - **Drips**: about one every 2.5 s forms at the lowest tips of the hair and coat. A drip swells over 0.5 s, then
     falls under gravity until it reaches the ground line or 0.35 s has passed. Each is a small bead lit by the light
     map. The tip positions follow their layer's field. The schedule is wrapped, so the loop is periodic.

## Plate and checks

- **Plate**: the plate is filled in a band inside her matte edge, as wide as the largest idle move plus the drift
  near her plus 3 px. With idle on, the face is no longer excluded from the band, so the background shows behind a
  moved cheek.
- **`face_max_diff`**: her composited face core is compared with the still moved by the body field. It must be 0, so
  nothing else may draw on it.
- **`face_rigid`** (new): the worst gap, in px, between the body field over the face and its best-fit rigid
  transform, over all frames. It must be ≤ 0.05.
- **`stretch`**: now includes the body layer.
- **`halo`**: the ring just outside her is moved with her each frame.
- **`seam`, `repeat` and `ripples_on_her`**: unchanged.

## Non-goals

- See-through layers, Wan 2.2 and blinks. These are queued for the 4070. They are a later spec.
- No arm or hand motion. Arms are part of the body layer and only ride with the body; there is no separate rig.

## Approaches considered

- **A field-based idle on the existing cut-out** (chosen). It needs no download and reuses the layer and plate
  machinery.
- **A mesh or ARAP puppet.** It needs pins per still and gives little extra at these amplitudes.
- **Wan or See-through.** These need the 4070 and redraw pixels; they are queued instead.
- **DepthFlow for the drift.** It is AGPL and needs OpenGL; a numpy warp is a few lines.

## Left to the builder

Exact smoothing widths, the sheen gain and the drip size, tuned by eye on the three test stills. Costs are
measured against about +0.3 s per frame.
