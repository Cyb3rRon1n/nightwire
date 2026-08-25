# Nightwire Skill System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give nightwire a real 14-skill layer — governing-attribute-gated ranks, a starting point budget spent at character creation, milestone-granted points spent later — replacing `RequestRoll.skill_mod`'s model-invented integer with a real lookup against character data.

**Architecture:** New `ruleset/skills.py` (skill roster + gating-cap formula, same shape as `ruleset/roles.py`/`ruleset/lifepaths.py`). `CharacterSheet` gains `skills`/`unspent_skill_points`. `narrator/tools.py`'s `RequestRoll` swaps its `skill_mod: int` field for a `skill: Literal[...]` the schema itself constrains, and `ApplyCharacterUpdate` gains an optional `skill_points_delta` for narrator-granted milestones. `server/dispatch.py` validates and applies both starting allocation (at `join`) and later spends (a new `allocate_skill_points` message) server-side — never trusting client-computed budget math, same convention `roll_initiative` already established. Frontend gets one new shared `SkillPicker` component used at both call sites (pre-join creation, post-join milestone spend via the `Ctrl+K` sheet).

**Tech Stack:** Python 3.12, pydantic, pytest/pytest-asyncio (backend — this plan's automated tests); TypeScript/React/Next.js (frontend — no test framework, live-verify only, per existing project convention).

**Spec:** `docs/superpowers/specs/2026-08-24-skill-system-design.md`

## Global Constraints

- Ranks run 0–5. Gating cap: `min(5, modifier(governing_attribute_score) + 3)`.
- Starting budget: a flat 8 points for every role (no role-weighted budgets).
- Spend-only — no respec/decrease mechanism anywhere in this pass.
- Every attribute currently reads as 10 (no point-buy exists yet — real, working first pass; the cap formula already accepts real scores the moment that gap closes, no rework needed here).
- Server is always the authority on budget/cap math — never trust a client-computed allocation over the wire.
- 14 skills, snake_case internal names: `melee`, `athletics`, `ranged_combat`, `stealth`, `piloting`, `hacking`, `engineering`, `demolitions`, `intimidation`, `streetwise`, `perception`, `deduction`, `persuasion`, `performance`.

---

## Task 1: `ruleset/skills.py` — skill roster and gating cap

**Files:**
- Create: `ruleset/skills.py`
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: `ruleset.attributes.Attribute` (enum), `ruleset.attributes.modifier`.
- Produces: `Skill` dataclass (`name: str`, `governing_attribute: Attribute`, `description: str`), `SKILLS: dict[str, Skill]` (14 entries, keyed by snake_case internal name), `STARTING_SKILL_POINTS: int`, `skill_cap(attribute_score: int) -> int`.

- [ ] **Step 1: failing test** — create `tests/test_skills.py`:

```python
from ruleset.attributes import Attribute
from ruleset.skills import SKILLS, STARTING_SKILL_POINTS, Skill, skill_cap


def test_fourteen_skills_exist():
    assert len(SKILLS) == 14


def test_each_skill_has_a_valid_governing_attribute():
    for skill in SKILLS.values():
        assert isinstance(skill, Skill)
        assert isinstance(skill.governing_attribute, Attribute)


def test_every_skill_has_a_nonempty_description():
    for skill in SKILLS.values():
        assert skill.description.strip() != ""


def test_skills_grouped_by_governing_attribute():
    by_attribute: dict[Attribute, set[str]] = {}
    for internal_name, skill in SKILLS.items():
        by_attribute.setdefault(skill.governing_attribute, set()).add(internal_name)

    assert by_attribute[Attribute.BODY] == {"melee", "athletics"}
    assert by_attribute[Attribute.REFLEXES] == {"ranged_combat", "stealth", "piloting"}
    assert by_attribute[Attribute.TECH] == {"hacking", "engineering", "demolitions"}
    assert by_attribute[Attribute.COOL] == {"intimidation", "streetwise"}
    assert by_attribute[Attribute.INTELLECT] == {"perception", "deduction"}
    assert by_attribute[Attribute.PRESENCE] == {"persuasion", "performance"}


def test_skill_cap_scales_with_attribute_modifier():
    assert skill_cap(10) == 3  # modifier(10) == 0 -> 0 + 3
    assert skill_cap(16) == 5  # modifier(16) == 3 -> 3 + 3, clamped to 5
    assert skill_cap(8) == 2   # modifier(8) == -1 -> -1 + 3


def test_skill_cap_never_exceeds_five():
    assert skill_cap(30) == 5


def test_starting_skill_points_is_eight():
    assert STARTING_SKILL_POINTS == 8
```

- [ ] **Step 2: verify fails** — `ruleset/skills.py` doesn't exist:

Run: `pytest tests/test_skills.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ruleset.skills'`

- [ ] **Step 3: implement** — create `ruleset/skills.py`:

```python
from dataclasses import dataclass

from ruleset.attributes import Attribute, modifier


@dataclass(frozen=True)
class Skill:
    name: str
    governing_attribute: Attribute
    description: str


STARTING_SKILL_POINTS = 8


SKILLS: dict[str, Skill] = {
    "melee": Skill(
        name="Melee",
        governing_attribute=Attribute.BODY,
        description="Close-quarters combat with blades, fists, or improvised weapons.",
    ),
    "athletics": Skill(
        name="Athletics",
        governing_attribute=Attribute.BODY,
        description="Running, climbing, jumping, and other raw physical feats.",
    ),
    "ranged_combat": Skill(
        name="Ranged Combat",
        governing_attribute=Attribute.REFLEXES,
        description="Firearms and thrown weapons at range.",
    ),
    "stealth": Skill(
        name="Stealth",
        governing_attribute=Attribute.REFLEXES,
        description="Moving unseen, staying quiet, avoiding detection.",
    ),
    "piloting": Skill(
        name="Piloting",
        governing_attribute=Attribute.REFLEXES,
        description="Driving or flying vehicles, high-speed maneuvers.",
    ),
    "hacking": Skill(
        name="Hacking",
        governing_attribute=Attribute.TECH,
        description="Breaching networks, bypassing security software, digital intrusion.",
    ),
    "engineering": Skill(
        name="Engineering",
        governing_attribute=Attribute.TECH,
        description="Building, repairing, and modifying gear and cyberware.",
    ),
    "demolitions": Skill(
        name="Demolitions",
        governing_attribute=Attribute.TECH,
        description="Explosives - rigging, defusing, controlled destruction.",
    ),
    "intimidation": Skill(
        name="Intimidation",
        governing_attribute=Attribute.COOL,
        description="Coercion through threat, presence, or reputation.",
    ),
    "streetwise": Skill(
        name="Streetwise",
        governing_attribute=Attribute.COOL,
        description="Reading the street - contacts, black markets, gang politics.",
    ),
    "perception": Skill(
        name="Perception",
        governing_attribute=Attribute.INTELLECT,
        description="Noticing details, spotting danger, reading a scene.",
    ),
    "deduction": Skill(
        name="Deduction",
        governing_attribute=Attribute.INTELLECT,
        description="Piecing together clues, drawing logical conclusions.",
    ),
    "persuasion": Skill(
        name="Persuasion",
        governing_attribute=Attribute.PRESENCE,
        description="Convincing others through charm, logic, or negotiation.",
    ),
    "performance": Skill(
        name="Performance",
        governing_attribute=Attribute.PRESENCE,
        description="Holding a crowd - music, acting, showmanship.",
    ),
}


def skill_cap(attribute_score: int) -> int:
    return min(5, modifier(attribute_score) + 3)
```

- [ ] **Step 4: verify passes**

Run: `pytest tests/test_skills.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: commit**

```bash
git add ruleset/skills.py tests/test_skills.py
git commit -m "feat: add ruleset/skills.py - skill roster and gating cap"
```

---

## Task 2: `CharacterSheet.skills`/`unspent_skill_points` and persistence

**Files:**
- Modify: `engine/character.py`
- Test: `tests/test_persistence.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CharacterSheet.skills: dict[str, int]` (default `{}`), `CharacterSheet.unspent_skill_points: int` (default `0`).

- [ ] **Step 1: failing test** — add to `tests/test_persistence.py`, inside `test_save_then_load_round_trips_a_session_with_a_character` (add to the existing character construction and assertions, don't duplicate the test):

```python
    session.characters["p1"] = CharacterSheet(
        player_id="p1",
        name="Rook",
        role="solo",
        lifepath="streetkid",
        attributes={"body": 14, "reflexes": 12},
        health=7,
        max_health=10,
        armor=2,
        conditions=["bleeding"],
        inventory=["stim pack"],
        portrait_path="sessions/portraits/test-session/p1.png",
        skills={"stealth": 3, "hacking": 2},
        unspent_skill_points=1,
    )
```

and add to that same test's assertions:

```python
    assert loaded_character.skills == {"stealth": 3, "hacking": 2}
    assert loaded_character.unspent_skill_points == 1
```

Also add a new test to the same file, verifying the dataclass default (not a persistence-layer `.get()` — `CharacterSheet(**character_data)` already tolerates missing keys via its own field defaults, so this test proves that rather than assuming it):

```python
def test_load_defaults_character_skills_when_missing_from_an_older_character_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    from dataclasses import asdict

    session_data = asdict(session)
    del session_data["characters"]["p1"]["skills"]
    del session_data["characters"]["p1"]["unspent_skill_points"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(session_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.characters["p1"].skills == {}
    assert loaded.characters["p1"].unspent_skill_points == 0
```

- [ ] **Step 2: verify fails**

Run: `pytest tests/test_persistence.py -v`
Expected: FAIL — `TypeError: CharacterSheet.__init__() got an unexpected keyword argument 'skills'`

- [ ] **Step 3: implement** — `engine/character.py`, add two fields after `portrait_path`:

```python
    portrait_path: str | None = None
    skills: dict[str, int] = field(default_factory=dict)
    unspent_skill_points: int = 0
```

- [ ] **Step 4: verify passes**

Run: `pytest tests/test_persistence.py -v`
Expected: PASS (including the new legacy-file test — no changes needed to `engine/persistence.py`, since `CharacterSheet(**character_data)` already falls back to field defaults for any key absent from an older saved file)

- [ ] **Step 5: commit**

```bash
git add engine/character.py tests/test_persistence.py
git commit -m "feat: add CharacterSheet.skills and unspent_skill_points"
```

---

## Task 3: Real skill lookup on `RequestRoll`

**Files:**
- Modify: `narrator/tools.py`
- Modify: `tests/test_narrator_tools.py`
- Modify: `tests/test_narrator_client.py`
- Modify: `tests/test_harness.py`
- Modify: `tests/test_narration.py`

**Interfaces:**
- Consumes: `ruleset.skills.SKILLS` (Task 1), `CharacterSheet.skills` (Task 2).
- Produces: `RequestRoll.skill: Literal[14 skill names]` (replaces `RequestRoll.skill_mod: int`). `_execute_request_roll`'s returned dict keeps the `"skill_mod"` key (now a real looked-up value, not a clamped one) — no downstream caller's key names change.

This task replaces a model-invented, clamped integer with a real lookup — every existing test that builds a `request_roll` `tool_args` dict with `"skill_mod": N` breaks by construction (the field no longer exists) and needs `"skill": "<a valid skill name>"` instead. This is one coherent change, not several independent ones — the whole suite must go green together.

- [ ] **Step 1: failing test** — replace `test_request_roll_clamps_skill_mod_to_a_plausible_range` in `tests/test_narrator_tools.py` with:

```python
def test_request_roll_looks_up_the_characters_real_skill_rank():
    session = _session_with_character(skills={"ranged_combat": 3})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill": "ranged_combat",
        "difficulty": "easy", "reason": "quickdraw",
    })
    assert result["skill_mod"] == 3


def test_request_roll_defaults_an_untrained_skill_to_zero():
    session = _session_with_character()
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "body", "skill": "melee",
        "difficulty": "easy", "reason": "x",
    })
    assert result["skill_mod"] == 0
