# Shorts Production Sheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before any paid generation, every shot of a short is planned on one production sheet, passes pre-flight checks, and is approved by the owner; `submit` refuses anything else.

**Architecture:** The short's TOML stays the only source. New shot fields (size, angle, move, action, frame, at_start, at_end, props) load into the existing dataclasses. A pure `preflight` module checks a shot; an `approve` module fingerprints the exact prompt + references and syncs owner verdicts from the existing review API; `submit` runs preflight → approval → retry cap → budget before spending. A static sheet page (same pattern as the /shorts/ page) shows everything with Approve/Change/Reject buttons. A `stills` command renders a free opening-frame still per shot that replaces `place.png` in the references.

**Tech Stack:** Python 3.13, tomllib, pytest, PIL, ComfyUI via `narrator.comfyui_backend`, static HTML + vanilla JS, existing `/designs/api/images` verdict API.

**Spec:** `docs/superpowers/specs/2026-11-09-shorts-production-sheet-design.md`

## Global Constraints

- Run from the worktree root with `../../../.venv/bin/python` and `NIGHTWIRE_DESIGN_DIR=/home/sentinel/projects/github/repos/nightwire/design-data` for anything touching design data.
- Tests: `../../../.venv/bin/python -m pytest tests/ -q` must stay green (CI runs the full suite).
- No AI-attribution trailers in commits. Do not push; the controller asks the owner first.
- Never print or log FAL_KEY. No paid fal call anywhere in this plan; tests fake `fal.run_take`/`fal.start`.
- GPU box: one job at a time, check the queue first, free ComfyUI VRAM after; never touch Ollama.
- No daytime, no adult/explicit content in any still prompt.
- Owner-facing text (sheet page) is plain English, no jargon without a short explanation.
- Dialogue pace limit 2.5 words/s with 1.0 s of air; retry cap default 2 extra takes per approved fingerprint.
- Plan verdict ids: `plan--<slug>--<shot lower>--<fp>`, `fp` = first 10 hex of SHA-256.

## Rulings made while planning (spec conflicts)

- Ruling: shot state tables are named `[at_start]` / `[at_end]`, not `[start]` / `[end]` — shot TOML already uses `start`/`end` for times; reusing the keys would break every short. Cost if wrong: a rename.
- Ruling: missing new fields are reported by **preflight**, not `validate_short` — so `check` keeps passing on old shorts as the spec's last sentence requires; `validate_short` only checks values that are present (size in the list, cast ids valid). Cost if wrong: one function moves.
- Ruling: screen direction is checked as "a character's screen side (`screen-left`/`screen-right` in `[frame]`) does not swap between consecutive shots unless `cross_ok = true`"; `line_rule` is free text shown on the sheet. Parsing free text is not reliable. Cost if wrong: a stricter check later.
- Ruling: retry cap counts takes whose metadata `fp` equals the current approved fingerprint, so old pilot takes (made before fingerprints) never block the re-shoot.

Task 1 updates the spec text for the first two rulings.

## File map

| File | Responsibility |
|---|---|
| `tools/shorts/model.py` (modify) | new fields on `Shot` and `Short`, value validation |
| `tools/shorts/backends/fal.py` (modify) | `max_images` per model, `usable_refs()`, `run_take(meta=, note=)` |
| `tools/shorts/takes.py` (modify) | `Ledger.add(note=)` |
| `tools/shorts/prompt.py` (modify) | `has_still` → L1 line; `ref_files` swaps `place.png` for `start_frame.png` |
| `tools/shorts/preflight.py` (create) | pure checks, `Report` |
| `tools/shorts/approve.py` (create) | fingerprint, plan ids, approvals sync, take counting |
| `tools/shorts/sheet.py` + `sheet.html` (create) | production sheet data + page |
| `tools/shorts/stills.py` (create) | opening-frame still workflow + render |
| `tools/shorts/__main__.py` (modify) | `preflight`, `sheet`, `stills` commands; gated `submit`; `verdicts` also syncs approvals |
| `tests/test_shorts_*.py` | one test file per new module, CLI tests updated |
| `narrator/worlds/shorts/saeko-rin-izakaya/*` | pilot filled in with the new fields |
| `docs/shorts-guide.md` | the new plan → approve → shoot flow |

---

### Task 1: New shot and short fields

**Files:**
- Modify: `tools/shorts/model.py`
- Modify: `docs/superpowers/specs/2026-11-09-shorts-production-sheet-design.md` (rulings 1-2)
- Test: `tests/test_shorts_model.py`

**Interfaces:**
- Produces: `SIZES: tuple[str, ...]`; `Shot.size, angle, move, action: str`; `Shot.frame, at_start, at_end, props: dict[str, str]`; `Shot.prop_change: list[str]`; `Shot.cross_ok: bool`; `Short.line_rule: str`, `Short.model: str`, `Short.locks: dict[str, str]`, `Short.retry_cap: int` (default 2).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_shorts_model.py`)

```python
# Top-level keys must come before the first [table] in TOML, so the plan keys go right after `lens`
# and the plan tables go at the end.
PLAN_KEYS = '''lens = 35.0
size = "MCU"
angle = "eye level, over C1's right shoulder"
move = "slow push-in"
action = "C2 asks who paid her tab."
prop_change = ["C1"]
cross_ok = false'''
PLAN_TABLES = '''
[frame]
C2 = "screen-left, facing camera"
C1 = "foreground screen-right, back of head"

[at_start]
C1 = "seated, cup in right hand"

[at_end]
C2 = "leaning on the counter"

[props]
C1 = "sake cup in right hand"
'''
PLANNED = SHOT.replace("lens = 35.0", PLAN_KEYS) + PLAN_TABLES


def test_planned_fields_load(tmp_path):
    shot = load_short(write(tmp_path, shot=PLANNED)).shots[0]
    assert shot.size == "MCU" and shot.move == "slow push-in"
    assert shot.action == "C2 asks who paid her tab."
    assert shot.frame["C2"].startswith("screen-left")
    assert shot.at_start["C1"] == "seated, cup in right hand" and shot.at_end["C2"] == "leaning on the counter"
    assert shot.props == {"C1": "sake cup in right hand"} and shot.prop_change == ["C1"] and shot.cross_ok is False


def test_old_shots_still_load_with_empty_plan_fields(tmp_path):
    s = load_short(write(tmp_path))
    assert s.shots[0].size == "" and s.shots[0].frame == {} and s.retry_cap == 2 and s.locks == {}
    assert validate_short(s, designs()) == []


def test_short_plan_fields_load(tmp_path):
    short = SHORT.replace('budget_usd = 25.0', 'budget_usd = 25.0\nline_rule = "C1 is screen-right of C2"\nmodel = "seedance-2.0-fast"\nretry_cap = 3')
    short += '\n[locks]\nC1 = "chrome right hand"\n'  # a table goes at the end, after every top-level key
    s = load_short(write(tmp_path, short=short))
    assert s.line_rule.startswith("C1") and s.model == "seedance-2.0-fast" and s.retry_cap == 3
    assert s.locks == {"C1": "chrome right hand"}


@pytest.mark.parametrize("bad, expected", [
    (PLANNED.replace('size = "MCU"', 'size = "closeish"'), "size 'closeish' not in"),
    (PLANNED.replace('[frame]\nC2', '[frame]\nC7'), "unknown cast id C7"),
    (PLANNED.replace('[props]\nC1', '[props]\nC8'), "unknown cast id C8"),
])
def test_plan_field_values_are_checked(tmp_path, bad, expected):
    problems = validate_short(load_short(write(tmp_path, shot=bad)), designs())
    assert any(expected in p for p in problems), problems
```

Note: in TOML every key after a `[table]` header belongs to that table, so plan keys go before the first table and new tables go at the end (that is why `PLANNED` and the `[locks]` test are built this way). `SHOT` itself stays unchanged: it is the "old, unplanned shot" for tests that need missing fields.

- [ ] **Step 2: Run to verify they fail**

Run: `../../../.venv/bin/python -m pytest tests/test_shorts_model.py -q`
Expected: FAIL — `AttributeError: 'Shot' object has no attribute 'size'`.

- [ ] **Step 3: Implement** in `tools/shorts/model.py`

Add after `MAX_SHOT_S`:

```python
# Shot sizes, closest first. ECU extreme close-up, CU close-up, MCU medium close-up (chest up), MS medium (waist up),
# MWS medium wide (knees up), WS wide (whole body), EWS extreme wide (the place dominates).
SIZES = ("ECU", "CU", "MCU", "MS", "MWS", "WS", "EWS")
```

Add fields to `Shot` (after `model: str = ""`):

```python
    size: str = ""
    angle: str = ""
    move: str = ""
    action: str = ""
    frame: dict[str, str] = field(default_factory=dict)      # who is in frame and where, at the cut
    at_start: dict[str, str] = field(default_factory=dict)   # pose / gaze / hands when the shot opens
    at_end: dict[str, str] = field(default_factory=dict)     # ... and when it cuts
    props: dict[str, str] = field(default_factory=dict)      # what each character holds, and in which hand
    prop_change: list[str] = field(default_factory=list)     # cast ids whose props change on purpose in this shot
    cross_ok: bool = False                                   # a deliberate crossing of the screen-direction line
