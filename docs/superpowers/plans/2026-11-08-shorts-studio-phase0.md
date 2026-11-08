# Shorts studio, Phase 0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `tools/shorts` package that turns a written short (TOML) into a Blender grey-box, layered prompts, reference bundles and paid/manual video takes with a spend guard, an AI Lab review page, an identity check and a rough cut — then runs the pilot (Saeko + Rin at Mama Sato's izakaya) and the anime A/B test.

**Architecture:** Plain-Python core (model, prompt, takes, backends, page, assemble) tested with pytest on the dev box. Blender scripts run headless on the GPU box (192.168.10.19) through a small rsync + ssh runner; ffmpeg runs locally. Review reuses the existing design-picks verdict API (`/designs/api/images/<id>`); the page is a static generator published like the design gallery.

**Tech Stack:** Python 3.11+ stdlib (`tomllib`, `json`, `subprocess`), httpx (already a dependency) for fal, Blender 4.5 LTS (bpy, headless, Workbench), ffmpeg, existing `tools.design_check` (dghs-imgutils, `qa` extra).

**Spec:** `docs/superpowers/specs/2026-11-08-shorts-studio-design.md` (read it first). Research: `docs/superpowers/research/2026-11-08-foyege-method.md`, `docs/superpowers/research/2026-11-08-ai-shorts-tools-and-hardware.md`.

**Scope:** Spec Phase 0 + the rough-cut tool. NOT in this plan: IndexTTS2 / ACE-Step installs and voice references (Phase 1 plan), local Wan backend and LoRA training (Phase 2 plan, needs the 24 GB card), ComfyUI partner-node backend.

## Global Constraints

- Shorts are promotion / personal use; NoobAI-XL designs stay the source of truth. Art-direction rules (`docs/art-direction.md`) apply unchanged; no adult/explicit content; no daytime scenes (owner rule 2026-11-07).
- Prompt layers L1–L5, each fact stated once; L2 (asset mapping) and L4 (character state) must not contain position words.
- Spend guard: no paid submit when `costs.json` total + estimate > `budget_usd` (default 25). Every take records its real cost.
- API keys live only in `~/.config/nightwire/secrets.env`, entered by the owner. Never print, log or commit them.
- Renders and takes live in git-ignored `design-data/shorts/<slug>/`; the script (short.toml + shot.tomls) is committed under `narrator/worlds/shorts/<slug>/`.
- GPU etiquette: one GPU job at a time on the GPU box; free ComfyUI VRAM (`POST /free`) and unload Ollama (`keep_alive 0`) before Blender renders.
- New sub-packages must be listed in `[tool.setuptools.packages.find]` (CI installs the package; lesson from Phase 19b).
- Commits go to `main` (project convention); no AI-attribution trailers (workspace rule). Ask the owner before every `git push`.
- Anything that downloads (Blender) or spends money (fal) needs the owner's go-ahead at that step.
- Tests: `python -m pytest tests/ -q` must stay green; Blender-dependent tests skip when `NIGHTWIRE_BLENDER` is unset.

## File map

| File | Responsibility |
|---|---|
| `tools/shorts/__init__.py` | package marker, `SHORTS_DIR`, `DATA_DIR` constants |
| `tools/shorts/model.py` | dataclasses + TOML loading/validation for short and shot |
| `tools/shorts/prompt.py` | L1–L5 assembly, position-word guard, reference file list |
| `tools/shorts/takes.py` | rates, estimate, ledger (`costs.json`), take filing, verdicts |
| `tools/shorts/backends/manual.py` | bundle folder writer, inbox import |
| `tools/shorts/backends/fal.py` | fal queue API client (submit, poll, download) |
| `tools/shorts/greybox/scene.py` | pure-Python: short → `scene.json` (no bpy) |
| `tools/shorts/greybox/blender_build.py` | runs inside Blender: build `.blend` from `scene.json`, render shots, floor plan |
| `tools/shorts/remote.py` | rsync + ssh runner for Blender on the GPU box |
| `tools/shorts/check.py` | sample frames from a take and run the existing identity check |
| `tools/shorts/assemble.py` | edit list, subtitle file, ffmpeg command for the rough cut |
| `tools/shorts/page.py` + `tools/shorts/page.html` | static `/shorts/` review page generator |
| `tools/shorts/__main__.py` | CLI: `check prompt greybox bundle inbox submit page verdicts idcheck assemble status` |
| `tools/design_check.py` (modify) | `--scenes-dir`, `--out` options |
| `narrator/worlds/shorts/saeko-rin-izakaya/` | pilot short.toml + shots/S01.toml |
| `docs/shorts-guide.md` | how to run the studio |
| `tests/test_shorts_*.py` | one test file per module |

---

### Task 1: Package skeleton and the short/shot model

**Files:**
- Create: `tools/shorts/__init__.py`, `tools/shorts/model.py`, `tests/test_shorts_model.py`
- Modify: `pyproject.toml` (packages.find, package-data)

**Interfaces:**
- Produces:
  - `tools.shorts.SHORTS_DIR: Path` = `narrator/worlds/shorts` (repo-relative via `Path(__file__)`), `tools.shorts.DATA_DIR: Path` = `Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "shorts"`
  - `Line(who: str, t: float, text: str, early_s: float = 0.0, overlap_s: float = 0.0, disfluency: str = "", on_word: str = "")`
  - `Acting(who: str, t: tuple[float, float], goal: str, emotion: str, trigger: str = "", face: str = "", gaze: str = "", voice: str = "", end: str = "")`
  - `Beat(t: tuple[float, float], text: str)`
  - `CameraKey(t: float, at: tuple[float, float, float], look: tuple[float, float, float])`
  - `Shot(id: str, start: float, end: float, summary: str, lens: float, camera: list[CameraKey], state: dict[str, str], beats: list[Beat], acting: list[Acting], lines: list[Line], model: str = "")` with property `duration -> float`
  - `Block(name: str, size: tuple[float, float, float], at: tuple[float, float, float], rot: float = 0.0)`
  - `Figure(id: str, tier: str, pose: str, keys: list[tuple[float, float, float, float]])` — keys are `(t, x, y, facing_deg)`
  - `Short(slug: str, title: str, logline: str, place: str, style: str, budget_usd: float, cast: dict[str, str], beats: list[str], blocks: list[Block], figures: dict[str, Figure], shots: list[Shot])`
  - `load_short(folder: Path) -> Short` — reads `folder/short.toml` and `folder/shots/*.toml` (sorted)
  - `validate_short(s: Short, designs: dict[str, Design]) -> list[str]` — returns problems (empty = OK)
  - constants `TIERS = ("capsule", "mannequin", "rigged")`, `DISFLUENCIES = ("", "block", "repeat", "silence", "self-correct")`, `MAX_SHOT_S = 30.0`

- [ ] **Step 1: Write the failing tests** — `tests/test_shorts_model.py`

```python
from pathlib import Path

import pytest

from narrator.designs import Design
from tools.shorts.model import load_short, validate_short

SHORT = '''
title = "Last orders"
logline = "Saeko pays Rin's tab and asks one question too many."
place = "mama-satos-izakaya"
style = "anime cinematic, neon night, rain on the windows"
budget_usd = 25.0
beats = ["anomaly: Rin's tab is already paid"]

[cast]
C1 = "saeko-kirigaya"
C2 = "rin-kageyama"

[[room.blocks]]
name = "counter"
size = [4.0, 0.6, 1.0]
at = [0.0, 1.2, 0.0]

[figures.C1]
tier = "mannequin"
pose = "sit"
keys = [[0.0, -0.6, 0.5, 90.0]]

[figures.C2]
tier = "capsule"
pose = "stand"
keys = [[0.0, 0.8, 0.5, 270.0], [4.0, 0.4, 0.5, 270.0]]
'''

SHOT = '''
id = "S01"
start = 0.0
end = 5.0
summary = "slow push in over C1's right shoulder to C2 medium close-up"
lens = 35.0
camera = [
  { t = 0.0, at = [-1.8, -1.5, 1.4], look = [0.6, 0.5, 1.2] },
  { t = 5.0, at = [-1.1, -0.6, 1.35], look = [0.5, 0.5, 1.3] },
]

[state]
C1 = "tired, amused, decided"
C2 = "guarded, pretending not to care"

[[beats]]
t = [0.0, 2.5]
text = "C1 MCU from behind, C2 enters frame right in background, looks at C1"

[[acting]]
who = "C2"
t = [1.0, 3.5]
goal = "find out why her tab is paid"
emotion = "suspicion cracking into embarrassment"
trigger = "paid"

[[lines]]
who = "C2"
t = 1.2
text = "Who paid it?"
disfluency = "block"
on_word = "Who"
'''


def write(tmp_path: Path, short=SHORT, shot=SHOT) -> Path:
    (tmp_path / "shots").mkdir(parents=True)
    (tmp_path / "short.toml").write_text(short)
    (tmp_path / "shots" / "S01.toml").write_text(shot)
    return tmp_path


def designs():
    return {s: Design(name=n, kind="character", source="t", tags="x", status="approved")
            for s, n in (("saeko-kirigaya", "Saeko Kirigaya"), ("rin-kageyama", "Rin Kageyama"))} | {
        "mama-satos-izakaya": Design(name="Mama Sato's Izakaya", kind="location", source="t", tags="x", status="approved")}


def test_load_short_reads_cast_figures_and_shots(tmp_path):
    s = load_short(write(tmp_path))
    assert s.slug == tmp_path.name
    assert s.cast == {"C1": "saeko-kirigaya", "C2": "rin-kageyama"}
    assert s.figures["C2"].keys[1] == (4.0, 0.4, 0.5, 270.0)
    shot = s.shots[0]
    assert shot.id == "S01" and shot.duration == 5.0
    assert shot.camera[1].at == (-1.1, -0.6, 1.35)
    assert shot.lines[0].disfluency == "block"
    assert shot.acting[0].t == (1.0, 3.5)


def test_valid_short_has_no_problems(tmp_path):
    assert validate_short(load_short(write(tmp_path)), designs()) == []


@pytest.mark.parametrize("bad, expected", [
    (SHOT.replace('who = "C2"\nt = 1.2', 'who = "C9"\nt = 1.2'), "unknown cast id C9"),
    (SHOT.replace("end = 5.0", "end = 31.0"), "longer than 30"),
    (SHOT.replace('disfluency = "block"', 'disfluency = "stutter"'), "disfluency"),
    (SHOT.replace("t = 1.2", "t = 9.0"), "outside the shot"),
])
def test_validate_short_reports_problems(tmp_path, bad, expected):
    problems = validate_short(load_short(write(tmp_path, shot=bad)), designs())
    assert any(expected in p for p in problems), problems


def test_unapproved_or_missing_design_is_a_problem(tmp_path):
    d = designs()
    d["rin-kageyama"].status = "draft"
    del d["mama-satos-izakaya"]
    problems = validate_short(load_short(write(tmp_path)), d)
    assert any("rin-kageyama is not approved" in p for p in problems)
    assert any("place mama-satos-izakaya" in p for p in problems)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_shorts_model.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'tools.shorts'`

- [ ] **Step 3: Implement** — `tools/shorts/__init__.py`

```python
"""Shorts studio: written shorts -> grey-box, prompts, takes, review, rough cut.
See docs/superpowers/specs/2026-11-08-shorts-studio-design.md."""

import os
from pathlib import Path

SHORTS_DIR = Path(__file__).resolve().parents[2] / "narrator" / "worlds" / "shorts"


def data_dir() -> Path:
    return Path(os.environ.get("NIGHTWIRE_DESIGN_DIR", "design-data")) / "shorts"
```

(`DATA_DIR` is a function `data_dir()` so tests can set the env var; use `data_dir()` everywhere.)

`tools/shorts/model.py`:

