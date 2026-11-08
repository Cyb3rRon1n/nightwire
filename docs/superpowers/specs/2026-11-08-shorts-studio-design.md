# Shorts studio — design (proposed Phase 23)

Date: 2026-11-08. Status: approved in brainstorming, awaiting owner review of this file.
Research: `docs/superpowers/research/2026-11-08-foyege-method.md` (reference creator's own tutorials,
transcribed) and `docs/superpowers/research/2026-11-08-ai-shorts-tools-and-hardware.md` (services, models, GPUs, prices).

## Goal

Make short cinematic videos (15–60 s) of Nightwire characters in the Kuroshio world, in the style of
the creator Foyege (弗曳哥): consistent characters, staged multi-character scenes, directed acting and
overlapping dialogue. Long-term this feeds the "daily life" shorts goal. Shorts are for promotion and
personal use (owner decision, 2026-11-08), so the NoobAI-XL designs stay the source of truth.

## Owner decisions (brainstorming, 2026-11-07/08)

1. Use: promotion / personal, not monetised. NoobAI-XL stays.
2. Hosting: start now on the laptop GPU box (192.168.10.19) plus cloud video services; move to the 4U
   box with a 24 GB card when it is built.
3. Blender: Claude builds grey-box scenes headless and the owner reviews in the browser; `.blend`
   files stay ordinary so the owner can open and edit them later from the desktop.
4. Pilot: a calm two-character scene, 15–30 s. Default cast and place: Saeko Kirigaya (C1) and
   Rin Kageyama (C2) at Mama Sato's izakaya (`mama-satos-izakaya`). The owner may swap cast or place
   before Phase 0 starts.
5. Architecture: a shorts studio inside this repo (`tools/shorts/`), reusing designs, ComfyUI/TTS code
   and the AI Lab review pages. AI Movie Studio 2 is prior art for ideas, not a dependency.

## Prior art (why it is shaped this way)

- Foyege's tutorials (transcribed, see research doc): Seedance 2.5 with layered prompts; fixed character
  IDs C1..Cn; top-down floor plan as the single source of positions; Blender grey-box with three figure
  tiers; one Blender timeline per scene exported in ≤30 s segments; per-second timecodes; 8-dimension
  acting blocks with FACS action units; overlapping dialogue with explicit timings; 3–5 s test first;
  fix only the failing layer; re-shoot only the failing segment.
- Evolink "Awesome-Blender-Seedance-Workflow-Usecases" (25+ community cases): grey-box video as
  reference works; detailed proxies leak a CG look; foot sliding and drift are the common failures.
- RunComfy "Blender to ComfyUI AI Renderer" and ComfyUI.org Wan depth guide: Blender depth/outline/pose
  passes drive Wan VACE locally; depth is more stable than pose.
- AI Movie Studio 2 (AGPL): script → 3D storyboard → frames → video → timeline. We copy the shape,
  not the code.
- musubi-tuner docs: Wan LoRA training needs 24 GB for video (12 GB for image-only).

## 1. Data layout

```
design-data/shorts/<short-slug>/          git-ignored, like all renders
  short.toml        title, logline, beat sheet, cast map C1..Cn -> design slugs, place slug,
                    budget_usd (default 25), style notes
  floorplan.png     top-down plan rendered from scene.blend, C1..Cn labelled
  scene.blend       one Blender file, one timeline for the whole short
  shots/S01/
    shot.toml       start/end seconds, camera, figure tier, prompt layers L1-L5, acting blocks, dialogue
    greybox.mp4     grey-box render of this shot
    depth.mp4, pose.mp4   control passes for local models (Phase 2)
    preview/        start / middle / end frames
    takes/t001.mp4 + t001.json   service, model, seconds, cost, prompt hash, refs used
    verdicts.json   keep / reject per take
  costs.json        running spend for this short
  draft.mp4         rough cut
narrator/worlds/shorts/<slug>/  committed copies of short.toml and shots/*/shot.toml (the script)
```

Rules:
- C1..Cn map to approved design TOMLs; reference images (turnaround, expressions, colour guide,
  place art) are looked up from existing design-data, never copied by hand.
- Prompt layers, each stated once:
  L1 grey-box role and camera summary · L2 asset mapping only (C1 = …) · L3 look/camera/light ·
  L4 character state and voice · L5 per-second timecodes in camera terms (who is in frame,
  foreground/background, facing and eyeline per shot).
- `python -m tools.shorts prompt <slug> S01` assembles the prompt and rejects it if L2 or L4 contain
  position words (left/right/behind/next to/at the …) — positions belong to the floor plan and L5 only.
- Acting blocks use the 8 dimensions: time range, goal, emotion change, trigger word, facial action
  (+ optional FACS AU with intensity), gaze/body, voice/breath/pause, end state + listener reaction.
- Dialogue lines carry optional `overlap_s` and `early_s` and a `disfluency` field
  (block / repeat / silence / self-correct) placed on the hardest word.
- Each design TOML gains an optional `voice` line (timbre, age, accent, delivery).

## 2. Grey-box tooling (`tools/shorts/greybox/`)

- Blender LTS unpacked to `~/opt/blender` on the GPU box; run as `blender -b -P <script> -- <args>`.
  Plain bpy scripts, no agent add-on.
- `room`: white walls, floor and only occluding / path-defining blocks (doors, counter, stairs, pillars)
  from `short.toml`; camera framing matched to the approved place art.