```

Add fields to `Short` (after `shots`):

```python
    line_rule: str = ""
    model: str = ""
    locks: dict[str, str] = field(default_factory=dict)
    retry_cap: int = 2
```

In `_shot`, add to the `Shot(...)` call:

```python
        size=d.get("size", ""), angle=d.get("angle", ""), move=d.get("move", ""), action=d.get("action", ""),
        frame=dict(d.get("frame", {})), at_start=dict(d.get("at_start", {})), at_end=dict(d.get("at_end", {})),
        props=dict(d.get("props", {})), prop_change=list(d.get("prop_change", [])), cross_ok=bool(d.get("cross_ok", False)),
```

In `load_short`, add to the `Short(...)` call:

```python
        line_rule=d.get("line_rule", ""), model=d.get("model", ""), locks=dict(d.get("locks", {})),
        retry_cap=int(d.get("retry_cap", 2)),
```

In `validate_short`, inside the `for shot in s.shots:` loop, after the existing `ids = ...` line, replace that line with:

```python
        ids = ([ln.who for ln in shot.lines] + [a.who for a in shot.acting] + list(shot.state) + list(shot.frame)
               + list(shot.at_start) + list(shot.at_end) + list(shot.props) + list(shot.prop_change))
```

and add before the `for ln in shot.lines:` loop:

```python
        if shot.size and shot.size not in SIZES:
            problems.append(f"{where}: size {shot.size!r} not in {SIZES}")
```

- [ ] **Step 4: Run tests**

Run: `../../../.venv/bin/python -m pytest tests/test_shorts_model.py -q`
Expected: all PASS.

- [ ] **Step 5: Update the spec for rulings 1-2**

In the spec's section 1 table, change the row `` `[start]` / `[end]` `` to `` `[at_start]` / `[at_end]` `` (shot TOML already uses `start`/`end` for times). Replace the paragraph starting "`validate_short` reports a missing required field" with: "Missing new fields are reported by pre-flight; `validate_short` only checks values that are present (size in the list, cast ids), so old shorts still pass `check`."

- [ ] **Step 6: Full suite + commit**

Run: `../../../.venv/bin/python -m pytest tests/ -q` → all PASS.

```bash
git add tools/shorts/model.py tests/test_shorts_model.py docs/superpowers/specs/2026-11-09-shorts-production-sheet-design.md
git commit -m "shorts: shot plan fields (size, angle, move, action, frame, at_start/at_end, props)"
```

---

### Task 2: Pre-flight checks

**Files:**
- Modify: `tools/shorts/backends/fal.py` (add `max_images`, `usable_refs`)
- Create: `tools/shorts/preflight.py`
- Modify: `tools/shorts/__main__.py` (`preflight` command; `submit` uses `usable_refs`)
- Test: `tests/test_shorts_preflight.py`, `tests/test_shorts_fal.py`

**Interfaces:**
- Consumes: Task 1 fields.
- Produces: `fal.usable_refs(model: str, refs: list[tuple[str, Path]]) -> tuple[list[tuple[str, Path]], list[str]]`; `preflight.Report(problems: list[str], warnings: list[str])` with `.ok -> bool`; `preflight.run(short, shot, prev: Shot | None, prompt: str, refs, model: str, spent: float) -> Report`; constants `WORDS_PER_S = 2.5`, `AIR_S = 1.0`, `FILTER_WORDS`.

- [ ] **Step 1: Write the failing tests** — `tests/test_shorts_preflight.py`

```python
from pathlib import Path

from test_shorts_model import PLANNED, SHORT, write
from tools.shorts import preflight
from tools.shorts.backends import fal
from tools.shorts.model import load_short


def shot(tmp_path, text=PLANNED):
    return load_short(write(tmp_path, shot=text))


def test_complete_shot_passes(tmp_path):
    s = shot(tmp_path)
    r = preflight.run(s, s.shots[0], None, "a calm prompt", [], "seedance-2.0-fast", 0.0)
    assert r.problems == [] and r.ok


def test_missing_fields_are_listed(tmp_path):
    from test_shorts_model import SHOT
    s = shot(tmp_path, SHOT)
    r = preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0.0)
    for f in ("size", "angle", "move", "action", "frame"):
        assert any(f"missing {f}" in p for p in r.problems), r.problems


def test_dialogue_pace(tmp_path):
    fast = PLANNED.replace('text = "Who paid it?"', 'text = "' + " ".join(["word"] * 12) + '"')
    s = shot(tmp_path, fast)  # 12 words in (5 s - 1 s air) = 3.0 words/s
    assert any("words/s" in p for p in preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0).problems)


def test_one_action_and_one_move(tmp_path):
    two = PLANNED.replace('action = "C2 asks who paid her tab."', 'action = "C2 sits. C1 leaves."')
    two = two.replace('move = "slow push-in"', 'move = "push-in then pan left"')
    s = shot(tmp_path, two)
    p = preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 0).problems
    assert any("one sentence" in x for x in p) and any("one camera move" in x for x in p)


def test_continuity_props_and_screen_side(tmp_path):
    s = shot(tmp_path)
    prev = s.shots[0]
    nxt = load_short(write(tmp_path / "b", shot=PLANNED.replace('prop_change = ["C1"]', 'prop_change = []')
                           .replace('C1 = "sake cup in right hand"', 'C1 = "sake cup in left hand"')
                           .replace('C2 = "screen-left, facing camera"', 'C2 = "screen-right, facing camera"'))).shots[0]
    p = preflight.run(s, nxt, prev, "p", [], "seedance-2.0-fast", 0).problems
    assert any("C1 props change" in x for x in p) and any("C2 swaps screen side" in x for x in p)


def test_refs_missing_and_over_limit(tmp_path):
    s = shot(tmp_path)
    (tmp_path / "a.png").write_bytes(b"x")
    refs = [(f"C{i}_x.png", tmp_path / "a.png") for i in range(10)] + [("gone.png", tmp_path / "nope.png")]
    p = preflight.run(s, s.shots[0], None, "p", refs, "seedance-2.0-fast", 0).problems
    assert any("gone.png" in x and "missing" in x for x in p) and any("images" in x and "limit 9" in x for x in p)


def test_filter_words_warn_only(tmp_path):
    s = shot(tmp_path)
    r = preflight.run(s, s.shots[0], None, "she tries to plug it in", [], "seedance-2.0-fast", 0)
    assert r.ok and any("plug it in" in w for w in r.warnings)


def test_budget(tmp_path):
    s = shot(tmp_path)  # budget 25, 5 s on 2.0-fast ~ $1.21
    assert any("budget" in p for p in preflight.run(s, s.shots[0], None, "p", [], "seedance-2.0-fast", 24.5).problems)


def test_usable_refs_applies_skip_and_video(tmp_path):
    refs = [("C1_turnaround.png", Path("a")), ("floorplan.png", Path("b")), ("greybox.mp4", Path("c"))]
    kept, out = fal.usable_refs("seedance-2.0-fast", refs)
    assert [l for l, _ in kept] == ["C1_turnaround.png", "greybox.mp4"] and out == ["floorplan.png"]
    kept, out = fal.usable_refs("kling-3", refs)
    assert "greybox.mp4" in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `../../../.venv/bin/python -m pytest tests/test_shorts_preflight.py -q`
Expected: FAIL — `ImportError` / `AttributeError: usable_refs`.

- [ ] **Step 3: Implement `fal.max_images` and `usable_refs`**

In `tools/shorts/backends/fal.py`, add `"max_images": 9` to the `seedance-2.0-fast` and `seedance-2.0` dicts, `"max_images": 30` to `seedance-2.5`, `"max_images": 7` to `kling-3`. Add after `MODELS`:

```python
def usable_refs(model: str, refs: list[tuple[str, Path]]) -> tuple[list[tuple[str, Path]], list[str]]:
    """The refs this model can take, and the labels left out (its skip list, and videos when it takes none)."""
    spec = MODELS[model]
    out = [label for label, _ in refs if label in spec.get("skip", ()) or (label.endswith(".mp4") and spec["video"] is None)]
    return [r for r in refs if r[0] not in out], out
```

In `tools/shorts/__main__.py` `cmd_submit`, replace the block from `spec = fal.MODELS[a.model]` through the `print(f"{a.model} can't take every reference; ...")` lines with:

