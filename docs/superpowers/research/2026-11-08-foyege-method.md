# Foyege (弗曳哥) — confirmed method (from own tutorial transcripts, 2026-11-07)

Source: 7 YouTube tutorials transcribed locally (faster-whisper large-v3 on GPU box), transcripts in tx/.
IDs: ZTiUwLPAqkM grey-box, TZ4JhoYvUlc dialogue/overlap, XMfnuc2Nf_w acting 8-dim formula,
T4QqUf5i-OI multi-character one-take, c1wWFrcy8wQ 3-layer spatial protocol, NZog-5vbTTA skin, JeIop-z9sSs story beats.
(VCeHUlOeUdI = film only, no speech.)

## Tools (their words)
- Video: Seedance 2.5, 30 s max per generation, native voice ("开启原声").
- Front ends: LibTV (LiblibAI canvas: 3D 导演台 director stage, Blender plugin that renders + imports into canvas,
  Auto Link asset matching for C1..Cn, 片段重拍 segment re-shoot) and 小云雀 (ByteDance AI canvas, style library).
- Character stills: "Seedream 5.0 Pro" at 4K in LibTV (for realistic faces) + LibTV portrait-texture adjust.
- Grey box: Blender (free) driven by "an Agent that can run local programs"; also UE5, game engines, LibTV 3D stage, phone camera path.
- Script: Laper AI (screenwriting agent) for beats + auto storyboard.
- Cost claim: 4M-view acting short = 700 credits, generated once, text only (no reference image/video).

## Pipeline
1. Story beats: anomaly → immediate goal → fatal rule → time-pressure resistance → identity/info reversal → unfinished answer. World info only through action. Emotion changes every few seconds.
2. Character assets: three-view (front/side) per character, high-res; fixed IDs C1..C6 used everywhere.
3. Top-down floor plan with C1..Cn marked (world topology). New floor plan when the scene moves to a new space.
4. Grey box (only when needed: continuous camera path, multi-person staging, exact contact/action):
   - Scene first from a generated scene image; white walls; only occluding/path structures (doors, stairs, pillars).
   - Three tiers of figure: cylinders (position/path) → clear-limbed mannequin (specific pose) → rigged skeleton (precise action/catches/fights).
   - More grey-box detail = more prompt needed to override stiffness; minimal = more model freedom.
   - Camera: describe start / passes / end; preview 3 moments; fix occlusion by naming the timestamp; adjust camera only.
   - Consecutive clips: same Blender file, one timeline, export in ≤30 s segments → spatial continuity.
   - Upload rendered video (not the .blend).
   - Not needed for simple talking / head turns — multi-reference mode is enough.
5. Prompt layers (never restate a fact in two layers):
   - L1 grey-box role ("provides camera path, positions, prop silhouettes, timing; replace mannequins with characters, drop grey material"), camera summary.
   - L2 asset mapping only: C1 = asset X … (no positions, no states).
   - L3 camera/light/look (or pick from style library).
   - L4 character state.
   - L5 per-second timecodes, camera-relative: who is in frame, foreground/background, facing + eyeline per shot
     (shot/reverse: "C2 MCU, C1 shoulder as blurred lower-left foreground, C2 looks at C1").
   - Re-describing all positions mid-prompt makes the model re-allocate space → chaos.
6. Acting (8 dimensions per time segment): time range, character's goal, emotion change, dialogue trigger word,
   facial action + FACS AU with intensity A–E (onset/peak/offset), gaze + body, voice/breath/pause, end state + listener reaction.
   Emotion arc with protective layer failing (anger → crack → confession), not jumps.
   Grief = physiological leak + self-control + caring for the other.
7. Dialogue: design turn-taking, not lines; overlaps with explicit timings (enter 0.1 s early, 0.2 s overlap);
   disfluency on the hardest word (block, repetition, silence, self-correction); guard: "no turn-by-turn reading, don't auto-complete interrupted lines".
8. Testing: 3–5 s no-dialogue test first; check asset identity, prop relations, head count after camera move, L/R flip on reverse shots.
   Fix only the failing layer. Use segment re-shoot instead of regenerating 30 s.
9. Skin realism (live-action only): 6-part formula; write pore detail only in close-ups.

## Gap for Nightwire
All their work is realistic/live-action look. Anime (NoobAI-XL neon) on Seedance 2.5 is untested → A/B needed.
