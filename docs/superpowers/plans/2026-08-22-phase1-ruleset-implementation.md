# Phase 1 Ruleset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Nightwire's core ruleset as real, tested Python code — attributes, roles, lifepaths, difficulty bands, and the tiered d10 resolution mechanic. No engine, no narrator, no frontend — this is the "SRD" data and math the rest of the project will consume.

**Architecture:** A single top-level `ruleset` package, one module per concern (attributes, roles, lifepaths, difficulty, resolution). Plain dataclasses and enums — no ORM, no framework, nothing beyond the standard library, since this is pure data plus one pure function.

**Tech Stack:** Python 3.11+, pytest. No other dependencies.

**Spec:** `docs/superpowers/specs/2026-08-22-cyberpunk-ruleset-design.md`

## Global Constraints

- Six attributes: Body, Reflexes, Tech, Cool, Intellect, Presence (spec's Attributes section).
- Four roles: Solo (Reflexes), Netrunner (Tech), Techie (Tech), Fixer (Presence) (spec's Roles section, post rename).
- Three lifepaths: Corpo, Streetkid, Nomad — zero mechanical effect, flavor only (spec's Lifepath section).
- Difficulty bands: Easy=8, Moderate=12, Hard=16, Extreme=20 (spec's Core resolution mechanic section).
- Resolution: `1d10 + attribute_modifier + skill_modifier` vs DC. Natural 10 on the die is always at least a clean success regardless of total. Natural 1 is always a failure regardless of total. Otherwise: total ≥ DC+5 is a clean success, total ≥ DC (but < DC+5) is a success with a complication, total < DC is a failure (spec's Core resolution mechanic section).
- Attribute modifier formula: `(score - 10) // 2` (spec's Attributes section).

---

### Task 1: Project scaffold + Attributes module

**Files:**
- Create: `pyproject.toml`
- Create: `ruleset/__init__.py`
- Create: `ruleset/attributes.py`
- Test: `tests/test_attributes.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `ruleset.attributes.Attribute` (str Enum with members `BODY`, `REFLEXES`, `TECH`, `COOL`, `INTELLECT`, `PRESENCE`, values `"body"`, `"reflexes"`, `"tech"`, `"cool"`, `"intellect"`, `"presence"`); `ruleset.attributes.modifier(score: int) -> int`.

- [ ] **Step 1: Create the project scaffold**

Create `pyproject.toml`:

```toml
[project]
name = "nightwire"
version = "0.1.0"
requires-python = ">=3.11"

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `ruleset/__init__.py` (empty file).

- [ ] **Step 2: Install dev dependencies**

Run: `pip install -e ".[dev]"`
Expected: installs without error, `pytest` importable.

- [ ] **Step 3: Write the failing test**

Create `tests/test_attributes.py`:

```python
from ruleset.attributes import Attribute, modifier


def test_all_six_attributes_exist():
    assert {a.value for a in Attribute} == {
        "body", "reflexes", "tech", "cool", "intellect", "presence",
    }


def test_modifier_formula():
    assert modifier(10) == 0
    assert modifier(11) == 0
    assert modifier(12) == 1
    assert modifier(8) == -1
    assert modifier(20) == 5
    assert modifier(3) == -4
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_attributes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ruleset.attributes'`

- [ ] **Step 5: Write minimal implementation**

Create `ruleset/attributes.py`:

```python
from enum import Enum


class Attribute(str, Enum):
    BODY = "body"
    REFLEXES = "reflexes"
    TECH = "tech"
    COOL = "cool"
    INTELLECT = "intellect"
    PRESENCE = "presence"


def modifier(score: int) -> int:
    return (score - 10) // 2
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_attributes.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml ruleset/__init__.py ruleset/attributes.py tests/test_attributes.py
git commit -m "feat: attributes module - six attributes, modifier formula"
```

---

### Task 2: Roles module

**Files:**
- Create: `ruleset/roles.py`
- Test: `tests/test_roles.py`

**Interfaces:**
- Consumes: `ruleset.attributes.Attribute` (Task 1).
- Produces: `ruleset.roles.Role` (frozen dataclass: `name: str`, `primary_attribute: Attribute`, `description: str`); `ruleset.roles.ROLES: dict[str, Role]` keyed by lowercase role id (`"solo"`, `"netrunner"`, `"techie"`, `"fixer"`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_roles.py`:

```python
from ruleset.attributes import Attribute
from ruleset.roles import ROLES, Role


def test_four_roles_exist():
    assert set(ROLES.keys()) == {"solo", "netrunner", "techie", "fixer"}


def test_each_role_has_a_valid_primary_attribute():
    for role in ROLES.values():
        assert isinstance(role, Role)
        assert isinstance(role.primary_attribute, Attribute)


def test_solo_keys_off_reflexes():
    assert ROLES["solo"].primary_attribute == Attribute.REFLEXES


def test_netrunner_and_techie_both_key_off_tech():
    assert ROLES["netrunner"].primary_attribute == Attribute.TECH
    assert ROLES["techie"].primary_attribute == Attribute.TECH


def test_fixer_keys_off_presence():
    assert ROLES["fixer"].primary_attribute == Attribute.PRESENCE


def test_every_role_has_a_nonempty_description():
    for role in ROLES.values():
        assert role.description.strip() != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_roles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ruleset.roles'`

- [ ] **Step 3: Write minimal implementation**

Create `ruleset/roles.py`:

```python
from dataclasses import dataclass

from ruleset.attributes import Attribute


@dataclass(frozen=True)
class Role:
    name: str
    primary_attribute: Attribute
    description: str


ROLES: dict[str, Role] = {
    "solo": Role(
        name="Solo",
        primary_attribute=Attribute.REFLEXES,
        description=(
            "Front-line combat specialist. Best attack rolls, highest "
            "Health, a passive Initiative/Awareness edge."
        ),
    ),
    "netrunner": Role(
        name="Netrunner",
        primary_attribute=Attribute.TECH,
        description=(
            "Hacking specialist. Bypasses locks, pulls data, and disables "
            "weapons/cameras/drones mid-combat."
        ),
    ),
    "techie": Role(
        name="Techie",
        primary_attribute=Attribute.TECH,
        description=(
            "Gear specialist. Repairs damaged equipment and cyberware, "
            "installs upgrades, crafts - keeps the party's equipment "
            "working, not a healer."
        ),
    ),
    "fixer": Role(
        name="Fixer",
        primary_attribute=Attribute.PRESENCE,
        description=(
            "Social specialist. Negotiation, contacts, contraband access - "
            "talks past trouble instead of shooting through it."
        ),
    ),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_roles.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add ruleset/roles.py tests/test_roles.py
git commit -m "feat: roles module - Solo/Netrunner/Techie/Fixer"
```

---

### Task 3: Lifepaths module

**Files:**
- Create: `ruleset/lifepaths.py`
- Test: `tests/test_lifepaths.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ruleset.lifepaths.Lifepath` (frozen dataclass: `name: str`, `description: str`); `ruleset.lifepaths.LIFEPATHS: dict[str, Lifepath]` keyed by lowercase id (`"corpo"`, `"streetkid"`, `"nomad"`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_lifepaths.py`:

```python
from ruleset.lifepaths import LIFEPATHS, Lifepath


def test_three_lifepaths_exist():
    assert set(LIFEPATHS.keys()) == {"corpo", "streetkid", "nomad"}


def test_every_lifepath_has_a_nonempty_description():
    for lifepath in LIFEPATHS.values():
        assert isinstance(lifepath, Lifepath)
        assert lifepath.description.strip() != ""


def test_lifepath_has_no_mechanical_fields():
    # Zero mechanical weight per spec - a Lifepath is name + description
    # only, nothing a rules engine would read as a stat bonus.
    fields = {f.name for f in Lifepath.__dataclass_fields__.values()}
    assert fields == {"name", "description"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_lifepaths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ruleset.lifepaths'`

- [ ] **Step 3: Write minimal implementation**

Create `ruleset/lifepaths.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Lifepath:
    name: str
    description: str


LIFEPATHS: dict[str, Lifepath] = {
    "corpo": Lifepath(
        name="Corpo",
        description=(
            "Came from megacorp life - contacts inside corporate "
            "structures, insider knowledge, expects to be listened to."
        ),
    ),
    "streetkid": Lifepath(
        name="Streetkid",
        description=(
            "Grew up in the sprawl - gang contacts, street cred, knows "
            "how things really work at ground level."
        ),
    ),
    "nomad": Lifepath(
        name="Nomad",
        description=(
            "Raised outside the city in a clan/family - vehicle know-how, "
            "an outsider's read on the corps, strong found-family loyalty."
        ),
    ),
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_lifepaths.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ruleset/lifepaths.py tests/test_lifepaths.py
git commit -m "feat: lifepaths module - Corpo/Streetkid/Nomad"
```

---

### Task 4: Difficulty bands

**Files:**
- Create: `ruleset/difficulty.py`
- Test: `tests/test_difficulty.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ruleset.difficulty.Difficulty` (IntEnum with members `EASY=8`, `MODERATE=12`, `HARD=16`, `EXTREME=20`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_difficulty.py`:

```python
from ruleset.difficulty import Difficulty


def test_difficulty_bands_match_spec_values():
    assert Difficulty.EASY == 8
    assert Difficulty.MODERATE == 12
    assert Difficulty.HARD == 16
    assert Difficulty.EXTREME == 20


def test_difficulty_is_usable_as_a_plain_int():
    # DCs get added/compared against roll totals elsewhere - must behave
    # as a real int, not just a named constant.
    assert Difficulty.MODERATE + 1 == 13
    assert Difficulty.HARD > Difficulty.EASY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_difficulty.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ruleset.difficulty'`

- [ ] **Step 3: Write minimal implementation**

Create `ruleset/difficulty.py`:

```python
from enum import IntEnum


class Difficulty(IntEnum):
    EASY = 8
    MODERATE = 12
    HARD = 16
    EXTREME = 20
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_difficulty.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ruleset/difficulty.py tests/test_difficulty.py
git commit -m "feat: difficulty bands - Easy/Moderate/Hard/Extreme"
```

---

### Task 5: Core resolution mechanic

**Files:**
- Create: `ruleset/resolution.py`
- Test: `tests/test_resolution.py`

**Interfaces:**
- Consumes: nothing directly (takes plain ints as arguments — attribute/skill modifiers are computed by the caller via `ruleset.attributes.modifier`, DC via `ruleset.difficulty.Difficulty`, but this module doesn't import either, keeping it a pure function over plain ints).
- Produces: `ruleset.resolution.Outcome` (str Enum: `CLEAN_SUCCESS = "clean_success"`, `COMPLICATION = "complication"`, `FAILURE = "failure"`); `ruleset.resolution.resolve_roll(die_result: int, attribute_mod: int, skill_mod: int, dc: int) -> Outcome`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_resolution.py`:

```python
from ruleset.resolution import Outcome, resolve_roll


def test_clean_success_when_total_beats_dc_by_5_or_more():
    # die=8, mods=+2 -> total 10, DC 5 -> beats by 5
    assert resolve_roll(die_result=8, attribute_mod=1, skill_mod=1, dc=5) == Outcome.CLEAN_SUCCESS


def test_complication_when_total_meets_dc_but_not_by_5():
    # die=5, mods=+2 -> total 7, DC 6 -> meets but doesn't beat by 5
    assert resolve_roll(die_result=5, attribute_mod=1, skill_mod=1, dc=6) == Outcome.COMPLICATION


def test_failure_when_total_is_below_dc():
    # die=3, mods=0 -> total 3, DC 10
    assert resolve_roll(die_result=3, attribute_mod=0, skill_mod=0, dc=10) == Outcome.FAILURE


def test_natural_10_is_always_at_least_clean_success():
    # die=10 but mods are so negative the raw total would fail against a
    # high DC - the natural 10 rule overrides the math entirely.
    assert resolve_roll(die_result=10, attribute_mod=-4, skill_mod=-4, dc=20) == Outcome.CLEAN_SUCCESS


def test_natural_1_is_always_failure():
    # die=1 but mods are so high the raw total would clear a low DC - the
    # natural 1 rule overrides the math entirely.
    assert resolve_roll(die_result=1, attribute_mod=5, skill_mod=5, dc=8) == Outcome.FAILURE


def test_boundary_exactly_at_dc_plus_5_is_clean_success():
    # die=5, mods=0, dc=0 -> total 5, exactly dc+5 -> clean success, not complication
    assert resolve_roll(die_result=5, attribute_mod=0, skill_mod=0, dc=0) == Outcome.CLEAN_SUCCESS


def test_boundary_one_below_dc_plus_5_is_complication_not_clean():
    assert resolve_roll(die_result=4, attribute_mod=0, skill_mod=0, dc=0) == Outcome.COMPLICATION
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resolution.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ruleset.resolution'`

- [ ] **Step 3: Write minimal implementation**

Create `ruleset/resolution.py`:

```python
from enum import Enum


class Outcome(str, Enum):
    CLEAN_SUCCESS = "clean_success"
    COMPLICATION = "complication"
    FAILURE = "failure"


def resolve_roll(die_result: int, attribute_mod: int, skill_mod: int, dc: int) -> Outcome:
    if die_result == 10:
        return Outcome.CLEAN_SUCCESS
    if die_result == 1:
        return Outcome.FAILURE

    total = die_result + attribute_mod + skill_mod
    if total >= dc + 5:
        return Outcome.CLEAN_SUCCESS
    if total >= dc:
        return Outcome.COMPLICATION
    return Outcome.FAILURE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_resolution.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add ruleset/resolution.py tests/test_resolution.py
git commit -m "feat: core resolution mechanic - tiered d10 with crit rules"
```

---

### Task 6: Full suite sanity check

**Files:**
- None created or modified — verification only.

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: nothing new.

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: PASS (20 passed: 2 attributes + 6 roles + 3 lifepaths + 2 difficulty + 7 resolution)

- [ ] **Step 2: Confirm no import errors across modules**

Run: `python -c "from ruleset.attributes import Attribute, modifier; from ruleset.roles import ROLES; from ruleset.lifepaths import LIFEPATHS; from ruleset.difficulty import Difficulty; from ruleset.resolution import Outcome, resolve_roll; print('all imports OK')"`
Expected: prints `all imports OK` with no errors

- [ ] **Step 3: Commit if anything was fixed during this check**

Only if Steps 1-2 required any fix:

```bash
git add -A
git commit -m "fix: resolve cross-module import issue found in full suite check"
```

If nothing needed fixing, skip this step - no empty commits.
