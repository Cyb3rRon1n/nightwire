# Suggested Actions with Skill Chips Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each story turn, show up to 3 suggested moves above the text box. A tagged chip shows skill, difficulty and the character's real chance, and clicking it rolls exactly that check.

**Architecture:** One small `judge()` call (`narrator/suggestions.py`) after each story turn writes raw chips. The engine checks them, caps the stakes and works out the chance from the same maths as `roll_check`, then stores them in `session.suggestions[player_id]`. `build_view` shows each player their own chips. A click sends only the chip id. `handle_action` looks the chip up, skips the risk check and has `_run_turn` hold the chip's roll instead of the narrator's.

**Tech Stack:** Python 3 / FastAPI / pydantic / pytest (asyncio auto), Ollama `qwen3:8b` via `NarratorClient.judge`, Next.js 16 + React (frontend), `node --test` for pure TS helpers.

**Spec:** `docs/superpowers/specs/2026-11-18-suggested-actions-design.md` (read it first).

## Global Constraints

- At most 3 chips; at least one plain chip. If none came back plain, keep the first 2 tagged chips and add the plain chip `I look around.`
- A tagged chip is a promise: its skill, attribute and difficulty are exactly the roll the player gets.
- A plain chip is a promise too: no roll on that turn.
- The browser only ever sends a chip id, never tag fields.
- Any `suggest()` failure means no chips that turn, logged as `[chips error: ...]`. The turn is never affected.
- Bracket log lines (`[...]`) are hidden from the feed and from the narrator's context. New log lines: `[chips error: ...]` and `[action source: chip]` / `[action source: typed]`.
- Workspace git rules: no `Co-Authored-By` or AI-attribution trailers; never push without asking the owner.
- Tests: `python -m pytest tests/` from the repo root with the repo's `.venv` active. Frontend: `npm run lint`, `npm run build`, `npm run test:nightwire` from `frontend/`.

## Deviations from the spec (decided while planning)

- `roll_chance` lives in `narrator/tools.py` next to `roll_check`, because that is where the modifier code is (the spec said `ruleset/`).
- Chips survive a reconnect or reload: they are part of the saved session, so a refresh shows the same chips (the spec said reload clears them; keeping them is less code and better for the player). Still cleared on any action or text.
- Difficulty colours use the existing theme tokens (`--nw-cyan` easy, `--nw-gold` moderate, `--nw-red` hard, `#ff8a80` extreme). The roll card has no per-difficulty colours to reuse.
- The attribute shows on hover (`title`) only. There's no long-press on phones.

## File structure

| File | Responsibility |
|---|---|
| `narrator/tools.py` (modify) | `_roll_mods` shared by `roll_check` and new `roll_chance` |
| `narrator/suggestions.py` (create) | `SCHEMA`, `suggest()` (the model call), `check_chips()` (engine checks) |
| `engine/session.py`, `engine/persistence.py` (modify) | `suggestions` field, saved and loaded |
| `server/narration.py` (modify) | chip click in `handle_action`, `chip_roll` in `_run_turn`, `_hold_roll(capped=)`, `refresh_suggestions()` |
| `server/phone_turns.py` (modify) | a text clears chips |
| `server/views.py`, `server/app.py` (modify) | send chips to their player; refresh after story turns |
| `frontend/src/lib/nightwire/protocol.ts`, `chips.ts` (create) | types, chip label helpers |
| `frontend/src/app/nightwire/play/FeedPanel.tsx`, `PlayScreen.tsx`, `play.css` (modify) | chip row, toggle |
| `tools/soak_test.py` (modify) | `--chips` |

---

### Task 1: `roll_chance`

**Files:**
- Modify: `narrator/tools.py:87-106` (`roll_check`)
- Test: `tests/test_narrator_tools.py`

**Interfaces:**
- Produces: `roll_chance(character: CharacterSheet, attribute: str, skill: str, difficulty: str) -> int`. Returns a percent (0–100, a multiple of 10) chance of not failing; a complication counts as success. `difficulty` is `"easy" | "moderate" | "hard" | "extreme"`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_narrator_tools.py`; add imports at the top if missing)

```python
import random

from engine.character import CharacterSheet
from narrator.tools import roll_chance, roll_check


def _rin(**kw):
    return CharacterSheet(player_id="p1", name="Rin", role="netrunner", lifepath="streetkid", **kw)


def test_roll_chance_counts_the_d10_faces():
    # Mods 0 vs Moderate 9: only a 9 (complication) and a natural 10 pass.
    assert roll_chance(_rin(), "presence", "persuasion", "moderate") == 20
    # Easy 6 with mods 0: faces 6-10.
    assert roll_chance(_rin(), "presence", "persuasion", "easy") == 50
    # +2 vs Moderate: faces 7-10 (ruleset/difficulty.py's "Moderate 40%" at +2).
    assert roll_chance(_rin(skills={"persuasion": 2}), "presence", "persuasion", "moderate") == 40
    # Untrained Hard: natural 10 only.
    assert roll_chance(_rin(), "body", "athletics", "hard") == 10


def test_roll_chance_includes_the_social_penalty():
    low = _rin(skills={"persuasion": 2})
    low.humanity = 30  # -1 on social skills
    assert roll_chance(low, "presence", "persuasion", "moderate") == 30