```

- [ ] **Step 2: verify fails**

Run: `pytest tests/test_narrator_tools.py -v`
Expected: FAIL — `pydantic.ValidationError` (no `skill` field on `RequestRoll` yet, `skill_mod` still required and missing)

- [ ] **Step 3: implement.** `narrator/tools.py` — replace the `RequestRoll` model:

```python
class RequestRoll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    attribute: Literal["body", "reflexes", "tech", "cool", "intellect", "presence"]
    skill: Literal[
        "melee", "athletics", "ranged_combat", "stealth", "piloting",
        "hacking", "engineering", "demolitions", "intimidation", "streetwise",
        "perception", "deduction", "persuasion", "performance",
    ]
    difficulty: Literal["easy", "moderate", "hard", "extreme"]
    reason: str
```

and `_execute_request_roll`:

```python
def _execute_request_roll(session: Session, tool: RequestRoll) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    character = session.characters[tool.player_id]
    raw_score = character.attributes.get(tool.attribute, 10)
    attribute_mod = modifier(raw_score)
    skill_mod = character.skills.get(tool.skill, 0)
    die_result = random.randint(1, 10)
    dc = Difficulty[tool.difficulty.upper()].value
    outcome = resolve_roll(die_result, attribute_mod, skill_mod, dc)
    return {
        "die_result": die_result,
        "attribute_mod": attribute_mod,
        "skill_mod": skill_mod,
        "dc": dc,
        "outcome": outcome.value,
    }
