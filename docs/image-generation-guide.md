# Generating Images with Nightwire's ComfyUI

This guide is for people and for coding agents such as opencode and Claude Code. It covers the homelab ComfyUI on the GPU box, which runs Nightwire's approved anime-cyberpunk look.

## Where it is

- **ComfyUI:** `http://192.168.10.19:8188` on the LAN, or `http://100.67.87.32:8188` over Tailscale.
- **GPU:** an RTX 2080 Max-Q with 8 GB of VRAM, shared with Ollama (`qwen3:8b`). Only one big job fits at a time.
- **Models on the host:**
  - `NoobAI-XL-Vpred-v1.0.safetensors` (checkpoint);
  - `Smooth_Booster_v3.safetensors` (LoRA);
  - `2x-AnimeSharpV2_RPLKSR_Soft.pth` (upscaler).
- **The look and its rules:** `docs/art-direction.md`. Read it before writing prompts for Nightwire content.

## The easy way: Image Studio (people)

Open **http://192.168.10.19:8080/studio/** (LAN or Tailscale; there's no login). Pick an approved character, a shot and a location, describe what's happening, then press Generate. Results show live progress and can be reused with the same seed or a new one.

It runs on `tools/image_studio.py` and enforces the content rules in `docs/art-direction.md` on the server: approved designs only, no raw prompts or custom negatives, and descriptions asking for nudity, sexual content or minors are refused. One character per image for now. Tags and seed alone don't hold a face perfectly steady across scenes.

