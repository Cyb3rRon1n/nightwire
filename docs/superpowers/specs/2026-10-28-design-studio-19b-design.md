# Nightwire Design Studio Design: Phase 19b

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-28.

Phase 19 split (owner-approved):
- **19a** (shipped): the image look.
- **19b** (this spec): the **design studio**, which makes model sheets and location designs, reviewed by the owner.
- **19c:** designs in play. Players design their look at creation, and scenes and portraits reuse saved designs.
- **19d:** stronger identity, meaning per-character LoRA or IPAdapter, and multi-character scenes, after a hardware test.

## Owner decisions (2026-10-28)

- **Model sheets for characters**, for consistency and in case the owner later makes an animated short. Each approved character gets three sheets: a turnaround, an expression sheet and a colour guide with callouts.
- **Location design sheets too**, for landmarks and frequent places: an establishing shot, an alternate angle, mood keys and props.
- **Storage:** option A. Small design records go in git; full-size images go in a data folder outside git, plus a zip export.
- **Review:** option A. Each design gets **4 candidates** per round; the owner picks one or asks for a reroll with notes; only picked designs get full sheets.
- **Scope:** option A. All **22 designs** in the first batch: 11 NPCs, 6 districts and 5 key places.
- **Tooling:** approach 1. A command-line studio plus the published review gallery; the owner replies in chat with picks and notes, and the controller applies them. Drafts are written from the world cards; the narrator model never invents a design.
- **Future studio track** (recorded in the ROADMAP, not built here):
  - more animation pre-production sheets: pose/action sheets, mouth and lip-sync charts, hand sheets, a height line-up, costume variants, colour script, prop and vehicle sheets (the chrome catalog first), faction graphics, FX sheets, and storyboard or animatic export from session logs;
  - a **stage view**, a visual-novel-style presentation that shows location art plus the speaking NPC with a matching expression over free-text play;
  - a clickable **district map**.

## Research grounding

