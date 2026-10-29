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

## Option A: the web UI (people)

1. Open ComfyUI and go to **Workflows** (left bar). Pick a `Nightwire - …` preset:

   | Preset | Makes |
   |---|---|
   | Portrait – portrait | head-and-shoulders character portrait, in-world neon |
   | Character – base / 4k | full-body character model sheet, dark backdrop |
   | Scene – base, 1080p, 4k, ultrawide, phone | locations with no people, including wallpapers |
   | Plain – same sizes | game style with no subject forced |

2. Edit the box titled **"Positive prompt (edit me)"**. Keep the quality and style tags at the front, and replace the example description at the end.
3. Leave **"Negative prompt"** alone unless you mean to change the rules.
4. Click **Run**. Results appear in **Save image** and **Assets**.

To regenerate the presets after a style change, run `python -m tools.comfy_presets --out <comfyui>/user/default/workflows`. On the GPU box that path is `/home/sentinel/anvil-deploy/stack/data/comfyui/basedir/user/default/workflows`.

## Option B: the command line (agents and scripts)

Run it from the `nightwire` repo with its venv (`.venv/bin/python`, or `uv run`):

```
python -m tools.imagegen "<tags or description>" --kind scene|portrait|character|plain --size base|1080p|1440p|4k|ultrawide|phone|square|portrait [--seed N] [--count N] [--negative "..."] [--raw]
```

- **`--kind`:**
  - `scene` adds the game style and "scenery, no humans";
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
