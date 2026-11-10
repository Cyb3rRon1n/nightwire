# Character Bible v2 for Every Character + Grey-box Library — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every approved Nightwire character gets a consistent v2 character bible (identity marks + outfit states, each a full matching sheet set in neutral light), and a reusable grey-box library provides stand-in poses and camera setups that drop into any scene for any character.

**Architecture:** Designs gain `identity` and `[wardrobe.<state>]`; `tools/design_studio.py sheets --state` renders a state's set into `design-data/<slug>/wardrobe/<state>/` with neutral-light portrait/expressions; the owner first approves each character's bible TEXT (identity + states) in the Review inbox, then each rendered set. A Blender library (`tools/greybox_library/`) renders posed mannequins on a neutral void from preset cameras (board, depth, pose) and a compositor drops them onto any plate as a grey draft board.

**Tech Stack:** Python 3.12, pytest, ComfyUI API (house NoobAI v-pred, existing pose ControlNet), Blender 4.5 headless on the GPU box, Pillow, the review registry (`tools/review/`).

**Spec:** `docs/superpowers/specs/2026-11-10-character-bible-and-day-films-design.md` (sections 1 and 3). Out of this plan: fal video, look-book warnings, films/wall (later plan).

## Global Constraints

- Worktree `.claude/worktrees/shorts-test`, branch `feat/shorts-production-sheet`; `NIGHTWIRE_DESIGN_DIR=/home/sentinel/projects/github/repos/nightwire/design-data`; python `../../../.venv/bin/python`. Suite green before each commit (1112 passed, 1 skipped at start).
- No AI-attribution trailers; never push without the owner's OK. No fal calls in this plan.
- GPU box: one ComfyUI job at a time; `python -m tools.taste` before a batch; free VRAM after; never touch Ollama. Renders are run by the controller, not implementers.
- Night/neutral only; no explicit content: every outfit state is covered (no bare thighs/cleavage); mature adult characters (house MATURE tags stay).
- Approved originals are never overwritten: v2 sheets live under `design-data/<slug>/wardrobe/<state>/`; existing `turnaround.png` etc. stay until the owner retires them.
- Reviews only through the review registry (`tools/review/producers.py`); ids match `[a-z0-9][a-z0-9-]{0,99}`.
- Neutral light for v2 portrait/expressions: plain mid-grey background, soft even light, no neon/blue tint (the approved E-on-grey turnaround look).

## File map

| File | Responsibility |
|---|---|
| `narrator/designs.py` | `Design.identity: list[str]`, `Design.wardrobe: dict[str, WardrobeState]` (text, tags, props), parse/save/validate |
| `narrator/design_sheets.py` | state-aware prompts: identity + state tags; neutral-light portrait/expression prompts |
| `tools/design_studio.py` | `sheets --state <name>` → `design-data/<slug>/wardrobe/<state>/{turnaround,portrait,expressions,props,colorguide}.png`; `bible-draft` export |
| `tools/review/producers.py` | `bibles` (text approval) and `sheet_sets` (v2 set approval) producers |
| `narrator/worlds/designs/*.toml` | identity + wardrobe states for all 21 characters (data, controller-authored, owner-approved) |
| `tools/greybox_library/{__init__,presets,build,insert}.py` + `blender_library.py` | pose and camera presets, Blender render, compositor onto plates |
| `design-data/greybox-library/` | rendered library (not in git) |
| `docs/greybox-library.md` | how to use the library (owner-readable) |

---

### Task 1: Identity and wardrobe states in designs

**Files:** Modify `narrator/designs.py`; Test `tests/test_designs.py` (append; find the existing design tests with `grep -l load_design tests/`).

**Interfaces — Produces:** `WardrobeState(text: str, tags: str, props: list[str] = [])`; `Design.identity: list[str] = []`; `Design.wardrobe: dict[str, WardrobeState] = {}`; TOML: top-level `identity = [...]`, tables `[wardrobe.<state>]` with `text`, `tags`, optional `props`. `save_design` round-trips them in a stable order after existing keys. Validation (in the existing design validation function): state names match `[a-z][a-z0-9-]*`; every state has non-empty text and tags; a character with any state must have non-empty identity.

- [ ] Step 1: tests — round-trip a design with identity + two states (load → save → load equal); unknown keys in a state rejected; empty text rejected; old designs without the fields load unchanged and save byte-identical.
- [ ] Step 2: run, see fail. Step 3: implement (dataclass field defaults via `field(default_factory=...)`; add `identity`, `wardrobe` to the known-key ordering `_ORDER` so load_design accepts them). Step 4: pass + full suite. Step 5: commit `designs: identity and wardrobe states`.

### Task 2: State-aware, neutral-light sheet prompts and `sheets --state`