def test_roll_chance_matches_roll_check_with_chrome(monkeypatch):
    c = _rin(skills={"persuasion": 1}, chrome=["silk_tongue"], attributes={"presence": 13})
    for difficulty in ("easy", "moderate", "hard", "extreme"):
        passes = 0
        for face in range(1, 11):
            monkeypatch.setattr(random, "randint", lambda a, b, f=face: f)
            passes += roll_check(c, "presence", "persuasion", difficulty)["outcome"] != "failure"
        assert roll_chance(c, "presence", "persuasion", difficulty) == passes * 10
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_narrator_tools.py -k roll_chance -v`
Expected: FAIL with `ImportError: cannot import name 'roll_chance'`

- [ ] **Step 3: Implement.** In `narrator/tools.py`, change the imports to `from ruleset.resolution import Outcome, resolve_roll`, then replace the first lines of `roll_check` and add `roll_chance` below it:

```python
def _roll_mods(character, attribute: str, skill: str) -> tuple[int, int]:
    """Attribute and skill modifiers exactly as a roll uses them: chrome bonus and the social penalty included."""
    attribute_mod = modifier(character.attributes.get(attribute, 10))
    skill_mod = character.skills.get(skill, 0) + chrome_roll_bonus(active_chrome(character), skill)
    if skill in SOCIAL_SKILLS:
        skill_mod += social_penalty(character.humanity)
    return attribute_mod, skill_mod


def roll_check(character, attribute: str, skill: str, difficulty: str, overclock_id: str | None = None) -> dict:
    attribute_mod, skill_mod = _roll_mods(character, attribute, skill)
    dc = Difficulty[difficulty.upper()].value
    # ... the rest of roll_check unchanged ...


def roll_chance(character, attribute: str, skill: str, difficulty: str) -> int:
    """Percent chance of not failing (a complication counts), from the same maths as roll_check, no overclock."""
    attribute_mod, skill_mod = _roll_mods(character, attribute, skill)
    dc = Difficulty[difficulty.upper()].value
    return 10 * sum(resolve_roll(face, attribute_mod, skill_mod, dc) != Outcome.FAILURE for face in range(1, 11))
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_narrator_tools.py -v`
Expected: all PASS (old roll tests included)

- [ ] **Step 5: Commit**

```bash
git add narrator/tools.py tests/test_narrator_tools.py
git commit -m "Roll chance from the same maths as roll_check"
```

---

### Task 2: `narrator/suggestions.py` and the session field

**Files:**
- Create: `narrator/suggestions.py`
- Modify: `engine/session.py` (add a field after `phone`), `engine/persistence.py` (`load`)
- Test: `tests/test_suggestions.py`

**Interfaces:**
- Consumes: `roll_chance` (Task 1); `difficulty_for` (`ruleset/difficulty.py`); `roll_attribute`, `SKILLS` (`ruleset/skills.py`); `NarratorBackend.judge(messages, schema) -> dict`.
- Produces:
  - `SCHEMA: dict`
  - `async suggest(client, story: list[str], place: str | None, character) -> list` returns the raw `chips` value from the model. It may raise; the caller catches.
  - `check_chips(raw, character, recent_stakes: list[str]) -> list[dict]`. Each chip is `{"id": str, "text": str, "skill": str | None, "attribute": str | None, "stakes": str | None, "difficulty": str | None, "chance": int | None}`; plain chips have every tag field `None`.
  - `Session.suggestions: dict[str, list[dict]]`

- [ ] **Step 1: Write the failing tests** (`tests/test_suggestions.py`)

```python
import json

from engine.character import CharacterSheet
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.suggestions import LOOK_AROUND, SCHEMA, check_chips, suggest


def _rin(**kw):
    return CharacterSheet(player_id="p1", name="Rin", role="netrunner", lifepath="streetkid",
                          skills={"hacking": 2, "persuasion": 1}, **kw)


def _tagged(text, skill, attribute="presence", stakes="normal"):
    return {"text": text, "skill": skill, "attribute": attribute, "stakes": stakes}


def _plain(text):
    return {"text": text, "skill": "none", "attribute": "none", "stakes": "none"}


def test_a_good_set_keeps_one_plain_and_two_tagged_with_real_chances():
    chips = check_chips([_plain("I ask Mama Sato about the collector."),
                         _tagged("I talk the doorman down.", "persuasion"),
                         _tagged("I slice the door lock.", "hacking", "tech", "high")], _rin(), [])
    assert [c["text"] for c in chips] == ["I ask Mama Sato about the collector.", "I talk the doorman down.",
                                         "I slice the door lock."]
    assert chips[0]["skill"] is None and chips[0]["chance"] is None
    assert chips[1] | {"id": "x"} == {"id": "x", "text": "I talk the doorman down.", "skill": "persuasion",
                                      "attribute": "presence", "stakes": "normal", "difficulty": "moderate",
                                      "chance": 30}
    assert chips[2]["difficulty"] == "hard" and chips[2]["attribute"] == "tech"
    assert len({c["id"] for c in chips}) == 3


