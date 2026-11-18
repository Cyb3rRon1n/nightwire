# Character Learning Loop: Design

Date: 2026-11-17. Status: direction approved by the owner in chat on 2026-11-17. Not yet planned or built; it targets the 4U GPU box (RTX 4070 12 GB + RTX 3060 Ti 8 GB).

## Goal

Players create a character once, then want many more images of that same character: magazine-cover shots, new scenes, new angles, outfits, expressions and group shots with other characters. The images should come out right more often over time, with fewer "looks off" clicks. The system keeps learning from what players keep and what they reject.

Success measure: **"looks off" clicks per 100 images shown**, on the AI Lab dashboard, falling week over week.

Builds on: `2026-11-01-character-creator-design.md` (creation, lock-in, photo rules) and the locked photo-first recipe (`tools/photo_first/v1_whole_plate.py`: realistic photo pass, then a NoobAI anime repaint at denoise 0.70).

## Generation stack (what the loop improves)

1. **Qwen-Image-Edit-2511**, with the reference sheet as input and the multi-angle camera LoRA. It handles angle, pose, outfit, expression and scene, and takes several reference images for group shots. Apache-2.0. Runs on the 4070 as GGUF Q4 or Nunchaku INT4.
2. **NoobAI anime repaint** at about 0.70, with the character's own LoRA. This is the house look, and the LoRA carries identity.
3. **xinsir ControlNet Union ProMax with DWPose** for poses in covers and set shots.
4. **Group shots:** regional prompting with one LoRA per character, compared against Qwen with several reference images. Use whichever wins in testing.

This supersedes the creator spec's IPAdapter likeness plan for drawn characters: IPAdapter Plus failed on the v-pred NoobAI model. Photo-reference rules from the creator spec still apply unchanged.

## Signals

Each event is recorded with: character id, preset, the full recipe (model versions, seed, settings, LoRA version, scorer version), image hash and timestamp.

| Signal | Meaning |
|---|---|
| Keep, favourite, download, set as cover | good |
| "Looks off", reroll, deleted within a minute | bad |
| Shown and no action | neutral, not used for training |

Recording starts on the first day of the 4U box. The data is what makes every later loop possible.

## Loop 1: best-of-N with a checker (every image, no training)

- Generate N = 4 candidates per request (N can be configured per preset).
- Score each candidate:
  - **Identity:** embedding similarity to the reference sheet and the kept images. The embedding model is chosen by testing; candidates are CLIP, DINOv2 and an anime-face embedder.
  - **Palette:** match against the character's colour guide.
  - **Anatomy:** existing FaceDetailer/YOLO detectors (face and hand counts, crops).
- Show the best candidate. If none scores above the threshold, regenerate once and then show the best available. Never loop without limit.
- Prior art: ImageReward (Xu et al., 2023, arXiv:2304.05977) and PickScore / Pick-a-Pic (Kirstain et al., 2023, arXiv:2305.01569) both show reranking candidates with a learned scorer raises human preference.

## Loop 2: per-character LoRA retraining (nightly)

- **Trigger:** a character has about 10 new kept images since its last LoRA version.
- **Dataset:**
  - The reference sheet: always included, as the anchor.
  - Kept images only.
  - Captions from the character's locked tag string.
  - Self-generated images are capped at 70% of the set. This guards against drift and collapse: training repeatedly on a model's own output degrades it (Shumailov et al., "AI models collapse when trained on recursively generated data", Nature 2024).
- **Train** on the 4070 overnight. Never during gaming hours. Same GPU etiquette as before: pause at 74°C until 62°C, rest between jobs.
- **Gate:** the new LoRA and the current one each render a fixed test set of 8 prompts and seeds. The new version is used only if its checker score is higher and identity similarity didn't drop. Otherwise it's discarded and logged.
- **Versioning:** every version is kept, and rollback is one click per character.
- Initial LoRA: built at lock-in from 20–40 Qwen multi-angle images, curated by the checker, with optional player picks.

## Loop 3: global learning (weekly)

- **Checker retrain:** a small head on frozen embeddings, trained on all keep vs "looks off" pairs. It learns what players reject, not only similarity. It has its own hold-out set and the same promote-or-discard gate as loop 2.
- **Settings tuning:** each preset (cover, scene, outfit, group) runs a multi-armed bandit over a few recipe variants: denoise, CFG, ProMax strength, Qwen steps. Traffic shifts to the variant with the lowest "looks off" rate. Variants stay within ranges the owner approved, so the house look can't drift.
- **Later, once there are thousands of pairs:** preference fine-tuning of the NoobAI base with Diffusion-DPO (Wallace et al., 2023, arXiv:2311.12908) on the keep/reject pairs. This is a separate project with its own spec.

## Guardrails

