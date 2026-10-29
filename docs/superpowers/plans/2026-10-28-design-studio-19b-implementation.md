# Design Studio (Phase 19b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An offline design studio that renders owner-reviewed character model sheets and location design sheets for Kuroshio's 22 designs, saving small design records in git and full-size images in a data folder.

**Architecture:** `narrator/designs.py` owns the design record (load/validate/save TOML). `narrator/design_sheets.py` holds pure prompt and ComfyUI-workflow builders plus Pillow helpers (mood-key strip, palette). `ComfyUIBackend.run_workflow()` is extracted from `_generate` so any workflow can be submitted. `tools/design_studio.py` is the CLI (candidates, approve, reroll, sheets, gallery, export). The 22 drafts are TOML files under `narrator/worlds/designs/`.

**Tech Stack:** Python 3.12+ stdlib (`tomllib`, `zipfile`, `argparse`, `asyncio`), httpx (existing), Pillow (new dev/design dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-10-28-design-studio-19b-design.md`

## Global Constraints

- Design file: `narrator/worlds/designs/<slug>.toml`; slug = lowercase, ASCII-folded (ō → o), spaces/apostrophes → hyphens, collapsed.
- Fields and order: `name, kind, source, presentation, tags, negative, alt_tags, props, status, seed, palette, notes`. kind ∈ {character, location}; status ∈ {draft, candidates, approved}; presentation ∈ {feminine, masculine, androgynous} (characters only); `alt_tags`/`props` locations only; approved ⇒ seed ≠ 0.
- Images: `NIGHTWIRE_DESIGN_DIR` (default `./design-data/`, git-ignored): `<slug>/candidates/r<round>-c<n>-<seed>.png`; character sheets `turnaround.png`, `expressions.png`, `colorguide.png`; location sheets `establishing.png`, `alternate.png`, `moodkeys.png`, `props.png`; `gallery/`; `exports/nightwire-designs-<YYYY-MM-DD>.zip`.
- Look (from 19a): checkpoint `NoobAI-XL-Vpred-v1.0.safetensors`; LoRA `Smooth_Booster_v3.safetensors` 0.6; `ModelSamplingDiscrete(v_prediction, zsnr=True)`; `RescaleCFG 0.6`; Euler, normal, CFG 4.5, 28 steps; clip skip -2; quality/negative strings from `narrator.image_prompt` (`QUALITY`, `STYLE`, `NEGATIVE`).
- `SHEET_STYLE = "anime coloring, cel shading, thick outlines, official art, flat lighting, simple background, white background"`.
- `SHEET_NEGATIVE_EXTRA = "scenery, background clutter, inconsistent outfit, different clothes, different hairstyle"`; character sheets use `NEGATIVE` with `", text"` removed, plus this, plus the design's `negative`.
- Sheet tag strings (verbatim): turnaround `character sheet, reference sheet, turnaround, multiple views, front view, from side, from behind, full body, standing`; expressions `expressions, expression chart, multiple views, portrait, upper body, smile, angry, surprised, sad, smirk, closed eyes`; colorguide `character sheet, reference sheet, color guide, multiple views, full body, front view, from behind, close-up`; props `still life, no humans, object focus, multiple views, white background`; mood suffixes `night, neon lights` / `rain, wet street` / `dawn, sunrise, soft light`.
- Sizes: candidates and base 1216×832; full sheets end at 3648×2496 via refine (AnimeSharp `2x-AnimeSharpV2_RPLKSR_Soft.pth` → `ImageScaleBy 0.75` → `VAEEncodeTiled` → KSampler 20 steps denoise 0.35 → `VAEDecodeTiled`) then a second `ImageUpscaleWithModel`; mood-key strip 3648×832.
- Palette: 6 colours, `#rrggbb`, Pillow `quantize`, sorted by pixel count.
- GPU etiquette: before a batch POST `{"model": <OLLAMA model or "qwen3:8b">, "keep_alive": 0}` to `$OLLAMA_HOST/api/generate` (best-effort); after a batch POST `/free` `{"unload_models": true, "free_memory": true}` to ComfyUI (best-effort).
- Never add Co-Authored-By or AI-attribution trailers. Tests: `.venv/bin/python -m pytest tests/ -q`.

**Controller ruling (recorded here):** the spec's "`World.designs` lazily loaded" is implemented as `narrator.designs.kuroshio_designs()` (functools-cached loader of `DESIGNS_DIR`) instead of a field on the frozen `World` dataclass — same read-only access, no change to `World`/`parse_world`. Cost if wrong: one call-site rename in 19c.

---

### Task 1: Design records (`narrator/designs.py`)

**Files:**
- Create: `narrator/designs.py`, `narrator/worlds/designs/.gitkeep`, `tests/test_designs.py`
- Modify: `pyproject.toml` (add `"pillow>=10"` to the `dev` extra and a new `design = ["pillow>=10"]` extra), `.gitignore` (add `design-data/`)

**Interfaces:**
- Produces: `DESIGNS_DIR: Path` (= `narrator/worlds/designs`); `@dataclass Design(name: str, kind: str, source: str, tags: str, presentation: str | None = None, negative: str = "", alt_tags: str = "", props: list[str] = [], status: str = "draft", seed: int = 0, palette: list[str] = [], notes: list[str] = [])` with property `slug`; `slugify(name: str) -> str`; `load_design(path: Path) -> Design`; `load_designs(directory: Path = DESIGNS_DIR) -> dict[str, Design]` (keyed by slug, sorted); `save_design(design: Design, path: Path) -> None`; `validate(design: Design) -> None`; `kuroshio_designs() -> dict[str, Design]` (cached).

- [ ] **Step 1: Write the failing tests** — `tests/test_designs.py`:

```python
import pytest

from narrator.designs import Design, load_design, load_designs, save_design, slugify, validate


def _char(**kw):
    base = dict(name="Mama Sato", kind="character", source="npc:Mama Sato", presentation="feminine",
                tags="1girl, mature female, grey hair, hair bun, warm smile, apron")
    base.update(kw)
    return Design(**base)


def _loc(**kw):
    base = dict(name="Mama Sato's izakaya", kind="location", source="place:Mama Sato's izakaya",
                tags="scenery, no humans, izakaya, paper lanterns", alt_tags="indoors, counter, bar stools",
                props=["paper lanterns", "ramen bowl"])
    base.update(kw)
    return Design(**base)


@pytest.mark.parametrize("name,slug", [("Mama Sato", "mama-sato"), ("Brother Tōru", "brother-toru"),
                                       ("Tenjō Heights", "tenjo-heights"), ("Mama Sato's izakaya", "mama-satos-izakaya"),
                                       ("Hanabira-chō", "hanabira-cho"), ("Yomi  Line", "yomi-line")])
def test_slugify(name, slug):
    assert slugify(name) == slug
    assert _char(name=name).slug == slug


def test_valid_designs_pass():
    validate(_char())
    validate(_loc())
    validate(_char(status="approved", seed=42))


@pytest.mark.parametrize("bad,message", [
    (dict(kind="vehicle"), "kind"),
    (dict(status="done"), "status"),
    (dict(name=""), "name"),
    (dict(tags=""), "tags"),
    (dict(presentation="robot"), "presentation"),
    (dict(alt_tags="indoors"), "alt_tags"),
    (dict(props=["cup"]), "props"),
    (dict(status="approved", seed=0), "seed"),
])
def test_invalid_characters_raise(bad, message):
    with pytest.raises(ValueError, match=message):
        validate(_char(**bad))


def test_location_cannot_have_presentation():
    with pytest.raises(ValueError, match="presentation"):
        validate(_loc(presentation="feminine"))


def test_round_trip_and_stable_order(tmp_path):
    d = _loc(status="approved", seed=7, palette=["#111111", "#ffcc00"], notes=["2026-10-28 draft from world card"])
    path = tmp_path / f"{d.slug}.toml"
    save_design(d, path)
    text = path.read_text()
    keys = [line.split(" = ")[0] for line in text.splitlines() if " = " in line]
    assert keys == ["name", "kind", "source", "tags", "negative", "alt_tags", "props", "status", "seed", "palette", "notes"]
    assert load_design(path) == d
    save_design(load_design(path), path)
    assert path.read_text() == text


def test_character_toml_includes_presentation_and_omits_location_fields(tmp_path):
    d = _char(negative='two mechanical arms, "quoted"')
    path = tmp_path / "x.toml"
    save_design(d, path)
    text = path.read_text()
    assert 'presentation = "feminine"' in text and "alt_tags" not in text and "props" not in text
    assert load_design(path) == d


def test_load_designs_keys_by_slug(tmp_path):
    save_design(_char(), tmp_path / "mama-sato.toml")
    save_design(_loc(), tmp_path / "mama-satos-izakaya.toml")
    assert list(load_designs(tmp_path)) == ["mama-sato", "mama-satos-izakaya"]


def test_load_design_rejects_invalid_file(tmp_path):
    path = tmp_path / "bad.toml"
    path.write_text('name = "X"\nkind = "vehicle"\nsource = "npc:X"\ntags = "a"\n')
    with pytest.raises(ValueError, match="kind"):
        load_design(path)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pip install -e ".[dev]" -q && .venv/bin/python -m pytest tests/test_designs.py -q` (after editing pyproject in Step 3 the install picks up Pillow; on this first run expect ModuleNotFoundError for `narrator.designs`).

- [ ] **Step 3: Implement**

`pyproject.toml`: in `[project.optional-dependencies]` add `"pillow>=10"` to `dev`, and add `design = ["pillow>=10"]`. `.gitignore`: append a line `design-data/`. Create empty `narrator/worlds/designs/.gitkeep`.

`narrator/designs.py`:

```python
"""Phase 19b design records: one small TOML per character or location in
narrator/worlds/designs/, the full-size sheets live outside git.
See docs/superpowers/specs/2026-10-28-design-studio-19b-design.md."""

import functools
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DESIGNS_DIR = Path(__file__).parent / "worlds" / "designs"
KINDS = ("character", "location")
STATUSES = ("draft", "candidates", "approved")
PRESENTATIONS = ("feminine", "masculine", "androgynous")
_ORDER = ("name", "kind", "source", "presentation", "tags", "negative", "alt_tags", "props",
          "status", "seed", "palette", "notes")


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_name = ascii_name.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


@dataclass
class Design:
    name: str
    kind: str
    source: str
    tags: str
    presentation: str | None = None
    negative: str = ""
    alt_tags: str = ""
    props: list[str] = field(default_factory=list)
    status: str = "draft"
    seed: int = 0
    palette: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return slugify(self.name)


def validate(d: Design) -> None:
    if not d.name.strip():
        raise ValueError("design name is required")
    if d.kind not in KINDS:
        raise ValueError(f"unknown kind {d.kind!r}")
    if d.status not in STATUSES:
        raise ValueError(f"unknown status {d.status!r}")
    if not d.tags.strip():
        raise ValueError(f"{d.name}: tags are required")
    if d.kind == "character":
        if d.presentation is not None and d.presentation not in PRESENTATIONS:
            raise ValueError(f"{d.name}: presentation must be one of {PRESENTATIONS}")
        if d.alt_tags or d.props:
            raise ValueError(f"{d.name}: alt_tags and props are for locations only")
    elif d.presentation is not None:
        raise ValueError(f"{d.name}: presentation is for characters only")
    if d.status == "approved" and not d.seed:
        raise ValueError(f"{d.name}: an approved design needs a seed")


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def save_design(d: Design, path: Path) -> None:
    validate(d)
    lines = []
    for key in _ORDER:
        value = getattr(d, key)
        if key == "presentation" and (d.kind != "character" or value is None):
            continue
        if key in ("alt_tags", "props") and d.kind != "location":
            continue
        lines.append(f"{key} = {_toml_value(value)}")
    path.write_text("\n".join(lines) + "\n")


def load_design(path: Path) -> Design:
    with path.open("rb") as f:
        data = tomllib.load(f)
    unknown = set(data) - set(_ORDER)
    if unknown:
        raise ValueError(f"{path.name}: unknown fields {sorted(unknown)}")
    d = Design(**data)
    validate(d)
    return d


def load_designs(directory: Path = DESIGNS_DIR) -> dict[str, Design]:
    designs = {}
    for path in sorted(Path(directory).glob("*.toml")):
        d = load_design(path)
        designs[d.slug] = d
    return designs


@functools.cache
def kuroshio_designs() -> dict[str, Design]:
    return load_designs(DESIGNS_DIR)
```

Note the round-trip test lists keys for a location (no `presentation`); for characters the key order includes `presentation` after `source`.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pip install -e ".[dev]" -q && .venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/designs.py narrator/worlds/designs/.gitkeep tests/test_designs.py pyproject.toml .gitignore
git commit -m "feat(19b): design records - load, validate, save TOML"
```

---

### Task 2: Sheet prompts, workflows and image helpers (`narrator/design_sheets.py`)

**Files:**
- Create: `narrator/design_sheets.py`, `tests/test_design_sheets.py`

**Interfaces:**
- Consumes: `Design` (Task 1); `QUALITY`, `STYLE`, `NEGATIVE` from `narrator.image_prompt`.
- Produces:
  - constants `SHEET_STYLE`, `SHEET_NEGATIVE_EXTRA`, `CHARACTER_SHEETS = ("turnaround", "expressions", "colorguide")`, `LOCATION_SHEETS = ("establishing", "alternate", "moodkeys", "props")`, `MOOD_SUFFIXES = ("night, neon lights", "rain, wet street", "dawn, sunrise, soft light")`, `BASE_SIZE = (1216, 832)`, `SHEET_SIZE = (3648, 2496)`;
  - `subject_for(d: Design) -> str`;
  - `candidate_prompt(d: Design) -> tuple[str, str]` (positive, negative);
  - `sheet_prompt(d: Design, sheet: str, mood: str | None = None) -> tuple[str, str]`;
  - `candidate_workflow(positive: str, negative: str, seed: int) -> dict`;
  - `sheet_workflow(positive: str, negative: str, seed: int, high_res: bool = True) -> dict`;
  - `join_strip(images: list[bytes]) -> bytes` (PNG);
  - `extract_palette(png: bytes, n: int = 6) -> list[str]`.

- [ ] **Step 1: Write the failing tests** — `tests/test_design_sheets.py`:

```python
import io

import pytest
from PIL import Image

from narrator.design_sheets import (
    BASE_SIZE, MOOD_SUFFIXES, SHEET_NEGATIVE_EXTRA, SHEET_STYLE, candidate_prompt, candidate_workflow,
    extract_palette, join_strip, sheet_prompt, sheet_workflow, subject_for,
)
from narrator.designs import Design
from narrator.image_prompt import NEGATIVE, QUALITY, STYLE


def _char(**kw):
    base = dict(name="Rook", kind="character", source="npc:Rook", presentation="feminine",
                tags="black hair, short hair, yellow eyes, black bomber jacket, mechanical left arm, human right hand",
                negative="two mechanical arms")
    base.update(kw)
    return Design(**base)


def _loc():
    return Design(name="Izakaya", kind="location", source="place:Izakaya",
                  tags="izakaya, paper lanterns, noren", alt_tags="indoors, counter, bar stools",
                  props=["paper lanterns", "ramen bowl", "sake bottle"])


def _types(wf):
    return [n["class_type"] for n in wf.values()]


def test_subjects():
    assert subject_for(_char()) == "1girl"
    assert subject_for(_char(presentation="masculine")) == "1boy"
    assert subject_for(_char(presentation=None)) == "1other"
    assert subject_for(_char(source="npc:Hachi", tags="android, robot joints, station attendant uniform")) == "1other"
    assert subject_for(_loc()) == "scenery, no humans"


def test_character_candidate_is_a_turnaround_preview():
    pos, neg = candidate_prompt(_char())
    assert pos.startswith(QUALITY + ", " + SHEET_STYLE + ", character sheet, reference sheet, turnaround")
    assert pos.endswith(", 1girl, black hair, short hair, yellow eyes, black bomber jacket, mechanical left arm, human right hand")
    assert ", text," not in neg and SHEET_NEGATIVE_EXTRA in neg and neg.endswith("two mechanical arms")


def test_location_candidate_uses_the_game_style():
    pos, neg = candidate_prompt(_loc())
    assert pos == ", ".join([QUALITY, STYLE, "scenery, no humans", "izakaya, paper lanterns, noren"])
    assert neg == NEGATIVE


def test_colorguide_focuses_the_signature_chrome():
    pos, _ = sheet_prompt(_char(), "colorguide")
    assert "color guide" in pos and "mechanical left arm focus" in pos


def test_expressions_sheet_tags():
    pos, _ = sheet_prompt(_char(), "expressions")
    assert "expressions, expression chart, multiple views, portrait, upper body" in pos


def test_location_sheets():
    alt, _ = sheet_prompt(_loc(), "alternate")
    assert "indoors, counter, bar stools" in alt and "izakaya, paper lanterns" not in alt
    mood, _ = sheet_prompt(_loc(), "moodkeys", mood=MOOD_SUFFIXES[1])
    assert mood.endswith("rain, wet street")
    props, _ = sheet_prompt(_loc(), "props")
    assert SHEET_STYLE in props and "still life, no humans, object focus, multiple views, white background" in props
    assert "paper lanterns, ramen bowl, sake bottle" in props


def test_unknown_sheet_raises():
    with pytest.raises(ValueError):
        sheet_prompt(_char(), "establishing")
    with pytest.raises(ValueError):
        sheet_prompt(_loc(), "turnaround")


def test_candidate_workflow_is_single_pass_with_the_19a_look():
    wf = candidate_workflow("P", "N", 7)
    t = _types(wf)
    assert t.count("KSampler") == 1 and "UpscaleModelLoader" not in t
    nodes = {n["class_type"]: n["inputs"] for n in wf.values()}
    assert nodes["CheckpointLoaderSimple"]["ckpt_name"] == "NoobAI-XL-Vpred-v1.0.safetensors"
    assert nodes["LoraLoader"]["lora_name"] == "Smooth_Booster_v3.safetensors"
    assert nodes["ModelSamplingDiscrete"]["sampling"] == "v_prediction" and nodes["RescaleCFG"]["multiplier"] == 0.6
    assert (nodes["EmptyLatentImage"]["width"], nodes["EmptyLatentImage"]["height"]) == BASE_SIZE
    assert nodes["KSampler"]["seed"] == 7 and nodes["KSampler"]["cfg"] == 4.5


def test_sheet_workflow_has_refine_and_final_upscale():
    wf = sheet_workflow("P", "N", 7)
    t = _types(wf)
    assert t.count("KSampler") == 2 and t.count("ImageUpscaleWithModel") == 2
    refine = [n["inputs"] for n in wf.values() if n["class_type"] == "KSampler" and n["inputs"]["denoise"] < 1][0]
    assert refine["denoise"] == 0.35 and refine["steps"] == 20
    scale = [n["inputs"] for n in wf.values() if n["class_type"] == "ImageScaleBy"][0]
    assert scale["scale_by"] == 0.75
    save = [n["inputs"] for n in wf.values() if n["class_type"] == "SaveImage"][0]
    final = wf[save["images"][0]]
    assert final["class_type"] == "ImageUpscaleWithModel"


def test_sheet_workflow_low_res_is_single_pass():
    assert _types(sheet_workflow("P", "N", 7, high_res=False)).count("KSampler") == 1


def _png(color, size=(1216, 832)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_join_strip():
    out = Image.open(io.BytesIO(join_strip([_png("red"), _png("green"), _png("blue")])))
    assert out.size == (3648, 832)
    assert out.getpixel((10, 10)) == (255, 0, 0) and out.getpixel((1216 + 10, 10))[1] > 100


def test_extract_palette():
    img = Image.new("RGB", (100, 100), (255, 204, 0))
    img.paste((17, 17, 17), (0, 0, 100, 30))
    buf = io.BytesIO(); img.save(buf, "PNG")
    palette = extract_palette(buf.getvalue(), n=2)
    assert palette[0] == "#ffcc00" and palette[1] == "#111111"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_design_sheets.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `narrator/design_sheets.py`**

```python
"""Phase 19b sheet prompts and ComfyUI workflows (19a look) for the design studio.
Pure builders plus two Pillow helpers; no network here."""

import io

from PIL import Image

from narrator.designs import Design
from narrator.image_prompt import NEGATIVE, QUALITY, STYLE

CHECKPOINT = "NoobAI-XL-Vpred-v1.0.safetensors"
LORA = "Smooth_Booster_v3.safetensors"
UPSCALER = "2x-AnimeSharpV2_RPLKSR_Soft.pth"
BASE_SIZE = (1216, 832)
SHEET_SIZE = (3648, 2496)
SHEET_STYLE = ("anime coloring, cel shading, thick outlines, official art, flat lighting, simple background, "
               "white background")
SHEET_NEGATIVE_EXTRA = "scenery, background clutter, inconsistent outfit, different clothes, different hairstyle"
CHARACTER_SHEETS = ("turnaround", "expressions", "colorguide")
LOCATION_SHEETS = ("establishing", "alternate", "moodkeys", "props")
MOOD_SUFFIXES = ("night, neon lights", "rain, wet street", "dawn, sunrise, soft light")
_SHEET_TAGS = {
    "turnaround": ("character sheet, reference sheet, turnaround, multiple views, front view, from side, "
                   "from behind, full body, standing"),
    "expressions": ("expressions, expression chart, multiple views, portrait, upper body, smile, angry, "
                    "surprised, sad, smirk, closed eyes"),
    "colorguide": ("character sheet, reference sheet, color guide, multiple views, full body, front view, "
                   "from behind, close-up"),
}
_PROPS_TAGS = "still life, no humans, object focus, multiple views, white background"
_SIGNATURE_WORDS = ("mechanical", "cyber", "prosthetic", "robot", "chrome", "implant", "weapon", "sword", "gun")
_PRESENTATION = {"feminine": "1girl", "masculine": "1boy", "androgynous": "1other"}


def subject_for(d: Design) -> str:
    if d.kind == "location":
        return "scenery, no humans"
    if "android" in d.tags:
        return "1other"
    return _PRESENTATION.get(d.presentation, "1other")


def _join(*parts: str) -> str:
    return ", ".join(p for p in parts if p)


def _character_negative(d: Design) -> str:
    return _join(NEGATIVE.replace(", text,", ","), SHEET_NEGATIVE_EXTRA, d.negative)


def _location_negative(d: Design) -> str:
    return _join(NEGATIVE, d.negative)


def _signature_focus(d: Design) -> str:
    for tag in (t.strip() for t in d.tags.split(",")):
        if any(w in tag for w in _SIGNATURE_WORDS):
            return f"{tag} focus"
    return ""


def candidate_prompt(d: Design) -> tuple[str, str]:
    if d.kind == "character":
        return sheet_prompt(d, "turnaround")
    return sheet_prompt(d, "establishing")


def sheet_prompt(d: Design, sheet: str, mood: str | None = None) -> tuple[str, str]:
    if d.kind == "character":
        if sheet not in CHARACTER_SHEETS:
            raise ValueError(f"{sheet!r} is not a character sheet")
        extra = _signature_focus(d) if sheet == "colorguide" else ""
        pos = _join(QUALITY, SHEET_STYLE, _SHEET_TAGS[sheet], extra, subject_for(d), d.tags)
        return pos, _character_negative(d)
    if sheet not in LOCATION_SHEETS:
        raise ValueError(f"{sheet!r} is not a location sheet")
    if sheet == "props":
        return _join(QUALITY, SHEET_STYLE, _PROPS_TAGS, ", ".join(d.props)), _character_negative(d)
    content = d.alt_tags if sheet == "alternate" else d.tags
    pos = _join(QUALITY, STYLE, subject_for(d), content, mood if sheet == "moodkeys" else "")
    return pos, _location_negative(d)


def _base(positive: str, negative: str, seed: int) -> dict:
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "20": {"class_type": "LoraLoader", "inputs": {"model": ["4", 0], "clip": ["4", 1], "lora_name": LORA,
               "strength_model": 0.6, "strength_clip": 0.6}},
        "21": {"class_type": "ModelSamplingDiscrete", "inputs": {"model": ["20", 0], "sampling": "v_prediction", "zsnr": True}},
        "22": {"class_type": "RescaleCFG", "inputs": {"model": ["21", 0], "multiplier": 0.6}},
        "10": {"class_type": "CLIPSetLastLayer", "inputs": {"clip": ["20", 1], "stop_at_clip_layer": -2}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["10", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["10", 0]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": BASE_SIZE[0], "height": BASE_SIZE[1], "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 28, "cfg": 4.5, "sampler_name": "euler",
              "scheduler": "normal", "denoise": 1.0, "model": ["22", 0], "positive": ["6", 0],
              "negative": ["7", 0], "latent_image": ["5", 0]}},
        "8": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["3", 0], "vae": ["4", 2], "tile_size": 512,
              "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}},
    }


def candidate_workflow(positive: str, negative: str, seed: int) -> dict:
    wf = _base(positive, negative, seed)
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_design", "images": ["8", 0]}}
    return wf


def sheet_workflow(positive: str, negative: str, seed: int, high_res: bool = True) -> dict:
    if not high_res:
        return candidate_workflow(positive, negative, seed)
    wf = _base(positive, negative, seed)
    tiled = {"tile_size": 512, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}
    wf["30"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": UPSCALER}}
    wf["31"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["30", 0], "image": ["8", 0]}}
    wf["32"] = {"class_type": "ImageScaleBy", "inputs": {"image": ["31", 0], "upscale_method": "lanczos", "scale_by": 0.75}}
    wf["33"] = {"class_type": "VAEEncodeTiled", "inputs": {"pixels": ["32", 0], "vae": ["4", 2], **tiled}}
    wf["34"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 20, "cfg": 4.5, "sampler_name": "euler",
                "scheduler": "normal", "denoise": 0.35, "model": ["22", 0], "positive": ["6", 0],
                "negative": ["7", 0], "latent_image": ["33", 0]}}
    wf["35"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["34", 0], "vae": ["4", 2], **tiled}}
    wf["40"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["30", 0], "image": ["35", 0]}}
    wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "nightwire_design", "images": ["40", 0]}}
    return wf


def join_strip(images: list[bytes]) -> bytes:
    frames = [Image.open(io.BytesIO(b)).convert("RGB") for b in images]
    strip = Image.new("RGB", (sum(f.width for f in frames), max(f.height for f in frames)))
    x = 0
    for f in frames:
        strip.paste(f, (x, 0))
        x += f.width
    out = io.BytesIO()
    strip.save(out, "PNG")
    return out.getvalue()


def extract_palette(png: bytes, n: int = 6) -> list[str]:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img.thumbnail((256, 256))
    quantized = img.quantize(colors=n)
    flat = quantized.getpalette()
    counts = sorted(quantized.getcolors(), reverse=True)
    return ["#%02x%02x%02x" % tuple(flat[i * 3:i * 3 + 3]) for _count, i in counts[:n]]
```

Note: `NEGATIVE` contains the substring `"..., text, watermark, ..."`; `_character_negative` removes `" text,"` by replacing `", text,"` with `","` so labels can appear on sheets. Verify by test (`", text," not in neg`).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/design_sheets.py tests/test_design_sheets.py
git commit -m "feat(19b): sheet prompts, ComfyUI sheet workflows, strip and palette helpers"
```

---

### Task 3: `run_workflow` and the design-studio CLI

**Files:**
- Modify: `narrator/comfyui_backend.py` (extract `run_workflow`)
- Create: `tools/__init__.py` (empty), `tools/design_studio.py`, `tests/test_design_studio.py`
- Test: `tests/test_comfyui_backend.py` (one test for `run_workflow`)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `ComfyUIBackend.run_workflow(workflow: dict) -> bytes` (submit, poll, fetch first image — the body of today's `_generate` after the workflow is built; `_generate` now builds then calls it). `tools/design_studio.py`: `async def main(argv: list[str], backend=None) -> int` and functions `next_round(slug_dir: Path) -> int`, `cmd_candidates`, `cmd_approve`, `cmd_reroll`, `cmd_sheets`, `cmd_gallery`, `cmd_export` (signatures below); `python -m tools.design_studio` runs `asyncio.run(main(sys.argv[1:]))`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_comfyui_backend.py` (reuse the file's `_FakeComfyClient`):

```python
async def test_run_workflow_submits_any_graph_and_returns_image_bytes():
    client = _FakeComfyClient(image_bytes=b"design-png")
    backend = ComfyUIBackend(base_url="http://x", client=client, sleep_fn=_no_sleep)
    out = await backend.run_workflow({"9": {"class_type": "SaveImage", "inputs": {}}})
    assert out == b"design-png"
```

(If the file has no `_no_sleep` helper, define `async def _no_sleep(_): pass` above the test.)

Create `tests/test_design_studio.py`:

```python
import io
import zipfile

import pytest
from PIL import Image

from narrator.designs import Design, load_design, save_design
from tools import design_studio as ds


def _png(color=(200, 50, 50), size=(64, 48)):
    buf = io.BytesIO(); Image.new("RGB", size, color).save(buf, "PNG"); return buf.getvalue()


class FakeBackend:
    def __init__(self):
        self.workflows = []

    async def run_workflow(self, workflow):
        self.workflows.append(workflow)
        return _png()


@pytest.fixture
def studio(tmp_path):
    designs = tmp_path / "designs"; data = tmp_path / "data"
    designs.mkdir(); data.mkdir()
    save_design(Design(name="Mama Sato", kind="character", source="npc:Mama Sato", presentation="feminine",
                       tags="grey hair, hair bun, apron"), designs / "mama-sato.toml")
    save_design(Design(name="Izakaya", kind="location", source="place:Izakaya", tags="izakaya, lanterns",
                       alt_tags="indoors, counter", props=["lantern", "ramen bowl"]), designs / "izakaya.toml")
    return designs, data


def _args(studio, *rest):
    designs, data = studio
    return ["--designs-dir", str(designs), "--design-dir", str(data), "--no-gpu-etiquette", *rest]


async def test_candidates_writes_four_and_updates_status(studio):
    designs, data = studio
    backend = FakeBackend()
    assert await ds.main(_args(studio, "candidates", "mama-sato"), backend=backend) == 0
    files = sorted((data / "mama-sato" / "candidates").glob("r1-c*-*.png"))
    assert [f.name.split("-")[1] for f in files] == ["c1", "c2", "c3", "c4"]
    d = load_design(designs / "mama-sato.toml")
    assert d.status == "candidates" and d.notes[-1].endswith("round 1: 4 candidates")
    assert len(backend.workflows) == 4
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=backend)
    assert len(list((data / "mama-sato" / "candidates").glob("r2-c*-*.png"))) == 4


async def test_all_drafts_and_rerolls_selection(studio):
    designs, _ = studio
    backend = FakeBackend()
    await ds.main(_args(studio, "candidates", "--all-drafts"), backend=backend)
    assert len(backend.workflows) == 8
    await ds.main(_args(studio, "reroll", "izakaya", "warmer light"))
    backend.workflows.clear()
    await ds.main(_args(studio, "candidates", "--rerolls"), backend=backend)
    assert len(backend.workflows) == 4
    assert "reroll: warmer light" in load_design(designs / "izakaya.toml").notes[-2]


async def test_approve_sets_seed_from_candidate(studio):
    designs, data = studio
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=FakeBackend())
    c3 = next((data / "mama-sato" / "candidates").glob("r1-c3-*.png"))
    seed = int(c3.stem.split("-")[2])
    assert await ds.main(_args(studio, "approve", "mama-sato", "3")) == 0
    d = load_design(designs / "mama-sato.toml")
    assert d.status == "approved" and d.seed == seed and "approved r1 #3" in d.notes[-1]


async def test_approve_unknown_candidate_fails(studio):
    assert await ds.main(_args(studio, "approve", "mama-sato", "2")) == 1


async def test_sheets_for_character_and_location(studio):
    designs, data = studio
    backend = FakeBackend()
    for slug in ("mama-sato", "izakaya"):
        await ds.main(_args(studio, "candidates", slug), backend=backend)
        await ds.main(_args(studio, "approve", slug, "1"))
    backend.workflows.clear()
    assert await ds.main(_args(studio, "sheets", "--approved-missing"), backend=backend) == 0
    assert sorted(p.name for p in (data / "mama-sato").glob("*.png")) == ["colorguide.png", "expressions.png", "turnaround.png"]
    assert sorted(p.name for p in (data / "izakaya").glob("*.png")) == ["alternate.png", "establishing.png", "moodkeys.png", "props.png"]
    # 3 character sheets + establishing + alternate + props + 3 mood renders
    assert len(backend.workflows) == 9
    assert load_design(designs / "mama-sato.toml").palette
    backend.workflows.clear()
    await ds.main(_args(studio, "sheets", "--approved-missing"), backend=backend)
    assert backend.workflows == []


async def test_gallery_and_export(studio):
    designs, data = studio
    await ds.main(_args(studio, "candidates", "mama-sato"), backend=FakeBackend())
    await ds.main(_args(studio, "approve", "mama-sato", "1"))
    await ds.main(_args(studio, "sheets", "mama-sato"), backend=FakeBackend())
    await ds.main(_args(studio, "candidates", "izakaya"), backend=FakeBackend())
    assert await ds.main(_args(studio, "gallery")) == 0
    html = (data / "gallery" / "index.html").read_text()
    assert "Mama Sato" in html and "Izakaya" in html and "#4" in html
    assert (data / "gallery" / "img").is_dir()
    assert await ds.main(_args(studio, "export")) == 0
    zips = list((data / "exports").glob("nightwire-designs-*.zip"))
    names = zipfile.ZipFile(zips[0]).namelist()
    assert "mama-sato/design.toml" in names and "mama-sato/turnaround.png" in names
    assert not any(n.startswith("izakaya/") for n in names) and "index.html" in names
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_design_studio.py tests/test_comfyui_backend.py -q`
Expected: FAIL.

- [ ] **Step 3a: Extract `run_workflow` in `narrator/comfyui_backend.py`**

Move everything in `_generate` after `workflow = self._build_workflow(...)` into:

```python
    async def run_workflow(self, workflow: dict) -> bytes:
        """Submit any ComfyUI workflow, wait for it, return the first output image's bytes."""
        submit = await self._client.post("/prompt", json={"prompt": workflow})
        ...  # the existing submit/poll/view body, unchanged
        return view.content
```

and make `_generate` end with `return await self.run_workflow(workflow)`.

- [ ] **Step 3b: Implement `tools/design_studio.py`** (and empty `tools/__init__.py`)

```python
"""Phase 19b design studio CLI: render, approve and export Kuroshio's
character model sheets and location designs.

    python -m tools.design_studio candidates mama-sato | --all-drafts | --rerolls
    python -m tools.design_studio approve mama-sato 3
    python -m tools.design_studio reroll mama-sato "older, thinner"
    python -m tools.design_studio sheets mama-sato | --approved-missing
    python -m tools.design_studio gallery
    python -m tools.design_studio export
"""

import argparse
import asyncio
import datetime as dt
import html
import io
import json
import os
import random
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

from narrator.comfyui_backend import ComfyUIBackend
from narrator.design_sheets import (
    CHARACTER_SHEETS, LOCATION_SHEETS, MOOD_SUFFIXES, candidate_prompt, candidate_workflow,
    extract_palette, join_strip, sheet_prompt, sheet_workflow,
)
from narrator.designs import DESIGNS_DIR, Design, load_designs, save_design

_CANDIDATE = re.compile(r"^r(\d+)-c(\d+)-(\d+)\.png$")
CANDIDATES_PER_ROUND = 4


def _today() -> str:
    return dt.date.today().isoformat()


def next_round(slug_dir: Path) -> int:
    rounds = [int(m.group(1)) for p in (slug_dir / "candidates").glob("*.png") if (m := _CANDIDATE.match(p.name))]
    return max(rounds, default=0) + 1


def _latest_candidates(slug_dir: Path, round_no: int | None = None) -> tuple[int, dict[int, Path]]:
    found: dict[int, dict[int, Path]] = {}
    for p in (slug_dir / "candidates").glob("*.png"):
        if m := _CANDIDATE.match(p.name):
            found.setdefault(int(m.group(1)), {})[int(m.group(2))] = p
    if not found:
        return 0, {}
    r = round_no or max(found)
    return r, found.get(r, {})


def _gpu_etiquette(comfyui_url: str, before: bool) -> None:
    try:
        if before:
            host = os.environ.get("OLLAMA_HOST", "http://192.168.10.19:11434").rstrip("/")
            body = {"model": os.environ.get("NIGHTWIRE_MODEL", "qwen3:8b"), "keep_alive": 0}
            urllib.request.urlopen(urllib.request.Request(f"{host}/api/generate", data=json.dumps(body).encode()), timeout=30)
        else:
            body = {"unload_models": True, "free_memory": True}
            urllib.request.urlopen(urllib.request.Request(f"{comfyui_url.rstrip('/')}/free", data=json.dumps(body).encode(),
                                                          headers={"Content-Type": "application/json"}), timeout=30)
    except Exception as e:  # best-effort: never block a render batch
        print(f"gpu etiquette skipped: {e}", file=sys.stderr)


async def cmd_candidates(designs: dict[str, Design], slugs: list[str], args, backend) -> int:
    for slug in slugs:
        d = designs[slug]
        slug_dir = args.design_dir / slug
        (slug_dir / "candidates").mkdir(parents=True, exist_ok=True)
        r = next_round(slug_dir)
        pos, neg = candidate_prompt(d)
        for n in range(1, CANDIDATES_PER_ROUND + 1):
            seed = random.randint(1, 2**32 - 1)
            png = await backend.run_workflow(candidate_workflow(pos, neg, seed))
            (slug_dir / "candidates" / f"r{r}-c{n}-{seed}.png").write_bytes(png)
            print(f"{slug}: round {r} candidate {n} (seed {seed})", flush=True)
        if d.status != "approved":
            d.status = "candidates"
        d.notes.append(f"{_today()} round {r}: {CANDIDATES_PER_ROUND} candidates")
        save_design(d, args.designs_dir / f"{slug}.toml")
    return 0


def cmd_approve(designs, slug: str, n: int, round_no: int | None, args) -> int:
    d = designs[slug]
    r, cands = _latest_candidates(args.design_dir / slug, round_no)
    if n not in cands:
        print(f"{slug}: no candidate #{n} in round {r}", file=sys.stderr)
        return 1
    d.seed = int(_CANDIDATE.match(cands[n].name).group(3))
    d.status = "approved"
    d.notes.append(f"{_today()} approved r{r} #{n} (seed {d.seed})")
    save_design(d, args.designs_dir / f"{slug}.toml")
    return 0


def cmd_reroll(designs, slug: str, note: str, args) -> int:
    d = designs[slug]
    d.notes.append(f"{_today()} reroll: {note}")
    save_design(d, args.designs_dir / f"{slug}.toml")
    return 0


async def cmd_sheets(designs, slugs: list[str], args, backend) -> int:
    for slug in slugs:
        d = designs[slug]
        if d.status != "approved":
            print(f"{slug}: not approved, skipping", file=sys.stderr)
            continue
        slug_dir = args.design_dir / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
        for sheet in sheets:
            if sheet == "moodkeys":
                frames = []
                for mood in MOOD_SUFFIXES:
                    pos, neg = sheet_prompt(d, sheet, mood=mood)
                    frames.append(await backend.run_workflow(sheet_workflow(pos, neg, d.seed, high_res=False)))
                png = join_strip(frames)
            else:
                pos, neg = sheet_prompt(d, sheet)
                png = await backend.run_workflow(sheet_workflow(pos, neg, d.seed))
            (slug_dir / f"{sheet}.png").write_bytes(png)
            print(f"{slug}: {sheet}", flush=True)
        key = "turnaround" if d.kind == "character" else "establishing"
        d.palette = extract_palette((slug_dir / f"{key}.png").read_bytes())
        save_design(d, args.designs_dir / f"{slug}.toml")
    return 0


def _sheets_present(d: Design, slug_dir: Path) -> bool:
    sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
    return all((slug_dir / f"{s}.png").exists() for s in sheets)


def _web_copy(src: Path, dest: Path) -> None:
    im = Image.open(src).convert("RGB")
    im.thumbnail((1100, 1100))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=84)


def cmd_gallery(designs, args) -> int:
    out = args.design_dir / "gallery"
    sections = []
    for slug, d in designs.items():
        slug_dir = args.design_dir / slug
        r, cands = _latest_candidates(slug_dir)
        figs = []
        for n, p in sorted(cands.items()):
            rel = f"img/{slug}/r{r}-c{n}.jpg"
            _web_copy(p, out / rel)
            figs.append(f'<figure><img src="{rel}" alt="{html.escape(d.name)} candidate {n}"><figcaption>#{n}</figcaption></figure>')
        sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
        for s in sheets:
            if (slug_dir / f"{s}.png").exists():
                rel = f"img/{slug}/{s}.jpg"
                _web_copy(slug_dir / f"{s}.png", out / rel)
                figs.append(f'<figure><img src="{rel}" alt="{html.escape(d.name)} {s}"><figcaption>{s}</figcaption></figure>')
        notes = "".join(f"<li>{html.escape(n)}</li>" for n in d.notes[-3:])
        sections.append(
            f'<section><h2>{html.escape(d.name)} <small>{d.kind} · {d.status} · round {r}</small></h2>'
            f'<p class="tags">{html.escape(d.tags)}</p><div class="grid">{"".join(figs)}</div><ul>{notes}</ul></section>')
    page = ("<!doctype html><meta charset=utf-8><title>Kuroshio Design Studio</title>"
            "<style>body{background:#0d0b14;color:#e9e4f2;font:15px/1.5 system-ui;padding:24px}"
            ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}"
            "img{width:100%;display:block}figure{margin:0;background:#16121f}figcaption{padding:4px 8px;color:#ffe14d}"
            ".tags{color:#9a91ad;font:12px ui-monospace,monospace}h2 small{color:#9a91ad;font-weight:400}</style>"
            + "".join(sections))
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page)
    print(out / "index.html")
    return 0


def cmd_export(designs, args) -> int:
    exports = args.design_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    path = exports / f"nightwire-designs-{_today()}.zip"
    index = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for slug, d in designs.items():
            slug_dir = args.design_dir / slug
            if d.status != "approved" or not _sheets_present(d, slug_dir):
                continue
            z.write(args.designs_dir / f"{slug}.toml", f"{slug}/design.toml")
            sheets = CHARACTER_SHEETS if d.kind == "character" else LOCATION_SHEETS
            for s in sheets:
                z.write(slug_dir / f"{s}.png", f"{slug}/{s}.png")
            index.append(f'<li><a href="{slug}/">{html.escape(d.name)}</a> ({d.kind})</li>')
        z.writestr("index.html", "<!doctype html><meta charset=utf-8><title>Nightwire designs</title><ul>"
                   + "".join(index) + "</ul>")
    print(path)
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tools.design_studio")
    p.add_argument("--designs-dir", type=Path, default=DESIGNS_DIR)
    p.add_argument("--design-dir", type=Path, default=Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")))
    p.add_argument("--comfyui-url", default=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"))
    p.add_argument("--no-gpu-etiquette", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("candidates"); c.add_argument("slugs", nargs="*")
    c.add_argument("--all-drafts", action="store_true"); c.add_argument("--rerolls", action="store_true")
    a = sub.add_parser("approve"); a.add_argument("slug"); a.add_argument("n", type=int); a.add_argument("--round", type=int)
    r = sub.add_parser("reroll"); r.add_argument("slug"); r.add_argument("note")
    s = sub.add_parser("sheets"); s.add_argument("slugs", nargs="*"); s.add_argument("--approved-missing", action="store_true")
    sub.add_parser("gallery"); sub.add_parser("export")
    return p


async def main(argv: list[str], backend=None) -> int:
    args = _parser().parse_args(argv)
    designs = load_designs(args.designs_dir)
    for slug in getattr(args, "slugs", []) or ([args.slug] if hasattr(args, "slug") else []):
        if slug not in designs:
            print(f"unknown design {slug!r}", file=sys.stderr)
            return 1
    if args.command in ("candidates", "sheets"):
        if args.command == "candidates":
            slugs = list(args.slugs)
            if args.all_drafts:
                slugs += [s for s, d in designs.items() if d.status == "draft"]
            if args.rerolls:
                slugs += [s for s, d in designs.items() if d.notes and " reroll: " in d.notes[-1]]
        else:
            slugs = list(args.slugs)
            if args.approved_missing:
                slugs += [s for s, d in designs.items()
                          if d.status == "approved" and not _sheets_present(d, args.design_dir / s)]
        slugs = list(dict.fromkeys(slugs))
        if not slugs:
            print("nothing to do")
            return 0
        backend = backend or ComfyUIBackend(base_url=args.comfyui_url, profile="noobai", timeout=600.0)
        if not args.no_gpu_etiquette:
            _gpu_etiquette(args.comfyui_url, before=True)
        try:
            if args.command == "candidates":
                return await cmd_candidates(designs, slugs, args, backend)
            return await cmd_sheets(designs, slugs, args, backend)
        finally:
            if not args.no_gpu_etiquette:
                _gpu_etiquette(args.comfyui_url, before=False)
    if args.command == "approve":
        return cmd_approve(designs, args.slug, args.n, args.round, args)
    if args.command == "reroll":
        return cmd_reroll(designs, args.slug, args.note, args)
    if args.command == "gallery":
        return cmd_gallery(designs, args)
    return cmd_export(designs, args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
```

Notes for the implementer:
- `--rerolls` selects designs whose **last** note is a reroll note (the note format is `"<date> reroll: <text>"`); after a new candidates round the last note becomes the round note, so a design isn't rerolled twice.
- In the test `test_all_drafts_and_rerolls_selection`, the expected `notes[-2]` check works because `candidates` appends its round note after the reroll note.
- `ComfyUIBackend(... timeout=600.0)` because a full sheet can exceed 300 s on a cold start.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/comfyui_backend.py tools/__init__.py tools/design_studio.py tests/test_design_studio.py tests/test_comfyui_backend.py
git commit -m "feat(19b): design studio CLI - candidates, approve, reroll, sheets, gallery, export"
```

---

### Task 4: The 22 draft designs

**Files:**
- Create: 22 files in `narrator/worlds/designs/` (slugs below), `tests/test_design_drafts.py`
- Read first: `narrator/worlds/kuroshio.toml` (primer, every `[[npc]]` card, every `[[district]]` card)

**Interfaces:**
- Consumes: `Design`, `save_design`, `load_designs`, `kuroshio_designs` (Task 1); `kuroshio()` (narrator/world.py).

**Designs to write** (each `status = "draft"`, `seed = 0`, `palette = []`, `notes = ["2026-10-28 draft from world card"]`):

Characters (`kind = "character"`, `source = "npc:<exact NPC name>"`): Mama Sato, Old Hara, Jun Arakawa, Saeko Kirigaya, Hoshikawa Tadamori, Hoshikawa Rei, Brother Tōru, Kenji Moro, Captain Ide, Mitsu, Hachi.

Districts (`kind = "location"`, `source = "district:<exact district name>"`): Tenjō Heights, Hanabira-chō, Ikebe Low, Kuroshio Docks, The Loop, Yomi Line.

Places (`kind = "location"`, `source = "place:<name>"`): Mama Sato's izakaya, Old Hara's clinic, Jun Arakawa's karaoke box, Hoshikawa penthouse, Hachi's pier.

**Writing rules (from the spec):**
- Characters: `presentation` set (feminine/masculine/androgynous; Hachi omits it — the tags start with `android, robot joints` so the subject is `1other`). `tags` order: hair → face/eyes → build/age → outfit → signature chrome/props. Chrome must name its side ("mechanical left arm, human right hand"); when a character has one-sided chrome, add the matching per-design `negative` ("two mechanical arms"). Use concrete Danbooru-style tags only (no sentences, no names, no franchise terms). Ground every visual in the card (role, district, voice, secret) — e.g. Old Hara: elderly male chrome-ya, thin, magnifier eyepiece, surgical apron; Saeko: torite crew leader, polite, throttle-locked chrome; Mitsu: idol with perfect-voice throat chrome; Kenji Moro: 19-year-old Kaminari Run bike-gang leader; Captain Ide: Ōgane Heavy precinct captain uniform; Hoshikawa Tadamori: elderly keiretsu patriarch, formal; Rei: 24-year-old heir slumming in Hanabira-chō; Brother Tōru: Lantern Guild keeper with a lantern; Hachi: utsusemi android shell, ex-station-announcer.
- Locations: `tags` order: place type → architecture → signage → lighting → weather (no subject tag — the code adds `scenery, no humans`). `alt_tags` = interior or reverse angle. `props` = 3–5 signature objects as short tag phrases (e.g. izakaya: `paper lanterns`, `ramen bowl`, `sake bottles`, `wooden counter`).
- 12–25 tags per design.

- [ ] **Step 1: Write the failing test** — `tests/test_design_drafts.py`:

```python
from narrator.designs import kuroshio_designs
from narrator.world import kuroshio


def test_all_22_drafts_load():
    designs = kuroshio_designs()
    assert len(designs) == 22
    assert sum(d.kind == "character" for d in designs.values()) == 11


def test_character_sources_match_world_npcs():
    npc_names = {n.name for n in kuroshio().npcs}
    sources = {d.source.removeprefix("npc:") for d in kuroshio_designs().values() if d.kind == "character"}
    assert sources == npc_names


def test_district_sources_match_world_districts():
    districts = {d.name for d in kuroshio().districts}
    sources = {d.source.removeprefix("district:") for d in kuroshio_designs().values() if d.source.startswith("district:")}
    assert sources == districts


def test_drafts_follow_the_writing_rules():
    for d in kuroshio_designs().values():
        tags = [t.strip() for t in d.tags.split(",")]
        assert 12 <= len(tags) <= 25, d.name
        assert d.status == "draft" and d.notes == ["2026-10-28 draft from world card"], d.name
        if d.kind == "location":
            assert d.alt_tags and 3 <= len(d.props) <= 5, d.name
            assert "scenery" not in d.tags, d.name
        if "mechanical left arm" in d.tags or "mechanical right arm" in d.tags:
            assert "two mechanical arms" in d.negative, d.name
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_design_drafts.py -q` — FAIL (0 designs).

- [ ] **Step 3: Write the 22 TOML files**

Write each with `save_design` from a short throwaway script (so the field order and escaping are canonical), or by hand in exactly the canonical order — then confirm with `python -c "from narrator.designs import load_designs; print(len(load_designs()))"`. Note `kuroshio_designs()` is `functools.cache`d — tests run in a fresh process so this is fine.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/ -q` — all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/worlds/designs/ tests/test_design_drafts.py
git commit -m "feat(19b): 22 draft designs from the Kuroshio world cards"
```

---

## Verification (controller, after the final review)

- **Live** on the GPU box: `python -m tools.design_studio candidates mama-sato mama-satos-izakaya`, `approve` #1 for each (test only), `sheets mama-sato mama-satos-izakaya`, `gallery`; record timings and peak VRAM; then reset the two test designs to their committed draft state (git checkout of those two TOMLs, delete their `design-data/` folders).
- **Review round 1:** `candidates --all-drafts` (overnight-sized, ~45 min) → `gallery` → republish the owner's gallery link.
- **Docs:** README "Design studio" section (commands, data folder, export); ROADMAP "19b." entry plus the studio-track candidates (pose/mouth/hand/height sheets, costume variants, colour script, prop/vehicle/chrome-catalog sheets, faction graphics, FX sheets, storyboard export, stage view, district map).
