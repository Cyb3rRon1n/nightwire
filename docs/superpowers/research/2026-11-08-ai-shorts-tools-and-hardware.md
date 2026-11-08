# AI shorts: tools, services and hardware (research, 2026-11-07/08)

Synthesis of four researcher passes. Most sources are vendor or SEO pages; numbers are
low-to-medium confidence unless marked (official). Re-check every price before paying.
Method of the reference creator (Foyege): see 2026-11-08-foyege-method.md.

## Cloud video models (price per generated second, 720p)
| Model | Route | $/s | Notes |
|---|---|---|---|
| Seedance 2.5 | fal (official page) | ~0.47 | 4–30 s, 480/720p, 30 img + 10 video + 10 audio refs, first/last frame, native voice + lip-sync |
| Seedance 2.5 | Dreamina credits (official) | ~0.35 | 37 credits/s; Basic $15/mo = 1,575 credits; $0.29 first-month promo (US, from 2026-10-21) |
| Seedance 2.0 | fal / Dreamina | 0.24–0.30 (fal), ~0.05–0.16 (Dreamina Mini/Fast/Pro) | up to 12 refs on fal |
| Kling 3.0 | ComfyUI partner nodes (official) | ~0.084 (no audio) | Elements: reusable character refs |
| Veo 3.1 Lite / Fast / full | ComfyUI partner nodes (official) | 0.03 / 0.08 / 0.20 (+audio more) | 3 reference images |
| Vidu Q3 Turbo | ComfyUI partner nodes (official) | ~0.06 | claimed best anime reference-to-video (vendor claim) |
| Wan 2.5–3.0 | API only | 0.10–0.14 | last open Wan = 2.2 |
| Sora 2 | — | — | API sunset 2026-09-24 |

ComfyUI partner-node credits: 211 credits = $1; no subscription needed; runs from local ComfyUI.
LibTV (LiblibAI, liblib.tv): canvas + 3D director stage + Blender plugin, routes Kling/Seedance; China-first, no USD pricing found.
Lifetime "deal" plans: not recommended (retroactive credit changes, model deprecation).

## Local open models
- Wan 2.2 (Apache 2.0): 5B and 14B (GGUF). 8 GB: 480p, ~3 min per 5 s clip with lightx2v speed LoRA (8 GB laptop figure, not our 2080).
  24 GB: 720p 81 frames with fp8/GGUF + block swap (musubi-tuner docs). VACE (depth/pose/outline control) = Wan 2.1-era; depth more stable than pose.
- AniSora (Bilibili, Apache 2.0 for V3): anime-tuned Wan; V3.2 on Wan 2.2, 8-step; runs via Kijai WanVideoWrapper.
- LTX-2.x (community licence, free under $10M revenue): native audio; Q4 ~10 GB, fp8 720p ~16 GB.
- HunyuanVideo 1.5: ~14–24 GB; licence excludes EU/UK/South Korea.
- Turing (RTX 2080) has no bf16/fp8: expect slower than published 8 GB numbers.
- Multi-GPU (ComfyUI-MultiGPU) only offloads text encoder/VAE; no speed-up.

## GPU purchase (US, Jul–Nov 2026)
| Card | Price | Verdict |
|---|---|---|
| Used RTX 3090 24 GB | ~$1,200–1,460 eBay | best value; prefer 2-slot blower "Turbo" for 4U |
| Used RTX 4090 24 GB | ~$2,500–3,000 | poor value now |
| RTX 5090 32 GB | $1,999 MSRP; street $3,300–5,000 | only near MSRP; ~2–4x a 3090 |
| RTX PRO 4500/5000/6000 | $3.4k / $4.5k / ~$8.5k | skip unless 48–96 GB is a hard need |
| Modded 4090 48 GB, AMD R9700/7900 XTX, Intel B60 | — | skip (provenance / ROCm-XPU immaturity) |

Rental (RunPod official, Nov 2026): 4090 $0.34 community / $0.89 secure per hour; 5090 $0.69 / $1.19; A6000 48 GB $0.33.
Break-even for a $1,300 3090: ~1,650–5,400 GPU-hours.
Build notes: ≥1,200 W PSU for 3090 + 4070; 64 GB system RAM minimum, 128 GB preferred for offload/training.

## Supporting tools
- Voice: IndexTTS2 (emotion separate from timbre), CosyVoice 2, Fish Speech; lip-sync native in Seedance/Veo/LTX; InfiniteTalk, LatentSync (photoreal bias).
- Music: ACE-Step 1.5 (MIT, <4 GB). Suno paid tiers carry commercial rights.
- Upscale: SeedVR2 (GGUF, block swap). Interpolation: RIFE.
- Edit on Fedora: Kdenlive (flatpak) easiest; DaVinci Resolve free has AAC/H.264 caveats on Linux.
- Orchestration prior art: AI Movie Studio 2 (AGPL, 3D storyboard → frames → video → timeline), Evolink Awesome-Blender-Seedance-Workflow-Usecases (25+ grey-box cases; failure modes: foot sliding, CG leakage from detailed proxies, drift).

## Policy / licence
- NoobAI-XL added terms forbid monetising generated products (enforceability disputed). Owner decision 2026-11-08: shorts are promotion/personal use, NoobAI stays.
- YouTube (Jul 2026): targets mass-produced repetitive AI video; disclose synthetic media.
- Cloud filters: stylised violence usually OK; real faces and franchise characters refused. Test a dark scene on a free tier first.

## Key sources
fal.ai/learn/devs/seedance-2-5-vs-seedance-2-0 · dreamina.capcut.com/seedance/seedance-price · docs.comfy.org/tutorials/partner-nodes/pricing ·
runpod.io/pricing · github.com/bilibili/Index-anisora · github.com/kohya-ss/musubi-tuner · github.com/cheercheung/Awesome-Blender-Seedance-Workflow-Usecases ·
runcomfy.com (Blender to ComfyUI AI Renderer 2.0) · resaleprices.com/gpu/nvidia-rtx-3090 · civarchive.com/articles/18619/what-the-license
