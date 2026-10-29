# 19b research notes — character consistency on 8 GB (2026-10-28, researcher subagent; evidence thin, mostly community)
Ranked:
1. BUILD FIRST: canonical tag block + fixed seed + owner-approved sheet/portrait per character. 0 VRAM. Holds hair/eye/outfit colour, not exact face shape/ornaments. Identity tags first (later tags dilute). Ref: https://rentry.org/OC-creation-and-character-consistency-with-NAID ; https://civarchive.com/articles/23210
2. SPIKE: per-character LoRA for principals only (PC + 2-3 recurring NPCs). ~0 extra inference VRAM. 8 GB training feasible (fp16, bs1-2, grad ckpt, 8-bit AdamW) https://civitai-proxy.pages.dev/articles/10872 ; ~6 h on 3060 12GB (2080 unknown). Dataset 15-30 crops from approved sheet. v-pred needs v-pred/zsnr flags in sd-scripts (verify). Can't train while ComfyUI/Ollama hold VRAM.
3. SPIKE: IPAdapter PLUS (not FACE) weight 0.3-0.5 (cubiq/ComfyUI_IPAdapter_plus, maintenance-only since 2025-04). ViT-H encoder ~2.5GB + adapter ~0.8GB on top of 7.7GB peak — likely over budget unless embeds pre-encoded/encoder unloaded. Untested with v-pred.
4. Optional: kataragi/Noob_ipadapter (.bin pickle, 1.4GB, openrail-m) — sandbox only.
5. SKIP: InstantID/PuLID/Arc2Face/FaceID (photoreal encoders).
Model sheets: tags "character sheet, reference sheet, turnaround, multiple views, front view, from side, from behind, simple background, white background" @1216x832; charsheet LoRA (Hassaku-trained, trigger `charsheet`, 0.5-0.6) URL not found. Use sheet crops as LoRA data / IPAdapter ref.
Multi-character: Attention Couple (PPM, pamparamm), Tiled Attention Couple, EasyIllustrious regional conditioning; best when characters spatially separated. VRAM unmeasured.
Storage: per-character folder/JSON: tags, seed, negative, sheet.png, refs/, optional lora + trigger, approved flag.
Spike plan: (1) tag blocks for 3 NPCs x10 scenes + sheet tags; (2) IPAdapter PLUS VRAM; (3) one LoRA train timed; (4) 2-char Attention Couple; (5) decide tiering.

## Owner requirement (2026-10-28)
Every player + NPC gets an exportable **character model sheet** (turnaround: front / 3/4 / side / back; expression sheet; colour-palette callouts; detail callouts e.g. chrome) — owner may later use them for an animated video/short. Sheets double as the consistency source (references / LoRA training crops). Store per character: tag block, seed, approved sheet images, palette, presentation.