**Files:** Modify `narrator/design_sheets.py`, `tools/design_studio.py`; Tests `tests/test_design_sheets.py`, `tests/test_design_studio.py` (append).

**Interfaces — Consumes:** Task 1. **Produces:** `sheet_prompt(d, sheet, mood=None, state: str | None = None)` — when `state` is given: the design's own outfit tags are replaced by `d.wardrobe[state].tags` (drop tags listed in `d.held` that describe clothing — use the existing split between `required` identity-ish tags and outfit tags; where unclear, keep `required` and replace `tags`), `", ".join(d.identity)` is appended to every positive, and for `portrait`/`expressions` the scene STYLE/neon mood is replaced by `NEUTRAL_LIGHT = "plain grey background, soft even studio light, neutral colors, no neon"` with negative additions `"neon, blue light, cyan tint, colored light, rim light"`. `expression_prompts(d, state=None)` and `portrait_prompt(d, state=None)` follow. A `props` sheet for a state renders `d.wardrobe[state].props` (or the design's signature props when empty) as a close-up hands-and-props sheet on grey (reuse the existing props approach if one exists in the codebase — grep `props.png`; otherwise a `sheet_workflow` with "hands and props close-up, product sheet, grey background").
`tools/design_studio.py sheets <slugs> --state <name>`: writes to `design-data/<slug>/wardrobe/<state>/<sheet>.png` (turnaround, expressions, portrait, props, colorguide built from that state's turnaround); never writes the top-level originals; skips existing files unless `--redo`; same Batch progress, one job at a time. `--state all` iterates the design's states.

- [ ] Step 1: tests — `sheet_prompt(d, "turnaround", state="work")` contains the state tags and every identity item and not the replaced outfit tags; portrait/expressions with a state contain NEUTRAL_LIGHT and their negative has "blue light"; CLI writes into `wardrobe/<state>/` (backend faked) and never touches `<slug>/turnaround.png`.
- [ ] Steps 2-5: fail → implement → pass/full suite → commit `design studio: v2 sheet sets per wardrobe state in neutral light`.

### Task 3: Bible text and sheet-set review items

**Files:** Modify `tools/review/producers.py`, `tools/design_studio.py`; Test `tests/test_review_producers.py`.

**Interfaces — Produces:**
- `python -m tools.design_studio bible-draft [slugs]` prints/writes `design-data/bibles/<slug>.md` (identity list, each state's text/tags/props, the approved candidate image path) — the owner-readable draft.
- Producer `bibles(ctx)`: one Item per character with identity or states: id `bible--<slug>--<sha10 of identity+states JSON>`, kind `bible`, stage `designs`, files = web copy of the current `turnaround.png` and `portrait.png` (what exists today, for comparison), context = the bible text. Approving the TEXT is the gate before rendering.
- Producer `sheet_sets(ctx)`: per character and state with all four v2 sheets present: id `sheet--<slug>--<state>--<sha10 over the set's file bytes in sheet order>`, kind `sheet-set`, stage `designs`, files = web copies of the set, compare = the approved original turnaround + portrait, context = identity + state text. Append both to `ALL`.
- `design_studio` refuses `sheets --state` for a character whose bible item has no `keep` verdict in the images API unless `--force` (prevents rendering unapproved bibles); API unreachable → refuse with a clear message.

- [ ] Steps: tests (ids change when text/files change; refuse-without-approval with API faked) → implement → full suite → commit `review: bible text and v2 sheet-set items; render only approved bibles`.

### Task 4: Author the bibles for all 21 characters (data, controller)

**Files:** `narrator/worlds/designs/<slug>.toml` for every approved character.

- [ ] Step 1: for each character, Claude reads the design TOML, the world card (`narrator/worlds/kuroshio.toml` and related) and views the current sheets at full size; writes `identity` (3-6 marks visible on the sheets: scars, prostheses, hair, eyes, tattoos, piercings) and two states by default — `work` (their job outfit, covered) and `offduty` (casual/home, covered) — plus `props` per state. Characters whose world role clearly needs a different pair (e.g. a uniform) get named states accordingly.
- [ ] Step 2: `python -m tools.design_check` (no crash), suite green, commit `designs: v2 bibles (identity + wardrobe states) for all characters`.
- [ ] Step 3: `bible-draft` for all; `python -m tools.review build`; publish. **Owner approves bible texts in the inbox** (Fix notes → Claude edits → republish).

### Task 5: Render v2 sheet sets (controller, GPU queue)

- [ ] Step 1: `python -m tools.taste`; for each character with an approved bible, `python -m tools.design_studio sheets <slug> --state all` in batches of 3 characters (Batch progress shows on the dashboard); free VRAM between batches; Nightwire play tests can be slotted between batches on request.
- [ ] Step 2: Claude reviews every set at full size: identity marks present on every sheet, same outfit across turnaround/portrait/expressions, neutral light, covered outfit, adult look; fixes with `python -m tools.fix_area` (local) or re-renders a sheet with another seed (`--redo --seed`); records each fix in the ledger.
- [ ] Step 3: build + publish inbox; **owner approves each set**; Fix notes loop back to Step 2.

### Task 6: Grey-box library — presets and Blender render

**Files:** Create `tools/greybox_library/__init__.py`, `presets.py`, `build.py`, `blender_library.py`; Test `tests/test_greybox_library.py`.

**Interfaces — Produces:**
- `presets.POSES`: named mannequin poses as bone rotations for the existing 11-bone LAYOUT (reuse `tools/shorts/greybox/blender_build.py` LAYOUT and mannequin builder — import or share, don't copy): at least `stand`, `walk`, `sit-stool`, `sit-ledge` (legs over an edge), `lean-rail` (forearms on a rail), `stand-back` (facing away), `stand-window-back`, `crouch`, `lie-side`, `sit-floor`.
- `presets.CAMERAS`: named setups relative to the figure (distance, height, yaw, lens): `ews-high` (overview from above, figure small), `ws-front`, `ws-back`, `ws-profile`, `ms-front`, `ms-profile`, `mcu-front`, `ots-left`, `ots-right`, `low-hero`, `top-down`.
- `build.py`: `python -m tools.greybox_library build [--poses ...] [--cameras ...] [--height 165]` renders on the GPU box (reuse `tools/shorts/remote.py` patterns) every pose × camera on a neutral grey void floor at 1216x832 into `design-data/greybox-library/<pose>/<camera>/{board.png, depth.png, pose.json, pose.png, meta.json}` — board = flat grey figure on a lighter grey floor with a 1 m grid and a horizon line; depth white = near; pose.json in the format of Task 11/round-4 guides (18 OpenPose points, `back` flag); meta.json = camera (height, pitch, lens) + figure screen box + feet point.
- Unit tests for preset data (every pose has every bone or defaults; every camera has distance/height/yaw/lens; ids are slug-safe) and for build's job list and output paths (remote faked).

- [ ] Steps: tests → implement → py_compile blender_library.py → full suite → commit `greybox library: pose and camera presets, Blender render`. Controller runs the real build and reviews the boards.

### Task 7: Insert a library stand-in into any scene

**Files:** Create `tools/greybox_library/insert.py`; Test `tests/test_greybox_library.py`.

**Interfaces — Produces:** `insert(plate: Path, entry: Path, feet_xy: tuple[float, float], height_frac: float, label: str, out: Path) -> Path` — composites the entry's figure (cut from board.png by its screen box; flat mid-grey silhouette with a thin outline) onto a darkened copy of the plate (plate at 55% brightness) with the figure's feet at `feet_xy` (0..1 fractions) scaled so the figure is `height_frac` of the frame height, and writes a small label (e.g. "C1 Saeko — sit-stool") in a corner tag; also writes the matching scaled `pose.json`/`pose.png` and a depth patch for later guided renders. CLI: `python -m tools.greybox_library insert PLATE POSE CAMERA --feet 0.4,0.92 --height 0.6 --label "C1" --out board.png`. Multiple `--figure` groups allowed for two characters.
Plus `docs/greybox-library.md`: what the library is, the pose and camera names with a thumbnail table (generated), and how a shot picks one.

- [ ] Steps: tests (feet position and scale exact within 2 px; label present; output sizes; two figures) → implement → full suite → commit `greybox library: insert stand-ins into any plate; docs`. Controller makes three sample boards on the izakaya plates and publishes them on the library page (`/shorts/library/`, browse only) for the owner to look at.

---

Final: whole-branch review of Tasks 1-3, 6-7 (most capable model), fixes, then ask the owner before merge/push.

### Task 8: Retire the old sheets (owner request 2026-11-10)

Per character, only after the owner has approved ALL of that character's v2 sets:
- [ ] Move `design-data/<slug>/{turnaround,portrait,expressions,colorguide,props}.png` (and `-old.png` variants, and `design-data/<slug>/shorts/`) into `/home/sentinel/projects/github/repos/nightwire-design-backup-<YYYY-MM-DD>/<slug>/` (archive, not delete); list what moved in the ledger.
- [ ] Point every consumer at the v2 set: the default sheet for a character becomes its first wardrobe state (`work`) — `tools/shorts/prompt.py` expected_refs, `tools/review/producers.py` sheets, `tools/design_studio.py` gallery/review pages, image_studio/stills subject references, `tools/shorts/keyframes.py` compare list. One helper `narrator.designs.sheet_path(design_dir, slug, sheet, state=None)` used everywhere; tests.
- [ ] Rebuild and publish gallery, inbox and wall pages; confirm no page links a moved file (grep the built sites for the old paths).
Permanent deletion of the archive only if the owner asks again.