```python
"""A short is one TOML (cast, room, figures on one shared timeline) plus one TOML per shot."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TIERS = ("capsule", "mannequin", "rigged")
DISFLUENCIES = ("", "block", "repeat", "silence", "self-correct")
MAX_SHOT_S = 30.0


@dataclass
class Line:
    who: str
    t: float
    text: str
    early_s: float = 0.0
    overlap_s: float = 0.0
    disfluency: str = ""
    on_word: str = ""


@dataclass
class Acting:
    who: str
    t: tuple[float, float]
    goal: str
    emotion: str
    trigger: str = ""
    face: str = ""
    gaze: str = ""
    voice: str = ""
    end: str = ""


@dataclass
class Beat:
    t: tuple[float, float]
    text: str


@dataclass
class CameraKey:
    t: float
    at: tuple[float, float, float]
    look: tuple[float, float, float]


@dataclass
class Shot:
    id: str
    start: float
    end: float
    summary: str
    lens: float
    camera: list[CameraKey]
    state: dict[str, str] = field(default_factory=dict)
    beats: list[Beat] = field(default_factory=list)
    acting: list[Acting] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    model: str = ""

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


@dataclass
class Block:
    name: str
    size: tuple[float, float, float]
    at: tuple[float, float, float]
    rot: float = 0.0


@dataclass
class Figure:
    id: str
    tier: str
    pose: str
    keys: list[tuple[float, float, float, float]]


@dataclass
class Short:
    slug: str
    title: str
    logline: str
    place: str
    style: str
    budget_usd: float
    cast: dict[str, str]
    beats: list[str]
    blocks: list[Block]
    figures: dict[str, Figure]
    shots: list[Shot]


def _shot(d: dict) -> Shot:
    return Shot(
        id=d["id"], start=float(d["start"]), end=float(d["end"]), summary=d["summary"], lens=float(d.get("lens", 35.0)),
        camera=[CameraKey(float(k["t"]), tuple(k["at"]), tuple(k["look"])) for k in d["camera"]],
        state=dict(d.get("state", {})),
        beats=[Beat(tuple(b["t"]), b["text"]) for b in d.get("beats", [])],
        acting=[Acting(**{**a, "t": tuple(a["t"])}) for a in d.get("acting", [])],
        lines=[Line(**ln) for ln in d.get("lines", [])],
        model=d.get("model", ""),
    )


def load_short(folder: Path) -> Short:
    d = tomllib.loads((folder / "short.toml").read_text())
    return Short(
        slug=folder.name, title=d["title"], logline=d.get("logline", ""), place=d["place"], style=d.get("style", ""),
        budget_usd=float(d.get("budget_usd", 25.0)), cast=dict(d["cast"]), beats=list(d.get("beats", [])),
        blocks=[Block(b["name"], tuple(b["size"]), tuple(b["at"]), float(b.get("rot", 0.0)))
                for b in d.get("room", {}).get("blocks", [])],
        figures={cid: Figure(cid, f["tier"], f.get("pose", "stand"), [tuple(map(float, k)) for k in f["keys"]])
                 for cid, f in d.get("figures", {}).items()},
        shots=[_shot(tomllib.loads(p.read_text())) for p in sorted((folder / "shots").glob("*.toml"))],
    )


def validate_short(s: Short, designs: dict) -> list[str]:
    problems = []
    for cid, slug in s.cast.items():
        d = designs.get(slug)
        if d is None:
            problems.append(f"{cid}: no design {slug}")
        elif d.status != "approved":
            problems.append(f"{cid}: {slug} is not approved")
    place = designs.get(s.place)
    if place is None or place.kind != "location":
        problems.append(f"place {s.place} is not a location design")
    for cid, f in s.figures.items():
        if cid not in s.cast:
            problems.append(f"figure: unknown cast id {cid}")
        if f.tier not in TIERS:
            problems.append(f"figure {cid}: tier {f.tier!r} not in {TIERS}")
    for shot in s.shots:
        where = f"shot {shot.id}"
        if shot.duration <= 0 or shot.duration > MAX_SHOT_S:
            problems.append(f"{where}: {shot.duration}s is empty or longer than 30 s")
        if len(shot.camera) < 1:
            problems.append(f"{where}: needs at least one camera key")
        ids = [ln.who for ln in shot.lines] + [a.who for a in shot.acting] + list(shot.state)
        for cid in ids:
            if cid not in s.cast:
                problems.append(f"{where}: unknown cast id {cid}")
        for ln in shot.lines:
            if ln.disfluency not in DISFLUENCIES:
                problems.append(f"{where}: disfluency {ln.disfluency!r} not in {DISFLUENCIES}")
            if not shot.start <= ln.t <= shot.end:
                problems.append(f"{where}: line at {ln.t}s is outside the shot")
    return problems
```

`pyproject.toml`: change `include = ["ruleset", "engine", "server", "narrator", "tools"]` to `include = ["ruleset", "engine", "server", "narrator", "tools", "tools.*"]`, and add `"shorts/page.html"` to the `tools` package-data list.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_shorts_model.py -q` → PASS
- [ ] **Step 5: Commit** — `git add tools/shorts pyproject.toml tests/test_shorts_model.py && git commit -m "feat(shorts): short and shot model with validation"`

---

### Task 2: Prompt assembly (L1–L5) and reference list

**Files:**
- Create: `tools/shorts/prompt.py`, `tests/test_shorts_prompt.py`

**Interfaces:**
- Consumes: `Short`, `Shot`, `Line`, `Acting`, `Beat` from Task 1; `narrator.designs.Design`.
- Produces:
  - `POSITION_WORDS: re.Pattern`
  - `layers(short: Short, shot: Shot, designs: dict[str, Design]) -> dict[str, str]` keys `"L1".."L5"`
  - `position_problems(layers: dict[str, str]) -> list[str]` (checks L2 and L4 only)
  - `build_prompt(short, shot, designs) -> str` — raises `ValueError` listing problems
  - `ref_files(short: Short, design_dir: Path, shot_dir: Path) -> list[tuple[str, Path]]` — `(label, path)` in order: `C1_turnaround.png, C1_expressions.png, C1_colorguide.png, …, place.png, floorplan.png, greybox.mp4`; only existing files

- [ ] **Step 1: Failing tests** — `tests/test_shorts_prompt.py`

```python
import pytest

from test_shorts_model import designs, write
from tools.shorts.model import load_short
from tools.shorts.prompt import build_prompt, layers, position_problems, ref_files


def short_and_shot(tmp_path):
    s = load_short(write(tmp_path / "pilot"))
    return s, s.shots[0]


def test_layers_state_each_fact_once(tmp_path):
    s, shot = short_and_shot(tmp_path)
    L = layers(s, shot, designs())
    assert "grey-box" in L["L1"] and shot.summary in L["L1"]
    assert "C1 = Saeko Kirigaya" in L["L2"] and "C2 = Rin Kageyama" in L["L2"]
    assert s.style in L["L3"]
    assert "C2: guarded, pretending not to care" in L["L4"]
    assert "0.0-2.5s" in L["L5"] and "Who paid it?" in L["L5"]
    assert "block on \"Who\"" in L["L5"]


def test_build_prompt_joins_layers_in_order(tmp_path):
    s, shot = short_and_shot(tmp_path)
    p = build_prompt(s, shot, designs())
    assert p.index("C1 = Saeko") < p.index(s.style) < p.index("Who paid it?")


@pytest.mark.parametrize("text", ["sits on the left", "behind the counter", "next to C1", "in front of the door"])
def test_position_words_in_state_are_rejected(text):
    assert position_problems({"L1": "", "L2": "C1 = Saeko", "L3": "", "L4": f"C1: tired, {text}", "L5": "C1 left"})


def test_position_words_in_timecodes_are_fine():
    assert position_problems({"L1": "", "L2": "C1 = Saeko", "L3": "", "L4": "C1: tired", "L5": "C2 frame right"}) == []


def test_build_prompt_raises_on_position_words(tmp_path):
    s, shot = short_and_shot(tmp_path)
    shot.state["C1"] = "tired, sitting left of the door"
    with pytest.raises(ValueError, match="L4"):
        build_prompt(s, shot, designs())


def test_ref_files_lists_existing_refs_in_order(tmp_path):
    s, shot = short_and_shot(tmp_path)
    dd = tmp_path / "design-data"
    for slug, files in {"saeko-kirigaya": ["turnaround.png", "expressions.png"], "rin-kageyama": ["turnaround.png"],
                        "mama-satos-izakaya": ["play.png"]}.items():
        (dd / slug).mkdir(parents=True)
        for f in files:
            (dd / slug / f).write_bytes(b"x")
    shot_dir = tmp_path / "S01"
    shot_dir.mkdir()
    (shot_dir / "greybox.mp4").write_bytes(b"x")
    labels = [label for label, _ in ref_files(s, dd, shot_dir)]
    assert labels == ["C1_turnaround.png", "C1_expressions.png", "C2_turnaround.png", "place.png", "greybox.mp4"]
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_shorts_prompt.py -q` → FAIL (no module)

- [ ] **Step 3: Implement** — `tools/shorts/prompt.py`

```python
"""Foyege's layered prompt: L1 grey-box role, L2 who is who, L3 look, L4 state, L5 timecodes.
Each fact lives in one layer; positions only in the floor plan / grey-box and in L5's camera terms."""

import re
from pathlib import Path

from tools.shorts.model import Short, Shot

POSITION_WORDS = re.compile(
    r"\b(left|right|behind|beside|next to|in front of|across from|opposite|near|corner|at the (?:counter|door|bar|table|window))\b",
    re.IGNORECASE)
CHARACTER_SHEETS = ("turnaround.png", "expressions.png", "colorguide.png")


def _t(a: float, b: float) -> str:
    return f"{a:.1f}-{b:.1f}s"


def layers(short: Short, shot: Shot, designs: dict) -> dict[str, str]:
    l1 = ("The grey-box reference video provides camera path, character positions, silhouettes and timing. "
          "Replace each grey mannequin with its character, keep no grey material. "
          f"Camera: {shot.summary}. Floor plan: C1..C{len(short.cast)} as marked.")
    l2 = "\n".join(f"{cid} = {designs[slug].name} (refs {cid}_*)" for cid, slug in short.cast.items())
    l3 = short.style
    l4 = "\n".join(f"{cid}: {state}" for cid, state in shot.state.items())
    rows: list[tuple[float, str]] = [(b.t[0], f"{_t(*b.t)} {b.text}") for b in shot.beats]
    for a in shot.acting:
        parts = [f"goal: {a.goal}", f"emotion: {a.emotion}"]
        parts += [f"{k}: {v}" for k, v in (("trigger word", a.trigger), ("face", a.face), ("gaze/body", a.gaze),
                                          ("voice/breath", a.voice), ("ends", a.end)) if v]
        rows.append((a.t[0], f"{_t(*a.t)} {a.who} acting - " + "; ".join(parts)))
    for ln in shot.lines:
        extra = []
        if ln.early_s:
            extra.append(f"enters {ln.early_s:.1f}s early")
        if ln.overlap_s:
            extra.append(f"overlaps {ln.overlap_s:.1f}s")
        if ln.disfluency:
            extra.append(f'{ln.disfluency} on "{ln.on_word}"' if ln.on_word else ln.disfluency)
        rows.append((ln.t, f'{ln.t:.1f}s {ln.who} says: "{ln.text}"' + (f" ({', '.join(extra)})" if extra else "")))
    rows.sort(key=lambda r: r[0])
    l5 = "\n".join(r for _, r in rows)
    l5 += "\nNo turn-by-turn reading; do not finish interrupted lines."
    return {"L1": l1, "L2": l2, "L3": l3, "L4": l4, "L5": l5}


def position_problems(L: dict[str, str]) -> list[str]:
    return [f"{k}: position word {m.group(0)!r} (positions belong to the floor plan and L5)"
            for k in ("L2", "L4") for m in POSITION_WORDS.finditer(L[k])]


def build_prompt(short: Short, shot: Shot, designs: dict) -> str:
    L = layers(short, shot, designs)
    problems = position_problems(L)
    if problems:
        raise ValueError("; ".join(problems))
    return "\n\n".join(L[k] for k in ("L1", "L2", "L3", "L4", "L5"))