```python
    refs, left_out = fal.usable_refs(a.model, refs)
    if left_out:
        print(f"{a.model} can't take every reference; left out: {', '.join(left_out)}")
```

- [ ] **Step 4: Implement `tools/shorts/preflight.py`**

```python
"""Checks a shot must pass before money is spent on it. Problems block `submit`; warnings are shown only.
Numbers are defaults to tune (spec 2026-11-09): 2.5 spoken words per second with 1 s of air in each shot."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.shorts.backends import fal
from tools.shorts.model import Shot, Short
from tools.shorts.takes import estimate

WORDS_PER_S = 2.5
AIR_S = 1.0
# Phrases that tripped ByteDance's content filter on the pilot (S02, 2026-11-08); a warning, not a block.
FILTER_WORDS = ("plug it in", "plug in", "open it", "stuck", "jack in")
REQUIRED = ("size", "angle", "move", "action")
SIDE = re.compile(r"screen[- ]?(left|right)", re.IGNORECASE)


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def required(shot: Shot) -> list[str]:
    out = [f"missing {f}" for f in REQUIRED if not getattr(shot, f).strip()]
    for name in ("frame", "at_start", "at_end"):
        if not getattr(shot, name):
            out.append(f"missing {name}")
    return out


def pace(shot: Shot) -> list[str]:
    words = sum(len(ln.text.split()) for ln in shot.lines)
    room = max(shot.duration - AIR_S, 0.5)
    rate = words / room
    return [f"dialogue {words} words in {room:g} s = {rate:.1f} words/s (limit {WORDS_PER_S})"] if rate > WORDS_PER_S else []


def one_action(shot: Shot) -> list[str]:
    out = []
    if len(re.findall(r"[.!?](?:\s|$)", shot.action.strip())) > 1:
        out.append("action must be one sentence (one main thing happens)")
    if re.search(r"\b(and|then)\b|,", shot.move):
        out.append(f"move {shot.move!r}: one camera move per shot")
    return out


def _side(text: str) -> str | None:
    m = SIDE.search(text)
    return m.group(1).lower() if m else None


def continuity(prev: Shot | None, shot: Shot) -> list[str]:
    if prev is None:
        return []
    out = []
    for cid in sorted(set(prev.props) & set(shot.props)):
        if prev.props[cid] != shot.props[cid] and cid not in shot.prop_change:
            out.append(f"{cid} props change from {prev.id} ({prev.props[cid]!r} -> {shot.props[cid]!r}); "
                       f"add {cid} to prop_change if that is on purpose")
    for cid in sorted(set(prev.frame) & set(shot.frame)):
        a, b = _side(prev.frame[cid]), _side(shot.frame[cid])
        if a and b and a != b and not shot.cross_ok:
            out.append(f"{cid} swaps screen side ({prev.id} {a} -> {shot.id} {b}); set cross_ok = true if that is on purpose")
    return out


def refs(model: str, ref_list: list[tuple[str, Path]]) -> list[str]:
    out = [f"{label}: file missing ({p})" for label, p in ref_list if not p.exists()]
    images = sum(1 for label, _ in ref_list if label.endswith(".png"))
    limit = fal.MODELS[model]["max_images"]
    if images > limit:
        out.append(f"{images} images, {model} limit {limit}")
    return out


def filter_words(prompt: str) -> list[str]:
    low = prompt.lower()
    return [f"content filter risk: {w!r} (tripped ByteDance's filter on the pilot; prefer plain technical words)"
            for w in FILTER_WORDS if w in low]


def budget(short: Short, shot: Shot, model: str, spent: float) -> list[str]:
    cost = estimate(model, int(round(shot.duration)))
    left = short.budget_usd - spent
    return [f"${cost:.2f} would pass the budget (${left:.2f} left of ${short.budget_usd:.0f})"] if cost > left else []


def run(short: Short, shot: Shot, prev: Shot | None, prompt: str, ref_list, model: str, spent: float) -> Report:
    used, _ = fal.usable_refs(model, ref_list)
    return Report(problems=required(shot) + pace(shot) + one_action(shot) + continuity(prev, shot) + refs(model, used)
                  + budget(short, shot, model, spent),
                  warnings=filter_words(prompt))
```

- [ ] **Step 5: Add the `preflight` command** in `tools/shorts/__main__.py`

```python
def _prev(short, shot):
    i = [s.id for s in short.shots].index(shot.id)
    return short.shots[i - 1] if i else None


def _preflight(s, shot, model, designs):
    from tools.shorts import preflight
    work = _work(s.slug)
    shot_dir = work / "shots" / shot.id
    prompt = build_prompt(s, shot, designs, has_still=(shot_dir / "still.png").exists())
    refs = ref_files(s, data_dir().parent, shot_dir)
    return preflight.run(s, shot, _prev(s, shot), prompt, refs, model, Ledger(work / "costs.json").total()), prompt, refs


def cmd_preflight(a) -> int:
    s, designs = _short(a.slug), load_designs()
    model = a.model or s.model
    if not model:
        raise CliError("no model: pass --model or set model in short.toml")
    bad = 0
    for shot in [_shot(s, a.shot)] if a.shot else s.shots:
        report = _preflight(s, shot, model, designs)[0]
        print(f"{shot.id}: {'ok' if report.ok else 'FAIL'}")
        for p in report.problems:
            print(f"  problem: {p}")
        for w in report.warnings:
            print(f"  warning: {w}")
        bad += not report.ok
    return 1 if bad else 0
```

Note: `build_prompt(..., has_still=...)` is added in Task 5. Until then, implement `_preflight` with `build_prompt(s, shot, designs)` and Task 5 adds the keyword. In `main`, register:

```python
    q = sub.add_parser("preflight"); q.add_argument("slug"); q.add_argument("shot", nargs="?"); q.add_argument("--model")
```

Add a CLI test to `tests/test_shorts_cli.py`:

```python
def test_preflight_reports_missing_fields(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, shot=SHOT)
    assert main(["preflight", "pilot", "--model", "seedance-2.0-fast"]) == 1
    assert "missing size" in capsys.readouterr().out
```

- [ ] **Step 6: Run tests**

Run: `../../../.venv/bin/python -m pytest tests/test_shorts_preflight.py tests/test_shorts_cli.py tests/test_shorts_fal.py -q` → PASS, then the full suite → PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/shorts/preflight.py tools/shorts/backends/fal.py tools/shorts/__main__.py tests/test_shorts_preflight.py tests/test_shorts_cli.py
git commit -m "shorts: pre-flight checks (fields, pace, one action, continuity, refs, filter words, budget)"
```

---

### Task 3: Fingerprint, approvals and the money gate

**Files:**
- Create: `tools/shorts/approve.py`
- Modify: `tools/shorts/takes.py` (`Ledger.add(note=)`), `tools/shorts/backends/fal.py` (`run_take(meta=, note=)`), `tools/shorts/__main__.py` (`submit` gate, `verdicts` syncs approvals)
- Test: `tests/test_shorts_approve.py`, `tests/test_shorts_cli.py`, `tests/test_shorts_takes.py`

**Interfaces:**
- Consumes: `fal.usable_refs`, `preflight.Report`, `_preflight(s, shot, model, designs) -> (Report, prompt, refs)` from Task 2.
- Produces: `approve.fingerprint(model: str, prompt: str, refs: list[tuple[str, Path]]) -> str`; `approve.plan_image_id(slug, shot_id, fp) -> str`; `approve.apply_approvals(short_dir, slug, api) -> dict`; `approve.approval(short_dir, shot_id, fp) -> dict | None`; `approve.takes_under(shot_dir, fp) -> int`. `fal.run_take(..., meta: dict | None = None, note: str = "")`. `Ledger.add(shot, take, model, cost, note="")`.

- [ ] **Step 1: Write the failing tests** — `tests/test_shorts_approve.py`

```python
import json

import pytest

from tools.shorts import approve


def refs(tmp_path, content=b"a"):
    (tmp_path / "x.png").write_bytes(content)
    return [("C1_turnaround.png", tmp_path / "x.png")]


def test_fingerprint_is_stable_and_sensitive(tmp_path):
    fp = approve.fingerprint("seedance-2.0-fast", "prompt", refs(tmp_path))
    assert len(fp) == 10 and fp == approve.fingerprint("seedance-2.0-fast", "prompt", refs(tmp_path))
    assert fp != approve.fingerprint("seedance-2.0-fast", "prompt!", refs(tmp_path))
    assert fp != approve.fingerprint("seedance-2.0", "prompt", refs(tmp_path))
    assert fp != approve.fingerprint("seedance-2.0-fast", "prompt", refs(tmp_path, b"b"))


def test_plan_image_id_and_bad_slug():
    assert approve.plan_image_id("pilot", "S01", "abc") == "plan--pilot--s01--abc"
    with pytest.raises(ValueError):
        approve.plan_image_id("bad--slug", "S01", "abc")


