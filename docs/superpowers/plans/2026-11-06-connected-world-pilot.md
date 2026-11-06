# Connected World Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the Ring Line and class manners into the game text, add the pilot places as location designs, and render the 7 pilot images for owner review.

**Architecture:**
- **Game text:** lives in `narrator/worlds/kuroshio.toml`, which is checked by `narrator/world.py` at load time.
- **Locations:** each pilot place is a location `Design` in `narrator/worlds/designs/`. The Ring Line uses source `district:Ring Line`, so the existing district tests cover it. The other new places use the `new:` source, the convention for later additions.
- **Images:** rendered by a throwaway lab script with the existing `sheet_prompt` and `sheet_workflow` (location) and `natural_scene_workflow` (Shinji). They are published to the World Gallery for owner review. Day versions wait until the owner picks originals.

**Tech Stack:** Python 3.12, pytest, TOML, ComfyUI at 192.168.10.19:8188 (NoobAI v-pred SDXL), Playwright for the gallery check.

**Spec:** `docs/superpowers/specs/2026-11-06-connected-world-design.md`

## Global Constraints

- Cards: standalone, at most 400 characters, with unique names and aliases (`_MAX_CARD_CHARS = 400`).
- The primer plus glossary block must stay at or under 1900 characters (`_MAX_SYSTEM_BLOCK_CHARS`). It is at 1896 today, so every addition must be paid for by a cut.
- Use Japanese words only from the glossary.
- Images:
  - Adults only, with no nudity or gore.
  - Medium dark scene look.
  - Every image is reviewed at full size before it is published.
  - Local fixes use `tools/fix_area.py`.
  - Licensed sources only; photos are never used as references.
- Cyberpunk always shows. Even a traditional room shows the neon city outside, and the amount depends on class.
- Day versions are made only from an approved night original.
- Commit only when the owner asks. Never add Co-Authored-By or AI trailers. Pushes need the owner's approval.
- The ComfyUI box is a laptop GPU (8 GB). Render one job at a time.

---

### Task 1: Ring Line, class line and Kaede's bio in the game text

**Files:**
- Modify: `narrator/worlds/kuroshio.toml` (primer, new `[[district]]` after The Loop)
- Modify: `narrator/worlds/designs/kaede-mori.toml:6` (bio)
- Create: `narrator/worlds/designs/ring-line.toml`
- Test: `tests/test_world.py::test_shipped_kuroshio_world_loads`, `tests/test_design_drafts.py::test_all_23_drafts_load`

**Interfaces:**
- Produces: district `Ring Line`, with aliases `the Ring`, `Ring Line station`. Design slug `ring-line`, used by Task 3.

- [ ] **Step 1: Update the shipped-world tests first**