```

Now fix every other `"skill_mod": N` reference so the full suite can go green:

In `tests/test_narrator_tools.py`, in `_session_with_character`, no change needed (it already accepts `**overrides`, and `skills={...}` passed as an override works since `CharacterSheet` has that field from Task 2). Update the remaining `skill_mod` references in that file:

```python
def test_request_roll_uses_the_characters_real_attribute_score():
    session = _session_with_character(attributes={"reflexes": 16})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill": "stealth", "difficulty": "easy", "reason": "dodge",
    })
    assert result["attribute_mod"] == 3  # modifier(16) == (16 - 10) // 2 == 3


def test_request_roll_rejects_an_unknown_player_id():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        execute_tool(session, "request_roll", {
            "player_id": "ghost", "attribute": "body", "skill": "melee", "difficulty": "easy", "reason": "x",
        })


def test_request_roll_rolls_a_real_die_and_resolves_the_outcome():
    session = _session_with_character(attributes={"reflexes": 14}, skills={"stealth": 2})
    result = execute_tool(session, "request_roll", {
        "player_id": "p1", "attribute": "reflexes", "skill": "stealth", "difficulty": "easy", "reason": "climbing a wall",
    })
    assert 1 <= result["die_result"] <= 10
    assert result["dc"] == 8
    assert result["outcome"] in ("clean_success", "complication", "failure")


def test_request_roll_rejects_an_unknown_difficulty():
    session = _session_with_character()
    with pytest.raises(ValueError):
        execute_tool(session, "request_roll", {
            "player_id": "p1", "attribute": "body", "skill": "melee", "difficulty": "impossible", "reason": "x",
        })
```

In `tests/test_narrator_client.py`, `test_respond_returns_a_tool_call` (around line 50-66): change

```python
                    "player_id": "p1", "attribute": "reflexes", "skill_mod": 1,
```

to

```python
                    "player_id": "p1", "attribute": "reflexes", "skill": "athletics",
```

The comment in `test_respond_rejects_a_tool_call_with_the_wrong_argument_shape` references the real field list — update its wording from `{player_id, attribute, skill_mod, difficulty, reason}` to `{player_id, attribute, skill, difficulty, reason}` (comment only, no assertion change - that test's own `tool_args` is already a completely different shape, `{"scene": ..., "enemies": [...]}`, so it's unaffected otherwise).

In `tests/test_harness.py`, two occurrences: in `test_run_harness_scores_a_correct_tool_call_as_a_pass`, change

```python
                "player_id": "p1", "attribute": "reflexes", "skill_mod": 2,
