# Loop realism pass — design

Status: draft 2026-11-26, awaiting the owner's picks (Nightwire Reviews card `loop-realism`).

## Why

The owner kept all six loops and picked preset B (heavy rain, breathing neon, edge glow) as the default
(verdicts `loops-a`, `loops-b`, 2026-11-26), then asked for "more improvements and immersive realism". The bar is
unchanged: like a live photo where you can't tell it repeats; the face never changes; CPU only, no cost.

## What the stills show

- Ayame's alley already has painted neon reflections on the wet street; Rin's cobbles read wet; Yuki stands on a
  dark floor under a glowing window. A second, mirrored reflection on top of a painted one would double it, so the
  wet-ground effect makes the painted street itself ripple. A mirror is only an option for dry-looking ground.
- `tools/lights.py` already has car-light sweeps (`--sweeps`) and a sign that blinks after them; both are opt-in
  and the sweep lights only the street, not her.

## Goals

Each part is a periodic layer (whole cycle counts, or an envelope that is zero at the seam) and passes every
existing check (face 0, stretch, seam ≤ 1.25, halo, repeat ≥ 1.0).

1. **Rippling wet street** (`--ripples`, on by default). Under the ground line and outside her matte, raindrops
   land as ring waves: h = A·sin(k·r − ω·age)·exp(−r/σ)·exp(−age/τ). Each drop's whole life fits inside the loop
   (start times wrapped so none straddles the seam), positions and start times from the seed, density from the rain
   preset. The street plate is resampled through the ripple field's gradient (6–15 px at the near edge, scaled down
   with distance toward the ground line), so painted reflections shimmer and break up. A faint lit ring is added
   where the local plate is bright (a ring under neon picks up the neon's colour; one in shadow stays dark).
   Ripples are drawn at half size and scaled up.
   Option `--mirror`: a faint, blurred, flipped copy of what is above the ground line (city and her, as composited
   that frame) for stills whose street is dry; off by default.
2. **Neon bloom and halation** (on by default). Bright, saturated pixels are blurred at three sizes (about 6, 24
   and 80 px at 1920 wide) and screen-added; the widest gets a faint warm cast. The bloom follows the neon's
   breathing. Kept modest, so it stays anime glow, not photoreal glare. It is drawn behind her, and never on the face.
3. **Rain lit by the lights** (on by default). Rain streaks and fog are multiplied by a light map (the blurred
   brightness and colour of the plate), so drops glint and take colour near neon and nearly vanish in dark gaps. The
   map breathes with the lights. The near rain in front of her uses the same map.
4. **A passing car, once a loop** (on by default, `--no-car` to skip). One headlight sweep placed mid-loop with its
   envelope at zero well before the seam (reuses `lights.py` sweeps). New: the sweep also brightens her rim on the
   side it passes (the existing edge-tint ring, never the face), and the sign blink after it stays optional. A single
   rare event breaks the sense of a steady rhythm without showing the seam.
5. **Film grain** (on by default, very light, about 1.5% of full scale). Fresh noise each frame, seeded by
   frame number so a render is reproducible. It is added last, over everything but the face, so the face stays
   exact.

## Non-goals and anti-goals

- No camera drift or 2.5D parallax: either would move the face, and parallax from a depth guess tears cel edges and
  the filled plate.
- No lens drops yet. A few large drops are the loudest "this repeats" tell; revisit after the owner sees 1–5.
- No full relighting of her: overlay light flattens cel shading. Only the rim ring gets the car sweep.
- No lip-sync, no body animation (standing rule 2026-11-26).

## Later (not this pass, listed for the card)

- Drops beading on her shoulders and hair as small highlights.
- Depth map from Depth Anything V2 Small (Apache-2.0, run once, cached) to thin and blur rain with distance.
- Steam from vents, only for stills that have a vent.

## Checks

The existing checks hold. One new check: `ripples_on_her = 0`, meaning the ripple and mirror layers change no
pixel inside her hard matte. Grain is applied after the face check frame, so `face_max_diff` stays 0. The repeat
check now sees the grain, so it is measured on frames before grain is added.

## Cost

Estimated, not measured (to be measured in the build): ripples 15–40 ms, bloom 30–60 ms, lit rain and grain under
20 ms per 1920×1338 frame. That's about +1.5 minutes per 20 s clip on top of the current 6–7.

## Prior art

- Puddle ripple normals over a wet mask, refracting the reflection:
  https://gist.github.com/eviltak/e04b83ffdb91aa3d477bbfe0ca370da7,
  https://godotshaders.com/shader/rain-puddles-with-ripples-and-reflection/,
  https://deepspacebanana.github.io/blog/shader/art/unreal%20engine/Rainy-Surface-Shader-Part-1
- Rain lit by the lights it falls through, and splashes and ripples in city scenes: Tatarchuk, "Artist-Directable
  Real-Time Rain Rendering in City Environments", SIGGRAPH 2006 course,
  https://advances.realtimerendering.com/s2006/Chapter3-Artist-Directable_Real-Time_Rain_Rendering_in_City_Environments.pdf
- Surface imperfections diffuse and distort reflections in rain composites:
  https://www.provideocoalition.com/making-it-rain-in-post-literally/
- Depth Anything V2 licences (Small is Apache-2.0; Base, Large and Giant are CC-BY-NC-4.0):
  https://huggingface.co/depth-anything/Depth-Anything-V2-Small, https://github.com/DepthAnything/Depth-Anything-V2
- Earlier loop design and its sources: `2026-11-25-layered-loop-design.md`.

## Left to the builder

Exact amplitudes, drop counts per preset, the bloom threshold, and the light-map blur size are tuned on the three
test stills; record the chosen values in the plan's ledger.