def test_apply_and_read_approvals(tmp_path):
    api = {"plan--pilot--s01--abc": {"verdict": "keep"}, "plan--pilot--s02--def": {"verdict": "fix", "note": "closer"},
           "plan--other--s01--abc": {"verdict": "keep"}, "short--pilot--s01--t001": {"verdict": "keep"}, "plan--pilot--bad": {}}
    mine = approve.apply_approvals(tmp_path, "pilot", api)
    assert set(mine) == {"plan--pilot--s01--abc", "plan--pilot--s02--def"}
    assert approve.approval(tmp_path, "S01", "abc") == {"verdict": "keep"}
    assert approve.approval(tmp_path, "S01", "zzz") is None
    assert json.loads((tmp_path / "approvals.json").read_text())["S02"]["def"]["note"] == "closer"


def test_takes_under_counts_matching_fp(tmp_path):
    t = tmp_path / "takes"
    t.mkdir()
    (t / "t001.json").write_text(json.dumps({"model": "x"}))
    (t / "t002.json").write_text(json.dumps({"fp": "abc"}))
    (t / "t003.json").write_text(json.dumps({"fp": "abc"}))
    assert approve.takes_under(tmp_path, "abc") == 2 and approve.takes_under(tmp_path, "zzz") == 0
```

Add to `tests/test_shorts_takes.py`:

```python
def test_ledger_note_is_saved(tmp_path):
    from tools.shorts.takes import Ledger
    led = Ledger(tmp_path / "costs.json")
    led.add("S01", "t001", "m", 1.0, note="override: owner said go")
    led.add("S01", "t002", "m", 1.0)
    rows = json.loads((tmp_path / "costs.json").read_text())
    assert rows[0]["note"] == "override: owner said go" and "note" not in rows[1]
```

(`tests/test_shorts_takes.py` already imports `json`; if not, add `import json`.)

- [ ] **Step 2: Run to verify they fail**

Run: `../../../.venv/bin/python -m pytest tests/test_shorts_approve.py tests/test_shorts_takes.py -q` → FAIL (`ModuleNotFoundError: tools.shorts.approve`).

- [ ] **Step 3: Implement `tools/shorts/approve.py`**

```python
"""Owner sign-off per shot. An approval belongs to one exact prompt + reference set (its fingerprint), so any edit
after approval needs a new approval. Verdicts travel through the existing /designs/api/images review API under the
id plan--<slug>--<shot>--<fp> (keep = approved, fix = change with a note, reject)."""

import hashlib
import json
from pathlib import Path

from tools.shorts.takes import SLUG


def fingerprint(model: str, prompt: str, refs: list[tuple[str, Path]]) -> str:
    h = hashlib.sha256(model.encode() + b"\0" + prompt.encode())
    for label, path in refs:
        h.update(b"\0" + label.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()[:10]


def plan_image_id(slug: str, shot_id: str, fp: str) -> str:
    if "--" in slug or not SLUG.fullmatch(slug):
        raise ValueError(f"slug {slug!r} must match [a-z0-9][a-z0-9-]* and must not contain '--'")
    return f"plan--{slug}--{shot_id.lower()}--{fp}"


def apply_approvals(short_dir: Path, slug: str, api: dict) -> dict[str, dict]:
    prefix = f"plan--{slug}--"
    mine, per_shot = {}, {}
    for key, v in api.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].split("--")
        if len(parts) != 2:
            continue  # malformed id from the shared API; skip it
        mine[key] = v
        per_shot.setdefault(parts[0].upper(), {})[parts[1]] = {k: v[k] for k in ("verdict", "note") if k in v}
    short_dir.mkdir(parents=True, exist_ok=True)
    (short_dir / "approvals.json").write_text(json.dumps(per_shot, indent=1, sort_keys=True))
    return mine


def approval(short_dir: Path, shot_id: str, fp: str) -> dict | None:
    path = short_dir / "approvals.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    return data.get(shot_id, {}).get(fp)


def takes_under(shot_dir: Path, fp: str) -> int:
    return sum(1 for m in (shot_dir / "takes").glob("t*.json") if json.loads(m.read_text()).get("fp") == fp)
```

- [ ] **Step 4: `Ledger.add(note=)` and `run_take(meta=, note=)`**

In `tools/shorts/takes.py` change `Ledger.add`:

```python
    def add(self, shot: str, take: str, model: str, cost: float, note: str = "") -> None:
        row = {"shot": shot, "take": take, "model": model, "cost": cost,
               "at": dt.datetime.now().isoformat(timespec="seconds")}
        if note:
            row["note"] = note
        rows = self._rows() + [row]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, indent=1))
```

In `tools/shorts/backends/fal.py` change `run_take`'s signature to
`def run_take(short_dir, shot_id, model, prompt, refs, seconds, budget, *, key, client, meta=None, note="") -> str:`,
change `ledger.add(shot_id, f"req-{job['request_id']}", model, cost)` to
`ledger.add(shot_id, f"req-{job['request_id']}", model, cost, note=note)`, and change the `file_take(...)` meta dict to
`{**(meta or {}), "model": model, "cost": cost, "backend": "fal", "seconds": seconds, "request_id": job["request_id"], "refs": [label for label, _ in refs]}`.

- [ ] **Step 5: Gate `submit` and sync approvals in `verdicts`**

In `tools/shorts/__main__.py` add `from tools.shorts import approve` to the imports. Replace `cmd_submit` with:

```python
def cmd_submit(a) -> int:
    import httpx

    from tools.shorts.backends import fal
    if a.model not in fal.MODELS:
        raise CliError(f"unknown model {a.model!r}; choose from: {', '.join(fal.MODELS)}")
    s, work, designs = _short(a.slug), _work(a.slug), load_designs()
    shot = _shot(s, a.shot)
    shot_dir = work / "shots" / a.shot
    report, prompt, refs = _preflight(s, shot, a.model, designs)
    for w in report.warnings:
        print(f"warning: {w}")
    if not report.ok:
        for p in report.problems:
            print(f"problem: {p}", file=sys.stderr)
        print("pre-flight failed: nothing was spent", file=sys.stderr)
        return 1
    refs, left_out = fal.usable_refs(a.model, refs)
    if left_out:
        print(f"{a.model} can't take every reference; left out: {', '.join(left_out)}")
    fp = approve.fingerprint(a.model, prompt, refs)
    ok = approve.approval(work, a.shot, fp)
    if not (ok and ok.get("verdict") == "keep"):
        if not a.override:
            print(f"{a.shot} is not approved for this exact prompt and references (fingerprint {fp}); "
                  "approve it on the production sheet, run `verdicts`, or pass --override \"<reason>\"", file=sys.stderr)
            return 1
        print(f"override: {a.override}")
    made = approve.takes_under(shot_dir, fp)
    if made >= 1 + s.retry_cap:
        print(f"{a.shot} already has {made} takes for this approval (cap {1 + s.retry_cap}); raise retry_cap in short.toml",
              file=sys.stderr)
        return 1
    seconds = int(round(a.seconds or shot.duration))  # fal bills whole seconds
    cost = estimate(a.model, seconds)
    print(f"{a.model} {seconds}s ≈ ${cost:.2f}; spent ${Ledger(work / 'costs.json').total():.2f} of ${s.budget_usd:.0f}")
    try:
        if not a.yes and input("submit? [y/N] ").strip().lower() != "y":
            return 1
    except EOFError:
        print("no answer on stdin; pass --yes to submit non-interactively", file=sys.stderr)
        return 1
    try:
        with httpx.Client() as client:
            tid = fal.run_take(work, a.shot, a.model, prompt, refs, seconds, s.budget_usd, key=fal.load_key(), client=client,
                               meta={"fp": fp}, note=f"override: {a.override}" if a.override else "")
    except (ValueError, BudgetError, RuntimeError) as e:
        print(e, file=sys.stderr)
        return 1
    print(shot_dir / "takes" / f"{tid}.mp4")
    return 0
```

In `main`, add to the submit parser: `q.add_argument("--override", default="")`.

Change `cmd_verdicts` to:

```python
def cmd_verdicts(a) -> int:
    with urllib.request.urlopen(PICKS_API, timeout=10) as r:
        api = json.load(r)
    print(f"{len(apply_verdicts(_work(a.slug), a.slug, api))} take verdict(s), "
          f"{len(approve.apply_approvals(_work(a.slug), a.slug, api))} plan verdict(s)")
    return 0