```

to

```python
                "player_id": "p1", "attribute": "reflexes", "skill": "ranged_combat",
```

and in `test_run_harness_fails_a_scenario_whose_tool_args_dont_validate`, change

```python
            "tool_args": {"player_id": "p1", "attribute": "body", "skill_mod": 1, "difficulty": "nightmarish", "reason": "leap"},
```

to

```python
            "tool_args": {"player_id": "p1", "attribute": "body", "skill": "athletics", "difficulty": "nightmarish", "reason": "leap"},
```

In `tests/test_narration.py`, two occurrences, both `tool_args={"player_id": "someone-else", "attribute": "reflexes", "skill_mod": 1, "difficulty": "easy", "reason": "leap"}` (in `test_handle_action_executes_a_tool_call_and_logs_the_result` and `test_handle_action_overrides_the_models_player_id_for_request_roll`) — change each to:

```python
        tool_args={
            "player_id": "someone-else", "attribute": "reflexes", "skill": "athletics",
            "difficulty": "easy", "reason": "leap",
        },
```

- [ ] **Step 4: verify passes**

Run: `pytest -v`
Expected: PASS, full suite (this task touches shared schema, so the whole suite must be checked, not just the modified files)

- [ ] **Step 5: commit**

```bash
git add narrator/tools.py tests/test_narrator_tools.py tests/test_narrator_client.py tests/test_harness.py tests/test_narration.py
git commit -m "feat: RequestRoll.skill looks up a real character skill rank

Replaces the model-invented, clamped skill_mod integer (a Phase 1
gap - no skill system existed yet) with a real Literal[14 skill
names] the schema itself constrains, looked up against
CharacterSheet.skills."
```

---

## Task 4: `ApplyCharacterUpdate.skill_points_delta`

**Files:**
- Modify: `narrator/tools.py`
- Modify: `tests/test_narrator_tools.py`

**Interfaces:**
- Consumes: `CharacterSheet.unspent_skill_points` (Task 2).
- Produces: `ApplyCharacterUpdate.skill_points_delta: int = 0`. `_execute_apply_character_update`'s returned dict gains an `"unspent_skill_points"` key.

- [ ] **Step 1: failing test** — add to `tests/test_narrator_tools.py`:

```python
def test_apply_character_update_grants_skill_points():
    session = _session_with_character()
    result = execute_tool(session, "apply_character_update", {
        "player_id": "p1", "skill_points_delta": 2,
    })
    assert session.characters["p1"].unspent_skill_points == 2
    assert result["unspent_skill_points"] == 2
```

- [ ] **Step 2: verify fails**

Run: `pytest tests/test_narrator_tools.py -v`
Expected: FAIL — `pydantic.ValidationError: Extra inputs are not permitted` for `skill_points_delta`

- [ ] **Step 3: implement.** `narrator/tools.py` — add the field to `ApplyCharacterUpdate`:

```python
class ApplyCharacterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    health_delta: int = 0
    armor_delta: int = 0
    add_conditions: list[str] = []
    remove_conditions: list[str] = []
    add_inventory: list[str] = []
    remove_inventory: list[str] = []
    skill_points_delta: int = 0
```

and in `_execute_apply_character_update`, after the armor line:

```python
    character.health = max(0, min(character.max_health, character.health + tool.health_delta))
    character.armor = max(0, character.armor + tool.armor_delta)
    character.unspent_skill_points = max(0, character.unspent_skill_points + tool.skill_points_delta)
```

and add the key to the returned dict:

```python
    return {
        "player_id": tool.player_id,
        "health": character.health,
        "armor": character.armor,
        "unspent_skill_points": character.unspent_skill_points,
    }
```

- [ ] **Step 4: verify passes**

Run: `pytest tests/test_narrator_tools.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add narrator/tools.py tests/test_narrator_tools.py
git commit -m "feat: apply_character_update can grant skill points"
```

---

## Task 5: `join` validates and finalizes the starting skill allocation

**Files:**
- Modify: `server/dispatch.py`
- Modify: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `ruleset.skills.SKILLS`, `ruleset.skills.STARTING_SKILL_POINTS`, `ruleset.skills.skill_cap` (Task 1).
- Produces: `_skill_rank_cap(skill_name: str, attributes: dict[str, int]) -> int` (module-private helper, reused by Task 6). `join` now rejects an over-budget or over-cap starting `skills` allocation, and authoritatively computes `unspent_skill_points` server-side (leftover starting points are never lost, and a client can never claim more than what it actually left unspent).

- [ ] **Step 1: failing test** — add to `tests/test_dispatch.py`:

```python
def test_join_accepts_a_valid_starting_skill_allocation():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "skills": {"stealth": 2, "hacking": 1},
        },
    }, "p1")

    character = session.characters["p1"]
    assert character.skills == {"stealth": 2, "hacking": 1}
    assert character.unspent_skill_points == 5  # 8 - 3 spent


def test_join_rejects_a_starting_allocation_over_budget():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="exceed the starting budget"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "skills": {"melee": 3, "athletics": 3, "stealth": 3},  # 9 > budget of 8
            },
        }, "p1")