def ref_files(short: Short, design_dir: Path, shot_dir: Path) -> list[tuple[str, Path]]:
    out = []
    for cid, slug in short.cast.items():
        out += [(f"{cid}_{f}", design_dir / slug / f) for f in CHARACTER_SHEETS]
    out.append(("place.png", design_dir / short.place / "play.png"))
    out.append(("floorplan.png", shot_dir.parent.parent / "floorplan.png"))
    out.append(("greybox.mp4", shot_dir / "greybox.mp4"))
    return [(label, p) for label, p in out if p.exists()]
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_shorts_prompt.py -q` → PASS
- [ ] **Step 5: Commit** — `git commit -am "feat(shorts): layered prompt assembly with position-word guard" ` (add the new files first: `git add tools/shorts/prompt.py tests/test_shorts_prompt.py`)

---

### Task 3: Rates, spend guard, take filing, verdicts

**Files:**
- Create: `tools/shorts/takes.py`, `tests/test_shorts_takes.py`

**Interfaces:**
- Produces:
  - `RATES: dict[str, float]` USD per generated second (keys are model keys used by backends)
  - `estimate(model: str, seconds: float) -> float` — `KeyError` for unknown model
  - `class Ledger(path: Path)`: `.total() -> float`, `.add(shot: str, take: str, model: str, cost: float) -> None`, `.check(budget: float, cost: float) -> None` raises `BudgetError`
  - `class BudgetError(Exception)`
  - `next_take_id(shot_dir: Path) -> str` → `"t001"`, `"t002"`…
  - `file_take(shot_dir: Path, video: Path, meta: dict) -> str` — copies video to `takes/<id>.mp4`, writes `takes/<id>.json` (meta + `"id"`, `"at"` ISO time), returns id
  - `take_image_id(slug: str, shot: str, take: str) -> str` → `"short--<slug>--<shot lowercased>--<take>"` (id used with the design-picks images API, which only accepts `[a-z0-9][a-z0-9-]{0,99}`; shot ids are upper-case like `S01`, so they are lowercased here and upper-cased back in `apply_verdicts`)
  - `apply_verdicts(short_dir: Path, slug: str, api: dict) -> dict[str, dict]` — writes each shot's `verdicts.json` from the API dict, returns `{image_id: verdict}` for this short

- [ ] **Step 1: Failing tests** — `tests/test_shorts_takes.py`

```python
import json

import pytest

from tools.shorts.takes import (BudgetError, Ledger, apply_verdicts, estimate, file_take, next_take_id,
                                take_image_id)


def test_estimate_uses_rate_per_second():
    assert estimate("seedance-2.5", 5) == pytest.approx(5 * 0.473)
    with pytest.raises(KeyError):
        estimate("nope", 5)


def test_ledger_totals_and_refuses_over_budget(tmp_path):
    led = Ledger(tmp_path / "costs.json")
    led.add("S01", "t001", "seedance-2.0-fast", 1.21)
    led.add("S01", "t002", "kling-3", 0.70)
    assert led.total() == pytest.approx(1.91)
    led.check(budget=25, cost=20)
    with pytest.raises(BudgetError, match="25"):
        led.check(budget=25, cost=24)
    assert json.loads((tmp_path / "costs.json").read_text())[0]["take"] == "t001"


def test_take_ids_count_up_and_files_are_written(tmp_path):
    shot = tmp_path / "S01"
    src = tmp_path / "x.mp4"
    src.write_bytes(b"video")
    assert next_take_id(shot) == "t001"
    assert file_take(shot, src, {"model": "kling-3", "cost": 0.7}) == "t001"
    assert file_take(shot, src, {"model": "kling-3", "cost": 0.7}) == "t002"
    assert (shot / "takes" / "t002.mp4").read_bytes() == b"video"
    meta = json.loads((shot / "takes" / "t001.json").read_text())
    assert meta["model"] == "kling-3" and meta["id"] == "t001" and "at" in meta


def test_take_image_id_matches_picks_api_rule():
    import re
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", take_image_id("saeko-rin-izakaya", "S01", "t001"))


def test_apply_verdicts_writes_per_shot_files(tmp_path):
    (tmp_path / "shots" / "S01").mkdir(parents=True)
    api = {take_image_id("pilot", "S01", "t001"): {"verdict": "keep"},
           take_image_id("pilot", "S01", "t002"): {"verdict": "fix", "note": "C2 flips side at 3s"},
           "other--image": {"verdict": "keep"}}
    mine = apply_verdicts(tmp_path, "pilot", api)
    assert len(mine) == 2
    v = json.loads((tmp_path / "shots" / "S01" / "verdicts.json").read_text())
    assert v == {"t001": {"verdict": "keep"}, "t002": {"verdict": "fix", "note": "C2 flips side at 3s"}}
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_shorts_takes.py -q` → FAIL

- [ ] **Step 3: Implement** — `tools/shorts/takes.py`

```python
"""What a take costs, what has been spent, and where takes and verdicts are filed."""

import datetime as dt
import json
import shutil
from pathlib import Path

# USD per generated second at 720p. From docs/superpowers/research/2026-11-08-ai-shorts-tools-and-hardware.md;
# Task 5 re-checks the fal ones against fal.ai before the first paid run. "manual" costs are typed in by hand.
RATES = {
    "seedance-2.5": 0.473,
    "seedance-2.0": 0.3034,
    "seedance-2.0-fast": 0.2419,
    "kling-3": 0.14,
    "veo-3.1-fast": 0.10,
}


class BudgetError(Exception):
    pass


def estimate(model: str, seconds: float) -> float:
    return round(RATES[model] * seconds, 4)


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    def _rows(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def total(self) -> float:
        return round(sum(r["cost"] for r in self._rows()), 4)

    def add(self, shot: str, take: str, model: str, cost: float) -> None:
        rows = self._rows() + [{"shot": shot, "take": take, "model": model, "cost": cost,
                                "at": dt.datetime.now().isoformat(timespec="seconds")}]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, indent=1))

    def check(self, budget: float, cost: float) -> None:
        if self.total() + cost > budget:
            raise BudgetError(f"spent ${self.total():.2f} + ${cost:.2f} would pass the ${budget:.0f} budget; "
                              "raise budget_usd in short.toml to continue")


def next_take_id(shot_dir: Path) -> str:
    return f"t{len(list((shot_dir / 'takes').glob('t*.mp4'))) + 1:03d}"


def file_take(shot_dir: Path, video: Path, meta: dict) -> str:
    tid = next_take_id(shot_dir)
    (shot_dir / "takes").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(video, shot_dir / "takes" / f"{tid}.mp4")
    meta = {**meta, "id": tid, "at": dt.datetime.now().isoformat(timespec="seconds")}
    (shot_dir / "takes" / f"{tid}.json").write_text(json.dumps(meta, indent=1))
    return tid


def take_image_id(slug: str, shot: str, take: str) -> str:
    return f"short--{slug}--{shot.lower()}--{take}"


def apply_verdicts(short_dir: Path, slug: str, api: dict) -> dict[str, dict]:
    prefix = f"short--{slug}--"
    mine = {k: v for k, v in api.items() if k.startswith(prefix)}
    per_shot: dict[str, dict] = {}
    for key, v in mine.items():
        shot, take = key[len(prefix):].split("--")
        shot = shot.upper()
        per_shot.setdefault(shot, {})[take] = {k: v[k] for k in ("verdict", "note") if k in v}
    for shot, verdicts in per_shot.items():
        (short_dir / "shots" / shot).mkdir(parents=True, exist_ok=True)
        (short_dir / "shots" / shot / "verdicts.json").write_text(json.dumps(verdicts, indent=1, sort_keys=True))
    return mine