def test_a_bad_tag_turns_the_chip_plain_and_an_empty_chip_is_dropped():
    chips = check_chips([_tagged("I juggle the knives.", "juggling"), {"text": "  "}], _rin(), [])
    assert [(c["text"], c["skill"]) for c in chips] == [("I juggle the knives.", None)]


def test_no_plain_chip_adds_look_around_and_keeps_two_tagged():
    raw = [_tagged("I talk my way in.", "persuasion"), _tagged("I hack the camera.", "hacking", "tech"),
           _tagged("I charm the guard.", "persuasion")]
    chips = check_chips(raw, _rin(), [])
    assert [c["text"] for c in chips] == [LOOK_AROUND, "I talk my way in.", "I hack the camera."]


def test_the_difficulty_cap_is_applied_when_the_chip_is_made():
    chips = check_chips([_plain("I wait."), _tagged("I jump the gap.", "athletics", "body", "high")],
                        _rin(), ["high", "high"])
    assert chips[1]["stakes"] == "normal" and chips[1]["difficulty"] == "moderate"


def test_the_attribute_is_corrected_to_a_sensible_pair():
    chips = check_chips([_plain("I wait."), _tagged("I sneak past.", "stealth", "presence")], _rin(), [])
    assert chips[1]["attribute"] != "presence"  # ruleset/skills.py: no Stealth (Presence)


def test_a_bodiless_character_gets_no_physical_chips():
    ghost = _rin()
    ghost.bodiless = True
    chips = check_chips([_plain("I listen."), _tagged("I climb the crane.", "athletics", "body")], ghost, [])
    assert [c["text"] for c in chips] == ["I listen."]


def test_junk_answers_give_no_chips():
    assert check_chips(False, _rin(), []) == []
    assert check_chips([], _rin(), []) == []
    assert check_chips(["nope", {"text": ""}], _rin(), []) == []


async def test_suggest_asks_the_judge_with_the_scene_and_returns_the_chips():
    seen = {}

    class Judge:
        async def judge(self, messages, schema):
            seen.update(messages=messages, schema=schema)
            return {"chips": [_plain("I look at the menu.")]}

    raw = await suggest(Judge(), ["Mama Sato wipes the counter."], "Ikebe Low", _rin())
    assert raw == [_plain("I look at the menu.")]
    assert seen["schema"] is SCHEMA
    prompt = seen["messages"][-1]["content"]
    assert "Mama Sato wipes the counter." in prompt and "Ikebe Low" in prompt and "hacking" in prompt


def test_suggestions_are_saved_and_loaded(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="s1", suggestions={"p1": [{"id": "a", "text": "I wait."}]})
    store.save(session)
    assert store.load("s1").suggestions == {"p1": [{"id": "a", "text": "I wait."}]}
    json.dumps(SCHEMA)  # the schema must be plain JSON for Ollama
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_suggestions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.suggestions'`

- [ ] **Step 3: Add the session field.** In `engine/session.py`, after `phone`:

```python
    # Suggested actions (spec 2026-11-18): player_id -> the chips shown after their last story turn.
    suggestions: dict[str, list[dict]] = field(default_factory=dict)
```

In `engine/persistence.py` `load`, after `phone=data.get("phone", {}),`:

```python
            suggestions=data.get("suggestions", {}),
```

- [ ] **Step 4: Create `narrator/suggestions.py`**

```python
"""Suggested actions (spec 2026-11-18-suggested-actions-design.md): up to 3 chips after each story turn, one plain,
the others tagged with the roll they would cause. The model writes them; the engine checks every tag."""

import uuid
from typing import get_args

from narrator.tools import RequestRoll, roll_chance
from ruleset.attributes import Attribute
from ruleset.difficulty import STAKES, difficulty_for
from ruleset.skills import SKILLS, roll_attribute

LOOK_AROUND = "I look around."
_SKILL_NAMES = get_args(RequestRoll.model_fields["skill"].annotation)
_ATTRIBUTES = get_args(RequestRoll.model_fields["attribute"].annotation)
_MAX_WORDS = 20  # the prompt asks for 12; this only drops runaways

SCHEMA = {
    "type": "object",
    "properties": {"chips": {"type": "array", "maxItems": 3, "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "skill": {"type": "string", "enum": ["none", *_SKILL_NAMES]},
            "attribute": {"type": "string", "enum": ["none", *_ATTRIBUTES]},
            "stakes": {"type": "string", "enum": ["none", *STAKES]},
        },
        "required": ["text", "skill", "attribute", "stakes"],
    }}},
    "required": ["chips"],
}

_SYSTEM = "You suggest what a player could do next in a cyberpunk tabletop game. Answer only from the scene."


async def suggest(client, story: list[str], place: str | None, character) -> list:
    best = sorted(character.skills, key=character.skills.get, reverse=True)[:3]
    prompt = (
        "Scene (latest last):\n" + "\n".join(story) + "\n\n"
        f"Place: {place or 'unknown'}. Player character: {character.name}, a {character.role}; "
        f"best skills: {', '.join(best) or 'none'}.\n\n"
        "Suggest 3 moves this character could make now:\n"
        '- one plain move that needs no roll (talk, look, leave): skill, attribute and stakes "none";\n'
        "- two risky moves with different approaches (social, tech, stealth, force), each with the skill and "
        "attribute it tests and its stakes; use the character's best skills where the scene allows.\n"
        'Each move: first person, like "I talk the doorman down", at most 12 words, only people and things the '
        "scene has shown, and never say how it turns out."
    )
    answer = await client.judge([{"role": "system", "content": _SYSTEM}, {"role": "user", "content": prompt}], SCHEMA)
    return answer.get("chips")


def _plain(text: str) -> dict:
    return {"text": text, "skill": None, "attribute": None, "stakes": None, "difficulty": None, "chance": None}


def check_chips(raw, character, recent_stakes: list[str]) -> list[dict]:
    if not isinstance(raw, list):
        return []
    plain, tagged = [], []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text or len(text.split()) > _MAX_WORDS:
            continue
        skill, stakes = item.get("skill"), item.get("stakes")
        if skill not in SKILLS or stakes not in STAKES:
            plain.append(_plain(text))
            continue
        if character.bodiless and SKILLS[skill].governing_attribute in (Attribute.BODY, Attribute.REFLEXES):
            continue  # the engine would refuse this roll, so the chip can't keep its promise
        attribute = roll_attribute(skill, str(item.get("attribute"))).value
        effective, difficulty = difficulty_for(stakes, recent_stakes)
        level = difficulty.name.lower()
        tagged.append({"text": text, "skill": skill, "attribute": attribute, "stakes": effective,
                       "difficulty": level, "chance": roll_chance(character, attribute, skill, level)})
    if not plain and not tagged:
        return []
    chips = [plain[0] if plain else _plain(LOOK_AROUND), *tagged[:2]]
    chips += plain[1:1 + 3 - len(chips)]
    for chip in chips:
        chip["id"] = uuid.uuid4().hex[:8]
    return chips
```

