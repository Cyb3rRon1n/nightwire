# Day Film: Wall, Draft Boards, Animatic — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Plan a character's "day" film as an ordered set of scenes and shots, see it as a storyboard wall built from grey-box stand-ins on real location plates, and play it as a timed animatic — all free, before any fal spend.

**Spec:** `docs/superpowers/specs/2026-11-10-character-bible-and-day-films-design.md` sections 3-4 (draft boards, films, wall). Owner asked 2026-11-10 for: (1) the storyboard wall for Saeko's day, (2) new plates for her scenes, (3) animatics.

## Global Constraints
- Worktree `.claude/worktrees/shorts-test`; `NIGHTWIRE_DESIGN_DIR=/home/sentinel/projects/github/repos/nightwire/design-data`; python `../../../.venv/bin/python`; suite green; no AI trailers; no push; stage only own files.
- No fal calls. No local character renders (grey stand-ins only). Night only.
- Reviews only through the review registry; pages browse-only, built with textContent / html.escape.
- GPU box: one ComfyUI job at a time; Blender runs one at a time.

### Task 1: Films, scene shots as boards, wall page, film inbox item (code)
- `narrator/worlds/films/<slug>.toml`: `title`, `character`, `logline`, `mood`, ordered `scenes` (short slugs). Loader `tools/shorts/film.py: load_film(slug) -> Film` with validation (scenes exist).
- A scene is a short (existing model). Its shots gain an optional `[[board]]` list per keyframe: `which = "start"|"end"`, `figure = "C1"`, `pose`, `camera` (grey-box library names), `feet = [x, y]`, `height` (0..1 of frame), plus shot-level `plate` (existing). Validation: pose/camera exist in the library presets.
- `python -m tools.shorts boards <short> [shot]`: builds `shots/<id>/board-<which>.png` via `tools.greybox_library.insert` (multi-figure) on the shot's plate file (plates.plate_path); missing plate → a dark placeholder card with the plate name, so drafting never blocks.
- `python -m tools.shorts wall <film>`: page at `design-data/shorts/_site/films/<film>/index.html` — columns = scenes in order (title, time of day from the scene bible, place, wardrobe state per cast member, mood line), cards = shots (board thumbnail, size, camera move, duration, one-line action, look-book warnings if present); browse-only; link to the inbox.
- Producer `films(ctx)`: one inbox item per film, id `film--<slug>--<sha10 over the film TOML + every scene's shot TOMLs + board pngs>`, kind `wall`, stage `pre-production`, files = board thumbnails (≤12), context = scene/shot list text.
- Tests for each (loader, validation, board build with a fake plate + the real library format, wall page contents, id changes).

### Task 2: Animatic (code)
- Promote the scratchpad lights tool into `tools/lights.py` (same CLI/behaviour: light breathing, train/sweep options) — copy from `/tmp/claude-1000/-home-sentinel-projects-github-repos/905ac549-af5c-4e4d-81b5-e6573f62d065/scratchpad/lights.py`, keep it importable (`animate(still, out, seconds, fps, size, seed, strength, ...)`).
- `python -m tools.shorts animatic <film> [--fps 24]` → `design-data/shorts/_site/films/<film>/animatic.mp4`: for every scene and shot in order, the shot's start board for its duration (end board crossfades in over the last 1 s when present); camera `move` mimicked: "slow push-in" = slow centred zoom 1.00→1.06, "slow pan" = slight horizontal drift, static = still; plate lights breathe via tools.lights on the plate area (skip if too slow: lights only for shots ≤ 10 s, cache per plate); a lower-third caption (scene title · shot id · action) and 0.5 s black between scenes. Encode with the existing remote.encode/h264 helper. Link it on the wall page.
- Tests: frame count = Σ durations × fps (+ gaps), caption text present (render one frame), move zoom math.

### Task 3: Saeko's day — data + plates (controller)
- Film `saeko-one-night`; scenes (shorts): `saeko-wake` (danchi-block, her room), `saeko-ring-line` (ring-line platform/train), `saeko-collection` (ikebe-low alley, a repo job, her crew implied off-frame), `saeko-rin-izakaya` (existing pilot, re-planned in look-book grammar), `saeko-rooftop` (tenjo-heights or danchi roof over the city), `saeko-home` (danchi-block, alone, amber wrist light). 3-5 shots each, near-wordless, look-book grammar (WS/EWS, static or slow push, backs/profiles/silhouettes), each with scene bible, wardrobe state, plate names, boards.
- Plate catalogues for each place (narrator/worlds/plates/<place>.toml) and plate renders on the GPU (`shorts plates`), Claude picks candidates at full size; owner approves plates in the inbox.
- Build boards, wall, animatic; publish; owner reviews the wall item.