def test_join_rejects_a_starting_allocation_over_the_governing_attribute_cap():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="exceeds cap"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "skills": {"melee": 4},  # attribute defaults to 10 -> cap 3, 4 > 3
            },
        }, "p1")


def test_join_rejects_an_unknown_skill_name():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown skill"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "skills": {"lockpicking": 1},
            },
        }, "p1")


def test_join_with_no_skills_field_leaves_the_full_budget_unspent():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")

    assert session.characters["p1"].skills == {}
    assert session.characters["p1"].unspent_skill_points == 8
```

- [ ] **Step 2: verify fails**

Run: `pytest tests/test_dispatch.py -v`
Expected: `test_join_accepts_a_valid_starting_skill_allocation` and `test_join_with_no_skills_field_leaves_the_full_budget_unspent` FAIL (`unspent_skill_points == 0`, not 8/5 - nothing computes it yet); `test_join_rejects_a_starting_allocation_over_budget`, `..._over_the_governing_attribute_cap`, and `..._an_unknown_skill_name` FAIL (no `ValueError` raised - nothing validates yet)

- [ ] **Step 3: implement.** `server/dispatch.py` — add the import and two helpers, and call the new helper from the `join` branch:

```python
from engine.character import CharacterSheet
from engine.session import Session
from engine.turns import advance_turn, end_combat, join, roll_initiative
from ruleset.skills import SKILLS, STARTING_SKILL_POINTS, skill_cap


def _skill_rank_cap(skill_name: str, attributes: dict[str, int]) -> int:
    governing = SKILLS[skill_name].governing_attribute.value
    return skill_cap(attributes.get(governing, 10))


def _validate_and_finalize_skills(character_data: dict) -> None:
    skills = character_data.get("skills") or {}
    attributes = character_data.get("attributes") or {}
    spent = sum(skills.values())
    if spent > STARTING_SKILL_POINTS:
        raise ValueError(
            f"skill points spent ({spent}) exceed the starting budget ({STARTING_SKILL_POINTS})"
        )
    for skill_name, rank in skills.items():
        if skill_name not in SKILLS:
            raise ValueError(f"unknown skill: {skill_name!r}")
        cap = _skill_rank_cap(skill_name, attributes)
        if rank > cap:
            raise ValueError(f"skill {skill_name!r} rank {rank} exceeds cap {cap}")
    # Never trust the client to report its own leftover budget - the server
    # is the one place total spent is actually verified, so it's also the
    # only place that gets to decide what's left over.
    character_data["unspent_skill_points"] = STARTING_SKILL_POINTS - spent


def handle_message(session: Session, message: dict, player_id: str) -> None:
    message_type = message.get("type")
    if message_type is None:
        raise ValueError("missing 'type' in message")

    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        _validate_and_finalize_skills(character_data)
        join(session, CharacterSheet(**character_data))
```

(the `roll_initiative`/`advance_turn`/`end_combat` branches below are unchanged)

- [ ] **Step 4: verify passes**

Run: `pytest tests/test_dispatch.py -v`
Expected: PASS. Also run `pytest -v` for the full suite — `test_join_reconnect_does_not_reset_live_state` must still pass unchanged (the second `join` call's freshly-computed `unspent_skill_points` is discarded by `join()`'s own `setdefault`, same as every other field on a reconnect)

- [ ] **Step 5: commit**

```bash
git add server/dispatch.py tests/test_dispatch.py
git commit -m "feat: join validates and finalizes the starting skill allocation"
```

---

## Task 6: `allocate_skill_points` message

**Files:**
- Modify: `server/dispatch.py`
- Modify: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `_skill_rank_cap` (Task 5), `CharacterSheet.skills`/`unspent_skill_points` (Task 2).
- Produces: a new `allocate_skill_points` message type (`{"type": "allocate_skill_points", "skill": str, "amount": int}`), handled in `handle_message`.

- [ ] **Step 1: failing test** — add to `tests/test_dispatch.py`:

```python
def test_allocate_skill_points_increases_rank_and_decreases_unspent():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")

    handle_message(session, {"type": "allocate_skill_points", "skill": "hacking", "amount": 2}, "p1")

    character = session.characters["p1"]
    assert character.skills["hacking"] == 2
    assert character.unspent_skill_points == 6


def test_allocate_skill_points_rejects_insufficient_points():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "skills": {"hacking": 3, "engineering": 3, "melee": 2},
        },
    }, "p1")
    # all 8 points already spent, 0 unspent left

    with pytest.raises(ValueError, match="insufficient skill points"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "stealth", "amount": 1}, "p1")


def test_allocate_skill_points_rejects_exceeding_the_governing_attribute_cap():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "skills": {"hacking": 3},
        },
    }, "p1")
    # hacking is already at its cap of 3 (attribute defaults to 10)

    with pytest.raises(ValueError, match="would exceed cap"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "hacking", "amount": 1}, "p1")


def test_allocate_skill_points_rejects_an_unknown_skill():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")

    with pytest.raises(ValueError, match="unknown skill"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "lockpicking", "amount": 1}, "p1")


def test_allocate_skill_points_for_unjoined_player_raises_value_error():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown player_id"):
        handle_message(session, {"type": "allocate_skill_points", "skill": "hacking", "amount": 1}, "ghost")