- **Content filter before training:** nothing adult or suggestive enters any dataset. Designs with `from_photo = true` keep their safe-rating rules in every loop.
- **Consent:** players agree that kept images train their own character. The global checker learns only from scores and embeddings, never from pixels of photo-derived characters.
- **Deletion:** deleting a character deletes its LoRA versions, dataset and kept images. A photo-derived character's LoRA carries the likeness, so it's treated like the photo.
- **Fixed hold-out set** per character and globally, never trained on.
- **Kill switch:** each loop can be turned off independently from the AI Lab.
- **Dashboard:** "looks off" per 100 images, per preset and per character, plus the current LoRA and checker versions and their last gate results.

## Build order (4U box)

1. Event recording, plus loop 1 (checker and best-of-4). This is the fastest drop in "looks off" clicks.
2. Initial per-character LoRA at lock-in, plus loop 2 (nightly retrain with the gate).
3. Loop 3 (checker retrain and per-preset bandit).
4. DPO fine-tune: a future, separate spec.

Prerequisite tests from the Game Box Build page come first: the ProMax pose test, then the Qwen-Image-Edit multi-angle test.

## Open questions (verify before planning)

Research pass 2026-11-18 (primary pages opened unless noted; not legal advice):

- **NoobAI-XL licence: a blocker for anything public or paid.**
  - The licence is `fair-ai-public-license-1.0-sd` (FAIPL-1.0-SD), inherited from Illustrious-XL v0 (https://huggingface.co/Laxhar/noobai-XL-Vpred-1.0).
  - The licence text (https://freedevproject.org/faipl-1.0-sd/) says outputs aren't covered. Training or merging counts as modifying the model, and serving a modified model over a network means offering its weights under the same licence.
  - The model card goes further: it bans "any form of commercialization", including "model-generated products", and requires derivative LoRAs to be open-sourced.
  - **Working rule:** free hobby play with published character LoRAs is OK. Treat any paid or monetised use as not allowed unless the Laxhar team confirms otherwise.
  - Players' character LoRAs (loop 2) would have to be published, and that conflicts with the photo-likeness rules for `from_photo` characters. Owner decision needed before loop 2.
  - Not checked: SDXL's CreativeML Open RAIL++-M use restrictions, and the Civitai page.
- **Qwen-Image-Edit-2511 memory:** real VRAM and speed on the 12 GB 4070 (GGUF Q4 vs Nunchaku INT4). Still open; measure it on the 4U box.
- **Trainer:**
  - Use kohya sd-scripts (Apache-2.0; flags `--v_parameterization`, plus maybe `--zero_terminal_snr`; v-pred LoRA reportedly only on its dev branch, unverified) or OneTrainer (AGPL-3.0, has zero-terminal-SNR rescaling).
  - Skip ai-toolkit (MIT) until its v-pred support is confirmed.
  - Community advice conflicts on zero terminal SNR for LoRAs: test with and without it.
  - Time per retrain: one unopened guide claims 20–30 min on a 4070 SUPER. That's weak evidence; measure it.
- **Multi-angle LoRA:** use the 2511-native https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA (Apache-2.0, 96 camera positions, prompt `<sks> front view eye-level shot medium shot`). dx8152's LoRA only claims 2509.
  - Qwen-Image-Edit-2511 and unsloth's GGUF are both Apache-2.0.
  - Nunchaku code is Apache-2.0; the licence of its INT4 2511 weights is unverified.
- **Identity embedder:** start with CCIP (deepghs, https://huggingface.co/deepghs/ccip; `ccip-caformer_b36-24` has F1 0.941 at a same-character threshold of 0.213).
  - It only scores single-character images, so group shots need per-character crops.
  - The weights are OpenRAIL (use-restricted); the `imgutils` code is MIT.
  - CLIP and DINOv2 stay as fallback baselines. No published anime comparison was found, so settle it by test on our own keep/reject data.

## Research basis

- Qwen-Image-Edit-2511: https://huggingface.co/Qwen/Qwen-Image-Edit-2511 (Apache-2.0); GGUF: https://huggingface.co/unsloth/Qwen-Image-Edit-2511-GGUF
- Qwen-made LoRA datasets: https://weirdwonderfulai.art/comfyui/qwen-image-edit-can-create-character-consistent-lora-dataset/
- NovelAI Precise Reference, the commercial benchmark (one reference per generation, nothing persists): https://docs.novelai.net/en/image/precisereference
- Persistent vs per-generation consistency: https://getimg.ai/blog/how-to-create-consistent-characters-with-ai
- ImageReward: arXiv:2304.05977. PickScore: arXiv:2305.01569. Diffusion-DPO: arXiv:2311.12908. Model collapse: Shumailov et al., Nature 631 (2024).
- Rejected: PuLID, InstantID and FaceID (InsightFace weights are non-commercial, and they handle anime faces poorly); IPAdapter on v-pred (failed in our own test).
