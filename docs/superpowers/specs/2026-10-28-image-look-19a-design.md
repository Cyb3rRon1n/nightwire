# Nightwire Image Look Design: Phase 19a

Status: designed, not yet implemented. Brainstormed and art-directed with the owner on 2026-10-28.

**Split.** Phase 19 is split in two:
- **19a** (this spec) is the locked art style, the tag-writer and the player presentation field.
- **19b** is the character model sheets: persistent per-character designs for players and NPCs, reused in scenes, with owner review of the NPC sheets. It is designed after 19a ships; its research notes are in `.superpowers/imagebench/research-19b-consistency.md`.

## Owner decisions (2026-10-28)

The owner reviewed four gallery rounds rendered on the GPU box (RTX 2080 Max-Q, 8 GB):
- **Round 1:** NoobAI-XL over SD1.5; a single pass over the latent upscale, which produced jagged edges.
- **Round 2:** fixed the blue skin and judged it "too simple". The owner liked F (Smooth Booster LoRA), H (DPM++ 2M SDE) and I (v-pred).
- **Round 3:** "They all look amazing! The I + F and the I + F + H combos are the best!"
- **Round 4** (real narrator prompts): the owner chose **B**, the tag-writer, over wrapping the narrator's sentence.

Further owner decisions:
- **Presentation:** players set an optional presentation (feminine, masculine or androgynous). NPC presentation is decided by the owner during the 19b sheet review.
- **Split approved:** 19a now, 19b next.

**Locked look ("I + F"):**
- NoobAI-XL **v-pred** 1.0 with `ModelSamplingDiscrete` (v_prediction, zsnr) and `RescaleCFG` 0.6;
- the **Smooth Booster v3** LoRA at 0.6;
- Euler, CFG 4.5, 28 steps, clip skip 2;
- 832×1216 for portraits and 1216×832 for scenes;
- tiled VAE decode.

Measured: about 26–33 s per image, with a peak of 7.7 GB of VRAM. I + F + H (DPM++ 2M SDE, beta, CFG 5, rescale 0.7) is a configuration option.

## Research grounding