```

- [ ] **Step 2: verify fails**

Run: `pytest tests/test_dispatch.py -v`
Expected: all five new tests FAIL with `unknown message type: 'allocate_skill_points'`

- [ ] **Step 3: implement.** `server/dispatch.py` — add a new branch to `handle_message`, after the existing `roll_initiative` branch and before `advance_turn`:

```python
    elif message_type == "allocate_skill_points":
        if player_id not in session.characters:
            raise ValueError(f"unknown player_id: {player_id!r}")
        skill_name = message.get("skill")
        amount = message.get("amount")
        if skill_name not in SKILLS:
            raise ValueError(f"unknown skill: {skill_name!r}")
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError(f"invalid amount: {amount!r}")
        character = session.characters[player_id]
        if character.unspent_skill_points < amount:
            raise ValueError(
                f"insufficient skill points: has {character.unspent_skill_points}, needs {amount}"
            )
        cap = _skill_rank_cap(skill_name, character.attributes)
        new_rank = character.skills.get(skill_name, 0) + amount
        if new_rank > cap:
            raise ValueError(f"skill {skill_name!r} rank {new_rank} would exceed cap {cap}")
        character.skills[skill_name] = new_rank
        character.unspent_skill_points -= amount
```

- [ ] **Step 4: verify passes**

Run: `pytest tests/test_dispatch.py -v`
Expected: PASS. Also run `pytest -v` for the full suite.

- [ ] **Step 5: commit**

```bash
git add server/dispatch.py tests/test_dispatch.py
git commit -m "feat: allocate_skill_points message for milestone spends"
```

---

## Task 7: Frontend protocol types

**Files:**
- Modify: `frontend/src/lib/nightwire/protocol.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CharacterSheet.skills`/`unspent_skill_points`, `JoinMessage.character.skills?`, `AllocateSkillPointsMessage`.

No automated test — this project's frontend has no test framework (`ROADMAP.md`: "the real check is against the live backend... Vitest/RTL/MSW were part of the scrapped scaffold and were not carried forward"). Verified by `tsc` (already run as part of the existing `npm run` toolchain) and by Task 8/9's live-verify steps actually exercising these types.

- [ ] **Step 1:** Edit `frontend/src/lib/nightwire/protocol.ts` — add two fields to `CharacterSheet`:

```typescript
export interface CharacterSheet {
  player_id: string
  name: string
  role: string
  lifepath: string
  attributes: Record<string, number>
  health: number
  max_health: number
  armor: number
  conditions: string[]
  inventory: string[]
  portrait_path: string | null
  skills: Record<string, number>
  unspent_skill_points: number
}
```

- [ ] **Step 2:** Add `skills?` to `JoinMessage.character`:

```typescript
export interface JoinMessage {
  type: 'join'
  character: {
    player_id: string
    name: string
    role: string
    lifepath: string
    attributes?: Record<string, number>
    health?: number
    max_health?: number
    armor?: number
    conditions?: string[]
    inventory?: string[]
    skills?: Record<string, number>
  }
}
```

- [ ] **Step 3:** Add a new message type and include it in `ClientMessage`:

```typescript
export interface AllocateSkillPointsMessage {
  type: 'allocate_skill_points'
  skill: string
  amount: number
}
```

```typescript
export type ClientMessage =
  | JoinMessage
  | ActionMessage
  | RollInitiativeMessage
  | AdvanceTurnMessage
  | EndCombatMessage
  | ApproveCharacterMessage
  | AllocateSkillPointsMessage
```

- [ ] **Step 4: verify.** From `frontend/`, run:

Run: `npx tsc --noEmit`
Expected: no new errors (`RedactedCharacter` deliberately doesn't get `skills`/`unspent_skill_points` - other players' skill investments stay as hidden as their attributes/inventory already are, same `_REDACTED_FIELDS` whitelist in `server/views.py`, untouched by this plan)

- [ ] **Step 5: commit**

```bash
git add frontend/src/lib/nightwire/protocol.ts
git commit -m "feat: add skill fields to the nightwire protocol types"
```

---

## Task 8: `SkillPicker` component and the pre-join creation flow

**Files:**
- Create: `frontend/src/app/nightwire/SkillPicker.tsx`
- Modify: `frontend/src/app/nightwire/page.tsx`

**Interfaces:**
- Consumes: `Record<string, number>` skills/attributes shapes (Task 7).
- Produces: `SKILLS: SkillInfo[]` and `skillCap(attributeScore: number): number` (TypeScript mirrors of `ruleset/skills.py` - same duplication precedent `page.tsx`'s own `ROLES`/`LIFEPATHS` constants already established for ruleset content), and a `SkillPicker` component reused by Task 9.

- [ ] **Step 1:** Create `frontend/src/app/nightwire/SkillPicker.tsx`:

```typescript
"use client";

// Mirrors ruleset/skills.py's SKILLS dict and skill_cap() - same
// duplication pattern page.tsx's own ROLES/LIFEPATHS constants already
// use for this exact kind of static ruleset content, rather than a new
// REST endpoint on a WebSocket-first backend.
export interface SkillInfo {
  name: string;
  label: string;
  governingAttribute: string;
  description: string;
}