- `figures`: three tiers — capsule (position/path), procedural jointed mannequin (our own 11-bone
  armature with capsule limbs; no add-on) with named poses (`sit`, `lean_counter`, `kneel`, `arm_raised`, …),
  rigged clip import (e.g. Mixamo, owner's account) only when an action shot needs it.
  Experiment: faint per-character tint from the colour guide vs plain grey (A/B in Phase 0).
- `camera`: keyframed path from shot.toml — start, via points, end, lens, timing — described in film
  terms ("dolly in over C1's right shoulder to C2 MCU").
- `floorplan`: orthographic top-down render of the same scene with C1..Cn labels.
- `render`: Workbench render per shot to greybox.mp4, three preview frames, and depth/pose passes.
- Continuity: all shots live on one timeline; each shot exports its own range (≤30 s).
- Review: new AI Lab page `/shorts/` (GPU box nginx, same pattern as `/designs/review/` and
  World Gallery) showing floor plan, previews, grey-box video and takes, with comment and keep/reject.
  Camera fixes change only the camera.

## 3. Generation and review

Backends, one small module each behind a common `submit(shot, refs, prompt) -> take` shape:
- `manual`: writes `bundle/` with `prompt.txt` and clearly named refs (`C1_front.png`,
  `C1_expressions.png`, `place.png`, `greybox.mp4`, `floorplan.png`) for pasting into Dreamina or LibTV;
  the owner saves the result into `design-data/shorts/<slug>/inbox/` in the nightwire checkout (copy or scp; the
  design-picks service is read-only, so the page has no upload) and `python -m tools.shorts inbox <slug>`
  files it as a take with the cost entered on the command line.
- `fal`: Seedance 2.5 / 2.0, Kling, Veo via fal's API. Key in `~/.config/nightwire/secrets.env`,
  entered by the owner; never logged.
- Later: ComfyUI partner nodes (if Vidu or Veo Lite wins the test) and `local` Wan 2.2 / AniSora
  driven by depth/pose passes (Phase 2).

Spend guard: before any paid submit, estimate = seconds × model rate; refuse if `costs.json` total +
estimate > `budget_usd` unless the owner raises the budget. Every take records its real cost.

Loop per shot:
1. 3–5 s no-dialogue test on the cheapest adequate model.
2. Checks: right characters (existing `tools.design_check` face similarity against sheets on sampled
   frames), prop relations, head count after camera moves, no left/right flip on reverse shots (owner).
3. Fix only the failing layer; then the full shot with dialogue.
4. Partial failure: regenerate from the last good frame (first-frame input) for the failing span and
   splice.

Phase 0 anime test: one pilot shot, same prompt and refs, on Seedance 2.5, Seedance 2.0 fast,
Kling 3.0, Vidu Q3 and Veo 3.1 Lite (~5 s each, ~$3–6 total). Side-by-side page; owner picks the
service before any subscription.

## 4. Audio and edit

- Voices: model-native first (Seedance / Veo voice quoted lines with lip-sync). Fallback for voice
  drift: one fixed reference voice per character made once with IndexTTS2 (local); lines generated
  locally and passed to Seedance as audio references. Kokoro stays the in-game narrator.
- Music: ACE-Step 1.5 (MIT, local, <4 GB).
- SFX: model audio only at first; MMAudio / HunyuanFoley considered after the 24 GB card.
- `python -m tools.shorts assemble <slug>`: ffmpeg concat of kept takes in shot order, music bed,
  burned subtitles from shot.toml dialogue → draft.mp4, shown on `/shorts/`.
- Polish in Kdenlive (flatpak) on the desktop when the owner wants it.
- SeedVR2 upscale on the draft (GGUF on the laptop if it fits, otherwise after the 24 GB card);
  RIFE only for judder. Baseline 720p.

## 5. Hardware, spend and phases

Phase 0 (laptop + ~$20–30): Blender install, grey-box tools, pilot scene, anime test via fal,
Dreamina sign-up ($0.29 promo if eligible, then $15/mo). Owner creates the fal and Dreamina accounts.

Phase 1 (laptop): the full pilot — shots, takes, IndexTTS2 / ACE-Step, rough cut. One GPU job at a
time (existing etiquette: free ComfyUI VRAM before Ollama and vice versa).

Hardware purchase order:
1. 4U box board, CPU and RAM first (X570 Pro WS + Ryzen 7 5700X with owned DDR4; 64 GB minimum,
   128 GB preferred); confirm PSU ≥1,200 W.
2. Used RTX 3090, target ≤$1,300 on eBay sold prices; 2-slot blower (ASUS / Gigabyte Turbo)
   preferred for 4U; seller with returns; GPU-Z screenshot + loaded stress video with memory temps;
   plan a thermal-pad refresh.
3. RTX 5090 only near MSRP (≤ ~$2,100).
GPU roles: 3090 video / LoRA training / upscale · 4070 SDXL / TTS / music · 3060 Ti Ollama narrator
only if there is a clean third slot, else sold · laptop becomes spare or Blender render node.

Phase 2 (24 GB card): `local` backend (Wan 2.2 I2V + VACE depth, AniSora A/B), Wan character LoRAs
for the pilot cast from turnarounds (musubi-tuner), cloud kept for hero shots.

Running cost: ~$15–30/mo while building; ~$50–100/mo producing regularly. A 60 s short ≈ $40–60 on
cloud alone, ≈ $20–40 once local tests replace cloud tests.

## Out of scope

Monetisation and licence migration; Mixamo/rigged action until an action short is chosen; SFX models;
LoRA training before Phase 2; any adult/explicit content (art-direction rules apply unchanged).

## Testing

- Unit tests for prompt assembly (layer rules, position-word guard), shot/short TOML parsing,
  spend guard, take filing, and assemble's edit list (ffmpeg command built, not run).
- Grey-box scripts: a headless Blender smoke test on the GPU box that builds a two-figure room and
  renders 3 frames; CI skips it when Blender is absent.
- Live checks per phase: the Phase 0 anime test page, a full pilot draft.mp4 reviewed by the owner.