```

- [ ] **Step 4: Run** — PASS
- [ ] **Step 5: Commit** — `git add tools/shorts/takes.py tests/test_shorts_takes.py && git commit -m "feat(shorts): rates, spend guard, take filing and verdicts"`

---

### Task 4: Manual backend — bundle and inbox

**Files:**
- Create: `tools/shorts/backends/__init__.py` (empty), `tools/shorts/backends/manual.py`, `tests/test_shorts_manual.py`

**Interfaces:**
- Consumes: `ref_files`, `build_prompt` (Task 2); `file_take`, `Ledger` (Task 3).
- Produces:
  - `write_bundle(shot_dir: Path, prompt: str, refs: list[tuple[str, Path]]) -> Path` — recreates `shot_dir/bundle/` with `prompt.txt` and copies of refs under their labels; returns the folder
  - `import_inbox(short_dir: Path, shot_id: str, cost: float, model: str, ledger: Ledger) -> list[str]` — files every `short_dir/inbox/*.mp4` as a take of `shot_id` (meta `{"model", "cost", "backend": "manual", "source": name}`), adds to ledger, moves the source to `inbox/done/`; returns take ids

- [ ] **Step 1: Failing tests** — `tests/test_shorts_manual.py`

```python
from tools.shorts.backends.manual import import_inbox, write_bundle
from tools.shorts.takes import Ledger


def test_bundle_has_prompt_and_named_refs(tmp_path):
    ref = tmp_path / "turnaround.png"
    ref.write_bytes(b"png")
    shot = tmp_path / "S01"
    (shot / "bundle").mkdir(parents=True)
    (shot / "bundle" / "stale.png").write_bytes(b"old")
    out = write_bundle(shot, "the prompt", [("C1_turnaround.png", ref)])
    assert (out / "prompt.txt").read_text() == "the prompt"
    assert (out / "C1_turnaround.png").read_bytes() == b"png"
    assert not (out / "stale.png").exists()


def test_inbox_files_takes_and_records_cost(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "dreamina_123.mp4").write_bytes(b"v")
    led = Ledger(tmp_path / "costs.json")
    assert import_inbox(tmp_path, "S01", 0.35, "seedance-2.5", led) == ["t001"]
    assert (tmp_path / "shots" / "S01" / "takes" / "t001.mp4").exists()
    assert (tmp_path / "inbox" / "done" / "dreamina_123.mp4").exists()
    assert led.total() == 0.35
```

- [ ] **Step 2: Run** — FAIL
- [ ] **Step 3: Implement** — `tools/shorts/backends/manual.py`

```python
"""Hand-off for Dreamina / LibTV: a folder to paste from, and an inbox to file results from."""

import shutil
from pathlib import Path

from tools.shorts.takes import Ledger, file_take


def write_bundle(shot_dir: Path, prompt: str, refs: list[tuple[str, Path]]) -> Path:
    out = shot_dir / "bundle"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    (out / "prompt.txt").write_text(prompt)
    for label, path in refs:
        shutil.copyfile(path, out / label)
    return out


def import_inbox(short_dir: Path, shot_id: str, cost: float, model: str, ledger: Ledger) -> list[str]:
    inbox, done = short_dir / "inbox", short_dir / "inbox" / "done"
    done.mkdir(parents=True, exist_ok=True)
    ids = []
    for video in sorted(inbox.glob("*.mp4")):
        tid = file_take(short_dir / "shots" / shot_id, video,
                        {"model": model, "cost": cost, "backend": "manual", "source": video.name})
        ledger.add(shot_id, tid, model, cost)
        shutil.move(video, done / video.name)
        ids.append(tid)
    return ids
```

- [ ] **Step 4: Run** — PASS
- [ ] **Step 5: Commit** — `git add tools/shorts/backends tests/test_shorts_manual.py && git commit -m "feat(shorts): manual bundle and inbox import"`

---

### Task 5: fal backend

**Files:**
- Create: `tools/shorts/backends/fal.py`, `tests/test_shorts_fal.py`
- Modify: `tools/shorts/takes.py` (RATES, only if fal's current prices differ)

**Interfaces:**
- Consumes: `estimate`, `Ledger`, `BudgetError`, `file_take` (Task 3).
- Produces:
  - `MODELS: dict[str, dict]` — per model key: `{"endpoint": str, "prompt": str, "images": str, "video": str | None, "duration": str, "extra": dict}` (input field names)
  - `load_key(path: Path = Path.home() / ".config/nightwire/secrets.env") -> str` — reads `FAL_KEY=...`; raises `RuntimeError("FAL_KEY missing in …")` without echoing contents
  - `data_uri(path: Path) -> str`
  - `build_input(model: str, prompt: str, refs: list[tuple[str, Path]], seconds: float) -> dict`
  - `submit(model, prompt, refs, seconds, *, key: str, client: httpx.Client, poll_s: float = 5.0, timeout_s: float = 900) -> bytes` — returns the video bytes
  - `run_take(short_dir, shot_id, model, prompt, refs, seconds, budget, *, key, client) -> str` — budget check → submit → file take → ledger; returns take id

- [ ] **Step 1: Verify the endpoints and fields (no code).** Open fal.ai's model pages for Seedance 2.5, Seedance 2.0 (standard + fast), Kling 3.0 image/reference-to-video and Veo 3.1 Fast. For each, note the exact endpoint id, the input field names for prompt, reference images, reference video, duration, and whether audio is on by default; note the current $/s at 720p. Fill `MODELS` below with what the pages say (the values in Step 3 are the expected shape, not verified ids) and update `RATES` in `takes.py` if a price changed. Write the date checked in a comment.

- [ ] **Step 2: Failing tests** — `tests/test_shorts_fal.py` (no network: `httpx.MockTransport`)

```python
import json

import httpx
import pytest

from tools.shorts.backends import fal
from tools.shorts.takes import BudgetError, Ledger


def transport(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url), request.headers.get("authorization")))
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "r1", "status_url": "https://queue.fal.run/x/requests/r1/status",
                                             "response_url": "https://queue.fal.run/x/requests/r1"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=b"mp4bytes")
        return httpx.Response(200, json={"video": {"url": "https://cdn.example/v.mp4"}})
    return httpx.MockTransport(handler)


def test_load_key_reads_env_file_and_hides_contents(tmp_path):
    f = tmp_path / "secrets.env"
    f.write_text("OTHER=1\nFAL_KEY=abc:def\n")
    assert fal.load_key(f) == "abc:def"
    f.write_text("OTHER=secretvalue\n")
    with pytest.raises(RuntimeError) as e:
        fal.load_key(f)
    assert "secretvalue" not in str(e.value)


def test_build_input_uses_model_field_names(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")
    model = next(iter(fal.MODELS))
    body = fal.build_input(model, "hello", [("C1_turnaround.png", img)], 5)
    spec = fal.MODELS[model]
    assert body[spec["prompt"]] == "hello"
    assert body[spec["images"]][0].startswith("data:image/png;base64,")


def test_run_take_submits_files_and_records(tmp_path):
    calls = []
    client = httpx.Client(transport=transport(calls))
    model = next(iter(fal.MODELS))
    tid = fal.run_take(tmp_path, "S01", model, "p", [], 5, 25, key="k", client=client)
    assert tid == "t001"
    assert (tmp_path / "shots" / "S01" / "takes" / "t001.mp4").read_bytes() == b"mp4bytes"
    assert calls[0][2] == "Key k"
    assert Ledger(tmp_path / "costs.json").total() > 0


def test_run_take_refuses_over_budget_before_any_request(tmp_path):
    calls = []
    client = httpx.Client(transport=transport(calls))
    with pytest.raises(BudgetError):
        fal.run_take(tmp_path, "S01", next(iter(fal.MODELS)), "p", [], 30, 1, key="k", client=client)
    assert calls == []
```

- [ ] **Step 3: Implement** — `tools/shorts/backends/fal.py`

```python
"""fal.ai queue API: POST the input, poll status, fetch the result, download the video.
Endpoint ids and field names verified on fal.ai on <date> (Task 5 Step 1)."""

import base64
import mimetypes
import time
from pathlib import Path

import httpx

from tools.shorts.takes import Ledger, estimate, file_take

QUEUE = "https://queue.fal.run"
MODELS = {
    # Shape only: the endpoint id and field names below are a guess until Task 5 Step 1 checks fal.ai.
    "seedance-2.0-fast": {"endpoint": "fal-ai/bytedance/seedance/v2/fast/reference-to-video", "prompt": "prompt", "images": "reference_image_urls",
                          "video": "reference_video_urls", "duration": "duration", "extra": {"resolution": "720p"}},
}


def load_key(path: Path = Path.home() / ".config" / "nightwire" / "secrets.env") -> str:
    if path.exists():
        for line in path.read_text().splitlines():
            if line.startswith("FAL_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"FAL_KEY missing in {path}; the owner adds it (FAL_KEY=...)")


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def build_input(model: str, prompt: str, refs: list[tuple[str, Path]], seconds: float) -> dict:
    spec = MODELS[model]
    body = {spec["prompt"]: prompt, spec["duration"]: int(round(seconds)), **spec["extra"]}
    images = [data_uri(p) for label, p in refs if label.endswith(".png")]
    videos = [data_uri(p) for label, p in refs if label.endswith(".mp4")]
    if images:
        body[spec["images"]] = images
    if videos and spec["video"]:
        body[spec["video"]] = videos
    return body


def submit(model, prompt, refs, seconds, *, key: str, client: httpx.Client, poll_s: float = 5.0,
           timeout_s: float = 900) -> bytes:
    headers = {"Authorization": f"Key {key}"}
    job = client.post(f"{QUEUE}/{MODELS[model]['endpoint']}", json=build_input(model, prompt, refs, seconds),
                      headers=headers, timeout=120).raise_for_status().json()
    deadline = time.monotonic() + timeout_s
    while client.get(job["status_url"], headers=headers, timeout=30).raise_for_status().json()["status"] != "COMPLETED":
        if time.monotonic() > deadline:
            raise TimeoutError(f"fal request {job['request_id']} not done after {timeout_s}s")
        time.sleep(poll_s)
    result = client.get(job["response_url"], headers=headers, timeout=60).raise_for_status().json()
    return client.get(result["video"]["url"], timeout=300).raise_for_status().content


def run_take(short_dir: Path, shot_id: str, model: str, prompt: str, refs, seconds: float, budget: float, *,
             key: str, client: httpx.Client) -> str:
    ledger, cost = Ledger(short_dir / "costs.json"), estimate(model, seconds)
    ledger.check(budget, cost)
    video = submit(model, prompt, refs, seconds, key=key, client=client)
    tmp = short_dir / "shots" / shot_id / "incoming.mp4"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(video)
    tid = file_take(short_dir / "shots" / shot_id, tmp, {"model": model, "cost": cost, "backend": "fal",
                                                          "seconds": seconds, "refs": [label for label, _ in refs]})
    tmp.unlink()
    ledger.add(shot_id, tid, model, cost)
    return tid
```

Every model key added to `MODELS` must also exist in `RATES`. Add a test: `assert set(fal.MODELS) <= set(RATES)`.

- [ ] **Step 4: Run** — `python -m pytest tests/test_shorts_fal.py -q` → PASS (ensure the poll loop doesn't sleep in tests: the mock returns COMPLETED first time)
- [ ] **Step 5: Commit** — `git add tools/shorts/backends/fal.py tests/test_shorts_fal.py tools/shorts/takes.py && git commit -m "feat(shorts): fal backend with spend guard"`

---

### Task 6: Grey-box — scene description (pure Python)

**Files:**
- Create: `tools/shorts/greybox/__init__.py` (empty), `tools/shorts/greybox/scene.py`, `tests/test_shorts_scene.py`

**Interfaces:**
- Consumes: `Short`, `Figure`, `Block`, `Shot` (Task 1).
- Produces:
  - `FPS = 24`, `RES = (1280, 720)`
  - `POSES: dict[str, dict[str, tuple[float, float, float]]]` — bone name → XYZ euler degrees; names: `stand`, `sit`, `lean_counter`, `kneel`, `arm_raised`
  - `BONES: tuple[str, ...]` = `("hips", "spine", "head", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R", "thigh.L", "shin.L", "thigh.R", "shin.R")`
  - `scene_json(short: Short) -> dict` — `{"fps", "res", "frames", "blocks": [...], "figures": [{"id","tier","pose","rotations","tint","keys":[[frame,x,y,facing]]}], "shots": [{"id","start_frame","end_frame","lens","camera":[[frame,at,look]]}]}`; shot camera times are relative to the shot's `start`
  - `tint(colorguide_hex: str | None) -> list[float]` — RGB 0..1 mixed 15 % into grey 0.6; plain grey when None

- [ ] **Step 1: Failing tests** — `tests/test_shorts_scene.py`

```python
from test_shorts_model import write
from tools.shorts.greybox.scene import BONES, FPS, POSES, scene_json, tint
from tools.shorts.model import load_short


def test_scene_json_converts_seconds_to_frames(tmp_path):
    sj = scene_json(load_short(write(tmp_path / "pilot")))
    assert sj["fps"] == FPS and sj["res"] == [1280, 720]
    shot = sj["shots"][0]
    assert shot["start_frame"] == 0 and shot["end_frame"] == 5 * FPS
    assert shot["camera"][1][0] == 5 * FPS
    c2 = next(f for f in sj["figures"] if f["id"] == "C2")
    assert c2["keys"][1] == [4 * FPS, 0.4, 0.5, 270.0]
    assert sj["frames"] == 5 * FPS
    assert sj["blocks"][0]["name"] == "counter"


def test_poses_only_use_known_bones():
    for pose in POSES.values():
        assert set(pose) <= set(BONES)
    assert {"stand", "sit", "lean_counter", "kneel", "arm_raised"} <= set(POSES)


def test_tint_is_mostly_grey():
    assert tint(None) == [0.6, 0.6, 0.6]
    r, g, b = tint("#ff0000")
    assert 0.65 < r < 0.7 and g < 0.6
```

- [ ] **Step 2: Run** — FAIL
- [ ] **Step 3: Implement** — `tools/shorts/greybox/scene.py`

```python
"""Short -> scene.json, the only input the Blender script reads. No bpy here, so it is unit-tested."""

from tools.shorts.model import Short

FPS = 24
RES = (1280, 720)
BONES = ("hips", "spine", "head", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R",
         "thigh.L", "shin.L", "thigh.R", "shin.R")
POSES = {
    "stand": {},
    "sit": {"thigh.L": (-90, 0, 0), "thigh.R": (-90, 0, 0), "shin.L": (90, 0, 0), "shin.R": (90, 0, 0)},
    "lean_counter": {"spine": (-25, 0, 0), "upper_arm.L": (-60, 0, 10), "upper_arm.R": (-60, 0, -10),
                     "forearm.L": (-30, 0, 0), "forearm.R": (-30, 0, 0)},
    "kneel": {"thigh.L": (-90, 0, 0), "shin.L": (90, 0, 0), "thigh.R": (0, 0, 0), "shin.R": (90, 0, 0)},
    "arm_raised": {"upper_arm.R": (-170, 0, 0)},
}
GREY = 0.6


def tint(colorguide_hex: str | None) -> list[float]:
    if not colorguide_hex:
        return [GREY] * 3
    h = colorguide_hex.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [round(GREY * 0.85 + c * 0.15, 4) for c in rgb]


def _f(seconds: float) -> int:
    return round(seconds * FPS)


def scene_json(short: Short, palettes: dict[str, str] | None = None) -> dict:
    palettes = palettes or {}
    return {
        "fps": FPS, "res": list(RES),
        "frames": max((_f(s.end) for s in short.shots), default=0),
        "blocks": [{"name": b.name, "size": list(b.size), "at": list(b.at), "rot": b.rot} for b in short.blocks],
        "figures": [{"id": f.id, "tier": f.tier, "pose": f.pose, "rotations": POSES.get(f.pose, {}),
                     "tint": tint(palettes.get(f.id)),
                     "keys": [[_f(t), x, y, facing] for t, x, y, facing in f.keys]} for f in short.figures.values()],
        "shots": [{"id": s.id, "start_frame": _f(s.start), "end_frame": _f(s.end), "lens": s.lens,
                   "camera": [[_f(s.start + k.t), list(k.at), list(k.look)] for k in s.camera]} for s in short.shots],
    }
```

(`palettes` maps cast id → first hex of the design's `palette`; the CLI in Task 9 fills it only when `--tint` is passed, for the tinted-vs-grey A/B.)

- [ ] **Step 4: Run** — PASS
- [ ] **Step 5: Commit** — `git add tools/shorts/greybox tests/test_shorts_scene.py && git commit -m "feat(shorts): grey-box scene description"`

---

### Task 7: Grey-box — Blender script and remote runner

**Files:**
- Create: `tools/shorts/greybox/blender_build.py`, `tools/shorts/remote.py`, `tests/test_shorts_remote.py`, `tests/test_shorts_blender.py`

**Interfaces:**
- Consumes: `scene.json` from Task 6.
- Produces:
  - `blender_build.py` CLI (inside Blender): `blender -b -P blender_build.py -- <scene.json> <outdir>` writes `outdir/scene.blend`, `outdir/floorplan.png`, `outdir/shots/<id>/frames/####.png` and `outdir/shots/<id>/preview/{start,middle,end}.png`
  - `remote.BLENDER_HOST = os.environ.get("NIGHTWIRE_BLENDER_HOST", "192.168.10.19")`, `remote.BLENDER = os.environ.get("NIGHTWIRE_BLENDER", "~/opt/blender/blender")`
  - `remote.commands(short_dir: Path, slug: str) -> list[list[str]]` — the rsync-up, ssh-run, rsync-down argv lists (pure, tested)
  - `remote.run(short_dir: Path, slug: str) -> None` — runs them with `check=True`
  - `remote.encode(frames_dir: Path, out: Path, fps: int) -> list[str]` — ffmpeg argv `-framerate fps -i frames/%04d.png -c:v libx264 -pix_fmt yuv420p out`

- [ ] **Step 1: Failing tests** — `tests/test_shorts_remote.py`

```python
from pathlib import Path

from tools.shorts import remote


def test_commands_sync_run_and_fetch(tmp_path):
    up, run, down = remote.commands(tmp_path, "pilot")
    assert up[0] == "rsync" and str(tmp_path / "scene.json") in up
    assert run[0] == "ssh" and "-b" in run[-1] and "blender_build.py" in run[-1] and "pilot" in run[-1]
    assert down[0] == "rsync" and down[-1].rstrip("/") == str(tmp_path)


def test_encode_builds_h264_command(tmp_path):
    argv = remote.encode(tmp_path / "frames", tmp_path / "greybox.mp4", 24)
    assert argv[:3] == ["ffmpeg", "-y", "-framerate"] and "libx264" in argv and argv[-1].endswith("greybox.mp4")
```

`tests/test_shorts_blender.py` (live smoke test, skipped without Blender):

```python
import json
import os
import subprocess
from pathlib import Path

import pytest

BLENDER = os.environ.get("NIGHTWIRE_BLENDER")
pytestmark = pytest.mark.skipif(not BLENDER, reason="set NIGHTWIRE_BLENDER to a local blender binary")


def test_two_figure_room_renders(tmp_path):
    scene = {"fps": 24, "res": [320, 180], "frames": 24,
             "blocks": [{"name": "counter", "size": [2, 0.5, 1], "at": [0, 1, 0], "rot": 0}],
             "figures": [{"id": "C1", "tier": "mannequin", "pose": "sit", "rotations": {"thigh.L": [-90, 0, 0]},
                          "tint": [0.6, 0.6, 0.6], "keys": [[0, -0.5, 0, 90]]},
                         {"id": "C2", "tier": "capsule", "pose": "stand", "rotations": {}, "tint": [0.6, 0.6, 0.6],
                          "keys": [[0, 0.5, 0, 270], [24, 0.2, 0, 270]]}],
             "shots": [{"id": "S01", "start_frame": 0, "end_frame": 24, "lens": 35,
                        "camera": [[0, [-2, -2, 1.5], [0, 0, 1]], [24, [-1.5, -1.5, 1.4], [0, 0, 1]]]}]}
    (tmp_path / "scene.json").write_text(json.dumps(scene))
    script = Path(__file__).parents[1] / "tools" / "shorts" / "greybox" / "blender_build.py"
    subprocess.run([BLENDER, "-b", "-P", str(script), "--", str(tmp_path / "scene.json"), str(tmp_path)], check=True)
    assert (tmp_path / "scene.blend").exists() and (tmp_path / "floorplan.png").exists()
    assert len(list((tmp_path / "shots" / "S01" / "frames").glob("*.png"))) == 25
    assert {p.name for p in (tmp_path / "shots" / "S01" / "preview").iterdir()} == {"start.png", "middle.png", "end.png"}
```

- [ ] **Step 2: Run** — `python -m pytest tests/test_shorts_remote.py -q` → FAIL
- [ ] **Step 3: Implement** — `tools/shorts/remote.py`

```python
"""Blender runs on the GPU box: push scene.json, render there, pull the results back."""

import os
import subprocess
from pathlib import Path

BLENDER_HOST = os.environ.get("NIGHTWIRE_BLENDER_HOST", "192.168.10.19")
BLENDER = os.environ.get("NIGHTWIRE_BLENDER", "~/opt/blender/blender")
REMOTE_ROOT = "nightwire-shorts"
SCRIPT = Path(__file__).parent / "greybox" / "blender_build.py"


def commands(short_dir: Path, slug: str) -> list[list[str]]:
    remote_dir = f"{REMOTE_ROOT}/{slug}"
    up = ["rsync", "-a", "--mkpath", str(short_dir / "scene.json"), str(SCRIPT), f"{BLENDER_HOST}:{remote_dir}/"]
    run = ["ssh", BLENDER_HOST,
           f"cd {remote_dir} && {BLENDER} -b -P blender_build.py -- scene.json . > blender.log 2>&1 || (tail -30 blender.log; exit 1)"]
    down = ["rsync", "-a", "--exclude", "blender_build.py", f"{BLENDER_HOST}:{remote_dir}/", f"{short_dir}/"]
    return [up, run, down]


def run(short_dir: Path, slug: str) -> None:
    for argv in commands(short_dir, slug):
        subprocess.run(argv, check=True)


def encode(frames_dir: Path, out: Path, fps: int) -> list[str]:
    return ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_dir / "%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)]
```

`tools/shorts/greybox/blender_build.py` (runs only inside Blender; not imported by tests):

```python
"""Inside Blender: blender -b -P blender_build.py -- scene.json outdir
Builds white room blocks, grey figures (capsule or 11-bone mannequin), one camera per shot on one timeline,
saves scene.blend, renders each shot's frames + start/middle/end previews, and an overhead floor plan."""

import json
import math
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
scene_path, out = Path(args[0]), Path(args[1])
S = json.loads(scene_path.read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "OBJECT"
sc.render.resolution_x, sc.render.resolution_y = S["res"]
sc.render.fps = S["fps"]
sc.frame_start, sc.frame_end = 0, max(S["frames"], 1)
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.05, 0.05, 0.06)

def box(name, size, at, rot=0.0, colour=(0.92, 0.92, 0.92, 1)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(at[0], at[1], at[2] + size[2] / 2))
    o = bpy.context.object
    o.name, o.scale, o.rotation_euler[2], o.color = name, size, math.radians(rot), colour
    return o

box("floor", (12, 12, 0.02), (0, 0, -0.02))
for b in S["blocks"]:
    box(b["name"], b["size"], b["at"], b.get("rot", 0))

# Bone layout of the mannequin: (name, parent, head, tail) in metres, standing at origin facing +Y.
LAYOUT = [("hips", None, (0, 0, 0.95), (0, 0, 1.1)), ("spine", "hips", (0, 0, 1.1), (0, 0, 1.45)),
          ("head", "spine", (0, 0, 1.5), (0, 0, 1.72)),
          ("upper_arm.L", "spine", (0.2, 0, 1.42), (0.2, 0, 1.12)), ("forearm.L", "upper_arm.L", (0.2, 0, 1.12), (0.2, 0, 0.86)),
          ("upper_arm.R", "spine", (-0.2, 0, 1.42), (-0.2, 0, 1.12)), ("forearm.R", "upper_arm.R", (-0.2, 0, 1.12), (-0.2, 0, 0.86)),
          ("thigh.L", "hips", (0.1, 0, 0.95), (0.1, 0, 0.5)), ("shin.L", "thigh.L", (0.1, 0, 0.5), (0.1, 0, 0.05)),
          ("thigh.R", "hips", (-0.1, 0, 0.95), (-0.1, 0, 0.5)), ("shin.R", "thigh.R", (-0.1, 0, 0.5), (-0.1, 0, 0.05))]

def mannequin(fid, colour, rotations):
    """11-bone armature at the origin; one cylinder per bone, rigidly skinned with a vertex group + Armature modifier."""
    arm_data = bpy.data.armatures.new(fid)
    rig = bpy.data.objects.new(fid, arm_data)
    sc.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, head, tail in LAYOUT:
        b = arm_data.edit_bones.new(name)
        b.head, b.tail = head, tail
        if parent:
            b.parent = arm_data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    for name, _parent, head, tail in LAYOUT:
        length = (Vector(tail) - Vector(head)).length
        radius = 0.11 if name == "head" else 0.07 if "arm" in name else 0.09
        bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=length, location=(Vector(head) + Vector(tail)) / 2)
        part = bpy.context.object
        part.name, part.color = f"{fid}.{name}", colour
        vg = part.vertex_groups.new(name=name)
        vg.add(range(len(part.data.vertices)), 1.0, "REPLACE")
        part.modifiers.new("rig", "ARMATURE").object = rig
        part.parent = rig  # rig sits at the origin with identity transform here, so world == local
    for name, (x, y, z) in rotations.items():
        pb = rig.pose.bones[name]
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
    return rig

def capsule(fid, colour):
    """Body cylinder plus a cone 'nose' showing facing; both parented to an empty at the origin."""
    root = bpy.data.objects.new(fid, None)
    sc.collection.objects.link(root)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=1.7, location=(0, 0, 0.85))
    body = bpy.context.object
    body.color, body.parent = colour, root
    bpy.ops.mesh.primitive_cone_add(radius1=0.08, depth=0.2, location=(0, 0.25, 1.5), rotation=(math.radians(-90), 0, 0))
    nose = bpy.context.object
    nose.color, nose.parent = colour, root
    return root

figures = {}
for f in S["figures"]:
    colour = (*f["tint"], 1)
    obj = mannequin(f["id"], colour, f["rotations"]) if f["tier"] in ("mannequin", "rigged") else capsule(f["id"], colour)
    for frame, x, y, facing in f["keys"]:
        obj.location = (x, y, 0)
        obj.rotation_euler = (0, 0, math.radians(facing - 90))
        obj.keyframe_insert("location", frame=frame)
        obj.keyframe_insert("rotation_euler", frame=frame)
    figures[f["id"]] = obj

def aim(cam, at, look):
    cam.location = at
    cam.rotation_euler = (Vector(look) - Vector(at)).to_track_quat("-Z", "Y").to_euler()

def render_still(path):
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)

for shot in S["shots"]:
    cam = bpy.data.objects.new(shot["id"], bpy.data.cameras.new(shot["id"]))
    sc.collection.objects.link(cam)
    cam.data.lens = shot["lens"]
    for frame, at, look in shot["camera"]:
        aim(cam, at, look)
        cam.keyframe_insert("location", frame=frame)
        cam.keyframe_insert("rotation_euler", frame=frame)
    sc.camera = cam
    sc.frame_start, sc.frame_end = shot["start_frame"], shot["end_frame"]
    frames = out / "shots" / shot["id"] / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    sc.render.filepath = str(frames / "####")
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(animation=True)
    preview = out / "shots" / shot["id"] / "preview"
    preview.mkdir(parents=True, exist_ok=True)
    mid = (shot["start_frame"] + shot["end_frame"]) // 2
    for label, frame in (("start", shot["start_frame"]), ("middle", mid), ("end", shot["end_frame"])):
        sc.frame_set(frame)
        render_still(preview / f"{label}.png")

# Overhead floor plan with C labels, figures at the first frame.
sc.frame_set(0)
top = bpy.data.objects.new("plan", bpy.data.cameras.new("plan"))
sc.collection.objects.link(top)
top.data.type, top.data.ortho_scale = "ORTHO", 8
top.location, top.rotation_euler = (0, 0, 12), (0, 0, 0)
for fid, obj in figures.items():
    bpy.ops.object.text_add(location=(obj.location.x, obj.location.y, 2.2))
    t = bpy.context.object
    t.data.body, t.data.size, t.data.align_x, t.color = fid, 0.45, "CENTER", (0.9, 0.1, 0.1, 1)
sc.camera = top
sc.render.resolution_x = sc.render.resolution_y = 1024
render_still(out / "floorplan.png")
bpy.ops.wm.save_as_mainfile(filepath=str(out / "scene.blend"))
```

Facing convention: `facing` degrees, 90 = +Y (the figure's rest direction), so the script rotates by `facing - 90`.
If the smoke test's `preview/middle.png` shows limbs detached or the sit pose bending the wrong way, fix the sign in `POSES` (Task 6) — rotations are about each bone's local X.

- [ ] **Step 4: Run unit tests** — `python -m pytest tests/test_shorts_remote.py -q` → PASS
- [ ] **Step 5: Install Blender on the GPU box (ask the owner first: download ~350 MB from download.blender.org).** Use the current 4.5 LTS Linux x64 tarball:

```bash
ssh 192.168.10.19 'mkdir -p ~/opt && cd ~/opt && curl -fLO https://download.blender.org/release/Blender4.5/blender-4.5.<latest>-linux-x64.tar.xz && tar xf blender-4.5.*-linux-x64.tar.xz && ln -sfn ~/opt/blender-4.5.*-linux-x64 ~/opt/blender && ~/opt/blender/blender -b --version'
```

Check the exact latest 4.5.x file name on download.blender.org/release/Blender4.5/ first. Expected: prints `Blender 4.5.x`.

- [ ] **Step 6: Run the smoke test on the GPU box** — copy `tests/test_shorts_blender.py` and `tools/shorts/greybox/blender_build.py` there and run with `NIGHTWIRE_BLENDER=~/opt/blender/blender python3 -m pytest` (or run the Blender command from the test by hand). Free GPU first (Global Constraints). Expected: PASS; pull `preview/middle.png` back and look at it — two figures, counter, sensible camera.
- [ ] **Step 7: Commit** — `git add tools/shorts/remote.py tools/shorts/greybox/blender_build.py tests/test_shorts_remote.py tests/test_shorts_blender.py && git commit -m "feat(shorts): Blender grey-box build and GPU-box runner"`

---

### Task 8: Identity check on takes

**Files:**
- Modify: `tools/design_check.py` (`main` arguments; `check_scenes` uses them)
- Create: `tools/shorts/check.py`, `tests/test_shorts_check.py`
- Test: extend `tests/test_design_check.py` with one argument test

**Interfaces:**
- Consumes: `tools.design_check.main(argv)` / `check_scenes(args)`; `scene_people(name)` naming rule (`pair--a--b--loc.png`).
- Produces:
  - `design_check` options `--scenes-dir PATH` (default `design-data/scenes`) and `--out PATH` (default `design-data/qa/scenes.json`)
  - `check.frame_names(cast_slugs: list[str], shot: str, take: str, n: int) -> list[str]` — e.g. `pair--saeko-kirigaya--rin-kageyama--S01-t001-f1.png`; single cast → `saeko-kirigaya--S01-t001-f1.png`
  - `check.extract_cmd(video: Path, out_pattern: Path, n: int, seconds: float) -> list[str]` — ffmpeg sampling `n` evenly spaced frames
  - `check.run(short_dir, shot_id, take, cast_slugs, seconds, n=4) -> dict` — extracts frames to `short_dir/qa/<shot>-<take>/`, calls `design_check.main([... "--scenes", "--scenes-dir", that, "--out", that/"scenes.json"])`, returns the parsed report

- [ ] **Step 1: Failing tests** — `tests/test_shorts_check.py`

```python
from pathlib import Path

from tools.design_check import scene_people
from tools.shorts.check import extract_cmd, frame_names


def test_frame_names_follow_design_check_naming():
    names = frame_names(["saeko-kirigaya", "rin-kageyama"], "S01", "t001", 2)
    assert names == ["pair--saeko-kirigaya--rin-kageyama--S01-t001-f1.png",
                     "pair--saeko-kirigaya--rin-kageyama--S01-t001-f2.png"]
    assert scene_people(names[0]) == ["saeko-kirigaya", "rin-kageyama"]
    assert scene_people(frame_names(["saeko-kirigaya"], "S01", "t001", 1)[0]) == ["saeko-kirigaya"]


def test_extract_cmd_samples_evenly():
    argv = extract_cmd(Path("t.mp4"), Path("out/f%d.png"), 4, 8.0)
    assert argv[0] == "ffmpeg" and "fps=0.5" in " ".join(argv)
```

Add to `tests/test_design_check.py`:

```python
def test_scene_dir_and_out_options_parse(monkeypatch, tmp_path):
    import tools.design_check as dc
    seen = {}
    monkeypatch.setattr(dc, "check_scenes", lambda args: seen.update(vars(args)) or 0)
    dc.main(["--scenes", "--scenes-dir", str(tmp_path), "--out", str(tmp_path / "r.json")])
    assert seen["scenes_dir"] == tmp_path and seen["out"] == tmp_path / "r.json"
```

- [ ] **Step 2: Run** — FAIL
- [ ] **Step 3: Implement.** In `tools/design_check.py` `main`, add:

```python
    parser.add_argument("--scenes-dir", type=Path, default=None, help="folder of scene images (default design-data/scenes)")
    parser.add_argument("--out", type=Path, default=None, help="report path (default design-data/qa/scenes.json)")
```

and in `check_scenes` replace `args.design_dir / "scenes"` with `(args.scenes_dir or args.design_dir / "scenes")` and `out = args.design_dir / "qa" / "scenes.json"` with `out = args.out or args.design_dir / "qa" / "scenes.json"`. Use `getattr(args, "scenes_dir", None)` / `getattr(args, "out", None)` so existing callers that build `args` by hand keep working.

`tools/shorts/check.py`:

```python
"""Does each sampled frame of a take show the right characters? Reuses design_check's scene check,
which ranks every cast member against each head it finds (rank 1 = right person came out closest)."""

import json
import shutil
import subprocess
from pathlib import Path

from tools import design_check


def frame_names(cast_slugs: list[str], shot: str, take: str, n: int) -> list[str]:
    who = (["pair"] + cast_slugs[:2]) if len(cast_slugs) > 1 else cast_slugs[:1]
    return ["--".join(who + [f"{shot}-{take}-f{i}"]) + ".png" for i in range(1, n + 1)]


def extract_cmd(video: Path, out_pattern: Path, n: int, seconds: float) -> list[str]:
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", f"fps={n / seconds:g}",
            "-frames:v", str(n), str(out_pattern)]


def run(short_dir: Path, shot_id: str, take: str, cast_slugs: list[str], seconds: float, n: int = 4) -> dict:
    qa = short_dir / "qa" / f"{shot_id}-{take}"
    shutil.rmtree(qa, ignore_errors=True)
    qa.mkdir(parents=True)
    subprocess.run(extract_cmd(short_dir / "shots" / shot_id / "takes" / f"{take}.mp4", qa / "raw%d.png", n, seconds),
                   check=True)
    for i, name in enumerate(frame_names(cast_slugs, shot_id, take, n), start=1):
        if (qa / f"raw{i}.png").exists():
            (qa / f"raw{i}.png").rename(qa / name)
    design_check.main(["--scenes", "--scenes-dir", str(qa), "--out", str(qa / "scenes.json")])
    return json.loads((qa / "scenes.json").read_text())
```

- [ ] **Step 4: Run** — `python -m pytest tests/test_shorts_check.py tests/test_design_check.py -q` → PASS
- [ ] **Step 5: Commit** — `git add tools/design_check.py tools/shorts/check.py tests/test_shorts_check.py tests/test_design_check.py && git commit -m "feat(shorts): identity check on sampled take frames"`

---

### Task 9: CLI

**Files:**
- Create: `tools/shorts/__main__.py`, `tests/test_shorts_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `python -m tools.shorts <cmd> <slug> [...]` where `<slug>` names `narrator/worlds/shorts/<slug>/` (script) and `data_dir()/<slug>/` (work folder). Commands:
  - `check <slug>` — validate; print problems; exit 1 if any
  - `prompt <slug> <shot>` — print the assembled prompt (exit 1 on guard failure)
  - `greybox <slug> [--tint] [--local]` — write `scene.json`, run Blender remotely (or locally with `--local` using `NIGHTWIRE_BLENDER`), encode each shot's `greybox.mp4` locally with ffmpeg
  - `bundle <slug> <shot>` — manual bundle; prints its path
  - `inbox <slug> <shot> --cost USD --model KEY`
  - `submit <slug> <shot> --model KEY [--seconds N]` — fal; prints estimate and asks `y/N` on stdin unless `--yes`
  - `verdicts <slug>` — GET `http://192.168.10.19:8080/designs/api/images`, apply
  - `idcheck <slug> <shot> <take>`
  - `status <slug>` — per shot: takes, verdicts, spend vs budget
  - `page` and `assemble` are added by Tasks 10 and 11
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Failing tests** — `tests/test_shorts_cli.py`

```python
import shutil

from test_shorts_model import SHORT, SHOT
from tools.shorts.__main__ import main


def setup(tmp_path, monkeypatch, shot=SHOT):
    script = tmp_path / "script" / "pilot"
    (script / "shots").mkdir(parents=True)
    (script / "short.toml").write_text(SHORT)
    (script / "shots" / "S01.toml").write_text(shot)
    monkeypatch.setattr("tools.shorts.__main__.SHORTS_DIR", tmp_path / "script")
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(tmp_path / "design-data"))
    from test_shorts_model import designs
    monkeypatch.setattr("tools.shorts.__main__.load_designs", lambda: designs())


def test_check_ok_and_prompt_prints_layers(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["check", "pilot"]) == 0
    assert main(["prompt", "pilot", "S01"]) == 0
    assert "C1 = Saeko Kirigaya" in capsys.readouterr().out


def test_check_fails_on_problems(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, shot=SHOT.replace("end = 5.0", "end = 40.0"))
    assert main(["check", "pilot"]) == 1


def test_bundle_writes_prompt(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    assert main(["bundle", "pilot", "S01"]) == 0
    assert (tmp_path / "design-data" / "shorts" / "pilot" / "shots" / "S01" / "bundle" / "prompt.txt").exists()


def test_submit_without_yes_and_no_answer_spends_nothing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(1))
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    from tools.shorts.backends import fal
    model = next(iter(fal.MODELS))
    assert main(["submit", "pilot", "S01", "--model", model]) == 1
    assert called == []
```

- [ ] **Step 2: Run** — FAIL
- [ ] **Step 3: Implement** — `tools/shorts/__main__.py`

```python
"""python -m tools.shorts <command> <slug> ... — see docs/shorts-guide.md."""

import argparse
import json
import subprocess
import sys
import urllib.request

from narrator.designs import kuroshio_designs
from tools.shorts import SHORTS_DIR, data_dir, remote
from tools.shorts.backends import manual
from tools.shorts.greybox.scene import FPS, scene_json
from tools.shorts.model import load_short, validate_short
from tools.shorts.prompt import build_prompt, ref_files
from tools.shorts.takes import Ledger, apply_verdicts, estimate

PICKS_API = "http://192.168.10.19:8080/designs/api/images"


def load_designs():
    return kuroshio_designs()


def _short(slug):
    return load_short(SHORTS_DIR / slug)


def _shot(short, shot_id):
    return next(s for s in short.shots if s.id == shot_id)


def _work(slug):
    return data_dir() / slug


def cmd_check(a) -> int:
    problems = validate_short(_short(a.slug), load_designs())
    for p in problems:
        print(p)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_prompt(a) -> int:
    s = _short(a.slug)
    try:
        print(build_prompt(s, _shot(s, a.shot), load_designs()))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def cmd_greybox(a) -> int:
    s, work, designs = _short(a.slug), _work(a.slug), load_designs()
    palettes = {cid: designs[slug].palette[0] for cid, slug in s.cast.items() if a.tint and designs[slug].palette}
    work.mkdir(parents=True, exist_ok=True)
    (work / "scene.json").write_text(json.dumps(scene_json(s, palettes), indent=1))
    if a.local:
        subprocess.run([remote.BLENDER, "-b", "-P", str(remote.SCRIPT), "--", str(work / "scene.json"), str(work)], check=True)
    else:
        remote.run(work, a.slug)
    for shot in s.shots:
        sd = work / "shots" / shot.id
        subprocess.run(remote.encode(sd / "frames", sd / "greybox.mp4", FPS), check=True)
        print(sd / "greybox.mp4")
    return 0


def cmd_bundle(a) -> int:
    s, work = _short(a.slug), _work(a.slug)
    shot_dir = work / "shots" / a.shot
    out = manual.write_bundle(shot_dir, build_prompt(s, _shot(s, a.shot), load_designs()),
                              ref_files(s, data_dir().parent, shot_dir))
    print(out)
    return 0


def cmd_inbox(a) -> int:
    work = _work(a.slug)
    print(manual.import_inbox(work, a.shot, a.cost, a.model, Ledger(work / "costs.json")))
    return 0


def cmd_submit(a) -> int:
    import httpx

    from tools.shorts.backends import fal
    s, work = _short(a.slug), _work(a.slug)
    shot = _shot(s, a.shot)
    seconds = a.seconds or shot.duration
    cost = estimate(a.model, seconds)
    print(f"{a.model} {seconds}s ≈ ${cost:.2f}; spent ${Ledger(work / 'costs.json').total():.2f} of ${s.budget_usd:.0f}")
    if not a.yes and input("submit? [y/N] ").strip().lower() != "y":
        return 1
    shot_dir = work / "shots" / a.shot
    with httpx.Client() as client:
        tid = fal.run_take(work, a.shot, a.model, build_prompt(s, shot, load_designs()),
                           ref_files(s, data_dir().parent, shot_dir), seconds, s.budget_usd,
                           key=fal.load_key(), client=client)
    print(shot_dir / "takes" / f"{tid}.mp4")
    return 0


def cmd_verdicts(a) -> int:
    with urllib.request.urlopen(PICKS_API, timeout=10) as r:
        api = json.load(r)
    print(f"{len(apply_verdicts(_work(a.slug), a.slug, api))} verdict(s)")
    return 0


def cmd_idcheck(a) -> int:
    from tools.shorts import check
    s = _short(a.slug)
    report = check.run(_work(a.slug), a.shot, a.take, list(s.cast.values()), _shot(s, a.shot).duration)
    print(json.dumps(report, indent=1))
    return 0


def cmd_status(a) -> int:
    s, work = _short(a.slug), _work(a.slug)
    for shot in s.shots:
        sd = work / "shots" / shot.id
        takes = sorted(p.stem for p in (sd / "takes").glob("t*.mp4"))
        verdicts = json.loads((sd / "verdicts.json").read_text()) if (sd / "verdicts.json").exists() else {}
        print(shot.id, f"{shot.duration}s", "takes:", ", ".join(f"{t}({verdicts.get(t, {}).get('verdict', '-')})" for t in takes) or "none")
    print(f"spent ${Ledger(work / 'costs.json').total():.2f} of ${s.budget_usd:.0f}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.shorts")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "status", "verdicts"):
        sub.add_parser(name).add_argument("slug")
    for name in ("prompt", "bundle"):
        q = sub.add_parser(name)
        q.add_argument("slug"); q.add_argument("shot")
    q = sub.add_parser("greybox"); q.add_argument("slug"); q.add_argument("--tint", action="store_true"); q.add_argument("--local", action="store_true")
    q = sub.add_parser("inbox"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("--cost", type=float, required=True); q.add_argument("--model", required=True)
    q = sub.add_parser("submit"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("--model", required=True)
    q.add_argument("--seconds", type=float); q.add_argument("--yes", action="store_true")
    q = sub.add_parser("idcheck"); q.add_argument("slug"); q.add_argument("shot"); q.add_argument("take")
    a = p.parse_args(argv)
    return globals()[f"cmd_{a.cmd}"](a)


if __name__ == "__main__":
    sys.exit(main())
```

Note: `ref_files` takes the design-data root; `data_dir().parent` is that root because `data_dir()` is `<design-data>/shorts`.

- [ ] **Step 4: Run** — `python -m pytest tests/test_shorts_cli.py -q` → PASS
- [ ] **Step 5: Commit** — `git add tools/shorts/__main__.py tests/test_shorts_cli.py && git commit -m "feat(shorts): command line"`

---

### Task 10: `/shorts/` review page

**Files:**
- Create: `tools/shorts/page.py`, `tools/shorts/page.html`, `tests/test_shorts_page.py`
- Modify: `tools/shorts/__main__.py` (add `page` command), homelab-ops `gpubox/nginx/nginx.conf` (add `/shorts/` location; back up first)

**Interfaces:**
- Consumes: `take_image_id` (Task 3); work folders.
- Produces:
  - `page.collect(work_root: Path) -> list[dict]` — one entry per short folder that has `scene.json`: `{"slug", "title", "spent", "budget", "floorplan", "shots": [{"id", "greybox", "previews": [...], "takes": [{"id", "image_id", "src", "model", "cost"}]}]}` with paths relative to the site root
  - `page.build(work_root: Path, site: Path, titles: dict[str, tuple[str, float]]) -> Path` — copies media into `site/<slug>/…`, writes `site/shorts.json` and `site/index.html` (from `page.html`); returns `site`
  - CLI `page` → builds `data_dir()/_site` and prints the rsync line: `rsync -a <site>/ 192.168.10.19:anvil-deploy/stack/dashboard/shorts/`

- [ ] **Step 1: Failing tests** — `tests/test_shorts_page.py`

```python
import json

from tools.shorts.page import build, collect


def make_work(root):
    w = root / "pilot"
    (w / "shots" / "S01" / "preview").mkdir(parents=True)
    (w / "shots" / "S01" / "takes").mkdir()
    (w / "scene.json").write_text("{}")
    (w / "floorplan.png").write_bytes(b"p")
    (w / "shots" / "S01" / "greybox.mp4").write_bytes(b"g")
    (w / "shots" / "S01" / "preview" / "start.png").write_bytes(b"s")
    (w / "shots" / "S01" / "takes" / "t001.mp4").write_bytes(b"t")
    (w / "shots" / "S01" / "takes" / "t001.json").write_text(json.dumps({"model": "kling-3", "cost": 0.7}))
    (w / "costs.json").write_text(json.dumps([{"cost": 0.7}]))
    return w


def test_collect_lists_shots_and_takes(tmp_path):
    make_work(tmp_path)
    [entry] = collect(tmp_path, {"pilot": ("Last orders", 25.0)})
    assert entry["title"] == "Last orders" and entry["spent"] == 0.7
    take = entry["shots"][0]["takes"][0]
    assert take["image_id"] == "short--pilot--s01--t001" and take["src"] == "pilot/shots/S01/takes/t001.mp4"


def test_build_copies_media_and_writes_page(tmp_path):
    make_work(tmp_path / "work")
    site = build(tmp_path / "work", tmp_path / "site", {"pilot": ("Last orders", 25.0)})
    assert (site / "pilot" / "shots" / "S01" / "takes" / "t001.mp4").read_bytes() == b"t"
    assert json.loads((site / "shorts.json").read_text())[0]["slug"] == "pilot"
    html = (site / "index.html").read_text()
    assert "/designs/api/images/" in html and "shorts.json" in html
```

- [ ] **Step 2: Run** — FAIL
- [ ] **Step 3: Implement** — `tools/shorts/page.py`

```python
"""Static /shorts/ page: floor plan, previews, grey-box and takes per shot; verdicts go to the
existing design-picks images API, so no new server is needed."""

import json
import shutil
from pathlib import Path

from tools.shorts.takes import take_image_id

HTML = Path(__file__).with_name("page.html")


def collect(work_root: Path, titles: dict[str, tuple[str, float]]) -> list[dict]:
    out = []
    for w in sorted(p for p in work_root.iterdir() if (p / "scene.json").exists()):
        slug = w.name
        costs = json.loads((w / "costs.json").read_text()) if (w / "costs.json").exists() else []
        title, budget = titles.get(slug, (slug, 25.0))
        shots = []
        for sd in sorted((w / "shots").iterdir()):
            rel = f"{slug}/shots/{sd.name}"
            takes = []
            for t in sorted((sd / "takes").glob("t*.mp4")):
                meta = json.loads(t.with_suffix(".json").read_text()) if t.with_suffix(".json").exists() else {}
                takes.append({"id": t.stem, "image_id": take_image_id(slug, sd.name, t.stem), "src": f"{rel}/takes/{t.name}",
                              "model": meta.get("model", ""), "cost": meta.get("cost", 0)})
            shots.append({"id": sd.name, "greybox": f"{rel}/greybox.mp4" if (sd / "greybox.mp4").exists() else "",
                          "previews": [f"{rel}/preview/{p.name}" for p in sorted((sd / "preview").glob("*.png"))]
                          if (sd / "preview").exists() else [], "takes": takes})
        out.append({"slug": slug, "title": title, "budget": budget, "spent": round(sum(c["cost"] for c in costs), 2),
                    "floorplan": f"{slug}/floorplan.png" if (w / "floorplan.png").exists() else "", "shots": shots})
    return out


def build(work_root: Path, site: Path, titles: dict[str, tuple[str, float]]) -> Path:
    entries = collect(work_root, titles)
    site.mkdir(parents=True, exist_ok=True)
    for e in entries:
        for rel in [e["floorplan"]] + [x for s in e["shots"] for x in [s["greybox"], *s["previews"], *(t["src"] for t in s["takes"])]]:
            if rel:
                dst = site / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(work_root / rel, dst)
    (site / "shorts.json").write_text(json.dumps(entries, indent=1))
    shutil.copyfile(HTML, site / "index.html")
    return site
```

`tools/shorts/page.html` (dark, matches the other AI Lab pages; verdict calls mirror the World Gallery's `verdicts.js`: `PUT /designs/api/images/<id>` with `Content-Type: application/json`):

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shorts</title>
<style>
:root{--bg:#0d0f14;--card:#171a22;--fg:#e8e8ee;--dim:#9aa0ad;--keep:#3fb37f;--rej:#d9534f;--fix:#e0a030}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif;padding:16px}
h1{font-size:22px;margin:0 0 12px} h2{font-size:18px;margin:24px 0 8px} h3{font-size:15px;margin:16px 0 6px;color:var(--dim)}
.row{display:flex;gap:12px;flex-wrap:wrap} .card{background:var(--card);border-radius:10px;padding:10px;max-width:100%}
video,img{max-width:min(560px,100%);border-radius:6px;display:block} .previews img{max-width:180px}
button{border:0;border-radius:6px;padding:6px 10px;margin:6px 4px 0 0;cursor:pointer;color:#fff}
.keep{background:var(--keep)} .reject{background:var(--rej)} .fix{background:var(--fix)}
.v{font-size:13px;color:var(--dim)} textarea{width:100%;background:#0b0d12;color:var(--fg);border:1px solid #333;border-radius:6px}
</style></head><body>
<h1>Shorts</h1><div id="app">Loading…</div>
<script>
const API = "/designs/api/images/";
async function setVerdict(id, verdict, note) {
  const body = note ? {verdict, note} : {verdict};
  const r = await fetch(API + encodeURIComponent(id), {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  if (!r.ok) alert("Saving failed: " + r.status); else load();
}
function el(tag, attrs = {}, ...kids) { const e = document.createElement(tag); Object.assign(e, attrs); kids.forEach(k => e.append(k)); return e; }
async function load() {
  const [shorts, verdicts] = await Promise.all([fetch("shorts.json", {cache: "no-store"}).then(r => r.json()),
                                                fetch(API, {cache: "no-store"}).then(r => r.json()).catch(() => ({}))]);
  const app = document.getElementById("app"); app.textContent = "";
  for (const s of shorts) {
    app.append(el("h2", {textContent: `${s.title} — $${s.spent.toFixed(2)} of $${s.budget}`}));
    if (s.floorplan) app.append(el("div", {className: "card"}, el("img", {src: s.floorplan, alt: "floor plan"})));
    for (const shot of s.shots) {
      app.append(el("h3", {textContent: shot.id}));
      const row = el("div", {className: "row"});
      if (shot.greybox) row.append(el("div", {className: "card"}, el("div", {className: "v", textContent: "grey-box"}),
                                       el("video", {src: shot.greybox, controls: true, loop: true, muted: true})));
      if (shot.previews.length) row.append(el("div", {className: "card previews"}, ...shot.previews.map(p => el("img", {src: p}))));
      for (const t of shot.takes) {
        const v = verdicts[t.image_id] || {};
        const note = el("textarea", {rows: 2, placeholder: "what to fix (e.g. C2 flips side at 3s)"});
        row.append(el("div", {className: "card"},
          el("div", {className: "v", textContent: `${t.id} · ${t.model} · $${(t.cost || 0).toFixed(2)} · ${v.verdict || "not reviewed"}${v.note ? " — " + v.note : ""}`}),
          el("video", {src: t.src, controls: true, loop: true}),
          el("button", {className: "keep", textContent: "Keep", onclick: () => setVerdict(t.image_id, "keep")}),
          el("button", {className: "reject", textContent: "Reject", onclick: () => setVerdict(t.image_id, "reject")}),
          note, el("button", {className: "fix", textContent: "Needs a fix", onclick: () => setVerdict(t.image_id, "fix", note.value)})));
      }
      app.append(row);
    }
  }
}
load();
</script></body></html>
```

The picks API (`tools/design_picks.py`) accepts verdicts `keep`, `original`, `reject`, and `fix` only with a non-empty note (400 otherwise — the page shows an alert); ids must match `[a-z0-9][a-z0-9-]{0,99}`, which `take_image_id` guarantees.

CLI addition in `__main__.py`:

```python
def cmd_page(a) -> int:
    from tools.shorts.page import build
    titles = {}
    for folder in SHORTS_DIR.iterdir():
        if (folder / "short.toml").exists():
            s = load_short(folder)
            titles[s.slug] = (s.title, s.budget_usd)
    site = build(data_dir(), data_dir() / "_site", titles)
    print(f"rsync -a --delete {site}/ 192.168.10.19:anvil-deploy/stack/dashboard/shorts/")
    return 0
```

and register `sub.add_parser("page")`. Make `collect` skip `_site` (it has no `scene.json`, so it is skipped already).

nginx (homelab-ops `gpubox/nginx/nginx.conf`, after the `/studio/api/` block; back up the live file on the box as `nginx.conf.bak-<date>` first, then deploy and `docker compose restart` the nginx service the way the README describes):

```nginx
    # Shorts studio review page (static; verdicts go to /designs/api/images/).
    location /shorts/ {
        root /usr/share/nginx/html;
        index index.html;
        add_header Cache-Control "no-cache";
        try_files $uri $uri/ =404;
    }
```

Also add a "Shorts" tile to the AI Lab dashboard next to "Review new images", following how the existing tiles are defined in the dashboard's index.html on the box (copy one tile, change title and link).

- [ ] **Step 4: Run** — `python -m pytest tests/test_shorts_page.py -q` → PASS
- [ ] **Step 5: Commit** — nightwire: `git add tools/shorts/page.py tools/shorts/page.html tools/shorts/__main__.py tests/test_shorts_page.py && git commit -m "feat(shorts): /shorts/ review page"`; homelab-ops: `git -C ../homelab-ops add gpubox/nginx/nginx.conf && git -C ../homelab-ops commit -m "gpubox: /shorts/ page location"` (copy the live dashboard index.html into homelab-ops if that is where the tile list is kept, per its README).

---

### Task 11: Rough cut (`assemble`)

**Files:**
- Create: `tools/shorts/assemble.py`, `tests/test_shorts_assemble.py`
- Modify: `tools/shorts/__main__.py` (add `assemble`)

**Interfaces:**
- Consumes: `Short`, `Shot.lines` (Task 1); `verdicts.json` per shot (Task 3).
- Produces:
  - `kept_takes(short: Short, work: Path) -> list[Path]` — per shot in order, the newest take with verdict `keep`; shots without one are skipped
  - `srt(short: Short, kept_shots: list[str]) -> str` — subtitle file; each line shown from its time to the next line or shot end, times shifted to the cut's running clock
  - `concat_cmd(takes: list[Path], listfile: Path, music: Path | None, srt_path: Path, out: Path) -> list[str]`
  - CLI `assemble <slug> [--music FILE]` → `work/draft.mp4`

- [ ] **Step 1: Failing tests** — `tests/test_shorts_assemble.py`

```python
import json

from test_shorts_model import write
from tools.shorts.assemble import concat_cmd, kept_takes, srt
from tools.shorts.model import load_short


def test_kept_takes_picks_newest_keep(tmp_path):
    s = load_short(write(tmp_path / "pilot"))
    sd = tmp_path / "work" / "shots" / "S01"
    (sd / "takes").mkdir(parents=True)
    for t in ("t001", "t002", "t003"):
        (sd / "takes" / f"{t}.mp4").write_bytes(b"x")
    (sd / "verdicts.json").write_text(json.dumps({"t001": {"verdict": "keep"}, "t002": {"verdict": "keep"},
                                                  "t003": {"verdict": "reject"}}))
    assert [p.name for p in kept_takes(s, tmp_path / "work")] == ["t002.mp4"]


def test_srt_times_and_text(tmp_path):
    s = load_short(write(tmp_path / "pilot"))
    out = srt(s, ["S01"])
    assert out.startswith("1\n00:00:01,200 --> 00:00:05,000\nWho paid it?")


def test_concat_cmd_with_music_and_subs(tmp_path):
    argv = concat_cmd([tmp_path / "a.mp4"], tmp_path / "list.txt", tmp_path / "m.mp3", tmp_path / "s.srt", tmp_path / "d.mp4")
    joined = " ".join(argv)
    assert argv[0] == "ffmpeg" and "concat" in joined and "subtitles=" in joined and "amix" in joined
    assert (tmp_path / "list.txt").read_text() == f"file '{tmp_path / 'a.mp4'}'\n"
```

- [ ] **Step 2: Run** — FAIL
- [ ] **Step 3: Implement** — `tools/shorts/assemble.py`

```python
"""Rough cut: kept takes in shot order, a music bed, burned subtitles from the script's exact lines."""

import json
from pathlib import Path

from tools.shorts.model import Short


def kept_takes(short: Short, work: Path) -> list[Path]:
    out = []
    for shot in short.shots:
        sd = work / "shots" / shot.id
        v = json.loads((sd / "verdicts.json").read_text()) if (sd / "verdicts.json").exists() else {}
        kept = sorted(t for t, x in v.items() if x.get("verdict") == "keep" and (sd / "takes" / f"{t}.mp4").exists())
        if kept:
            out.append(sd / "takes" / f"{kept[-1]}.mp4")
    return out


def _ts(sec: float) -> str:
    ms = round(sec * 1000)
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(short: Short, kept_shots: list[str]) -> str:
    blocks, clock, n = [], 0.0, 0
    for shot in short.shots:
        if shot.id not in kept_shots:
            continue
        lines = sorted(shot.lines, key=lambda ln: ln.t)
        for i, ln in enumerate(lines):
            end = lines[i + 1].t if i + 1 < len(lines) else shot.end
            n += 1
            blocks.append(f"{n}\n{_ts(clock + ln.t - shot.start)} --> {_ts(clock + end - shot.start)}\n{ln.text}\n")
        clock += shot.duration
    return "\n".join(blocks)


def concat_cmd(takes: list[Path], listfile: Path, music: Path | None, srt_path: Path, out: Path) -> list[str]:
    listfile.write_text("".join(f"file '{t}'\n" for t in takes))
    argv = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listfile)]
    vf = f"subtitles={srt_path}"
    if music:
        argv += ["-stream_loop", "-1", "-i", str(music),
                 "-filter_complex", f"[0:v]{vf}[v];[1:a]volume=0.25[m];[0:a][m]amix=inputs=2:duration=first[a]",
                 "-map", "[v]", "-map", "[a]"]
    else:
        argv += ["-vf", vf]
    return argv + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
```

Note: concat with `-f concat` needs every take to share codec, size and fps; fal/Dreamina 720p outputs normally do. If they differ, normalise each take first with `ffmpeg -i t.mp4 -vf scale=1280:720,fps=24 -c:v libx264 -c:a aac` into `work/norm/` and concat those. Takes with no audio track break `[0:a]` — when any kept take lacks audio (`ffprobe -select_streams a`), add `-f lavfi -i anullsrc` handling or normalise with `-af apad`. Handle this in the CLI (probe, then normalise) and cover the probe decision with a small test.

CLI:

```python
def cmd_assemble(a) -> int:
    from tools.shorts.assemble import concat_cmd, kept_takes, srt
    s, work = _short(a.slug), _work(a.slug)
    takes = kept_takes(s, work)
    if not takes:
        print("no kept takes yet — run verdicts first", file=sys.stderr)
        return 1
    (work / "draft.srt").write_text(srt(s, [t.parent.parent.name for t in takes]))
    subprocess.run(concat_cmd(takes, work / "draft.txt", a.music, work / "draft.srt", work / "draft.mp4"), check=True)
    print(work / "draft.mp4")
    return 0
```

register `q = sub.add_parser("assemble"); q.add_argument("slug"); q.add_argument("--music", type=Path)` (import `Path`). Have `page.collect` include `draft.mp4` when present (add a `"draft"` field and show it at the top of the short on the page).

- [ ] **Step 4: Run** — `python -m pytest tests/test_shorts_assemble.py tests/test_shorts_page.py -q` → PASS
- [ ] **Step 5: Commit** — `git add tools/shorts/assemble.py tools/shorts/__main__.py tools/shorts/page.py tools/shorts/page.html tests/test_shorts_assemble.py && git commit -m "feat(shorts): rough cut with subtitles and music bed"`

---

### Task 12: Pilot script, grey-box and owner review (live)

**Files:**
- Create: `narrator/worlds/shorts/saeko-rin-izakaya/short.toml`, `narrator/worlds/shorts/saeko-rin-izakaya/shots/S01.toml`
- Modify: `pyproject.toml` package-data (`"worlds/shorts/*/*.toml", "worlds/shorts/*/shots/*.toml"` under `narrator`)

- [ ] **Step 1: Confirm cast and place with the owner** (default Saeko C1, Rin C2, Mama Sato's izakaya). Read both characters' design TOMLs and world cards (`narrator/worlds/kuroshio.toml`) and the izakaya design; write a 15–30 s scene using Foyege's beat formula (strange event → immediate goal → unbreakable rule → ticking clock → reveal → open question), night only, no exposition. 2–3 shots, each ≤10 s, at least one shot/reverse pair. Lines short; one overlap and one disfluency where the research says they belong (on the hardest word).
- [ ] **Step 2: Lay out the room** from the izakaya's `play.png`: counter, stools, door, back shelf as blocks; C1 seated (`mannequin`, `sit`), C2 entering (`capsule` path → `mannequin` if she sits). Cameras per shot in film terms.
- [ ] **Step 3: Validate and build** — `python -m tools.shorts check saeko-rin-izakaya` → `ok`; `python -m tools.shorts prompt saeko-rin-izakaya S01` reads well; free the GPU, then `python -m tools.shorts greybox saeko-rin-izakaya` and the same with `--tint` into a copy (rename the work folder between runs) for the tint A/B.
- [ ] **Step 4: Publish** — `python -m tools.shorts page`, run the printed rsync, open `http://192.168.10.19:8080/shorts/` in a real browser (Playwright with `channel="chrome"`, as in earlier phases) and check video playback and that a Keep click round-trips through `/designs/api/images/`; undo the test verdict.
- [ ] **Step 5: Owner review loop** — the owner comments on floor plan and grey-box; fix camera/blocking only, re-render, republish, until the owner approves the grey-box.
- [ ] **Step 6: Commit** the script files: `git add narrator/worlds/shorts pyproject.toml && git commit -m "feat(shorts): pilot script Saeko and Rin at Mama Sato's"`

---

### Task 13: Anime A/B test (live, spends money — owner go-ahead required)

- [ ] **Step 1: Owner prerequisites** — owner creates the fal account, adds credit, writes `FAL_KEY=…` into `~/.config/nightwire/secrets.env` (`chmod 600`). Optionally signs up for Dreamina.
- [ ] **Step 2: Pick the test shot** (the calmest shot of the pilot, cut to 5 s via `--seconds 5`). Confirm the model list and total estimate with the owner (target $3–6): `seedance-2.5`, `seedance-2.0-fast`, `kling-3`, `veo-3.1-fast`, plus Dreamina (manual bundle → inbox) if the owner signed up.
- [ ] **Step 3: Run** — `python -m tools.shorts submit saeko-rin-izakaya S01 --model <key> --seconds 5 --yes` per model (one at a time; record any refusal message verbatim in the take notes); manual route: `bundle`, owner pastes into Dreamina, saves result to `inbox/`, `inbox --cost <real> --model seedance-2.5`.
- [ ] **Step 4: Identity check** — `python -m tools.shorts idcheck saeko-rin-izakaya S01 <take>` for each take (needs the `qa` extra installed); note rank 1/2 results next to each take.
- [ ] **Step 5: Owner picks** on `/shorts/` (Keep / Reject / Needs a fix with notes). `python -m tools.shorts verdicts saeko-rin-izakaya`; write the result (winner, cost per kept second, refusals, identity ranks) to `docs/superpowers/research/2026-11-08-anime-ab-results.md` and commit.

---

### Task 14: Docs and roadmap

**Files:**
- Create: `docs/shorts-guide.md`
- Modify: `ROADMAP.md` (new "Phase 23 — Shorts studio" section: what shipped, owner decisions, Phase 1/2 next), `README.md` (one line under tools)

- [ ] **Step 1: Write `docs/shorts-guide.md`** — the loop in order with exact commands: write script → `check` → `prompt` → `greybox` → `page` + rsync → review → `bundle`/`submit`/`inbox` → `idcheck` → `verdicts` → `assemble`; where files live; spend guard and how to raise `budget_usd`; secrets file; GPU etiquette; the prompt-layer rules and the 8-dimension acting block with one filled example from the pilot.
- [ ] **Step 2: ROADMAP + README**, then run the whole suite: `python -m pytest tests/ -q` → all pass.
- [ ] **Step 3: Commit** — `git add docs/shorts-guide.md ROADMAP.md README.md && git commit -m "docs(shorts): guide and roadmap"`
- [ ] **Step 4: Ask the owner before pushing** nightwire `main` (and homelab-ops).