- **The [NoobAI-XL v-pred card](https://huggingface.co/Laxhar/noobai-XL-Vpred-1.0)** gives Euler, CFG 4–5, 28–35 steps, 832×1216, v_prediction and zero-SNR. The **[community NoobAI guide](https://rentry.org/fluffscaler-noob)** gives RescaleCFG 0.5–0.7 and DPM++ 2M SDE with the beta schedule.
- **[Smooth Booster v3](https://huggingface.co/LyliaEngine/Smooth_Booster_v3)** (CDLA-Permissive-2.0) is a detail LoRA for SDXL, Illustrious and NoobAI.
- **The NoobAI card's prompt order and quality tags** (`masterpiece, best quality, newest, absurdres, highres, safe`, plus `very awa` and `year 2024`) and its negatives are used as given.
- **Licences:** NoobAI-XL is fair-ai-public-license-1.0-sd, **non-commercial**, and that covers generated images too. This is acceptable while Nightwire is a hobby or open-source project. The README states it.
- **Legal and ethical line:** an art style is not protected; characters and logos are. No character names, character LoRAs or franchise names appear in prompts.

## Design

### 1. `narrator/image_prompt.py` (new)

**Constants** (copied verbatim from the bench, `.superpowers/imagebench/bench2.py`):

```
QUALITY = "masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, safe"
STYLE = ("anime screenshot, anime coloring, cel shading, thick outlines, detailed background, neon lights, "
         "pink neon rim light, cyan backlight, yellow accents, high contrast, bloom, depth of field, "
         "chromatic aberration, cyberpunk, night")
NEGATIVE = ("nsfw, worst quality, old, early, low quality, lowres, signature, username, logo, bad hands, "
            "mutated hands, mammal, anthro, furry, ambiguous form, feral, semi-anthro, text, watermark, "
            "jpeg artifacts, blurry, worst aesthetic, flat color, simple background, blue skin, colored skin, "
            "monochrome, limited palette")
```

**The skin tag is not forced.** The bench's `light skin` is **not** added: forcing one skin tone on every player is wrong. The lighting rewrite and the blue/colored-skin negatives carry the fix, and the live gallery check confirms it. If blue skin returns, 19b adds a skin-tone field.

**Subject**, decided by the engine and never by the model. `subject_tags(kind, character=None) -> list[str]`:
- **scene:** `["scenery", "no humans"]`
- **portrait of a tsukumogami:** `["1other", "solo", "upper body", "android", "robot joints"]`
- **portrait of anyone else:** `{"feminine": "1girl", "masculine": "1boy", "androgynous": "1other", None: "1other"}[presentation]`, plus `["solo", "upper body", "looking at viewer"]`

**Tag-writer.** `async tagify(client, text) -> list[str]` calls `client.judge(messages, schema)`:
- **schema:** `{"tags": array of string}`, required;
- **system prompt:** the round-4 instruction, minus the subject guidance, since the engine owns the subject. Exact text: `"Convert the image description into Danbooru-style tags for an anime image model. Output 10-25 lowercase tags: setting, objects, people's clothing and features, lighting, weather, mood. Concrete nouns only; no subject-count tags, no style or quality tags, no artist names, no sentences."`

**Cleaning.** `clean_tags(raw: list[str]) -> list[str]` keeps the first 25 tags after it:
- lowercases and strips each tag, turning `_` into a space;
- drops empty tags;
- drops any tag matching `^\d+\w*$`, or `^1\w+` unless it is in `{1girl, 1boy, 1other}` (it also drops those three, since the engine owns the subject);
- drops any tag that contains a word from `{masterpiece, quality, best, absurdres, highres, aesthetic, style, artist, anime, detailed}`;
- dedupes, preserving order.

**Assembly.** `build_prompt(subject: list[str], content: list[str] | str) -> str` joins `QUALITY`, the subject, `STYLE` and the content with `", "`. A string content (the fallback) is appended as-is.

**Resolving.** `async resolve(client, kind, text, character=None) -> tuple[str, str, str]` returns `(positive, negative, source)`:
- `source` is `"tags"` when `tagify` returned at least 5 tags after cleaning;
- otherwise it is `"sentence"`, with the original text wrapped. A tag-writer exception also gives `"sentence"`.

### 2. `narrator/comfyui_backend.py`

**Profiles.** `ComfyUIBackend(profile="noobai" | "sd15", checkpoint, lora, lora_strength, sampler, scheduler, cfg)`.
- **`noobai`** builds the locked graph:
  - CheckpointLoader → LoraLoader → ModelSamplingDiscrete(v_prediction, zsnr=True) → RescaleCFG(0.6);
  - CLIPSetLastLayer(-2);
  - CLIPTextEncode for the positive and the negative;
  - EmptyLatentImage at the profile's size;
  - KSampler(Euler, normal, 28 steps, CFG 4.5);
  - VAEDecodeTiled(512, 64);
  - SaveImage.
- **`sd15`** is the existing graph, unchanged.

**Interface.** `ImageBackend.wants_tags: bool` is True for `noobai` and False for `sd15` and `flux_worker`. `generate_scene(prompt, reference_paths, negative=None)` and `generate_portrait(description, reference_photos=None, negative=None)` gain an optional `negative`; when it is None, the existing negative is used.

**Environment:**
- `COMFYUI_PROFILE`, default `noobai`;
- `COMFYUI_CHECKPOINT`, default per profile: `NoobAI-XL-Vpred-v1.0.safetensors` or `v1-5-pruned-emaonly-fp16.safetensors`;
- `COMFYUI_LORA`, default `Smooth_Booster_v3.safetensors` for noobai, and an empty value disables it;
- `COMFYUI_LORA_STRENGTH`, default 0.6;
- `COMFYUI_SAMPLER` / `COMFYUI_SCHEDULER` / `COMFYUI_CFG`, defaulting to euler, normal and 4.5.

The I+F+H variant is `dpmpp_2m_sde`, `beta`, CFG 5.0.

### 3. Call sites

**Scenes.** In `server/narration.py`'s image block, if `image_backend.wants_tags`, call `resolve(narrator_client, "scene", response.image_request.prompt)` **before** `narrator_client.unload()`, then log `[image prompt ({source}): {positive}]`. Then pass the positive and negative to `generate_scene`. Otherwise keep today's path.

**Portraits.** `server/portrait.py` builds the description from role and lifepath visuals, with no "highly detailed digital painting". With `wants_tags`, it resolves through `resolve(narrator_client, "portrait", description, character)`.

**Player presentation.** `CharacterSheet.presentation: str | None = None` stores one of `feminine | masculine | androgynous`, so old saves load. It is added to the join allowlist and validated, and any other value is a `ValueError`. The join screen gets a "Presentation" select (optional) beside lifepath, and the protocol type gains the field.

## Testing

**Unit tests:**
- `clean_tags`: the junk-tag cases from round 4 (`1structure`, `1neon`), style and quality words, dedupe, the cap at 25, and the underscore conversion;
- `subject_tags`: a scene, each presentation, None, and a tsukumogami overriding presentation;
- `build_prompt` order;
- `resolve`: tags, the fallback on an exception, and the fallback on fewer than 5 tags;
- the workflow graph for `noobai`: the nodes, v_prediction/zsnr, RescaleCFG 0.6, the LoRA strength, the sizes and the sampler; `sd15` unchanged; env profile selection; an empty `COMFYUI_LORA` disabling the LoRA;
- `wants_tags` per backend;
- narration: the image block calls `resolve` before `unload` and logs the `[image prompt` line; a non-tag backend keeps the old path;
- portrait: tsukumogami subject tags and no "digital painting";
- presentation: join validation, the allowlist, persistence and an old save.

**Live** (GPU box):
- six first-time location arrivals and two player portraits (one feminine solo, one tsukumogami) go through the **real game path**;
- record the tag source (tags or sentence), the times and the peak VRAM;
- the results go to the owner's gallery for sign-off, including skin tone with no forced `light skin`.

**Browser:** the presentation select at join, and a generated scene image rendering in the feed.

## Not in this phase

- Character model sheets, NPC images, scene casting of known characters, IPAdapter or LoRA identity, and multi-character regional prompting (all 19b).
- Upscaling (J was rejected as too slow for play).
- A skin-tone field (only if the live check needs it).
- Flux/FluxWorker changes.