```

- [ ] **Step 6: Update existing CLI tests so the gate is satisfied, add gate tests**

`SHOT` stays the old unplanned shot and `PLANNED` (Task 1) is the complete one. Leave both in `tests/test_shorts_model.py` as they are.

In `tests/test_shorts_cli.py` change `setup` to approve by default:

```python
def setup(tmp_path, monkeypatch, shot=PLANNED, approved=True):
    ...existing body unchanged...
    if approved:
        monkeypatch.setattr("tools.shorts.approve.approval", lambda *a: {"verdict": "keep"})
```

and change the first import line to `from test_shorts_model import PLANNED, SHORT, SHOT`. Tests that pass `shot=SHOT.replace(...)` (e.g. `test_check_fails_on_problems`) keep using the old shot on purpose; `check` must still work on it.

Add gate tests:

```python
def test_submit_refuses_unapproved_and_stale(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(k) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert "not approved" in capsys.readouterr().err and called == []
    work = tmp_path / "design-data" / "shorts" / "pilot"
    work.mkdir(parents=True, exist_ok=True)
    (work / "approvals.json").write_text('{"S01": {"0000000000": {"verdict": "keep"}}}')  # an old fingerprint
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1 and called == []


def test_submit_override_is_logged(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    got = {}
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: got.update(k) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes", "--override", "owner said go"]) == 0
    assert got["note"] == "override: owner said go" and len(got["meta"]["fp"]) == 10


def test_submit_blocked_by_preflight_spends_nothing(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, shot=SHOT)  # the unplanned shot fails pre-flight
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(1))
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert "pre-flight failed" in capsys.readouterr().err and called == []


def test_submit_retry_cap(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    monkeypatch.setattr("tools.shorts.approve.takes_under", lambda *a: 3)
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: "t004")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert "cap 3" in capsys.readouterr().err
```

Existing submit tests that used `--model seedance-2.5` or `kling-3` keep working (approval is faked in `setup`). The existing submit tests now run on `PLANNED` (it passes pre-flight; seedance-2.5 and kling-3 fit their image limits with the test refs). `test_submit_kling_drops_video_refs_and_says_so` reads `a[4]` for refs — `run_take`'s positional order is unchanged, so it still holds.

- [ ] **Step 7: Run tests**

Run: `../../../.venv/bin/python -m pytest tests/test_shorts_approve.py tests/test_shorts_cli.py tests/test_shorts_takes.py tests/test_shorts_fal.py tests/test_shorts_model.py tests/test_shorts_preflight.py -q` → PASS; full suite → PASS.

- [ ] **Step 8: Commit**

```bash
git add tools/shorts/approve.py tools/shorts/takes.py tools/shorts/backends/fal.py tools/shorts/__main__.py tests/
git commit -m "shorts: per-shot approval fingerprint and money gate on submit (preflight, approval, retry cap, logged override)"
```

---

### Task 4: The production sheet page

**Files:**
- Create: `tools/shorts/sheet.py`, `tools/shorts/sheet.html`
- Modify: `tools/shorts/__main__.py` (`sheet` command)
- Test: `tests/test_shorts_sheet.py`

**Interfaces:**
- Consumes: `_preflight` (Task 2), `approve.fingerprint`, `approve.plan_image_id` (Task 3), `fal.usable_refs`, `estimate`.
- Produces: `sheet.collect(short, designs, design_dir, work, model, plans) -> dict` where `plans = {shot_id: (Report, prompt, refs)}`; `sheet.build(data: dict, design_dir: Path, work: Path, site: Path) -> Path` writing `site/<slug>/sheet/index.html` + `sheet.json` + media.

- [ ] **Step 1: Write the failing test** — `tests/test_shorts_sheet.py`

```python
import json

from test_shorts_model import SHORT, SHOT, designs, write
from tools.shorts import sheet
from tools.shorts.model import load_short
from tools.shorts.preflight import Report


def test_collect_and_build(tmp_path):
    s = load_short(write(tmp_path / "script", short=SHORT.replace('budget_usd = 25.0', 'budget_usd = 25.0\nline_rule = "C1 screen-right"')))
    dd = tmp_path / "design-data"
    for slug in ("saeko-kirigaya", "rin-kageyama"):
        (dd / slug).mkdir(parents=True)
        from PIL import Image
        Image.new("RGB", (64, 64)).save(dd / slug / "turnaround.png")
    (dd / "mama-satos-izakaya").mkdir()
    from PIL import Image
    Image.new("RGB", (64, 64)).save(dd / "mama-satos-izakaya" / "play.png")
    work = dd / "shorts" / s.slug
    (work / "shots" / "S01").mkdir(parents=True)
    (work / "shots" / "S01" / "greybox.mp4").write_bytes(b"g")
    ref = dd / "saeko-kirigaya" / "turnaround.png"
    plans = {"S01": (Report(problems=["missing size"], warnings=["w"]), "PROMPT TEXT", [("C1_turnaround.png", ref)])}
    data = sheet.collect(s, designs(), dd, work, "seedance-2.0-fast", plans)
    row = data["shots"][0]
    assert row["id"] == "S01" and row["problems"] == ["missing size"] and row["prompt"] == "PROMPT TEXT"
    assert row["image_id"].startswith(f"plan--{s.slug}--s01--") and row["cost"] > 0
    assert data["line_rule"] == "C1 screen-right" and data["lines"][0]["who"] == "C2"
    site = sheet.build(data, dd, work, tmp_path / "site")
    assert (site / "index.html").exists() and json.loads((site / "sheet.json").read_text())["slug"] == s.slug
    assert (site / "cast" / "saeko-kirigaya-turnaround.jpg").exists()
    html = (site / "index.html").read_text()
    assert "/designs/api/images/" in html and "alert(" not in html
```

- [ ] **Step 2: Run to verify it fails**

Run: `../../../.venv/bin/python -m pytest tests/test_shorts_sheet.py -q` → FAIL (`ImportError`).

- [ ] **Step 3: Implement `tools/shorts/sheet.py`**

```python
"""The production sheet: one page per short with everything a shot needs before money is spent, and the owner's
Approve / Change / Reject per shot (stored through the existing /designs/api/images review API)."""

import json
import re
import shutil
from pathlib import Path

from PIL import Image

from tools.shorts import approve
from tools.shorts.backends import fal
from tools.shorts.prompt import CHARACTER_SHEETS
from tools.shorts.takes import estimate

HTML = Path(__file__).with_name("sheet.html")
THUMB = 1024


def collect(short, designs, design_dir: Path, work: Path, model: str, plans: dict) -> dict:
    shots = []
    for shot in short.shots:
        report, prompt, refs = plans[shot.id]
        used, left_out = fal.usable_refs(model, refs)
        fp = approve.fingerprint(model, prompt, used)
        shots.append({
            "id": shot.id, "time": f"{shot.duration:g} s ({shot.start:g}–{shot.end:g} s)", "summary": shot.summary,
            "size": shot.size, "angle": shot.angle, "lens": shot.lens, "move": shot.move, "action": shot.action,
            "frame": shot.frame, "at_start": shot.at_start, "at_end": shot.at_end, "props": shot.props,
            "lines": [{"who": ln.who, "t": round(ln.t - shot.start, 2), "text": ln.text} for ln in shot.lines],
            "refs": [label for label, _ in used], "left_out": left_out, "cost": estimate(model, int(round(shot.duration))),
            "problems": report.problems, "warnings": report.warnings, "prompt": prompt, "fp": fp,
            "image_id": approve.plan_image_id(short.slug, shot.id, fp), "prefix": f"plan--{short.slug}--{shot.id.lower()}--",
            "still": (work / "shots" / shot.id / "still.png").exists(),
            "greybox": (work / "shots" / shot.id / "greybox.mp4").exists(),
        })
    continuity = [{"from": a["id"], "to": b["id"], "end": a["at_end"], "start": b["at_start"],
                   "flags": [p for p in b["problems"] if "props change" in p or "screen side" in p]}
                  for a, b in zip(shots, shots[1:])]
    cast = [{"id": cid, "slug": slug, "name": designs[slug].name, "lock": ", ".join(
        [*designs[slug].required, *([short.locks[cid]] if cid in short.locks else [])]),
             "sheets": [f.removesuffix(".png") for f in CHARACTER_SHEETS if (design_dir / slug / f).exists()]}
            for cid, slug in short.cast.items()]
    return {"slug": short.slug, "title": short.title, "logline": short.logline, "model": model,
            "runtime": round(sum(s.duration for s in short.shots), 1), "budget": short.budget_usd,
            "spent": round(sum(r["cost"] for r in json.loads((work / "costs.json").read_text())), 2)
            if (work / "costs.json").exists() else 0.0,
            "line_rule": short.line_rule, "style": short.style, "place": short.place,
            "beats": [{"text": b, "shot": (re.findall(r"\((S\d+)\)", b) or [""])[0]} for b in short.beats],
            "cast": cast, "shots": shots, "continuity": continuity,
            "lines": sorted(({"who": ln.who, "t": ln.t, "text": ln.text, "shot": sh.id} for sh in short.shots for ln in sh.lines),
                            key=lambda x: x["t"])}


def _thumb(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail((THUMB, THUMB))
    im.save(dst, "JPEG", quality=85)


def build(data: dict, design_dir: Path, work: Path, site_root: Path) -> Path:
    site = site_root / data["slug"] / "sheet"
    site.mkdir(parents=True, exist_ok=True)
    for c in data["cast"]:
        for name in c["sheets"]:
            _thumb(design_dir / c["slug"] / f"{name}.png", site / "cast" / f"{c['slug']}-{name}.jpg")
    if (design_dir / data["place"] / "play.png").exists():
        _thumb(design_dir / data["place"] / "play.png", site / "place.jpg")
    if (work / "floorplan.png").exists():
        _thumb(work / "floorplan.png", site / "floorplan.jpg")
    for s in data["shots"]:
        sd = work / "shots" / s["id"]
        if s["still"]:
            _thumb(sd / "still.png", site / "shots" / f"{s['id']}-still.jpg")
        if s["greybox"]:
            (site / "shots").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sd / "greybox.mp4", site / "shots" / f"{s['id']}-greybox.mp4")
    (site / "sheet.json").write_text(json.dumps(data, indent=1))
    shutil.copyfile(HTML, site / "index.html")
    return site
```

- [ ] **Step 4: Implement `tools/shorts/sheet.html`**

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Production sheet</title>
<style>
:root{--bg:#0d0f14;--card:#171a22;--fg:#e8e8ee;--dim:#9aa0ad;--ok:#3fb37f;--bad:#d9534f;--warn:#e0a030;--line:#2a2f3b}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;padding:16px}
h1{font-size:22px;margin:0 0 4px} h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.dim{color:var(--dim);font-size:13px} .card{background:var(--card);border-radius:10px;padding:12px;margin:8px 0}
.row{display:flex;gap:12px;flex-wrap:wrap} img,video{max-width:min(420px,100%);border-radius:6px;display:block}
.cast img{max-width:200px} table{border-collapse:collapse;width:100%} td{vertical-align:top;padding:3px 8px 3px 0}
td:first-child{color:var(--dim);white-space:nowrap;width:110px}
.ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)}
button{border:0;border-radius:6px;padding:7px 12px;margin:6px 6px 0 0;cursor:pointer;color:#fff}
.b-keep{background:var(--ok)} .b-fix{background:var(--warn)} .b-reject{background:var(--bad)}
textarea{width:100%;background:#0b0d12;color:var(--fg);border:1px solid #333;border-radius:6px}
pre{white-space:pre-wrap;background:#0b0d12;padding:8px;border-radius:6px;font-size:12px}
.status{font-weight:600} .tl{position:relative;height:auto} .tl div{padding:2px 0;font-size:14px}
</style></head><body>
<div id="app">Loading…</div>
<script>
const API = "/designs/api/images/";
function el(tag, attrs = {}, ...kids) { const e = document.createElement(tag); Object.assign(e, attrs); kids.forEach(k => e.append(k)); return e; }
function kv(obj) { return Object.entries(obj || {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"; }
async function setVerdict(id, verdict, note, err) {
  err.textContent = "";
  try {
    const r = await fetch(API + encodeURIComponent(id), {method: "PUT", headers: {"Content-Type": "application/json"},
                          body: JSON.stringify(note ? {verdict, note} : {verdict})});
    if (!r.ok) { err.textContent = "Saving failed (" + r.status + ")"; return; }
  } catch (e) { err.textContent = "Saving failed: " + e; return; }
  load();
}
function status(shot, verdicts) {
  const now = verdicts[shot.image_id];
  if (now) return {keep: ["Approved", "ok"], fix: ["Change requested: " + (now.note || ""), "warn"], reject: ["Rejected", "bad"]}[now.verdict] || ["Not reviewed", "dim"];
  const old = Object.keys(verdicts).some(k => k.startsWith(shot.prefix) && verdicts[k].verdict === "keep");
  return old ? ["Changed since approval: please review again", "warn"] : ["Not reviewed yet", "dim"];
}
async function load() {
  const [d, vr] = await Promise.all([fetch("sheet.json", {cache: "no-store"}).then(r => r.json()),
                                     fetch("/designs/api/images", {cache: "no-store"}).catch(() => null)]);
  const verdicts = vr && vr.ok ? await vr.json() : {};
  const app = document.getElementById("app"); app.textContent = "";
  app.append(el("h1", {textContent: `Production sheet: ${d.title}`}),
    el("div", {className: "dim", textContent: `${d.logline} · ${d.runtime} s · model ${d.model} · ` +
      `estimate $${d.shots.reduce((a, s) => a + s.cost, 0).toFixed(2)} · spent $${d.spent.toFixed(2)} of $${d.budget}`}));
  if (!(vr && vr.ok)) app.append(el("div", {className: "bad", textContent: "Could not load saved approvals; buttons still work."}));
  app.append(el("div", {className: "card"}, el("b", {textContent: "How this works: "}),
    "Read each shot. Approve it if it is what you want, or write what to change and press Change. Nothing is paid for until a shot is approved, " +
    "and if Claude edits a shot after you approve it, it shows as changed and needs your approval again."));
  app.append(el("h2", {textContent: "1. Cast lock: who must always look like this"}));
  for (const c of d.cast) app.append(el("div", {className: "card"}, el("b", {textContent: `${c.id} = ${c.name}`}),
    el("div", {className: "dim", textContent: "Never changes: " + c.lock}),
    el("div", {className: "row cast"}, ...c.sheets.map(n => el("img", {src: `cast/${c.slug}-${n}.jpg`, alt: n, title: n})))));
  app.append(el("h2", {textContent: "2. Location and look"}),
    el("div", {className: "row"}, el("img", {src: "place.jpg", alt: "place"}), el("img", {src: "floorplan.jpg", alt: "floor plan"})),
    el("div", {className: "card"}, el("div", {textContent: "Screen direction: " + (d.line_rule || "—")}),
       el("div", {className: "dim", textContent: "Style sent on every shot: " + d.style})));
  app.append(el("h2", {textContent: "3. Story beats"}),
    el("ol", {}, ...d.beats.map(b => el("li", {textContent: b.text}))));
  app.append(el("h2", {textContent: "4. Shot list"}));
  for (const s of d.shots) {
    const [label, cls] = status(s, verdicts);
    const note = el("textarea", {rows: 2, placeholder: "what to change, e.g. closer on Rin, Saeko's hand must stay on the cup"});
    const err = el("div", {className: "bad"});
    const pics = el("div", {className: "row"});
    if (s.still) pics.append(el("img", {src: `shots/${s.id}-still.jpg`, alt: "opening frame"}));
    if (s.greybox) pics.append(el("video", {src: `shots/${s.id}-greybox.mp4`, controls: true, loop: true, muted: true}));
    app.append(el("div", {className: "card"},
      el("div", {}, el("b", {textContent: `${s.id} · ${s.time} · `}), el("span", {className: `status ${cls}`, textContent: label})),
      pics,
      el("table", {}, ...[["Shot", `${s.size} · ${s.angle} · ${s.lens} mm · ${s.move}`], ["Action", s.action], ["In frame", kv(s.frame)],
        ["Opens on", kv(s.at_start)], ["Cuts on", kv(s.at_end)], ["Holding", kv(s.props)],
        ["Dialogue", s.lines.map(l => `${l.t}s ${l.who}: "${l.text}"`).join("  ") || "none"],
        ["References", s.refs.join(", ") + (s.left_out.length ? ` (left out: ${s.left_out.join(", ")})` : "")],
        ["Cost", `about $${s.cost.toFixed(2)}`],
        ["Checks", s.problems.length ? "" : "all passed"]].map(([k, v]) => el("tr", {}, el("td", {textContent: k}), el("td", {textContent: v})))),
      ...s.problems.map(p => el("div", {className: "bad", textContent: "✗ " + p})),
      ...s.warnings.map(w => el("div", {className: "warn", textContent: "! " + w})),
      el("details", {}, el("summary", {className: "dim", textContent: "Exact prompt that will be paid for"}), el("pre", {textContent: s.prompt})),
      el("button", {className: "b-keep", textContent: "Approve", disabled: s.problems.length > 0,
                    title: s.problems.length ? "Fix the failed checks first" : "", onclick: () => setVerdict(s.image_id, "keep", "", err)}),
      note,
      el("button", {className: "b-fix", textContent: "Change", onclick: () => setVerdict(s.image_id, "fix", note.value, err)}),
      el("button", {className: "b-reject", textContent: "Reject", onclick: () => setVerdict(s.image_id, "reject", "", err)}), err));
  }
  app.append(el("h2", {textContent: "5. Dialogue timeline (whole short)"}),
    el("div", {className: "card tl"}, ...d.lines.map(l => el("div", {textContent: `${l.t.toFixed(1)} s · ${l.shot} · ${l.who}: "${l.text}"`}))));
  app.append(el("h2", {textContent: "6. Continuity: how each shot hands over to the next"}));
  for (const c of d.continuity) app.append(el("div", {className: "card"},
    el("b", {textContent: `${c.from} → ${c.to}`}),
    el("div", {className: "dim", textContent: `${c.from} cuts on: ${kv(c.end)}`}),
    el("div", {className: "dim", textContent: `${c.to} opens on: ${kv(c.start)}`}),
    ...(c.flags.length ? c.flags.map(f => el("div", {className: "bad", textContent: "✗ " + f})) : [el("div", {className: "ok", textContent: "matches"})])));
}
load();
</script></body></html>
```

- [ ] **Step 5: Add the `sheet` command** in `tools/shorts/__main__.py`

```python
def cmd_sheet(a) -> int:
    from tools.shorts import sheet
    s, designs = _short(a.slug), load_designs()
    model = a.model or s.model
    if not model:
        raise CliError("no model: pass --model or set model in short.toml")
    plans = {shot.id: _preflight(s, shot, model, designs) for shot in s.shots}
    data = sheet.collect(s, designs, data_dir().parent, _work(a.slug), model, plans)
    site = sheet.build(data, data_dir().parent, _work(a.slug), data_dir() / "_site")
    print(site)
    print(f"rsync -a {data_dir() / '_site'}/ 192.168.10.19:anvil-deploy/stack/dashboard/shorts/")
    return 0
```

Register: `q = sub.add_parser("sheet"); q.add_argument("slug"); q.add_argument("--model")`.

Note: the fingerprint in `collect` is computed over `usable_refs(model, refs)` — the same list `submit` fingerprints — so an approval from the sheet matches `submit`. Add a CLI test proving that:

```python
def test_sheet_fingerprint_matches_submit(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    assert main(["sheet", "pilot", "--model", "seedance-2.0-fast"]) == 0
    data = json.loads((tmp_path / "design-data" / "shorts" / "_site" / "pilot" / "sheet" / "sheet.json").read_text())
    fp = data["shots"][0]["fp"]
    work = tmp_path / "design-data" / "shorts" / "pilot"
    (work / "approvals.json").write_text(json.dumps({"S01": {fp: {"verdict": "keep"}}}))
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 0
```

(add `import json` at the top of `tests/test_shorts_cli.py` if missing).

- [ ] **Step 6: Run tests** — `tests/test_shorts_sheet.py tests/test_shorts_cli.py` → PASS; full suite → PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/shorts/sheet.py tools/shorts/sheet.html tools/shorts/__main__.py tests/test_shorts_sheet.py tests/test_shorts_cli.py
git commit -m "shorts: production sheet page with per-shot approve/change/reject"
```

---

### Task 5: Storyboard stills

**Files:**
- Create: `tools/shorts/stills.py`
- Modify: `tools/shorts/prompt.py` (`has_still`, `ref_files` swap), `tools/shorts/__main__.py` (`stills` command; pass `has_still` everywhere `build_prompt` is called)
- Test: `tests/test_shorts_stills.py`, `tests/test_shorts_prompt.py`

**Interfaces:**
- Consumes: `tools.design_scenes.pair_workflow(a, b, location, seed)`, `_region_tags(d)`, `tools.image_studio._subject(d)`, `tools.imagegen.build(prompt, kind, day, negative, size, seed, subject=...)`, `narrator.comfyui_backend.ComfyUIBackend.run_workflow(wf) -> bytes`, `tools.design_studio._gpu_etiquette(url, before=bool)`, `tools.design_scenes.gpu_busy(url)`.
- Produces: `stills.SIZE_WORDS: dict[str, str]`; `stills.in_frame_order(shot) -> list[str]` (cast ids, screen-left first); `stills.still_workflow(short, shot, designs, seed) -> dict`; `build_prompt(short, shot, designs, has_still: bool = False)`; `ref_files` returns `("start_frame.png", shot_dir/"still.png")` instead of `place.png` when the still exists.

- [ ] **Step 1: Write the failing tests**

`tests/test_shorts_stills.py`:

```python
from test_shorts_model import PLANNED, write
from tools.shorts import stills
from tools.shorts.model import load_short


def test_in_frame_order_puts_screen_left_first(tmp_path):
    shot = load_short(write(tmp_path, shot=PLANNED)).shots[0]  # C2 screen-left, C1 screen-right
    assert stills.in_frame_order(shot) == ["C2", "C1"]


def test_still_workflow_has_shot_words_and_both_characters(tmp_path, monkeypatch):
    s = load_short(write(tmp_path, shot=PLANNED))
    from narrator.designs import Design
    d = {"saeko-kirigaya": Design(name="Saeko", kind="character", source="t", tags="black hair", status="approved", required=["blunt bangs"]),
         "rin-kageyama": Design(name="Rin", kind="character", source="t", tags="pink hair tips", status="approved"),
         "mama-satos-izakaya": Design(name="Izakaya", kind="location", source="t", tags="izakaya counter", status="approved")}
    wf = stills.still_workflow(s, s.shots[0], d, 703)
    text = " ".join(str(n["inputs"].get("text", "")) for n in wf.values() if isinstance(n, dict) and "inputs" in n)
    assert "upper body" in text and "blunt bangs" in text and "pink hair tips" in text and "izakaya counter" in text
    assert "night" in text.lower()
```

Add to `tests/test_shorts_prompt.py`:

```python
def test_still_replaces_place_and_l1_says_so(tmp_path):
    from test_shorts_model import designs, write
    from tools.shorts.model import load_short
    from tools.shorts.prompt import build_prompt, ref_files
    s = load_short(write(tmp_path / "script"))
    dd = tmp_path / "dd"
    (dd / "mama-satos-izakaya").mkdir(parents=True)
    (dd / "mama-satos-izakaya" / "play.png").write_bytes(b"p")
    shot_dir = dd / "shorts" / s.slug / "shots" / "S01"
    shot_dir.mkdir(parents=True)
    assert "place.png" in [l for l, _ in ref_files(s, dd, shot_dir)]
    (shot_dir / "still.png").write_bytes(b"s")
    labels = [l for l, _ in ref_files(s, dd, shot_dir)]
    assert "start_frame.png" in labels and "place.png" not in labels
    assert "start_frame.png" in build_prompt(s, s.shots[0], designs(), has_still=True)
    assert "start_frame.png" not in build_prompt(s, s.shots[0], designs())
```

- [ ] **Step 2: Run to verify they fail** — `tests/test_shorts_stills.py tests/test_shorts_prompt.py` → FAIL.

Before writing `still_workflow`, read `tools/imagegen.py`'s `build` signature (`grep -n "^def build" -A 12 tools/imagegen.py`) and `tools/design_scenes.py` (`pair_workflow`, `_region_tags`); use them exactly as `design_scenes.py` does.

- [ ] **Step 3: Implement `prompt.py` changes**

`layers(short, shot, designs, has_still: bool = False)`: append to `l1` when `has_still`:
`" start_frame.png is the approved opening frame: match its composition, characters and light at 0 s."`
`build_prompt(short, shot, designs, has_still: bool = False)` passes it through.
In `ref_files`, replace the `place.png` line with:

```python
    still = shot_dir / "still.png"
    out.append(("start_frame.png", still) if still.exists() else ("place.png", design_dir / short.place / "play.png"))
```

In `__main__.py`, every `build_prompt(s, shot, designs)` call (`cmd_prompt`, `cmd_bundle`, `_preflight`) passes
`has_still=(_work(s.slug) / "shots" / shot.id / "still.png").exists()`.

- [ ] **Step 4: Implement `tools/shorts/stills.py`**

```python
"""A free local opening-frame still per shot (the storyboard frame the owner approves with the shot).
Two characters use design_scenes' left/right area prompts so they don't blend; one character uses imagegen's
subject workflow. Night look only (the house style string already says night)."""

import asyncio
import re

from tools.design_scenes import _region_tags, pair_workflow
from tools.image_studio import _subject
from tools.imagegen import build

SIZE_WORDS = {"ECU": "extreme close-up, face focus", "CU": "close-up, portrait", "MCU": "upper body",
              "MS": "cowboy shot", "MWS": "cowboy shot, wide", "WS": "full body, wide shot", "EWS": "very wide shot, scenery"}
SIDE = re.compile(r"screen[- ]?(left|right)", re.IGNORECASE)


def in_frame_order(shot) -> list[str]:
    def key(cid):
        m = SIDE.search(shot.frame[cid])
        return {"left": 0, "right": 2}.get(m.group(1).lower(), 1) if m else 1
    return sorted(shot.frame, key=key)


def still_workflow(short, shot, designs, seed: int) -> dict:
    who = [short.cast[c] for c in in_frame_order(shot)]
    place = designs[short.place]
    words = f"{SIZE_WORDS.get(shot.size, '')}, {shot.angle}, night"
    if len(who) >= 2:
        wf = pair_workflow(designs[who[0]], designs[who[1]], place, seed)
    else:
        d = designs[who[0]]
        wf = build(f"{_region_tags(d)}, {place.tags}", "subject", False, d.negative or "", "base", seed, subject=_subject(d))
    wf["6"]["inputs"]["text"] = f"{words}, " + wf["6"]["inputs"]["text"]
    wf["9"]["inputs"]["filename_prefix"] = f"nightwire_shorts/{short.slug}-{shot.id}"
    return wf


async def render(jobs, backend) -> list[str]:
    """jobs: [(path, workflow)]. Returns error strings; one failure does not stop the rest."""
    errors = []
    for path, wf in jobs:
        try:
            path.write_bytes(await backend.run_workflow(wf))
            print(path, flush=True)
        except Exception as e:  # keep going: a long batch should not lose the other shots
            errors.append(f"{path.parent.name}: {e}")
    return errors


def run(jobs, url: str) -> list[str]:
    from narrator.comfyui_backend import ComfyUIBackend
    from tools.design_studio import _gpu_etiquette
    _gpu_etiquette(url, before=True)
    try:
        return asyncio.run(render(jobs, ComfyUIBackend(base_url=url, profile="noobai", timeout=600.0)))
    finally:
        _gpu_etiquette(url, before=False)
```

If `still_workflow`'s node ids differ from `"6"` (positive text) and `"9"` (save) in the workflow `build` returns, use the ids `design_scenes.pair_workflow` uses (it edits `wf["6"]` and `wf["9"]`, so they are the same workflow family).

- [ ] **Step 5: Add the `stills` command**

```python
def cmd_stills(a) -> int:
    from tools.design_scenes import gpu_busy
    from tools.shorts import stills
    s, designs, work = _short(a.slug), load_designs(), _work(a.slug)
    url = os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188")
    if gpu_busy(url):
        print("ComfyUI is busy; wait for the current job to finish.", file=sys.stderr)
        return 1
    jobs = []
    for shot in [_shot(s, a.shot)] if a.shot else s.shots:
        out = work / "shots" / shot.id / "still.png"
        if out.exists() and not a.redo:
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((out, stills.still_workflow(s, shot, designs, a.seed)))
    errors = stills.run(jobs, url)
    for e in errors:
        print(e, file=sys.stderr)
    return 1 if errors else 0
```

Register: `q = sub.add_parser("stills"); q.add_argument("slug"); q.add_argument("shot", nargs="?"); q.add_argument("--seed", type=int, default=703); q.add_argument("--redo", action="store_true")`.

- [ ] **Step 6: Run tests** — `tests/test_shorts_stills.py tests/test_shorts_prompt.py tests/test_shorts_cli.py` → PASS; full suite → PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/shorts/stills.py tools/shorts/prompt.py tools/shorts/__main__.py tests/test_shorts_stills.py tests/test_shorts_prompt.py
git commit -m "shorts: storyboard stills per shot; an approved still replaces place.png as start_frame.png"
```

---

### Task 6: Fill in the pilot, render stills, publish the sheet

**Files:**
- Modify: `narrator/worlds/shorts/saeko-rin-izakaya/short.toml`, `shots/S01.toml`, `S02.toml`, `S03.toml`
- Modify: `docs/shorts-guide.md`

This task is done by the controller (it needs the GPU box and the owner), not a subagent.

- [ ] **Step 1: Short fields.** In `short.toml`, after `budget_usd`:

```toml
model = "seedance-2.0-fast"
line_rule = "C1 (Saeko) is screen-right of C2 (Rin) in every shot from S01's two-shot on"
retry_cap = 2
```

and at the end of the file:

```toml
[locks]
C1 = "chrome right hand with an amber ring light on the wrist, red trim on the black outfit, long straight black hair"
C2 = "black undercut with pink tips, black lips, white hoodie, white-silver cyberdeck on a strap"
```

- [ ] **Step 2: Shot fields.** Add to each shot, after `lens` (top-level keys) and as tables at the end:

S01: `size = "WS"`, `angle = "low eye level from the far end of the counter"`, `move = "slow push-in"`, `action = "Rin comes in out of the rain and stops one stool from Saeko, who hides her locked hand."`; `[frame]` C1 = "midground screen-right, three-quarter profile", C2 = "ends foreground screen-left, turned toward C1"; `[at_start]` C1 = "seated, chrome right hand locked around a sake cup, left hand on the counter", C2 = "outside, behind the noren"; `[at_end]` C1 = "left hand covering the chrome hand on the cup, eyes on the counter", C2 = "standing one stool away, eyes on the covered hand"; `[props]` C1 = "sake cup locked in the chrome right hand", C2 = "cyberdeck on a strap across her chest".

S02: `size = "MCU"`, `angle = "eye level, over C1's shoulder from across the counter"`, `move = "static"`, `action = "Rin offers to unlock the hand and slides her cable toward it."`; `[frame]` C2 = "screen-left of centre, facing camera", C1 = "foreground screen-right, shoulder and back of head"; `[at_start]` C1 = "left hand covering the chrome hand on the cup", C2 = "seated across, hands near her cyberdeck"; `[at_end]` C1 = "still, shoulder only", C2 = "two fingers on the cable's data jack on the counter"; `[props]` C1 = "sake cup locked in the chrome right hand", C2 = "cyberdeck on a strap across her chest".

S03: `size = "MCU"`, `angle = "eye level, reverse over C2's shoulder"`, `move = "slow push-in"`, `action = "Saeko hears Rin's price, turns the data jack over and does not connect it."`; `[frame]` C1 = "screen-right of centre, three-quarter", C2 = "foreground screen-left, hood and shoulder"; `[at_start]` C1 = "eyes on C2, chrome hand on the cup", C2 = "two fingers on the data jack"; `[at_end]` C1 = "data jack turned over in her human left fingers, eyes on C2", C2 = "frozen"; `[props]` C1 = "sake cup locked in the chrome right hand; the data jack in her human left fingers", C2 = "cyberdeck on a strap across her chest"; `prop_change = ["C1"]` (she picks up the jack on purpose).

S01's `[frame]` must not use the word "screen-left/right" for C2's start (she enters from the back); the side describes the cut.

- [ ] **Step 3: Check and pre-flight**

Run: `NIGHTWIRE_DESIGN_DIR=... ../../../.venv/bin/python -m tools.shorts check saeko-rin-izakaya` → `ok`.
Run: `... -m tools.shorts preflight saeko-rin-izakaya` → each shot `ok` (warnings allowed). Fix shot text (not the checks) until every shot passes; reword any filter-word warning.

- [ ] **Step 4: Stills** — run `python -m tools.taste` first (owner's standing rule), confirm the GPU queue is empty, then `... -m tools.shorts stills saeko-rin-izakaya`. Look at each still at full size beside the turnaround (owner's review rule); `--redo` a shot with a different `--seed` if a character is off model. Free VRAM is handled by the command.

- [ ] **Step 5: Build and publish the sheet**

Run `... -m tools.shorts sheet saeko-rin-izakaya`, then `... -m tools.shorts page` and the printed `rsync -a --delete design-data/shorts/_site/ 192.168.10.19:anvil-deploy/stack/dashboard/shorts/`. Verify `curl -s -o /dev/null -w "%{http_code}" http://192.168.10.19:8080/shorts/saeko-rin-izakaya/sheet/` is `200`, and that a PUT of a plan id round-trips: `curl -s http://192.168.10.19:8080/designs/api/images | python3 -c "import json,sys; print([k for k in json.load(sys.stdin) if k.startswith('plan--')])"` after the owner presses a button.

- [ ] **Step 6: Guide** — add a "Plan → approve → shoot" section to `docs/shorts-guide.md`: fill the new fields, `preflight`, `stills`, `sheet` + publish, owner approves, `verdicts`, `submit --model seedance-2.0-fast` (refuses unapproved; `--override "<reason>"` is logged).

- [ ] **Step 7: Full suite + commit**

```bash
../../../.venv/bin/python -m pytest tests/ -q
git add narrator/worlds/shorts/saeko-rin-izakaya docs/shorts-guide.md
git commit -m "shorts: pilot planned with shot fields and locks; guide covers plan, approve, shoot"
```

- [ ] **Step 8: Hand to the owner** — send the sheet link. The re-shoot (`submit` each approved shot on `seedance-2.0-fast`, ~$5) runs only after the owner approves the shots and says go.