**Updating it on the GPU box** (its own nightwire checkout isn't used):

```
rsync -a --delete --exclude __pycache__ --include 'tools/' --include 'tools/*.py' --include 'narrator/' --include 'narrator/**' --include 'engine/' --include 'engine/__init__.py' --include 'engine/character.py' --exclude '*' ./ 192.168.10.19:anvil-deploy/stack/image-studio/app/
scp tools/image_studio.html 192.168.10.19:anvil-deploy/stack/dashboard/studio/index.html
ssh 192.168.10.19 'cd anvil-deploy/stack && docker compose restart image-studio'
```

New approved designs need only the rsync. Jobs are in `image-studio/state/jobs.json`; images are in ComfyUI's `output/image_studio/`.

## Option A: the ComfyUI web UI (people)

1. Open ComfyUI and go to **Workflows** (left bar). Pick a `Nightwire - …` preset:

   | Preset | Makes |
   |---|---|
   | Portrait – portrait | head-and-shoulders character portrait, in-world neon |
   | Closeup – base, 1080p, 4k, phone | **owner favourite**: moody close bust, glowing neon, few tags (keep the prompt short) |
   | Character – base / 4k | full-body character model sheet, dark backdrop |
   | Scene – base, 1080p, 4k, ultrawide, phone | locations with no people, including wallpapers |
   | Plain – same sizes | game style with no subject forced |
   | Scene Day – same sizes | locations in daylight |
   | Subject / Crowd – base, 1080p, 4k (and phone for Subject) | in-world scene with one adult character, or a crowd seen from behind |
   | Painterly – base, 1080p, 4k | out-of-Nightwire oil-painting landscapes (non v-pred NoobAI + `wlop` LoRA) |

2. Edit the box titled **"Positive prompt (edit me)"**. Keep the quality and style tags at the front, and replace the example description at the end.
3. Leave **"Negative prompt"** alone unless you mean to change the rules.
4. Click **Run**. Results appear in **Save image** and **Assets**.

To regenerate the presets after a style change, run `python -m tools.comfy_presets --out <comfyui>/user/default/workflows`. On the GPU box that path is `/home/sentinel/anvil-deploy/stack/data/comfyui/basedir/user/default/workflows`.

## Option B: the command line (agents and scripts)

Run it from the `nightwire` repo with its venv (`.venv/bin/python`, or `uv run`):

```
python -m tools.imagegen "<tags or description>" --kind scene|subject|crowd|portrait|closeup|character|plain --size base|1080p|1440p|4k|ultrawide|phone|square|portrait [--seed N] [--count N] [--negative "..."] [--raw]
python -m tools.imagegen --design hachi --size 4k          # an approved design's tags, negative and seed
```

- **Other switches:**
  - `--day` gives the daylight look;
  - `--subject 1girl|1boy|1other` sets the subject (adult tags follow it);
  - `--sheet-style` gives a portrait on the model-sheet backdrop;
  - `--checkpoint`, `--lora`, `--steps`, `--cfg`, `--sampler`, `--scheduler` and `--no-vpred` experiment outside the locked look.

- **`--kind`:**
  - `scene` adds the game style and "scenery, no humans";
  - `subject` gives an in-world scene with one adult character, and `crowd` a crowd seen from behind;
  - `portrait` gives a bust portrait with the mature character look;
  - `character` gives a full-body sheet style;
  - `plain` adds the game style only.
- **`--raw`** sends the prompt exactly as written: no style, quality tags or default negatives.
- **Output:** `design-data/imagegen/<kind>-<size>-<seed>.png` plus `.workflow.json`, which you can open in the web UI to tweak.
- **Timing:** about 30 s at base size and about 2–3 min at 4k. Wallpaper sizes render at an SDXL bucket, then refine, upscale and resize to the exact size.
- **Prompts:** use Danbooru-style tags, not sentences. Subject first (`1girl, solo`, or `scenery, no humans`), then hair, face, body, outfit, setting, lighting.
- **Nightwire character and location designs** go through the design studio instead: `python -m tools.design_studio` (see `docs/design-studio-resume.md`).

Option C is the raw HTTP API: POST `{"prompt": <api workflow>}` to `/prompt`, poll `/history/<id>`, then fetch `/view`. `tools/imagegen.py` shows the exact graphs.

## Etiquette for agents

- **Check the queue first:** `curl -s http://192.168.10.19:8188/queue`. If a batch is running (for example a design-studio sheets run), wait or say so. Don't start a second batch.
- **Free the GPU first:** Ollama must not hold the GPU, since image jobs need about 7.7 GB. The tools do this; for raw API use, POST `{"model":"qwen3:8b","keep_alive":0}` to `http://192.168.10.19:11434/api/generate`.
- **Free ComfyUI afterwards** with `POST /free {"unload_models":true,"free_memory":true}`, so Ollama can reload.
- **Don't download new models or custom nodes** without the owner's OK.

## Content and licence

- **Nightwire's own pipeline** keeps characters adult and non-explicit (see `docs/art-direction.md`).
- **NoobAI-XL** is fair-ai-public-license-1.0-sd, and the **AnimeSharp** upscaler is CC BY-NC-SA 4.0. Both forbid commercial use, and that covers the images they generate.

## Review before publishing

Thumbnails hide most errors, so every image passes these steps before it goes on a page. Treat a failure as a reason to keep the image off the page or re-render it, and tell the owner about any flaw that remains.

1. **Prompt, before rendering.** Nothing requested may appear in the negatives (a design's `negative` can block a prop the shot needs). Outfit words must match the model sheet, not only the tags.
2. **Tagger.** Run `tools.design_check` for required features and forbidden tags. Its flags are prompts to look, not verdicts.
3. **Character, at full size beside the turnaround.** Check hair, face, every outfit piece, chrome on the correct side, and props.
4. **Construction, at full size.** Check hands, held objects, vehicles (wheels, forks, how a rider sits or touches it), extra limbs and merged people.
5. **Brief.** Check that the image shows what was asked, in the right place, and that it looks like Kuroshio. Look for lettering that shouldn't be there, stray people, and shots that repeat another shot.
6. **Age.** Crop every head and check each one reads as an adult. Remove anything unclear.
7. **Owner.** Publish what passed, with its remaining flaws stated.

## Fix an area or render again

Fix the area when the image is right apart from a local error: a prop, a hand, a face, a piece of clothing. Render again only when the pose, framing or place is wrong, because a full render changes everything else too.

    PYTHONPATH=. .venv/bin/python -m tools.fix_area IMAGE --shape X,Y X,Y X,Y... --prompt "what belongs there" --out FIXED.png

- **Shape.** Trace the area in the image's own pixels, following its outline. Stay inside the object's edges: the fill runs to the edge of the shape.
- **Strength (`--denoise`).** About 0.4 for hands and faces (one [NoobAI guide](https://rentry.org/fluffscaler-noob) found hands turn messy by 0.45). Test on the image and keep the lowest that works.
- **Changing what something is.** A redraw keeps the colours underneath: Kaede's bare stomach stayed skin at 0.7. Add `--fill R,G,B`, a rough coat of the new colour taken from the same image. 0.6 turned it into cloth.
- **Limit.** This changes what is already there. It failed to add new objects: a cup under Mama Sato's pour glowed or vanished over 5 tries, and a hand repaint left a flat block. A wider crop did not help. Pick a different render instead, or change the action.
- **Faces.** Repaint at 0.4 and keep the result only inside a tight oval around the head. At 0.55 faces became different people, and a wide oval changed the background.
- **Check.** The tool refuses to save if a pixel outside the mask moved, and writes `FIXED-compare.jpg`. Look at the result at normal size too: at heavy zoom a fix can look flatter than the area around it.

Then run the fix through "Review before publishing" like any new image, and keep the original beside it.

## Testing a method

Change one thing at a time on the same seeds and the same characters, and record the settings. Compare at full size. Keep a new method only if it beats the old one on the same images, and write down what would have disproved it first.

## Natural shots

`python -m tools.design_studio scene SLUG "PLACE AND ACTION TAGS" --name NAME --place WALLPAPER.png` puts a character in a location doing something. This is the default recipe: no skeleton, a start from the empty location at 0.8 so the figure takes the room's light, and the turnaround as reference from 35% to 75% of the steps at 0.7. `--standing` keeps the old full-body recipe. Without `--place` it starts from nothing, for rooms with no wallpaper yet.

- **Check the start image first.** Use a wallpaper with nobody in it that shows the place the prompt names. Kaede's highway came out as an alley because her start image was an alley with a figure in it.
- **Check the design's negative against the action.** Rin's blocked "monitor" and "cable", Kaede's blocked "motorcycle". Take those out for that shot.
- **Keep hands simple.** Holding something works better than a two-object action: pours failed, holding a cup worked.

## ComfyUI add-ons

Restarting the `comfyui` container reinstalls ComfyUI's Python requirements, and this can upgrade packages. Restart only when the queue is empty, and test a render afterwards.

ComfyUI-Inpaint-CropAndStitch is installed at commit 6005efc02f7745649118edd89cdd084c2b9bd3ae (v3.0.20, GPLv3), nodes only, with no bundled test files. The pinned commit is in `PINNED_COMMIT` in its folder. It has not replaced `tools.fix_area` yet: compare them on a real fix first.