- **Consistency on 8 GB** (`docs/superpowers/research/2026-10-28-19b-character-consistency.md`): build tag blocks, a fixed seed and an owner-approved sheet first. These cost no VRAM. They hold hair, eye and outfit colours, but not exact face geometry. Put identity tags first, because later tags dilute them ([OC consistency guide](https://rentry.org/OC-creation-and-character-consistency-with-NAID), [Illustrious prompt guide](https://civarchive.com/articles/23210)).
- **Sheet tags** (`character sheet, reference sheet, turnaround, multiple views, front view, from side, from behind, simple background, white background`; `expressions, expression chart`; `color guide`) were verified on the 19a stack by the 2026-10-28 Rook preview. That preview found two problems to fix: both arms came out mechanical, and the hair drifted between expression panels.
- **Standard animation pre-production practice:** model sheets (turnarounds), expression sheets and colour models for characters; location designs, colour keys and prop sheets for environments. This is the source of the future studio-track list.

## Design

### 1. Design records (in git)

There is one file per design: `narrator/worlds/designs/<slug>.toml`. The slug is the lowercase name with ASCII hyphens; ō becomes o.

```toml
name = "Mama Sato"
kind = "character"              # "character" | "location"
source = "npc:Mama Sato"        # "npc:<name>" | "district:<name>" | "place:<label>"
presentation = "feminine"       # characters only: feminine | masculine | androgynous
tags = "..."                    # identity block, identity-first ordering (below)
negative = ""                   # per-design negatives, e.g. "two mechanical arms"
alt_tags = ""                   # locations only: interior / reverse-angle content tags
props = []                      # locations only: signature props, each a short tag phrase
status = "draft"                # draft | candidates | approved
seed = 0                        # approved candidate seed (0 until approved)
palette = []                    # "#rrggbb" strings from the approved sheet
notes = []                      # dated review history, e.g. "2026-10-29 reroll: older, thinner"
```

**Tag ordering:**
- **Characters:** subject (from presentation, or `1other, android` for a tsukumogami), then **hair**, then face and eyes, then build and age, then outfit, then signature chrome or props, which must name their side: "mechanical left arm, human right hand".
- **Locations:** subject (`scenery, no humans`), then place type, then architecture, then signage, then lighting, then weather.

**Module `narrator/designs.py`:**
- `Design` is a dataclass mirroring the fields above.
- `load_design(path) -> Design` raises `ValueError` on:
  - an unknown kind or status;
  - a missing name or tags;
  - `presentation` set on a location, or `alt_tags` or `props` set on a character;
  - `status = "approved"` with `seed = 0`.
- `load_designs(dir) -> dict[slug, Design]`.
- `save_design(design, path)` writes TOML with a stable field order. It is the only writer; the CLI uses it.

**World access:** `World.designs` gives read-only access, loaded lazily. Nothing in gameplay reads it in 19b.

### 2. Images (outside git)

They live in `NIGHTWIRE_DESIGN_DIR`, default `./design-data/`, which goes in `.gitignore`. The layout:
- `<slug>/candidates/r<round>-c<n>-<seed>.png`: the 4 candidates for each round.
- **Approved character sheets:** `<slug>/turnaround.png`, `expressions.png` and `colorguide.png`.
- **Approved location sheets:** `<slug>/establishing.png`, `alternate.png`, `moodkeys.png` and `props.png`.
- `gallery/index.html` plus web-size JPEG copies for review.
- `exports/nightwire-designs-<date>.zip`.

### 3. Rendering (`narrator/design_sheets.py`)

It reuses the 19a look: the `NoobAI-XL-Vpred-v1.0` checkpoint, `ModelSamplingDiscrete(v_prediction, zsnr)`, `RescaleCFG 0.6`, Smooth Booster 0.6, Euler, CFG 4.5, 28 steps, clip skip 2, the `QUALITY` string, and `NEGATIVE` plus the design's `negative`. It builds ComfyUI workflow dicts (pure functions, so they're testable) and submits them through `ComfyUIBackend`'s client and poll path, with an added upscale chain.

**Candidates:** 1216×832, single pass, about 30 s each. Seeds are random and recorded in the filename.
- **Character:** `SHEET_STYLE` + the turnaround tags + the design tags.
- **Location:** the 19a `STYLE` + the design tags.

**Full sheets** use the approved seed. The base is 1216×832, then a refine pass, then upscaling to **3648×2496**. Character sheets take about 100 s each:
- **Refine pass:** `UpscaleModelLoader(2x-AnimeSharpV2_RPLKSR_Soft.pth)`, then `ImageUpscaleWithModel`, then `ImageScaleBy 0.75`, then `VAEEncodeTiled`, then a KSampler (20 steps, denoise 0.35), then `VAEDecodeTiled`.
- **Final upscale:** a second `ImageUpscaleWithModel` takes it to 3648×2496.

The strings:
- `SHEET_STYLE = "anime coloring, cel shading, thick outlines, official art, flat lighting, simple background, white background"`
- `SHEET_NEGATIVE_EXTRA = "scenery, background clutter, inconsistent outfit, different clothes, different hairstyle"`. It is used for character sheets, and "text" is removed from the base negative so callout labels can appear.

**The character sheets:**
- **turnaround:** `character sheet, reference sheet, turnaround, multiple views, front view, from side, from behind, full body, standing`
- **expressions:** `expressions, expression chart, multiple views, portrait, upper body, smile, angry, surprised, sad, smirk, closed eyes`
- **colorguide:** `character sheet, reference sheet, color guide, multiple views, full body, front view, from behind, close-up`, plus the first signature-chrome or prop tag with `focus` appended (e.g. `mechanical left arm focus`).

**The location sheets:**
- **establishing:** the candidate prompt, high-res.
- **alternate:** the location's `alt_tags` replace the design tags after the subject.
- **moodkeys:** three single-pass 1216×832 renders, each adding `night, neon lights`, `rain, wet street` or `dawn, sunrise, soft light`. They are joined left to right into one 3648×832 strip with Pillow.
- **props:** `still life, no humans, object focus, multiple views, white background`, plus the joined `props`, with `SHEET_STYLE` and the high-res chain.

**Palette:** `extract_palette(png_path, n=6) -> list[str]` uses Pillow's `quantize(colors=n)` on a 256-px thumbnail, sorted by pixel count. It runs on the approved turnaround (characters) or establishing shot (locations) and is saved to the design.

**GPU etiquette:** before a batch, unload Ollama (`keep_alive: 0` to `OLLAMA_HOST`); after a batch, `POST /free` to ComfyUI with `unload_models` and `free_memory`.

### 4. CLI (`tools/design_studio.py`, run as `python -m tools.design_studio`)

- `candidates <slug…> | --all-drafts | --rerolls`: renders 4 candidates for each named design. It sets `status = "candidates"` and the next round number, and records `notes += "<date> round <n>: 4 candidates"`. `--all-drafts` covers every design with status draft; `--rerolls` covers every design whose last note starts with "reroll".
- `approve <slug> <n> [--round r]`: sets the seed from candidate `n` of the latest (or given) round, `status = "approved"`, and adds a note.
- `reroll <slug> "<note>"`: appends `"<date> reroll: <note>"`. The controller edits the tags by hand from the note before the next `candidates --rerolls`.
- `sheets <slug…> | --approved-missing`: renders the full sheet set for approved designs and sets `palette`.
- `gallery`: writes `design-data/gallery/index.html` plus JPEG copies (1100 px longest side). Each design shows its 4 latest candidates numbered #1–#4, its current tags and notes, and the approved sheets if it has them. It uses the published page's dark style; the controller republishes it to the owner's gallery link.
- `export`: writes one zip with every approved design's TOML, its sheets, and `index.html`.

All commands take `--comfyui-url` (default `COMFYUI_URL`) and `--design-dir` (default `NIGHTWIRE_DESIGN_DIR`).

### 5. The 22 drafts

The controller writes them from the world cards during implementation:
- **Characters (11):** Mama Sato, Old Hara, Jun Arakawa, Saeko Kirigaya, Hoshikawa Tadamori, Hoshikawa Rei, Brother Tōru, Kenji Moro, Captain Ide, Mitsu, and Hachi (a tsukumogami, so `1other, android`).
- **Districts (6):** Tenjō Heights, Hanabira-chō, Ikebe Low, Kuroshio Docks, The Loop and the Yomi Line.
- **Places (5):** Mama Sato's izakaya, Old Hara's clinic, Jun Arakawa's karaoke box, the Hoshikawa penthouse and Hachi's pier.

Each draft's notes start with `"2026-10-28 draft from world card"`.

## Review loop (operations, not code)

1. `candidates --all-drafts`, run overnight; about 45 min for 88 candidates.
2. `gallery`, then the controller republishes to the owner's gallery link.
3. The owner replies per design: `pick #n`, `reroll: <notes>`, or `skip`.
4. The controller runs `approve` or `reroll` and edits the tags, then runs `sheets --approved-missing` and `candidates --rerolls`, and loops.
5. When all 22 are approved, run `export`, and the controller commits the approved TOMLs.

## Testing

**Unit tests:**
- `load_design` validation: each error case, plus a valid character and a valid location.
- A `save_design` and `load_design` round trip, with stable ordering.
- Slugs, including ō becoming o and spaces becoming hyphens.
- Prompt assembly: the identity block follows the sheet tags; the colour-guide focus tag; location sheet prompts including the alt tags and the mood suffixes; the per-design negative appended.
- Workflow graphs: the candidate is a single pass at 1216×832; a full sheet has the upscale chain, ImageScaleBy 0.75, a refine at denoise 0.35, a second model upscale, and the v-pred and LoRA nodes.
- Mood-key strip: three 1216×832 images joined into 3648×832.
- `extract_palette` on a synthetic image with known colours.
- The CLI against a fake ComfyUI client and a temp dir: `candidates` writes 4 files and updates the status and round; `approve` sets the seed and status; `reroll` appends a note; `sheets` writes the expected filenames and the palette; `gallery` writes the HTML; `export` zips the approved designs only.
- All 22 committed draft TOMLs load, and the 11 NPC sources match the world's NPC names.

**Live** (GPU box):
- candidates for one character (Mama Sato) and one location (Mama Sato's izakaya);
- a full sheet set for each after the controller approves #1 for the test;
- record timings and peak VRAM;
- then run `candidates --all-drafts` as **review round 1** for the owner.

## Not in this phase

- **19c:** player design at creation, and casting designs into scenes and portraits.
- **19d:** LoRA or IPAdapter identity, and multi-character regional prompting.
- **The studio track:** pose, mouth, hand and height sheets, costume variants, colour script, prop, vehicle and chrome-catalog sheets, faction graphics, FX sheets, and storyboard export.
- **The stage view and the district map.**