In `tests/test_world.py::test_shipped_kuroshio_world_loads`:
```python
    assert len(world.districts) == 7
    assert "Ring Line" in world.system_block()
    assert "quiet tradition" in world.primer
```
In `tests/test_design_drafts.py`, rename the test to `test_all_24_drafts_load` and change `== 23` to `== 24`.

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/python -m pytest tests/test_world.py::test_shipped_kuroshio_world_loads tests/test_design_drafts.py -q`
Expected: FAIL. There are 6 districts, the system block has no Ring Line, and there are 23 drafts.

- [ ] **Step 3: Edit the primer**

Make three exact replacements in the `primer` string of `narrator/worlds/kuroshio.toml`:
- `"Kuroshio, a Pacific megacity in Japan, 2089, named for the black ocean current that feeds its port."` → `"Kuroshio, a Pacific megacity in Japan, 2089."`
- `"The Loop, Yomi Line."` → `"The Loop, Ring Line, Yomi Line."`
- `"Atop Tenjō Heights the keiretsu families live as corporate royalty."` → `"Keiretsu families live atop Tenjō in quiet tradition; corporate money is loud; the street is wired."`

Measured result: 1884 of 1900 characters.

- [ ] **Step 4: Add the district card after The Loop's**

```toml
[[district]]
name = "Ring Line"
aliases = ["the Ring", "Ring Line station"]
card = "The Ring Line is the commuter loop under the expressway, stopping in every district but Tenjō: packed cars, the same line colour and signs everywhere, hub stations swallowed by shopping arcades and underground malls, Hoshikawa payment ads on every wall. Hazard: a red status light gets you turned back at the gate. Hook: a train keeps stopping at a station sealed twenty years ago."
```

- [ ] **Step 5: Add the Ring Line design** (`narrator/worlds/designs/ring-line.toml`)

```toml
name = "Ring Line"
kind = "location"
source = "district:Ring Line"
tags = "train station, platform, commuter train, station signs, line color stripe, ticket gates, shopping arcade, escalator, crowd barriers, fluorescent lights, advertisement screens, neon signs, vending machine, tiled floor, overhead cables, elevated tracks, night"
negative = "rural, countryside, steam locomotive"
alt_tags = "underground mall, shopping arcade, shop fronts, advertisement screens, escalator, station signs, tiled floor, night"
props = ["ticket gate", "line map", "vending machine", "station clock"]
status = "draft"
seed = 0
palette = []
notes = ["2026-11-06 draft from the connected world spec"]
```
The drafts test requires 12 to 25 tags, a first note starting with a date and then "draft", `alt_tags`, 3 to 5 props, and no "scenery" in the tags. This file meets all of them.

- [ ] **Step 6: Fix Kaede's bio**

In `narrator/worlds/designs/kaede-mori.toml`, change `"A courier and street racer on the Yomi Line. Fast, cheerful and rarely off her bike."` to `"A courier and street racer on the Loop. Fast, cheerful and rarely off her bike."`

- [ ] **Step 7: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, with a count of 752 or more. If a test pins the old primer text or the district count elsewhere, update it to the new value. Don't weaken it.

- [ ] **Step 8: Live narrator check (a mocked suite is not enough)**

Run a short session against the real local model with the action `"I take the Ring Line to Ikebe Low."`. Check that:
- the narration mentions the Ring Line;
- the location updates to a district;
- the tone holds.

Use the same live-check approach as the debt-society work, with the existing `scratchpad/lab/live.py` as the pattern. Record the narration excerpt in the task report.

- [ ] **Step 9: Commit (only if the owner has asked)**

```bash
git add narrator/worlds/kuroshio.toml narrator/worlds/designs/ring-line.toml narrator/worlds/designs/kaede-mori.toml tests/test_world.py tests/test_design_drafts.py
git commit -m "world: add the Ring Line, class line in the primer, Kaede races the Loop"
```

---

### Task 2: Pilot place designs

**Files:**
- Create in `narrator/worlds/designs/`:
  - `ogane-precinct.toml`
  - `old-family-house.toml`
  - `danchi-block.toml`
  - `rins-room.toml`
- Test: `tests/test_designs.py` (new test)

**Interfaces:**
- Produces: slugs `ogane-precinct`, `old-family-house`, `danchi-block` and `rins-room`, all `kind = "location"`, with the source prefix `new:`. Task 3 renders them with `sheet_prompt(design, "establishing")`.

- [ ] **Step 1: Write the failing test**

```python
def test_pilot_places_load_as_new_locations():
    from narrator.designs import DESIGNS_DIR
    designs = load_designs(DESIGNS_DIR)
    for slug in ("ogane-precinct", "old-family-house", "danchi-block", "rins-room"):
        d = designs[slug]
        assert d.kind == "location" and d.source.startswith("new:") and d.status == "draft", slug
        assert "night" in d.tags and "neon" in d.tags, slug  # cyberpunk always shows
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest tests/test_designs.py::test_pilot_places_load_as_new_locations -v`
Expected: FAIL with `KeyError: 'ogane-precinct'`.

- [ ] **Step 3: Write the four files**

`ogane-precinct.toml`: the island office, with the chief at the head and the harbour outside.
```toml
name = "Ōgane precinct"
kind = "location"
source = "new:Ōgane precinct"
tags = "police station interior, open-plan office, rows of desks, one large desk at the head of the room, computer monitors, case files, whiteboard, wall screens, window blinds, harbor cranes outside the window, neon signs outside, fluorescent lights, night, indoors"
negative = "classroom, school, courtroom"
alt_tags = "holding cells, police counter, wanted posters, wall screens, fluorescent lights, night, indoors"
props = ["case file", "desk lamp", "duty roster", "radio"]
status = "draft"
seed = 0
palette = []
notes = ["2026-11-06 draft from the connected world spec: Captain Ide and Shinji's workplace at the Docks"]
```
`old-family-house.toml`: quiet wood, with the cyberpunk city below.
```toml
name = "Old-family house"
kind = "location"
source = "new:Old-family house"
tags = "traditional japanese house, wooden veranda, tatami, shoji, zen garden, stone lantern, pine tree, koi pond, on top of a skyscraper, neon city far below, skyscrapers, holographic billboards in the distance, night, moonlight"
negative = "ruins, abandoned, modern furniture"
alt_tags = "tea room, tatami, tokonoma, hanging scroll, tea set, shoji, neon city through the window, night, indoors"
props = ["stone lantern", "tea set", "hanging scroll", "bonsai"]
status = "draft"
seed = 0
palette = []
notes = ["2026-11-06 draft from the connected world spec: Hoshikawa family home atop Tenjō"]
```
`danchi-block.toml`: working households.
```toml
name = "Danchi block"
kind = "location"
source = "new:Danchi block"
tags = "public housing apartment blocks, identical concrete buildings, open-air corridors, balconies, laundry hanging, air conditioner units, satellite dishes, neon signs, small shop at ground level, vending machines, bicycles, elevated train track, night, rain"
negative = "luxury, skyscraper, ruins, abandoned"
alt_tags = "open-air corridor, apartment doors, potted plants, laundry, fluorescent lights, neon city in the distance, night"
props = ["bicycle", "laundry pole", "mailboxes", "vending machine"]
status = "draft"
seed = 0
palette = []
notes = ["2026-11-06 draft from the connected world spec: Shinji's and Saeko's homes"]
```
`rins-room.toml`: cramped, wired and lived-in, not ruined (owner note: "post apocalyptic").
```toml
name = "Rin's room"
kind = "location"
source = "new:Rin's room"
tags = "small apartment room, lived-in, clean, multiple computer monitors, glowing screens, keyboard, cables neatly bundled, bed, snacks, posters, figurines, neon signs through the window, city lights, pink and cyan lighting, night, indoors"
negative = "ruins, rubble, abandoned, broken, dirty, dust, post-apocalypse, debris"
alt_tags = "desk with monitors, gaming chair, energy drink cans, sticky notes, neon window, night, indoors"
props = ["monitor", "keyboard", "headset", "energy drink"]
status = "draft"
seed = 0
palette = []
notes = ["2026-11-06 draft from the connected world spec: Rin's stacked-block room, redone"]
```

- [ ] **Step 4: Run the test and the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass. `kuroshio_designs()` still counts 24, because `new:` sources are excluded.

- [ ] **Step 5: Check that the design studio still lists them**

Run: `.venv/bin/python -m pytest tests/test_design_studio.py tests/test_image_studio.py -q`
Expected: pass. If a test pins the total number of designs, update the number and say so in the task report.

- [ ] **Step 6: Commit (only if the owner has asked)**

```bash
git add narrator/worlds/designs/ogane-precinct.toml narrator/worlds/designs/old-family-house.toml narrator/worlds/designs/danchi-block.toml narrator/worlds/designs/rins-room.toml tests/test_designs.py
git commit -m "designs: pilot places for the connected world"
```

---

### Task 3: Render the pilot (throwaway lab script)

**Files:**
- Create: `$S/lab/pilot.py`, where `$S` is the session scratchpad. It is not committed.
- Output: `$S/lab/pilot/*.png`

**Interfaces:**
- Consumes: the slugs from Tasks 1 and 2, plus the existing `ikebe-low` and `shinji-okubo` designs.
- Produces: `pilot/<slug>-<seed>.png`, with two seeds each (52817, 70342), and `pilot/shinji-okubo-<n>.png`.

- [ ] **Step 1: Write the script**

```python
"""Connected-world pilot: new places in the medium dark look, a new Ikebe original, and Shinji at his desk. Throwaway. Skips files that exist."""
import asyncio, io
from pathlib import Path
from PIL import Image
from narrator.designs import load_design
from narrator.design_sheets import SCENE_SIZE, front_figure, lift_blacks, natural_scene_workflow, scene_prompt, sheet_prompt, sheet_workflow
from narrator.comfyui_backend import ComfyUIBackend
from tools.design_studio import _scene_face
from tools.scene_images import square_on_blur

L = Path(__file__).parent
out = L / "pilot"
out.mkdir(exist_ok=True)
b = ComfyUIBackend("http://192.168.10.19:8188")
SIZE = (1344, 768)
SEEDS = (52817, 70342)
EMPTY = "scenery, no humans, deserted"
NOPE = "(1girl:1.5), (1boy:1.5), (person:1.5), people, human, figure, silhouette, solo, standing, child"
# Owner: Ikebe was "not getting cyberpunk vibes". Same alley, but the poorest district is the most wired.
IKEBE_MORE = "dense neon signs, hand-painted neon kanji, tangled cables overhead, status lights, vending machines, holographic ads, steam vents, cyberpunk"


async def place(slug, extra=""):
    p, n = sheet_prompt(load_design(Path(f"narrator/worlds/designs/{slug}.toml")), "establishing")
    for seed in SEEDS:
        f = out / f"{slug}-{seed}.png"
        if not f.exists():
            f.write_bytes(lift_blacks(await b.run_workflow(sheet_workflow(f"{EMPTY}, {p}, {extra}".rstrip(", "), f"{NOPE}, {n}", seed, size=SIZE, cfg=3.5))))
            print(f.name, flush=True)


async def shinji():
    slug, what = "shinji-okubo", "sitting at a desk in a police office, reading a case file, coffee cup, monitors"
    d = load_design(Path(f"narrator/worlds/designs/{slug}.toml"))
    ref = await b.upload_image(f"nightwire_scene_ref_{slug}.png", square_on_blur(front_figure(Path(f"design-data/{slug}/turnaround.png").read_bytes())))
    buf = io.BytesIO()
    Image.open(out / "ogane-precinct-52817.png").convert("RGB").resize(SCENE_SIZE).save(buf, "PNG")
    room = await b.upload_image("nightwire_scene_place_precinct.png", buf.getvalue())
    pos, neg = scene_prompt(d, what)
    for off in (0, 1):
        f = out / f"{slug}-{off}.png"
        if not f.exists():
            png = await b.run_workflow(natural_scene_workflow(f"{what}, detailed background, {pos}", neg, d.seed + off, ref, room))
            f.write_bytes(lift_blacks(await _scene_face(d, slug, png, b)))
            print(f.name, flush=True)


async def main():
    for slug in ("ogane-precinct", "old-family-house", "danchi-block", "ring-line", "rins-room"):
        await place(slug)
    await place("ikebe-low", IKEBE_MORE)
    await shinji()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run it in the background from the repo root**

Run: `cd nightwire && PYTHONPATH=. .venv/bin/python $S/lab/pilot.py` (in the background; wait for the completion notice, don't poll).
Expected: 14 place images and 2 Shinji images. About 1.5 minutes each on the laptop GPU.

- [ ] **Step 3: Review every image at full size**

Check each image against the spec:
- Does the class show?
  - The old-family house is quiet wood with the neon city below.
  - The danchi is worn and lived-in.
  - Ikebe is dense and wired.
  - The station shows the line colour and signs.
- Is cyberpunk visible in every one?
- Does Rin's room read as lived-in, not ruined?
- Is Shinji's face and outfit right, checked beside his turnaround?
- Is any fake lettering obvious?

Record one line per image. Fix small areas with `tools/fix_area.py`. Re-render only for the wrong place or framing.

- [ ] **Step 4: Publish to the World Gallery**

In `$S/lab/gen_world.py`, add a `PILOT` list of `(file stem, title, caption)` and a section called "One connected city: pilot". Build it with `fig(..., orig=True)` for places and without `orig` for Shinji, using the review lines as captions.

Then rebuild and sync:
```bash
cd nightwire && .venv/bin/python $S/lab/gen_world.py
rsync -a --delete $S/world-page/ 192.168.10.19:anvil-deploy/stack/dashboard/world/
```

- [ ] **Step 5: Verify the page**

Run `uv run --no-project --with playwright python $S/origcheck.py`, adjusted so that the place-button count includes the pilot places. Expected:
- every pilot place has an Original button;
- there are no page errors;
- the owner's existing records are unchanged in number.

---

### Task 4: Day versions of approved originals (gated on the owner)

Start only after the owner has marked pilot or existing images Keep or Original.

**Files:**
- Modify: `$S/lab/pair.py`. Its `main()` gets the approved list.

- [ ] **Step 1: Add the day rules to `day_prompt` in `pair.py`**

Day keeps its cyberpunk, so append `"screens still glowing, unlit neon signs, cables, signage, traffic drones"` to the positive prompt. For Tenjō, also append `"reflective glass windows"`, and add `"confetti, colorful dots"` to the negative.

- [ ] **Step 2: Render night to day for each approved original**

Use the existing guide: Canny at 0.08/0.25, the lineart ControlNet at strength 0.85 and end 0.85, chained into both passes, with the same seed. For the penthouse fix, re-render with the cyberpunk day words. The owner's note was "no cyberpunk vibes".

- [ ] **Step 3: Review, publish and verify**

Do this as in Task 3, steps 3 to 5, in the "Same picture, day and night" section.

---

## After the pilot

- When the owner approves, set `status = "approved"` and `seed` on the picked designs, and add a dated note.
- Run `bg.py` with the approved day stems. Deploy the slideshow (`index.html` + `bg/`), backing up `index.html` first, then run `lab_check.py`.
- Remaining places from the spec's table (security command, torite office, pachinko back room, gang office, studio, junkyard, capsule tower, garage, bike shop, depot, shrine): one batch per owner round.