export const SKILLS: SkillInfo[] = [
  { name: "melee", label: "Melee", governingAttribute: "body", description: "Close-quarters combat with blades, fists, or improvised weapons." },
  { name: "athletics", label: "Athletics", governingAttribute: "body", description: "Running, climbing, jumping, and other raw physical feats." },
  { name: "ranged_combat", label: "Ranged Combat", governingAttribute: "reflexes", description: "Firearms and thrown weapons at range." },
  { name: "stealth", label: "Stealth", governingAttribute: "reflexes", description: "Moving unseen, staying quiet, avoiding detection." },
  { name: "piloting", label: "Piloting", governingAttribute: "reflexes", description: "Driving or flying vehicles, high-speed maneuvers." },
  { name: "hacking", label: "Hacking", governingAttribute: "tech", description: "Breaching networks, bypassing security software, digital intrusion." },
  { name: "engineering", label: "Engineering", governingAttribute: "tech", description: "Building, repairing, and modifying gear and cyberware." },
  { name: "demolitions", label: "Demolitions", governingAttribute: "tech", description: "Explosives - rigging, defusing, controlled destruction." },
  { name: "intimidation", label: "Intimidation", governingAttribute: "cool", description: "Coercion through threat, presence, or reputation." },
  { name: "streetwise", label: "Streetwise", governingAttribute: "cool", description: "Reading the street - contacts, black markets, gang politics." },
  { name: "perception", label: "Perception", governingAttribute: "intellect", description: "Noticing details, spotting danger, reading a scene." },
  { name: "deduction", label: "Deduction", governingAttribute: "intellect", description: "Piecing together clues, drawing logical conclusions." },
  { name: "persuasion", label: "Persuasion", governingAttribute: "presence", description: "Convincing others through charm, logic, or negotiation." },
  { name: "performance", label: "Performance", governingAttribute: "presence", description: "Holding a crowd - music, acting, showmanship." },
];

// Mirrors ruleset/skills.py's skill_cap(): min(5, modifier(score) + 3).
export function skillCap(attributeScore: number): number {
  const modifier = Math.floor((attributeScore - 10) / 2);
  return Math.min(5, modifier + 3);
}

