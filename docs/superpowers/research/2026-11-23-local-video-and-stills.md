# Local video and stills for the 4U box (research, 2026-11-23)

## Owner goal (2026-11-23)

Don't pay for video unless it is a final clean touch-up or enhancement that only Seedance can do, or until a free
Seedance-class model can be run locally. Locally, the target is great still shots, with at most minimal looping
background animation (the city moves, the character stays still). Seedance is for the final polished product only.

## Hardware

4U box: RTX 4070 12 GB (ComfyUI) and RTX 3060 Ti 8 GB (Ollama narrator only), RDIMM DDR4 (64-128 GB). The 2026-11-08
shorts spec planned a used RTX 3090 24 GB for local video (Phase 2). This research says test on the 4070 first.

## Verification

[V] = fetched and read. [S] = second-hand (search snippets or third-party guides). [R] = researcher's reasoning, not
measured. Most VRAM figures come from one guide site (modelfit.io), not model cards. No time per clip on a 12 GB
card was found for any model, and no anime image-to-video benchmark exists.

## Stills

- **Keep NoobAI-XL v-pred** (SDXL, fits 12 GB, large LoRA/ControlNet ecosystem, the locked photo-first recipe).
  Nothing newer clearly beats it for this look.
- **Anima 2B**, one side test. https://huggingface.co/circlestone-labs/Anima [V]
  - Cosmos-Predict2-2B base, Danbooru tags plus natural language, 512-1536 px, a Turbo version, native ComfyUI.
  - Licence: the model is non-commercial; generated images may be used commercially; paid hosting needs a separate
    licence; NVIDIA's Open Model License also applies. Check before using for promotion.
- **NetaYume Lumina v4**, maybe. https://huggingface.co/duongve/NetaYume-Lumina-Image-2.0 [S] Licence and VRAM
  unchecked.
- **Z-Image Turbo**: skip. Its 8-step distillation weakens img2img repaint at denoise 0.70, which the photo-first
  recipe needs [S].
- Not checked: Flux.2, Chroma, HiDream, Qwen-Image (Qwen-Image-Edit-2511 stays on the character-consistency list).

## Local video on 12 GB, ranked

1. **Wan 2.2 image-to-video** (A14B, Q4-Q6 GGUF, lightx2v 4-step LoRAs).
   - Apache 2.0 [V on the TI2V-5B card, https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B; A14B card not checked].
   - First+last-frame: ComfyUI's `WanFirstLastFrameToVideo` and an official workflow [S]. The same still as first and
     last frame is the natural way to make a seamless loop: exactly the owner's "frozen character, moving city" shot.
   - Expect about 5 s at 480-720p, 16 fps [S]. Docs: https://docs.comfy.org/tutorials/video/wan/wan2_2.md [S]
2. **AniSora V3** (Bilibili, anime-trained). https://github.com/bilibili/Index-anisora [S]
   - Built on Wan 2.1 (about 14B), runs through Kijai's WanVideoWrapper with fp8 [S]. Probably 480p on 12 GB [R].
   - Licence and first/last-frame support not checked.
3. **LTX-2.3** (22B, GGUF, distilled 8-step, frame-indexed image conditioning). https://huggingface.co/Lightricks/LTX-2.3 [V]
   - Fastest iteration; 720p 5 s reported on an 8 GB card [S]. Licence "ltx-2-community-license-agreement": terms not
     read.
4. HunyuanVideo 1.5: fallback only. A secondary guide says its licence excludes EU/UK/South Korea users [S].

Also: Wan2.2 TI2V-5B (Apache 2.0, about 8 GB with offload [S]) as a cheap draft model. MiniMax H3 is listed as open
weights on the Artificial Analysis board; licence and weights unverified; reportedly needs about 75 GB of system RAM
on 12 GB [S], which the RDIMM box could have.

## What a 3090 24 GB would change [R]

- Wan 2.2: 720p and roughly 2-3x faster; VACE depth control from Blender passes becomes realistic (tight on 12 GB).
- Wan video LoRA training: practical only on 24 GB. musubi-tuner (block swap + fp8, 720x1280 on 24 GB) [S]; one user
  trained on 16 GB slowly (https://github.com/kohya-ss/musubi-tuner/discussions/455) [S]. NoobAI image LoRAs are
  fine on 12 GB.
- LTX-2.3, SeedVR2: faster, same quality. HunyuanVideo 1.5: 720p plausible. AniSora: 480-720p comfortably.
- Verdict: buy the 3090 only if the 4070 tests show Wan character LoRAs or depth control are needed.

## Seedance (the polish step)

- Artificial Analysis image-to-video leaderboard (with audio) [V]: Seedance 2.5 first (Elo 1161), Utopai X 1153,
  Boreal-H3 1152, Seedance 2.0 1142, Seedance 2.5 Flash 1140, MiniMax H3 1138, Wan 3.0 1112 (13th), Kling 3.0 about
  1000 (25th), Veo 3.1 955 (29th). Without audio, Utopai X is first and Seedance 2.5 second (1128). The board has
  several versions; re-read it before choosing.
  https://artificialanalysis.ai/video/leaderboard/image-to-video
- fal Seedance 2.5 image-to-video [V]: `image_url`, `end_image_url`, 480p/720p, 4-30 s, `seed`, `generate_audio`;
  about $0.47/s at 720p and $0.22/s at 480p. Tips: describe motion, camera and sound, not what is already in the
  image; name the camera move; use a clean high-resolution start frame; test at 4-5 s first.
  https://fal.ai/models/bytedance/seedance-2.5/image-to-video
- Third-party guides [S]: 4-5 references work better than the maximum of 9; name the opening and closing frames;
  prompt order subject/action, setting/lighting, camera, style; about 50-100 words.
- Local helpers: NoobAI stills as both first and last frame; SeedVR2 upscaler (Apache 2.0, 12 GB mode with BlockSwap,
  https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler [S]). RIFE / GIMM-VFI not checked.

## Plan this implies

1. Stills stay NoobAI (plus one Anima side test).
2. On the 4070, A/B against a few Seedance 2.5 reference clips, using looping background shots from approved stills:
   Wan 2.2 first+last frame, then AniSora V3, then LTX-2.3. Judge with the owner in Nightwire Reviews.
3. Seedance is used only for final polish of a finished short.
4. The 3090 is decided after step 2.
5. Re-check for an open Seedance-class model (MiniMax H3, Wan open releases) at each new test round.

Not researched: MMAudio and HunyuanFoley (sound effects).