Note: `SKILLS` keys are skill-name strings (`server/narration.py` already indexes `SKILLS[request.skill]`). If `SKILLS` is keyed by an enum in the version you have, use `skill not in {str(s) for s in SKILLS}` and look up accordingly. Check `ruleset/skills.py` first.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_suggestions.py -v`
Expected: all PASS. If `test_a_good_set...`'s chance is not 30, recompute it by hand from `_rin()` (presence 10 → mod 0, persuasion 1, humanity default; Moderate 9) and check the expected value, not the code, first.

- [ ] **Step 6: Commit**

```bash
git add narrator/suggestions.py engine/session.py engine/persistence.py tests/test_suggestions.py
git commit -m "Suggested actions: model call and engine checks"
```

---

### Task 3: Chip turns in `handle_action` and `_run_turn`

**Files:**
- Modify: `server/narration.py` (`_hold_roll` ~line 352, `handle_action` ~383, `_run_turn` ~524), `server/phone_turns.py` (`handle_text`)
- Test: `tests/test_narration.py`

**Interfaces:**
- Consumes: `Session.suggestions` chips (Task 2 shape).
- Produces: the action message `{"type": "action", "text": str, "chip": str}` (`chip` optional); `_run_turn(..., chip_roll: dict | None = None)`; `_hold_roll(session, player_id, tool_args, capped: bool = False)`.

Behaviour:
- `handle_action` with `chip`: unknown id raises `ValueError("those options have expired")`. The chip's own text is the action, whatever text came with it.
- Every story action clears `session.suggestions[player_id]` and logs `[action source: chip]` or `[action source: typed]` (not for OOC questions).
- **Tagged chip:** no `assess` call. `_run_turn(prompt_text=f"{text}\n\n{RISK_INSTRUCTION}", must_roll=True, chip_roll=chip)`. The narrator's `request_roll` is dropped; the chip's roll is held with `capped=True`. The outcome check runs even if the narrator asked no roll.
- **Plain chip:** no `assess` call; `no_roll=True`.
- `handle_text` clears that player's chips.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_narration.py`; `_scripted_client`, `_say`, `_call` and `_session_with_character` already exist there)