// Two call sites share this: the pre-join creation picker (onDecrement
// present - it's just adjusting a local draft, nothing's committed until
// Join is sent) and the post-join milestone spend (onDecrement omitted -
// spend-only, no mechanism to move already-committed points, per spec).
export function SkillPicker({
  skills,
  attributes,
  remaining,
  onIncrement,
  onDecrement,
}: {
  skills: Record<string, number>;
  attributes: Record<string, number>;
  remaining: number;
  onIncrement: (skillName: string) => void;
  onDecrement?: (skillName: string) => void;
}) {
  return (
    <div className="nw-hud flex flex-col gap-1 text-sm nw-text-body">
      <p className="nw-eyebrow">
        Skills ({remaining} point{remaining === 1 ? "" : "s"} remaining)
      </p>
      {SKILLS.map((skill) => {
        const rank = skills[skill.name] ?? 0;
        const cap = skillCap(attributes[skill.governingAttribute] ?? 10);
        return (
          <div key={skill.name} className="flex items-center justify-between gap-2">
            <span title={skill.description}>
              {skill.label} ({rank}/{cap})
            </span>
            <div className="flex gap-1">
              {onDecrement && (
                <button
                  type="button"
                  className="nw-btn-ghost"
                  onClick={() => onDecrement(skill.name)}
                  disabled={rank === 0}
                >
                  −
                </button>
              )}
              <button
                type="button"
                className="nw-btn-ghost"
                onClick={() => onIncrement(skill.name)}
                disabled={rank >= cap || remaining <= 0}
              >
                +
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2:** In `frontend/src/app/nightwire/page.tsx`, import the new component and add skill state:

```typescript
import { SkillPicker } from "./SkillPicker";
```

```typescript
  const [skills, setSkills] = useState<Record<string, number>>({});
```

(add alongside the existing `const [lifepath, setLifepath] = useState("");` line)

- [ ] **Step 3:** Render the picker in the pre-join form, right after the Lifepath description paragraph and before the Join button:

```tsx
              {lifepath && (
                <p className="text-xs nw-text-faint">{LIFEPATHS.find((l) => l.value === lifepath)?.description}</p>
              )}
              <SkillPicker
                skills={skills}
                attributes={{}}
                remaining={8 - Object.values(skills).reduce((a, b) => a + b, 0)}
                onIncrement={(name) =>
                  setSkills((s) => ({ ...s, [name]: (s[name] ?? 0) + 1 }))
                }
                onDecrement={(name) =>
                  setSkills((s) => ({ ...s, [name]: Math.max(0, (s[name] ?? 0) - 1) }))
                }
              />
              <button
                type="button"
                onClick={handleJoin}
                disabled={readyState !== ReadyState.OPEN}
                className="nw-btn-primary"
              >
                Join
              </button>
```

(`attributes={{}}` is deliberate, not a placeholder: attribute point-buy doesn't exist yet — every attribute reads as 10 everywhere in this codebase today, per Task 1's own `skill_cap(10) == 3`, so every skill's cap is honestly uniform until that gap closes, same caveat the design spec itself documents)

- [ ] **Step 4:** Update `handleJoin` to send the allocation:

```typescript
  function handleJoin() {
    send({
      type: "join",
      character: { player_id: playerId, name, role, lifepath, skills },
    });
  }
```

- [ ] **Step 5: Live-verify** in browser against a real running backend (no GPU needed - this is pure client-side state plus the `join`/`allocate_skill_points` validation from Tasks 5-6, no narrator/image/TTS calls). Connect, fill Name/Role/Lifepath, confirm: the skill picker renders all 14 skills with `(0/3)` next to each (cap 3, since attributes default to 10); clicking `+` on a skill increments its rank and decrements "points remaining"; clicking `+` past cap 3 is disabled; clicking `+` after all 8 points are spent is disabled on every remaining skill; clicking `-` decrements and frees up remaining points. Click Join with a real allocation (e.g. 3 into Hacking, 2 into Stealth) and confirm no `error` message renders — the join succeeded server-side. Open the character sheet (`Ctrl+K`, wired in Task 9) and confirm the spent ranks appear.

- [ ] **Step 6: commit**

```bash
git add frontend/src/app/nightwire/SkillPicker.tsx frontend/src/app/nightwire/page.tsx
git commit -m "feat: skill picker in the pre-join character creation flow"
```

---

## Task 9: Milestone skill spending in the character sheet overlay

**Files:**
- Modify: `frontend/src/app/nightwire/CharacterSheetOverlay.tsx`
- Modify: `frontend/src/app/nightwire/page.tsx`

**Interfaces:**
- Consumes: `SkillPicker`, `SKILLS` (Task 8), `CharacterSheet.skills`/`unspent_skill_points` (Task 7).
- Produces: `CharacterSheetOverlay` gains an `onAllocateSkill` prop, wired to send a real `allocate_skill_points` message.

- [ ] **Step 1:** In `frontend/src/app/nightwire/CharacterSheetOverlay.tsx`, import the picker and add a prop:

```typescript
import { SkillPicker } from "./SkillPicker";
```

```typescript
export function CharacterSheetOverlay({
  character,
  onClose,
  onAllocateSkill,
}: {
  character: CharacterSheet;
  onClose: () => void;
  onAllocateSkill: (skill: string) => void;
}) {
```

- [ ] **Step 2:** Add a Skills section, right after the existing Attributes section (before the Condition section):

```tsx
        <div className="nw-divider border-b py-3">
          <p className="nw-eyebrow mb-1">Skills</p>
          {character.unspent_skill_points > 0 ? (
            <SkillPicker
              skills={character.skills}
              attributes={character.attributes}
              remaining={character.unspent_skill_points}
              onIncrement={onAllocateSkill}
            />
          ) : Object.keys(character.skills).length === 0 ? (
            <p className="text-sm nw-text-faint">None trained.</p>
          ) : (
            <div className="nw-hud grid grid-cols-2 gap-1 text-sm nw-text-body">
              {Object.entries(character.skills).map(([skill, rank]) => (
                <span key={skill}>
                  {skill}: {rank}
                </span>
              ))}
            </div>
          )}
        </div>
```

(no `onDecrement` passed here - milestone spends are spend-only, matching the design spec's own "no respec/decrease path")

- [ ] **Step 3:** In `frontend/src/app/nightwire/page.tsx`, wire the new prop at the `CharacterSheetOverlay` call site:

```tsx
              {sheetOpen && "player_id" in view.characters[playerId] && (
                <CharacterSheetOverlay
                  character={view.characters[playerId] as CharacterSheet}
                  onClose={() => setSheetOpen(false)}
                  onAllocateSkill={(skill) => send({ type: "allocate_skill_points", skill, amount: 1 })}
                />
              )}
```

- [ ] **Step 4: Live-verify** in browser against a real running backend (no GPU needed - pure engine logic, same as Task 8). Join with some starting points deliberately left unspent (e.g. spend only 5 of 8). Open the character sheet (`Ctrl+K`) and confirm: the Skills section shows the `SkillPicker` (since `unspent_skill_points > 0`) with the already-spent ranks pre-filled and "points remaining" showing the correct leftover; click `+` on an untrained skill and confirm the rank increments and remaining decrements *without* closing the sheet (the next `state` broadcast re-renders it live); once all points are spent, confirm the section switches to the plain read-only list (no picker, no `+` buttons) and no `-` button ever appeared anywhere in this view.

- [ ] **Step 5: commit**

```bash
git add frontend/src/app/nightwire/CharacterSheetOverlay.tsx frontend/src/app/nightwire/page.tsx
git commit -m "feat: milestone skill point spending in the character sheet overlay"
```

---

## Task 10: `ROADMAP.md` — close out the gap

**Files:**
- Modify: `ROADMAP.md`

- [ ] **Step 1:** Update the "Explicitly not doing (yet)" bullet that currently reads:

```
- A real skill system — `RequestRoll.skill_mod` (`narrator/tools.py`) is clamped/trusted from the model rather than looked up against real character data, since Phase 1's ruleset never designed one. Known gap, not yet scheduled against a phase.
```

Remove that bullet (the gap is closed) and add an entry to the Phases section (after the Phase 6 TTS entry) summarizing what shipped: the 14-skill roster and gating cap (`ruleset/skills.py`), the real `RequestRoll.skill` lookup replacing the clamped integer, starting-budget allocation validated at `join` and milestone spends via `allocate_skill_points` (both server-authoritative), and the frontend `SkillPicker` used at both call sites. Note the explicitly-out-of-scope items from the design spec (attribute point-buy, respec, role-weighted budgets, the rest of the leveling economy) so they stay visible as open gaps rather than silently dropped.

- [ ] **Step 2: commit**

```bash
git add ROADMAP.md
git commit -m "docs: close out the skill system gap in ROADMAP.md"
```
