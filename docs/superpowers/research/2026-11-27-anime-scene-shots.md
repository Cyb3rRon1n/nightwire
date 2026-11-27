# Anime scene shots of a character doing something (researcher, 2026-11-27)

The owner's verdict on card `loops-idle` (fix) was that the CPU warp idle "looks very wavy, not realistic". They asked
for this instead: "make it like a anime scene shot … them naturally standing in an area doing something like leaning
against a wall, smoking a cigarette, or lounging around". They also said to forget the old rules and research freely.

## Findings

- **Why the warp reads as wavy.** This is reasoning, not a source. Anime idle cuts are held drawings with one motivated
  action that eases in and out: a smoke exhale, an ash flick, a hair gust. Between actions the figure is nearly still.
  Continuous sub-pixel motion over the whole body at 24 fps looks like a liquid filter.
- **Smoke is effects animation.** It is drawn frame by frame, separately from the body. So smoke and steam can be the
  main moving element. Sources: Tuts+, and Martinelli's class on Skillshare (both snippets).
- **Game idles.** Small motions are layered and never move in lockstep (Animschool, a snippet). That is a game source,
  not anime.
- **What people use now.** The common pipeline is a still, then an image-to-video model with a loop prompt or a set last
  frame, then an MP4. Wallpaper Animator on Steam uses Seedance on fal; a Patreon creator and an n8n template follow
  the same pattern. All three are snippets.
- **No independent comparison** of these models on anime smoking or idle shots was found. The paid test below is the
  evidence.

## Models (fal prices from opened pages; [S] = snippet or vendor claim)

| Model | Loop (end frame) | Resolution | Price |
|---|---|---|---|
| Seedance 2.5 | yes | 480p, 720p, 1080p; 4–30 s | about $0.22/s at 480p; $0.473/s at 720p |
| Seedance 2.0 | yes | 720p, 1080p | $0.302/s at 720p |
| Seedance 2.0 Fast | yes | 480p, 720p | $0.242/s at 720p |
| Kling 3 Pro | yes | from the start image | $0.112/s with audio off |
| Hailuo 2.3 Standard | not checked | 768p | about $0.28 per 6 s clip [S] |
| Wan 2.2 A14B, on fal | yes | up to 720p, 16 fps | about $0.08/s at 720p (recheck before use) |
| Wan 2.2, local | yes | 480–720p | free; an 8 s loop takes about 5 min on a 4070 [S] |
| AniSora V3, local | first and last frame [S] | 480p on 12 GB likely | free; V3 is about 82 GB at full size, and a "12 GB V3.1" build is said to exist (unverified) |

- fal showed a Black Friday banner on the Seedance pages ("up to 180 free Seedance 2.5 videos", running through
  December 1). The terms were not shown.

## Stills with a pose (needs the 4070)

- **NoobAI ControlNets on CivArchive.** All are eps models: depth, canny, lineart, softedge and others. There is no
  OpenPose, and no v-pred version. Our locked recipe is v-pred, so these must be tested before relying on them.
- **Other ControlNets to try.** xinsir ControlNet-Union (OpenPose plus depth; licence not opened) and
  `r3gm/controlnet-noobai-openpose-sdxl-fp16` (not opened).
- **Re-posing an approved still.** Qwen-Image-Edit-2511 can do this, using its GGUF build and a 4-step LoRA. Whether
  it fits in 12 GB is unconfirmed.
- **Stills we already have.** `saeko-kirigaya--hand-cup` (Saeko at a bar, a steaming bowl) is already a scene shot with
  an action.

## Recommendation

1. **Now: a paid test.** Make the character's action with a video model, and use our CPU tool only for the background
   and atmosphere (rain, neon, steam, a slow push-in). Three clips of 5 s each:
   - Seedance 2.0 Fast at 720p
   - Kling 3 Pro
   - Seedance 2.5 at 480p

   That comes to about $2.87, or about $5.70 with one retry each.
2. **On the 4070.** Make stills with a pose (a ControlNet or Qwen-Image-Edit), then motion with Wan 2.2 using a first
   = last frame loop, and AniSora V3 as the challenger. Seedance stays for final polish only.
3. **The body warp idle and the camera drift.** Turn them off by default. The code stays in place.

## Sources

- fal model pages (opened): Seedance 2.5, Seedance 2.0, Seedance 2.0 Fast, Kling 3 Pro, Wan 2.2 A14B (llms.txt).
- Hailuo 2.3 (snippet).
- [CivArchive NoobAI ControlNet](https://civarchive.com/models/929685/noobai-xl-controlnet) (opened).
- [Eugeoter noob depth](https://huggingface.co/Eugeoter/noob-sdxl-controlnet-depth) (opened).
- [Index-anisora](https://github.com/bilibili/Index-anisora) (snippet).
- [LTX-2.3](https://huggingface.co/Lightricks/LTX-2.3) (opened).
- [Qwen-Image-Edit-2511 GGUF](https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF) (snippet).
- [Animschool idle](https://blog.animschool.edu/2024/06/14/breathing-life-into-idle-animations) (snippet).
- [Wallpaper Animator](https://store.steampowered.com/app/4484970/Wallpaper_Animator) (snippet).