```python
async def _no_assess(*args, **kwargs):
    raise AssertionError("a chip turn must not run the risk check")


def _chip(**kw):
    base = {"id": "c1", "text": "I talk the doorman down.", "skill": "persuasion", "attribute": "presence",
            "stakes": "high", "difficulty": "hard", "chance": 10}
    return base | kw


async def test_a_tagged_chip_holds_exactly_its_roll(tmp_path, monkeypatch):
    monkeypatch.setattr("server.narration.assess", _no_assess)  # assess swallows errors itself, so patch it out
    session = _session_with_character()
    session.suggestions["p1"] = [_chip()]
    other = {"player_id": "p1", "attribute": "body", "skill": "athletics", "stakes": "low", "reason": "shove"}
    # No judge list: the outcome check gets the default "none" answer, so nothing is cut.
    client = _scripted_client([_say("The doorman folds his arms.", "request_roll", other)])
    await _call(session, client, "p1", {"text": "anything", "chip": "c1"}, tmp_path)
    pending = session.pending_rolls["p1"]
    assert (pending["skill"], pending["attribute"], pending["difficulty"]) == ("persuasion", "presence", "hard")
    assert pending["reason"] == "I talk the doorman down."
    assert "p1: I talk the doorman down." in session.log
    assert "[action source: chip]" in session.log
    assert session.suggestions == {}


async def test_a_tagged_chip_rolls_even_when_the_narrator_asks_none(tmp_path):
    session = _session_with_character()
    session.suggestions["p1"] = [_chip()]
    client = _scripted_client([_say("The doorman looks you over.")])
    await _call(session, client, "p1", {"text": "x", "chip": "c1"}, tmp_path)
    assert session.pending_rolls["p1"]["skill"] == "persuasion"


async def test_a_tagged_chip_keeps_its_capped_difficulty(tmp_path):
    session = _session_with_character()
    session.recent_stakes = ["high", "high"]  # difficulty_for would cap a fresh "high" to normal
    session.suggestions["p1"] = [_chip()]
    client = _scripted_client([_say("The doorman looks you over.")])
    await _call(session, client, "p1", {"text": "x", "chip": "c1"}, tmp_path)
    assert session.pending_rolls["p1"]["difficulty"] == "hard"


async def test_a_plain_chip_never_rolls(tmp_path, monkeypatch):
    monkeypatch.setattr("server.narration.assess", _no_assess)
    session = _session_with_character()
    session.suggestions["p1"] = [_chip(id="c2", text="I look around.", skill=None, attribute=None, stakes=None,
                                       difficulty=None, chance=None)]
    roll = {"player_id": "p1", "attribute": "cool", "skill": "perception", "stakes": "normal", "reason": "look"}
    client = _scripted_client([_say("Neon hums.", "request_roll", roll)])
    await _call(session, client, "p1", {"text": "x", "chip": "c2"}, tmp_path)
    assert "p1" not in session.pending_rolls


async def test_a_stale_chip_is_refused(tmp_path):
    session = _session_with_character()
    client = _scripted_client([_say("unused")])
    with pytest.raises(ValueError, match="those options have expired"):
        await _call(session, client, "p1", {"text": "x", "chip": "gone"}, tmp_path)


async def test_a_typed_action_clears_chips_and_is_logged_as_typed(tmp_path):
    session = _session_with_character()
    session.suggestions["p1"] = [_chip()]
    client = _scripted_client([_say("The alley is quiet.")])
    await _call(session, client, "p1", {"text": "I wait."}, tmp_path)
    assert session.suggestions == {}
    assert "[action source: typed]" in session.log
```

Append to `tests/test_phone_turns.py` (its `_session` and `Judge` helpers already exist):

```python
async def test_a_text_clears_the_players_chips():
    s = _session("partner", 5)
    s.suggestions["p1"] = [{"id": "c1", "text": "I wait."}]
    await handle_text(s, Judge(), "p1", {"to": "Mika", "text": "hi"})
    assert "p1" not in s.suggestions
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_narration.py -k chip -v`
Expected: FAIL (the stale chip test with no exception; the others with a missing roll or a wrong skill).

- [ ] **Step 3: `_hold_roll` gets `capped`.** Change its signature and the cap line:

```python
def _hold_roll(session: Session, player_id: str, tool_args: dict, capped: bool = False) -> str | None:
    ...
    # A chip's stakes were capped when the chip was made (narrator/suggestions.py): its promise stands.
    effective, difficulty = (request.stakes, STAKES[request.stakes]) if capped else difficulty_for(
        request.stakes, session.recent_stakes)
```

Add `STAKES` to the existing `from ruleset.difficulty import difficulty_for` import.

- [ ] **Step 4: `handle_action` reads the chip.** At the top, before the text checks:

```python
    chip = None
    if message.get("chip") is not None:
        chip = next((c for c in session.suggestions.get(player_id, []) if c["id"] == message["chip"]), None)
        if chip is None:
            raise ValueError("those options have expired")
        message = {**message, "text": chip["text"]}
    action_text = message.get("text")
```

After the OOC early return and the `roll first` check, add:

```python
    session.suggestions.pop(player_id, None)
    session.log.append(f"[action source: {'chip' if chip else 'typed'}]")
```

Then replace the `risky, roll_skill = ...` line through the `_run_turn(...)` call with:

```python
    if chip is not None and chip["skill"]:
        must_roll, no_roll, roll_skill = True, False, None
    elif chip is not None:
        must_roll, no_roll, roll_skill = False, True, None
    else:
        risky, roll_skill = await assess(narrator_client, action_text) if character is not None else (None, None)
        must_roll, no_roll = risky is True, risky is False
    await _run_turn(
        session, narrator_client, store, image_backend, tts_backend, player_id,
        prompt_text=f"{action_text}\n\n{RISK_INSTRUCTION}" if must_roll else action_text,
        actor_line=f"{player_id}: {action_text}", allow_roll=True, referee_action=action_text, must_roll=must_roll,
        no_roll=no_roll, roll_skill=roll_skill, chip_roll=chip if chip is not None and chip["skill"] else None,
    )
```

- [ ] **Step 5: `_run_turn` takes `chip_roll`.** Add the parameter `chip_roll: dict | None = None` after `roll_skill`. Then make three changes:

```python
    # 1. The narrator's roll doesn't matter on a chip turn, so neither does its refusal.
    refusal = None if chip_roll else _in_fiction_refusal(session, response, player_id, allow_roll)

    # 2. The outcome check guards a chip's set-up even when the narrator asked no roll.
    rolling = chip_roll is not None
    if allow_roll and refusal is None and (response.tool == "request_roll" or rolling):
        ...
            if retry.tool == "request_roll" or rolling:   # a redo that drops the roll keeps the first set-up
                response = retry

    # 3. Replace the _apply_tool line:
    if chip_roll is not None:
        if response.tool == "request_roll":
            response.tool_call = _NoTool()
        _apply_tool(session, response, player_id, allow_roll)
        _hold_roll(session, player_id, {"skill": chip_roll["skill"], "attribute": chip_roll["attribute"],
                                        "stakes": chip_roll["stakes"], "reason": chip_roll["text"]}, capped=True)
    else:
        _apply_tool(session, response, player_id, allow_roll, roll_skill)  # a refusal on the redo is only logged
```

- [ ] **Step 6: `handle_text` clears chips.** In `server/phone_turns.py` `handle_text`, after the text checks pass (before `phone.post`):

```python
    session.suggestions.pop(player_id, None)
```

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: all PASS. Old tests that compare a whole log may now see `[action source: typed]`. Fix those expectations (the line is intended), not the code.

- [ ] **Step 8: Commit**

```bash
git add server/narration.py server/phone_turns.py tests/
git commit -m "Chip clicks: a tagged chip holds its own roll, a plain chip never rolls"
```

---

### Task 4: Make chips after story turns and send them to their player

**Files:**
- Modify: `server/narration.py` (new `refresh_suggestions`), `server/views.py` (`build_view`), `server/app.py` (`websocket_endpoint`)
- Test: `tests/test_narration.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `suggest`, `check_chips` (Task 2).
- Produces: `async refresh_suggestions(session, narrator_client, player_id) -> None`; view field `"suggestions": [{"id", "text", "skill", "attribute", "difficulty", "chance"}]` (the viewer's own; `stakes` is not sent).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_narration.py` (add `from server.narration import refresh_suggestions`):

```python
async def test_refresh_makes_checked_chips_from_the_story():
    session = _session_with_character()
    session.log = ["p1: I sit down.", "[audio: x.wav]", "Mama Sato pours tea."]
    seen = []
    client = _scripted_client([_say("unused")], judge_answers=[{"chips": [
        {"text": "I ask about the collector.", "skill": "none", "attribute": "none", "stakes": "none"},
        {"text": "I talk her into a discount.", "skill": "persuasion", "attribute": "presence", "stakes": "low"},
    ]}])
    await refresh_suggestions(session, client, "p1")
    chips = session.suggestions["p1"]
    assert [c["text"] for c in chips] == ["I ask about the collector.", "I talk her into a discount."]
    assert chips[1]["difficulty"] == "easy"


async def test_refresh_makes_no_chips_while_a_roll_waits():
    session = _session_with_character()
    session.log = ["Mama Sato pours tea."]
    session.pending_rolls["p1"] = {"skill": "persuasion"}
    session.suggestions["p1"] = [{"id": "old", "text": "I wait."}]
    await refresh_suggestions(session, _scripted_client([_say("unused")], judge_answers=[]), "p1")
    assert "p1" not in session.suggestions


async def test_a_failed_suggest_logs_and_shows_no_chips():
    session = _session_with_character()
    session.log = ["Mama Sato pours tea."]
    client = _scripted_client([_say("unused")], judge_answers=[])  # IndexError inside the judge
    await refresh_suggestions(session, client, "p1")
    assert "p1" not in session.suggestions
    assert any(line.startswith("[chips error:") for line in session.log)
```

Append to `tests/test_app.py`:

```python
def test_each_player_sees_only_their_own_chips(tmp_path):
    from server.views import build_view
    from engine.session import Session
    from engine.character import CharacterSheet
    session = Session(session_id="s1", suggestions={"p1": [
        {"id": "a", "text": "I wait.", "skill": None, "attribute": None, "stakes": None, "difficulty": None,
         "chance": None}]})
    for pid in ("p1", "p2"):
        session.characters[pid] = CharacterSheet(player_id=pid, name=pid, role="solo", lifepath="streetkid")
    assert build_view(session, "p1")["suggestions"] == [
        {"id": "a", "text": "I wait.", "skill": None, "attribute": None, "difficulty": None, "chance": None}]
    assert build_view(session, "p2")["suggestions"] == []
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_narration.py -k refresh tests/test_app.py -k chips -v`
Expected: FAIL (`ImportError: cannot import name 'refresh_suggestions'`; `KeyError: 'suggestions'`)

- [ ] **Step 3: `refresh_suggestions`** in `server/narration.py` (import `from narrator.suggestions import check_chips, suggest`):

