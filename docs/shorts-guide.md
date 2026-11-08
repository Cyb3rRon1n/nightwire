# Shorts studio guide

Foyege-style AI shorts: a written short plus a Blender grey-box drive a video model, and the owner reviews takes on a page. Spec: `docs/superpowers/specs/2026-11-08-shorts-studio-design.md`. Method research: `docs/superpowers/research/2026-11-08-foyege-method.md`.

Shorts are promotion and personal use. Art rules in `docs/art-direction.md` apply; no adult content, no daytime scenes.

## Setup

- Run every command from the repo root of the main checkout so `design-data/` resolves (or set `NIGHTWIRE_DESIGN_DIR`). The CLI validates against all designs, so unapproved or `new:` cast members are caught by `check`.
- `FAL_KEY` goes in `~/.config/nightwire/secrets.env` (chmod 600), entered by the owner. Never print or commit it.
- Blender 4.5.15 LTS lives on the GPU box at `~/opt/blender` (host `NIGHTWIRE_BLENDER_HOST`, path `NIGHTWIRE_BLENDER`). Local ffmpeg is needed; the grey-box video uses libx264 if present, else libopenh264 (Fedora has only openh264).
- `idcheck` needs the `qa` extra: `pip install -e ".[qa]"`.

## Where files live

- Script (committed): `narrator/worlds/shorts/<slug>/short.toml` plus `shots/S01.toml`, `S02.toml`, ...
- Work files (git-ignored): `design-data/shorts/<slug>/` with `scene.json`, `floorplan.png`, `costs.json`, `draft.mp4`, and per shot `shots/<id>/{frames/,greybox.mp4,bundle/,takes/tNNN.mp4+.json,verdicts.json}`.

## The loop

Commands are `python -m tools.shorts <command> <slug> ...`. Pilot slug: `saeko-rin-izakaya`.

1. Write `short.toml` (cast, place, style, beats, room blocks, figure keys, `budget_usd`) and one TOML per shot (camera keys, `[state]`, beats, acting, lines).
2. `check <slug>` validates cast approval, place, figures, shot length (max 30 s), line times and disfluency names.
3. `prompt <slug> S01` prints the layered prompt for a shot; it fails if L2/L4 contain position words.
4. `greybox <slug> [--tint]` writes `scene.json`, renders on the GPU box over rsync+ssh, pulls frames back and encodes `shots/<id>/greybox.mp4`. `--tint` colours mannequins from each design's palette (for A/B). `--local` runs a local Blender instead. Free ComfyUI VRAM and unload Ollama first; one GPU job at a time.
5. `page` builds the review page and prints the `rsync` command; run it, then open http://192.168.10.19:8080/shorts/.
6. Review there: mark each take keep / reject with a note. The page writes to the design-picks images API.
7. Get takes, either way:
   - Manual: `bundle <slug> S01` writes prompt plus reference files to upload to any web tool; put the result in via `inbox <slug> S01 --cost 0.4 --model seedance-2.0`.
   - fal: `submit <slug> S01 --model kling-3 [--seconds N] [--yes]` shows the estimate and asks y/N (skip with `--yes`).
8. `idcheck <slug> S01 t001` (needs `qa` extra and a real take) prints a face-identity report per cast member. Not yet run on a real take.
9. `verdicts <slug>` pulls review verdicts into `shots/<id>/verdicts.json`; `status <slug>` lists shots, takes, verdicts and spend.
10. `assemble <slug> [--music bed.mp3]` writes `draft.mp4`: newest kept take per shot, mixed takes normalised to 1280x720 / 24 fps (silence added if a take has no audio), subtitles burned from the script lines.

## Models, cost and the spend guard

- fal models: `seedance-2.5`, `seedance-2.0`, `seedance-2.0-fast`, `kling-3`. Minimum clip length: Seedance 4 s, Kling 3 s. Veo 3.1 Fast was left out because fal removes that endpoint 2026-11-17.
- `RATES` (USD per second) are in `tools/shorts/takes.py`. Only Kling's rate was confirmed on fal's pricing page (2026-11-08); re-check the Seedance prices before the first paid run.
- Each job's cost goes into `costs.json` as soon as fal accepts it (ledger id `req-<request_id>`).
- `submit` refuses when spent + estimate would pass `budget_usd` in `short.toml` (default 25). To continue, raise `budget_usd` there; that is the owner's call.
- Anything that spends money or downloads software needs the owner's go-ahead at that step.

## Prompt layers

Each fact is stated once. `prompt` assembles them in order:

- L1 grey-box role: the video gives camera, positions, silhouettes and timing; replace mannequins with characters. Camera comes from the shot `summary`.
- L2 who is who: `C1 = <name> (refs C1_*)` from `[cast]`.
- L3 look: `style` from `short.toml`.
- L4 character state: one line per cast id from the shot `[state]`.
- L5 timecodes: beats, acting blocks and spoken lines merged by time.

Rules: L2 and L4 reject position words (left, right, behind, beside, near, at the counter...); positions belong to the floor plan, grey-box and L5 camera terms. L5 times are relative to each shot's start. In shot TOML, `beats`, `acting` and `lines` times are absolute on the short's timeline, but camera key `t` is seconds from the shot's start (`check` rejects keys outside 0..duration). Disfluency is one of `block`, `repeat`, `silence`, `self-correct`; lines may set `early_s`, `overlap_s`, `on_word`.

## Acting block (8 dimensions)

Each `[[acting]]` entry: `who`, `t`, `goal`, `emotion`, then optional `trigger` (trigger word), `face`, `gaze`, `voice`, `end`. Cite FACS action units with onset/peak times. Filled example from the pilot (S01):

```toml
[[acting]]
who = "C1"
t = [0.0, 8.0]
goal = "free the hand before anyone sees it"
emotion = "irritation held under a polite surface, a jolt of alarm when the noren moves, smoothed back to calm"
face = "AU4 brow lowerer B as the fingers will not open (onset 0.5 s, peak 1.5 s); AU24 lip presser C when the noren moves (peak 2.3 s); released to a neutral polite mouth by 6.0 s"
gaze = "eyes on the hand, flick to the door at 2.0 s, back down at 3.0 s; shoulders still, no turn of the head"
voice = "one slow breath out through the nose at 1.0 s; silent"
end = "left hand resting over the chrome hand, eyes on the counter, not on C2"
```

## Grey-box notes

- Room is in metres; `at` of a block is its bottom centre. Figure keys are `[t, x, y, facing]` on the shared timeline.
- Each shot renders frames `[start, end)` numbered from 0000.
- `pose = "sit"` lowers the figure so hips sit on a 0.45 m stool. One pose per figure for the whole short; changing pose over time is not supported yet.

## Pilot

"Resting": Saeko (C1) and Rin (C2) at Mama Sato's, 3 shots, 24 s. Grey-box built (`design-data/shorts/saeko-rin-izakaya` and `-grey`, with `--tint` for A/B); awaiting owner review on /shorts/. The anime A/B paid test (plan Task 13) has not been run; it needs the owner's fal account and go-ahead.

## Review page hosting

nginx location and the dashboard "Shorts" tile are deployed on the GPU box; config lives in the private homelab-ops repo under `gpubox/`.