```python
_CHIP_STORY_LINES = 6


async def refresh_suggestions(session: Session, narrator_client: NarratorClient, player_id: str) -> None:
    """The chips for a player's next move (spec 2026-11-18). Never costs a turn: any failure means no chips."""
    session.suggestions.pop(player_id, None)
    character = session.characters.get(player_id)
    story = [line for line in session.log if not line.startswith("[")][-_CHIP_STORY_LINES:]
    if character is None or player_id in session.pending_rolls or not story:
        return
    try:
        raw = await suggest(narrator_client, story, session.location, character)
        chips = check_chips(raw, character, session.recent_stakes)
    except Exception as e:  # timeout, bad JSON, a backend down: the story already went out
        session.log.append(f"[chips error: {e}]")
        return
    if chips:
        session.suggestions[player_id] = chips
```

- [ ] **Step 4: The view.** In `server/views.py` `build_view`, add to the returned dict:

```python
        "suggestions": [{k: chip.get(k) for k in ("id", "text", "skill", "attribute", "difficulty", "chance")}
                        for chip in session.suggestions.get(viewer_id, [])],
```

- [ ] **Step 5: The app.** In `server/app.py`, import `refresh_suggestions` from `server.narration`, then change the end of the locked block:

```python
                    store.save(session)
                    await manager.broadcast(session_id, session)
                    if message.get("type") in ("action", "roll", "join"):
                        # After the story went out, so chips never delay it.
                        await refresh_suggestions(session, narrator_client, player_id)
                        if player_id in session.suggestions:
                            store.save(session)
                            await manager.broadcast(session_id, session)
```

- [ ] **Step 6: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: all PASS. App tests using `NarratorClient(chat_fn=...)` get `_noop_judge`, which answers `{"chips": false}` → no chips → no extra broadcast. If an app test now receives one more message than it expects, make sure no chip broadcast happened (no chips) before changing anything.

- [ ] **Step 7: Commit**

```bash
git add server/narration.py server/views.py server/app.py tests/
git commit -m "Make chips after each story turn and show each player their own"
```

---

### Task 5: The chip row in the frontend

**Files:**
- Modify: `frontend/src/lib/nightwire/protocol.ts`
- Create: `frontend/src/lib/nightwire/chips.ts`, `frontend/tests/nightwire/chips.test.ts`
- Modify: `frontend/src/app/nightwire/play/FeedPanel.tsx`, `frontend/src/app/nightwire/play/PlayScreen.tsx`, `frontend/src/app/nightwire/play/play.css`

**Interfaces:**
- Consumes: the view's `suggestions` (Task 4); the action message with `chip` (Task 3).
- Produces: `chipTag(s: Suggestion): string | null`, `chipTitle(s: Suggestion): string | undefined`.

- [ ] **Step 1: Types.** In `protocol.ts`:

```ts
export interface Suggestion {
  id: string
  text: string
  skill: string | null
  attribute: string | null
  difficulty: PendingRoll['difficulty'] | null
  chance: number | null
}
```

Add `suggestions?: Suggestion[]` to `StateView` and `chip?: string` to `ActionMessage`.

- [ ] **Step 2: Write the failing test** (`frontend/tests/nightwire/chips.test.ts`)

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { chipTag, chipTitle } from "../../src/lib/nightwire/chips.ts";

const plain = { id: "a", text: "I wait.", skill: null, attribute: null, difficulty: null, chance: null };
const tagged = { id: "b", text: "I talk him down.", skill: "ranged_combat", attribute: "reflexes",
                 difficulty: "moderate" as const, chance: 60 };

test("a tagged chip shows skill, difficulty and chance", () => {
  assert.equal(chipTag(tagged), "Ranged combat · Moderate · 60%");
  assert.equal(chipTitle(tagged), "Reflexes + Ranged combat");
});

test("a plain chip has no tag", () => {
  assert.equal(chipTag(plain), null);
  assert.equal(chipTitle(plain), undefined);
});
```

Run: `cd frontend && npm run test:nightwire`
Expected: FAIL (cannot find `chips.ts`)

- [ ] **Step 3: `chips.ts`**

```ts
import type { Suggestion } from "./protocol.ts";

const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function chipTag(s: Suggestion): string | null {
  if (!s.skill || !s.difficulty || s.chance === null) return null;
  return `${label(s.skill)} · ${label(s.difficulty)} · ${s.chance}%`;
}

export function chipTitle(s: Suggestion): string | undefined {
  return s.skill && s.attribute ? `${label(s.attribute)} + ${label(s.skill)}` : undefined;
}
```

Check how `protocol.ts` is imported by the other node-tested libs (e.g. `phone.ts`). If they use `import type ... from "./protocol"` without `.ts`, match them.

Run: `npm run test:nightwire`. Expected: PASS.

- [ ] **Step 4: The row in `FeedPanel.tsx`.** Add `chips` to the props (`chips: boolean;` in the type, `chips = true` in the destructuring), import `chipTag, chipTitle` from `@/lib/nightwire/chips`, and add a sender next to `handleSendAction`:

```tsx
  function sendChip(s: Suggestion) {
    if (sending) return;
    send({ type: "action", text: s.text, chip: s.id });
    setSending(true);
    setPinned(true);
    pinnedRef.current = true;
  }
```

Inside the `<form ... className="nw-composer ...">`, directly after the `{error && ...}` line:

```tsx
        {chips && !sending && !myRollPending && (view.suggestions?.length ?? 0) > 0 && (
          <div className="nw-suggestions" role="group" aria-label="Suggested actions">
            {view.suggestions!.map((s) => {
              const tag = chipTag(s);
              return (
                <button key={s.id} type="button" className="nw-suggestion" title={chipTitle(s)} onClick={() => sendChip(s)}>
                  <span>{s.text}</span>
                  {tag && <span className="nw-suggestion-tag" data-difficulty={s.difficulty}>{tag}</span>}
                </button>
              );
            })}
          </div>
        )}
```

- [ ] **Step 5: CSS** (append to `play.css`)

```css
.nw-suggestions { display: flex; gap: 8px; overflow-x: auto; scrollbar-width: none; padding-bottom: 2px; }
.nw-suggestion { flex-shrink: 0; max-width: min(320px, 80vw); display: inline-flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 6px 10px; border: 1px solid var(--nw-frame-cool); background: rgba(11, 13, 17, .85); color: #e6e8eb; font: 500 14px var(--font-rajdhani), "Rajdhani", sans-serif; text-align: left; cursor: pointer; }
.nw-suggestion:hover, .nw-suggestion:focus-visible { border-color: var(--nw-cyan); }
.nw-suggestion-tag { font-size: 12px; letter-spacing: .1em; text-transform: uppercase; color: #9aa3ad; }
.nw-suggestion-tag[data-difficulty="easy"] { color: var(--nw-cyan); }
.nw-suggestion-tag[data-difficulty="moderate"] { color: var(--nw-gold); }
.nw-suggestion-tag[data-difficulty="hard"] { color: var(--nw-red); }
.nw-suggestion-tag[data-difficulty="extreme"] { color: #ff8a80; }
```

- [ ] **Step 6: The toggle in `PlayScreen.tsx`**, the same way as scene art:

```tsx
const CHIPS_KEY = "nightwire-chips";
// in the component:
  const [chips, setChips] = useState(() => readFlag(browserStore, CHIPS_KEY, true));
  function toggleChips() {
    writeFlag(browserStore, CHIPS_KEY, !chips);
    setChips(!chips);
  }
// next to the Scene art button:
        <button type="button" className="nw-chip" aria-pressed={chips} onClick={toggleChips}>Suggestions {chips ? "on" : "off"}</button>
```

Pass `chips={chips}` to **every** `<FeedPanel ...>` in `PlayScreen.tsx` (`grep -n "<FeedPanel" PlayScreen.tsx`; there are at least two).

- [ ] **Step 7: Check**

Run: `cd frontend && npm run lint && npm run build && npm run test:nightwire`
Expected: all pass, no new lint warnings.

- [ ] **Step 8: Commit**

```bash
git add frontend/src frontend/tests
git commit -m "Chip row above the text box, with a toggle"
```

---

### Task 6: Soak `--chips` and a live check

**Files:**
- Modify: `tools/soak_test.py`

**Interfaces:**
- Consumes: `refresh_suggestions` (Task 4), the chip action (Task 3).

- [ ] **Step 1: Add the flag.** In `tools/soak_test.py`:
  - Import `refresh_suggestions` from `server.narration`.
  - Change `main(turns)` to `main(turns, chips=False)`. Add `parser.add_argument("--chips", action="store_true", help="click a suggested chip every third turn and make chips after each turn")` and pass it through: `main(args.turns, args.chips)`.
  - In the loop, before `try:`, add:

```python
            offered = session.suggestions.get("rin", []) if chips else []
            if offered and not texting and n % 3 == 0:
                pick = offered[(n // 3) % len(offered)]
                action, row["chip"] = pick["text"], {k: pick[k] for k in ("text", "skill", "difficulty", "chance")}
                row["action"] = action
```

  - Send it with the chip id: change the `handle_action` call's message to `{"type": "action", "text": action, **({"chip": pick["id"]} if "chip" in row else {})}`.
  - After the roll block (still inside `try`), add `if chips: await refresh_suggestions(session, client, "rin")` and record `row["offered"] = [c["text"] for c in session.suggestions.get("rin", [])]` after the `try/except`.
  - Add `"[chips error"` to the `notes` prefixes and `"chip_turns": sum("chip" in r for r in rows)` to `summary`.

- [ ] **Step 2: Test it on two turns.** Run it on whatever narrator is available. CPU-only on this box, about 2–5 min a turn:

```bash
NIGHTWIRE_OLLAMA_TIMEOUT=600 NIGHTWIRE_THINK=off python -m tools.soak_test --turns 3 --chips
```

Expected: turn 3 has a `chip` field, every row has `offered`, no `error`, and the summary shows `chip_turns: 1`. Read the chip texts in the JSONL by eye. Check that they're short and first person, use only people from the scene and give no outcomes. Report what you see; don't tune the prompt in this task.

- [ ] **Step 3: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/soak_test.py
git commit -m "Soak test: --chips clicks a suggested chip every third turn"
```

- [ ] **Step 5: Live browser check (main session, not a subagent).** Start the game server and `npm run dev`, join, play two turns and check:
  - the chips appear after the story;
  - a tagged chip opens exactly its roll card;
  - a plain chip gives no roll;
  - the toggle hides the row;
  - at 375 px wide the row scrolls sideways with no page scroll.

  Report it with a screenshot.
