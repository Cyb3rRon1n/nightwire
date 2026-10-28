# Chrome and Humanity Implementation Plan (Phase 17a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cyberware ("chrome") with a humanity cost and tiers, retuned DCs that a d10 can actually beat, chrome-ya offers with accept, decline and remove, and ⚡ overclock buttons on the Phase 16 roll card.

**Architecture:**
- **`ruleset/cyberware.py`:** a pure catalog plus rules helpers.
- **`engine/chrome.py`:** the stateful operations on a `CharacterSheet` (install, remove, humanity change). They return world-event strings that callers queue on `session.pending_world_events`.
- **Roll math:** one chrome-aware function, `narrator.tools.roll_check`, used by both the narrator roll path and `resolve_roll`, the overclock path.
- **New surface:** a narrator `offer_chrome` tool, player messages in `server/dispatch.py`, prompt blocks in `server/narration.py` and `server/__main__.py`, and frontend components.

**Tech Stack:** Python 3.11+ (pydantic, FastAPI websockets, pytest), Next.js/React/TypeScript. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-27-chrome-humanity-17a-design.md` (its catalog and humanity tables are binding)

## Global Constraints

- **DCs:** `Difficulty` is EASY **6**, MODERATE **9**, HARD **12**, EXTREME **15**. Natural 10 and 1 and the outcome bands are unchanged.
- **Humanity:** 0–100, starts at 100.
- **Tiers:** Steady 70–100; Frayed 40–69; Slipping 20–39; Edge 1–19; Gone too far 0.
- **Social penalty:** Slipping −1, Edge and Gone too far −2. It applies to `persuasion` and `performance` only.
- **Overclock tier bonus:** +1 when humanity is below 40.
- **`gone_too_far`:** set when humanity hits 0, cleared when it rises above 20. While set, installs and overclocks are refused.
- **Confrontation scene:** fires once per character, the first time humanity drops below 40.
- **Slots:** `max(2, 3 + modifier(body))`, 1 slot per item, no duplicates.
- **Catalog:** the spec's 11 items with these exact ids, effects, costs and installments:

  | id | Effect | Humanity cost | Installments |
  |---|---|---|---|
  | hawkeye_optics | +1 perception | 3 | 2 |
  | reflex_wires | +1 ranged_combat | 6 | 3 |
  | kagerou | overclock: second d10, keep the higher, +2 | 10 | 5 |
  | kama_blades | +2 melee | 8 | 4 |
  | oni_arms | +1 melee, +1 athletics | 7 | 4 |
  | lacquer_skin | +10 armor | 6 | 3 |
  | yomi_jack | +1 hacking; overclock +3, hacking only | 5 | 3 |
  | pain_editor | +15 max_health | 5 | 3 |
  | silk_tongue | +1 persuasion | 3 | 2 |
  | kumo_hand | +1 engineering | 3 | 2 |
  | neon_ink | none | 0 | 1 |

- **Overclock cost:** 1d6 humanity, rolled by the engine.
- **Removal:** refunds `humanity_cost // 2`; installments stay owed.
- **`humanity_delta`:** `Field(0, ge=0, le=5)`.
- **Debt is recorded only:** `installments_owed += installments` on install. No clock, no payment field.
- **Old saves:** sessions saved before 17a load with defaults: humanity 100, no chrome, no debt, empty offers and events.
- **Not in 17a:** throttling, torite, repo, `installments_paid`, utsusemi mechanics. Those are 17b.
- **Prompt:** no anti-cliché rules.
- **Commits:** no `Co-Authored-By` or AI-attribution trailer. Don't push.
- **Checks:**
  - backend: `.venv/bin/python -m pytest tests/ -q` (354 pass before, with 1 pre-existing fastapi warning);
  - frontend: `cd frontend && npm run lint && npm run build`, with no new lint errors.

## File Structure

| File | Change |
|---|---|
| `ruleset/difficulty.py` | retuned values |
| `ruleset/cyberware.py` (new) | `Overclock`, `Chrome`, `CHROME`, `slot_capacity`, `humanity_tier`, `social_penalty`, `overclock_tier_bonus`, `chrome_roll_bonus`, `SOCIAL_SKILLS` |
| `engine/character.py`, `engine/session.py`, `engine/persistence.py` | new fields and defaults |
| `engine/chrome.py` (new) | `change_humanity`, `install_chrome`, `remove_chrome`, `usable_overclocks` |
| `narrator/tools.py`, `narrator/client.py` | `roll_check`; `OfferChrome` tool; `humanity_delta` |
| `server/narration.py` | overclock in `resolve_roll`, roll line, Crew and World event prompt blocks |
| `server/dispatch.py` | `starting_chrome`, `accept_chrome`, `decline_chrome`, `remove_chrome` |
| `server/views.py` | `pending_chrome_offers`; per-roll `overclocks` |
| `server/app.py` | pass `overclock` from the roll message |
| `server/__main__.py` | DC line and chrome block in the system prompt |
| `frontend/...` | catalog mirror, creation picker, sheet, offer card, overclock buttons |

---

### Task 1: Retune DCs

**Files:** `ruleset/difficulty.py`, `server/__main__.py`; tests `tests/test_difficulty.py`, `tests/test_narration.py`, `tests/test_server_main.py`

**Interfaces:** Produces `Difficulty.EASY == 6`, `MODERATE == 9`, `HARD == 12`, `EXTREME == 15`.

- [ ] **Step 1: Update and add tests**

`tests/test_difficulty.py`: assert the new values (6, 9, 12, 15) and `Difficulty.MODERATE + 1 == 10`.

`tests/test_narration.py`, existing Phase 16 expectations:
- `pending["dc"] == 16` becomes `pending["dc"] == 12`;
- every `"(7 +2 +0 = 9 vs 16)."` becomes `"(7 +2 +0 = 9 vs 12)."`. The outcome is still "a failure", since 9 < 12;
- `line.endswith("vs 16) — a natural 10.")` becomes `"vs 12) — a natural 10."`, and the natural 1 assertion changes the same way.

Leave the `_pending(..., dc=16)` helper's stored value alone. It is display data only, because the roll recomputes the DC from the difficulty.

`tests/test_server_main.py`, append:

```python
def test_system_prompt_steers_difficulty_toward_moderate():
    from server.__main__ import build_system_prompt

    assert "Most risks are Moderate; Hard is for real danger; Extreme is rare." in build_system_prompt()
```

- [ ] **Step 2: Run and see failures**

`.venv/bin/python -m pytest tests/test_difficulty.py tests/test_narration.py tests/test_server_main.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`ruleset/difficulty.py`: `EASY = 6`, `MODERATE = 9`, `HARD = 12`, `EXTREME = 15`. Add a comment above the class:

```python
    # Retuned in Phase 17a for a d10 game: with ~+2 starting modifiers, Hard
    # succeeds ~30% (the old 16 was beatable only on a natural 10).
```

`server/__main__.py`: append to the end of the `rules` literal:

```python
        " Most risks are Moderate; Hard is for real danger; Extreme is rare."
```

- [ ] **Step 4: Full suite, then commit**

```bash
git add ruleset/difficulty.py server/__main__.py tests/test_difficulty.py tests/test_narration.py tests/test_server_main.py
git commit -m "feat: retune DCs for a d10 game (6/9/12/15)"
```

---

### Task 2: Chrome catalog, character fields, and the humanity/install engine

**Files:**
- Create: `ruleset/cyberware.py`, `engine/chrome.py`, `tests/test_cyberware.py`, `tests/test_chrome.py`
- Modify: `engine/character.py`, `engine/session.py`, `engine/persistence.py`, `tests/test_persistence.py`

**Interfaces (Produces):**
- `ruleset.cyberware`:
  - `Overclock(bonus: int, second_die: bool, skill: str | None)`;
  - `Chrome(id, name, description, humanity_cost, installments, roll_bonus: dict[str, int], armor=0, max_health=0, overclock=None)`;
  - `CHROME: dict[str, Chrome]`;
  - `SOCIAL_SKILLS = ("persuasion", "performance")`;
  - `slot_capacity(attributes: dict) -> int`;
  - `humanity_tier(h: int) -> str`;
  - `social_penalty(h: int) -> int`;
  - `overclock_tier_bonus(h: int) -> int`;
  - `chrome_roll_bonus(chrome_ids: list[str], skill: str) -> int`.
- `engine.chrome`:
  - `change_humanity(character, delta) -> list[str]`;
  - `install_chrome(character, chrome_id) -> list[str]`;
  - `remove_chrome(character, chrome_id) -> list[str]`;
  - `usable_overclocks(character, skill) -> list[dict]`, each `{"id", "name", "bonus_text"}`.
- `CharacterSheet` gains `humanity=100`, `chrome: list[str]`, `installments_owed=0`, `slipping_warned=False`, `gone_too_far=False`.
- `Session` gains `pending_chrome_offers: dict[str, str]` and `pending_world_events: list[str]`.

- [ ] **Step 1: Write failing tests**

`tests/test_cyberware.py`:

```python
from ruleset.cyberware import (
    CHROME, SOCIAL_SKILLS, chrome_roll_bonus, humanity_tier, overclock_tier_bonus, slot_capacity, social_penalty,
)
from ruleset.skills import SKILLS


def test_catalog_has_the_eleven_spec_items():
    assert list(CHROME) == [
        "hawkeye_optics", "reflex_wires", "kagerou", "kama_blades", "oni_arms", "lacquer_skin",
        "yomi_jack", "pain_editor", "silk_tongue", "kumo_hand", "neon_ink",
    ]
    assert (CHROME["kagerou"].humanity_cost, CHROME["kagerou"].installments) == (10, 5)
    assert CHROME["neon_ink"].humanity_cost == 0


def test_catalog_skills_are_real_and_costs_non_negative():
    for chrome in CHROME.values():
        assert all(skill in SKILLS for skill in chrome.roll_bonus)
        assert chrome.humanity_cost >= 0 and chrome.installments >= 1


def test_overclocks():
    assert CHROME["kagerou"].overclock.second_die and CHROME["kagerou"].overclock.bonus == 2
    assert CHROME["kagerou"].overclock.skill is None
    assert CHROME["yomi_jack"].overclock.skill == "hacking" and CHROME["yomi_jack"].overclock.bonus == 3
    assert [c.id for c in CHROME.values() if c.overclock] == ["kagerou", "yomi_jack"]


def test_slot_capacity():
    assert slot_capacity({"body": 6}) == 2  # 3 + (-2) = 1 -> minimum 2
    assert slot_capacity({"body": 10}) == 3
    assert slot_capacity({"body": 16}) == 6


def test_tiers_and_penalties():
    assert [humanity_tier(h) for h in (100, 70, 69, 40, 39, 20, 19, 1, 0)] == [
        "Steady", "Steady", "Frayed", "Frayed", "Slipping", "Slipping", "Edge", "Edge", "Gone too far",
    ]
    assert [social_penalty(h) for h in (70, 40, 39, 19, 0)] == [0, 0, -1, -2, -2]
    assert [overclock_tier_bonus(h) for h in (40, 39, 1)] == [0, 1, 1]
    assert SOCIAL_SKILLS == ("persuasion", "performance")


def test_chrome_roll_bonus_sums_installed_items():
    assert chrome_roll_bonus(["kama_blades", "oni_arms"], "melee") == 3
    assert chrome_roll_bonus(["kama_blades"], "stealth") == 0
```

`tests/test_chrome.py`:

```python
import pytest

from engine.character import CharacterSheet
from engine.chrome import change_humanity, install_chrome, remove_chrome, usable_overclocks


def _rook(**kw):
    return CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"body": 10}, **kw)


def test_install_applies_cost_stats_debt_and_order():
    rook = _rook()
    install_chrome(rook, "lacquer_skin")
    install_chrome(rook, "pain_editor")
    assert rook.chrome == ["lacquer_skin", "pain_editor"]
    assert rook.humanity == 100 - 6 - 5
    assert rook.armor == 10 and rook.max_health == 115
    assert rook.installments_owed == 3 + 3


def test_install_rejects_duplicate_full_slots_and_gone_too_far():
    rook = _rook()
    install_chrome(rook, "neon_ink")
    with pytest.raises(ValueError, match="already installed"):
        install_chrome(rook, "neon_ink")
    install_chrome(rook, "hawkeye_optics")
    install_chrome(rook, "silk_tongue")  # body 10 -> 3 slots, now full
    with pytest.raises(ValueError, match="no free chrome slot"):
        install_chrome(rook, "kumo_hand")
    gone = _rook(humanity=0, gone_too_far=True)
    with pytest.raises(ValueError, match="humanity"):
        install_chrome(gone, "neon_ink")
    with pytest.raises(ValueError, match="unknown chrome"):
        install_chrome(_rook(), "nope")


def test_remove_refunds_half_reverses_stats_keeps_debt():
    rook = _rook()
    install_chrome(rook, "pain_editor")  # 95 humanity, 115 max
    rook.health = 110
    remove_chrome(rook, "pain_editor")
    assert rook.chrome == [] and rook.humanity == 97  # +5 // 2
    assert rook.max_health == 100 and rook.health == 100
    assert rook.installments_owed == 3
    with pytest.raises(ValueError, match="not installed"):
        remove_chrome(rook, "pain_editor")


def test_change_humanity_clamps_locks_and_unlocks():
    rook = _rook(humanity=5)
    change_humanity(rook, -50)
    assert rook.humanity == 0 and rook.gone_too_far
    change_humanity(rook, 20)
    assert rook.gone_too_far  # 20 is not above 20
    change_humanity(rook, 1)
    assert not rook.gone_too_far
    change_humanity(rook, 500)
    assert rook.humanity == 100


def test_confrontation_fires_once_below_forty():
    rook = _rook(humanity=42)
    assert change_humanity(rook, -1) == []
    events = change_humanity(rook, -3)
    assert len(events) == 1 and "Rook" in events[0]
    assert change_humanity(rook, -10) == []


def test_usable_overclocks_by_skill_and_lock():
    rook = _rook()
    install_chrome(rook, "kagerou")
    install_chrome(rook, "yomi_jack")
    assert [o["id"] for o in usable_overclocks(rook, "stealth")] == ["kagerou"]
    assert [o["id"] for o in usable_overclocks(rook, "hacking")] == ["kagerou", "yomi_jack"]
    rook.gone_too_far = True
    assert usable_overclocks(rook, "hacking") == []
```

In `tests/test_persistence.py`, append a round-trip test. Set `humanity=55`, `chrome=["kagerou"]`, `installments_owed=5` on a character, plus `session.pending_chrome_offers={"p1": "kagerou"}` and `session.pending_world_events=["x"]`. Save, load and assert them. Also add an old-file test that deletes `pending_chrome_offers` and `pending_world_events` from the saved JSON, and deletes the character's `humanity` and `chrome` keys, then asserts the defaults load. Follow the file's existing patterns, including `test_load_defaults_pending_rolls_when_missing_from_an_older_file`.

- [ ] **Step 2: Run and see failures** (import errors)

- [ ] **Step 3: Implement `ruleset/cyberware.py`**

```python
"""Phase 17a chrome catalog and humanity rules - see
docs/superpowers/specs/2026-10-27-chrome-humanity-17a-design.md."""

from dataclasses import dataclass, field

from ruleset.attributes import modifier

SOCIAL_SKILLS = ("persuasion", "performance")


@dataclass(frozen=True)
class Overclock:
    bonus: int
    second_die: bool
    skill: str | None  # None = usable on any roll


@dataclass(frozen=True)
class Chrome:
    id: str
    name: str
    description: str
    humanity_cost: int
    installments: int
    roll_bonus: dict[str, int] = field(default_factory=dict)
    armor: int = 0
    max_health: int = 0
    overclock: Overclock | None = None


CHROME: dict[str, Chrome] = {c.id: c for c in (
    Chrome("hawkeye_optics", "Hawkeye optics", "Zoom, low-light and threat-tagging eyes.", 3, 2, {"perception": 1}),
    Chrome("reflex_wires", "Reflex wires", "Boosted nerve paths for a faster trigger finger.", 6, 3, {"ranged_combat": 1}),
    Chrome("kagerou", "Kagerou", "A spine-mounted time-dilation rig; the world slows when you push it.", 10, 5,
           overclock=Overclock(bonus=2, second_die=True, skill=None)),
    Chrome("kama_blades", "Kama blades", "Forearm blades that unfold like a sickle.", 8, 4, {"melee": 2}),
    Chrome("oni_arms", "Oni arms", "Heavy cyberarms built for lifting and breaking.", 7, 4, {"melee": 1, "athletics": 1}),
    Chrome("lacquer_skin", "Lacquer skin", "Subdermal plating under a glossy finish.", 6, 3, armor=10),
    Chrome("yomi_jack", "Yomi jack", "A neural port that goes deeper into the net than it should.", 5, 3, {"hacking": 1},
           overclock=Overclock(bonus=3, second_die=False, skill="hacking")),
    Chrome("pain_editor", "Pain editor", "Filters pain signals so you keep moving.", 5, 3, max_health=15),
    Chrome("silk_tongue", "Silk tongue", "A voice modulator tuned to sound trustworthy.", 3, 2, {"persuasion": 1}),
    Chrome("kumo_hand", "Kumo hand", "A multi-tool hand with eight fine manipulators.", 3, 2, {"engineering": 1}),
    Chrome("neon_ink", "Neon ink", "Fashionware: living light under the skin.", 0, 1),
)}


def slot_capacity(attributes: dict) -> int:
    return max(2, 3 + modifier(attributes.get("body", 10)))


def humanity_tier(humanity: int) -> str:
    if humanity >= 70:
        return "Steady"
    if humanity >= 40:
        return "Frayed"
    if humanity >= 20:
        return "Slipping"
    if humanity >= 1:
        return "Edge"
    return "Gone too far"


def social_penalty(humanity: int) -> int:
    return 0 if humanity >= 40 else -1 if humanity >= 20 else -2


def overclock_tier_bonus(humanity: int) -> int:
    return 1 if humanity < 40 else 0


def chrome_roll_bonus(chrome_ids: list[str], skill: str) -> int:
    return sum(CHROME[c].roll_bonus.get(skill, 0) for c in chrome_ids)
```

- [ ] **Step 4: Fields**

`engine/character.py`, append to `CharacterSheet`:

```python
    # Phase 17a chrome + humanity
    humanity: int = 100
    chrome: list[str] = field(default_factory=list)
    installments_owed: int = 0
    slipping_warned: bool = False
    gone_too_far: bool = False
```

`engine/session.py`, append:

```python
    # Phase 17a: a chrome-ya's standing offer per player, and engine events
    # (e.g. the confrontation scene) the next prompt build shows once.
    pending_chrome_offers: dict[str, str] = field(default_factory=dict)
    pending_world_events: list[str] = field(default_factory=list)
```

`engine/persistence.py`, in `load`'s `Session(...)`, add:

```python
            pending_chrome_offers=data.get("pending_chrome_offers", {}),
            pending_world_events=data.get("pending_world_events", []),
```

`CharacterSheet(**character_data)` already defaults any missing new keys.

- [ ] **Step 5: Implement `engine/chrome.py`**

```python
"""Stateful chrome + humanity operations on a CharacterSheet (Phase 17a).
Functions return world-event strings; callers queue them on
session.pending_world_events for the next prompt."""

from engine.character import CharacterSheet
from ruleset.cyberware import CHROME, Chrome, overclock_tier_bonus, slot_capacity

_CONFRONTATION = (
    "{name} is slipping - someone close to them has noticed what the chrome is doing "
    "and confronts them about it."
)


def change_humanity(character: CharacterSheet, delta: int) -> list[str]:
    character.humanity = max(0, min(100, character.humanity + delta))
    if character.humanity == 0:
        character.gone_too_far = True
    elif character.humanity > 20:
        character.gone_too_far = False
    if character.humanity < 40 and not character.slipping_warned:
        character.slipping_warned = True
        return [_CONFRONTATION.format(name=character.name)]
    return []


def _apply_stats(character: CharacterSheet, chrome: Chrome, sign: int) -> None:
    character.armor = max(0, character.armor + sign * chrome.armor)
    character.max_health += sign * chrome.max_health
    character.health = min(character.health, character.max_health)


def install_chrome(character: CharacterSheet, chrome_id: str) -> list[str]:
    chrome = CHROME.get(chrome_id)
    if chrome is None:
        raise ValueError(f"unknown chrome: {chrome_id!r}")
    if chrome_id in character.chrome:
        raise ValueError(f"{chrome.name} is already installed")
    if len(character.chrome) >= slot_capacity(character.attributes):
        raise ValueError("no free chrome slot")
    if character.gone_too_far:
        raise ValueError("humanity too low for new chrome")
    character.chrome.append(chrome_id)
    _apply_stats(character, chrome, +1)
    character.installments_owed += chrome.installments
    return change_humanity(character, -chrome.humanity_cost)


def remove_chrome(character: CharacterSheet, chrome_id: str) -> list[str]:
    if chrome_id not in character.chrome:
        raise ValueError(f"{chrome_id!r} is not installed")
    chrome = CHROME[chrome_id]
    character.chrome.remove(chrome_id)
    _apply_stats(character, chrome, -1)
    return change_humanity(character, chrome.humanity_cost // 2)


def usable_overclocks(character: CharacterSheet, skill: str) -> list[dict]:
    if character.gone_too_far:
        return []
    bonus_tier = overclock_tier_bonus(character.humanity)
    usable = []
    for chrome_id in character.chrome:
        oc = CHROME[chrome_id].overclock
        if oc is None or (oc.skill is not None and oc.skill != skill):
            continue
        text = f"+{oc.bonus + bonus_tier}" + (", roll twice keep higher" if oc.second_die else "")
        usable.append({"id": chrome_id, "name": CHROME[chrome_id].name, "bonus_text": text})
    return usable
```

- [ ] **Step 6: Full suite, then commit**

```bash
git add ruleset/cyberware.py engine/chrome.py engine/character.py engine/session.py engine/persistence.py tests/test_cyberware.py tests/test_chrome.py tests/test_persistence.py
git commit -m "feat: chrome catalog, humanity tiers, install/remove engine"
```

---

### Task 3: Chrome-aware rolls and ⚡ overclock resolution

**Files:**
- Modify: `narrator/tools.py`, `server/narration.py` (`resolve_roll`, `_roll_line`, `handle_roll`), `server/views.py`, `server/app.py`
- Test: `tests/test_narration.py`, `tests/test_narrator_tools.py`, `tests/test_views.py`

**Interfaces:**
- Consumes: Task 2 (`chrome_roll_bonus`, `social_penalty`, `SOCIAL_SKILLS`, `CHROME`, `overclock_tier_bonus`, `change_humanity`, `usable_overclocks`).
- Produces:
  - `narrator.tools.roll_check(character, attribute, skill, difficulty, overclock_id=None) -> dict`, with keys `die_result, attribute_mod, skill_mod, dc, outcome` plus, when overclocked, `overclock, overclock_bonus` and (Kagerou) `second_die`;
  - `resolve_roll(session, player_id, overclock: str | None = None) -> dict`;
  - `handle_roll(..., player_id, overclock=None)`;
  - the view's pending entries gain `"overclocks": usable_overclocks(...)`.

- [ ] **Step 1: Failing tests**

`tests/test_narrator_tools.py` (follow its fixtures):

```python
def test_roll_check_adds_chrome_bonus_and_social_penalty(monkeypatch):
    from engine.character import CharacterSheet
    from narrator.tools import roll_check

    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: 5)
    rook = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid",
                          attributes={"reflexes": 10}, skills={"melee": 1}, chrome=["kama_blades"], humanity=30)
    assert roll_check(rook, "reflexes", "melee", "moderate")["skill_mod"] == 3        # 1 rank + 2 blades
    assert roll_check(rook, "presence", "persuasion", "moderate")["skill_mod"] == -1  # Slipping penalty


def test_roll_check_kagerou_keeps_higher_die_and_adds_bonus(monkeypatch):
    from engine.character import CharacterSheet
    from narrator.tools import roll_check

    rook = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid",
                          attributes={"reflexes": 10}, chrome=["kagerou"], humanity=90)
    dice = iter([3, 8])
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: next(dice))
    result = roll_check(rook, "reflexes", "stealth", "hard", overclock_id="kagerou")
    assert (result["first_die"], result["second_die"], result["die_result"]) == (3, 8, 8)
    assert result["overclock"] == "kagerou" and result["overclock_bonus"] == 2
    assert result["outcome"] == "failure"  # 8 + 0 + 0 + 2 = 10 < Hard 12

    dice = iter([3, 10])
    monkeypatch.setattr("narrator.tools.random.randint", lambda a, b: next(dice))
    assert roll_check(rook, "reflexes", "stealth", "hard", overclock_id="kagerou")["outcome"] == "clean_success"
```

`tests/test_narration.py`, using the existing `_pending` helper (which sets a stealth/hard pending roll for p1):

```python
@pytest.mark.asyncio
async def test_overclocked_roll_charges_humanity_and_names_it(tmp_path, monkeypatch):
    from server.narration import resolve_roll

    session = _session_with_character()
    session.characters["p1"].chrome = ["kagerou"]
    _pending(session)
    rolls = iter([4, 9, 3])  # d10, second d10, 1d6 humanity
    monkeypatch.setattr("random.randint", lambda a, b: next(rolls))  # both modules use the random module

    rolled = resolve_roll(session, "p1", overclock="kagerou")

    assert rolled["overclock"] == "kagerou" and rolled["humanity_loss"] == 3
    assert session.characters["p1"].humanity == 97
    assert any(line.startswith("Rook overclocks Kagerou (−3 humanity) and rolls Stealth (Reflexes) vs Hard:")
               and "(9 +2 +0 +2 = 13 vs 12)" in line for line in session.log)


def test_overclock_not_usable_on_this_roll_is_refused_and_roll_stays_pending():
    from server.narration import resolve_roll

    session = _session_with_character()
    session.characters["p1"].chrome = ["yomi_jack"]
    _pending(session)  # stealth, not hacking
    with pytest.raises(ValueError, match="overclock"):
        resolve_roll(session, "p1", overclock="yomi_jack")
    assert "p1" in session.pending_rolls
```

`server/narration.py` must `import random` (the 1d6 humanity roll lives there). Patching `random.randint` covers both modules.

`tests/test_views.py`: update `test_view_exposes_pending_rolls_to_every_viewer`. The view now adds `"overclocks": []` to each pending entry for a character without chrome. A pending roll for a player with no character sheet gets `[]`, so expect `{"player_id": "p1", "skill": "stealth", "dc": 16, "overclocks": []}`.

- [ ] **Step 2: Run and see failures**

- [ ] **Step 3: Implement `roll_check` in `narrator/tools.py`**

```python
from ruleset.cyberware import CHROME, SOCIAL_SKILLS, chrome_roll_bonus, overclock_tier_bonus, social_penalty


def roll_check(character, attribute: str, skill: str, difficulty: str, overclock_id: str | None = None) -> dict:
    attribute_mod = modifier(character.attributes.get(attribute, 10))
    skill_mod = character.skills.get(skill, 0) + chrome_roll_bonus(character.chrome, skill)
    if skill in SOCIAL_SKILLS:
        skill_mod += social_penalty(character.humanity)
    dc = Difficulty[difficulty.upper()].value
    die = random.randint(1, 10)
    result = {"attribute_mod": attribute_mod, "skill_mod": skill_mod, "dc": dc}
    bonus = 0
    if overclock_id is not None:
        oc = CHROME[overclock_id].overclock
        bonus = oc.bonus + overclock_tier_bonus(character.humanity)
        result.update(overclock=overclock_id, overclock_bonus=bonus)
        if oc.second_die:
            second = random.randint(1, 10)
            result.update(first_die=die, second_die=second)
            die = max(die, second)
    result["die_result"] = die
    result["outcome"] = resolve_roll(die, attribute_mod, skill_mod + bonus, dc).value
    return result
```

Then make `_execute_request_roll` delegate:

```python
def _execute_request_roll(session: Session, tool: RequestRoll) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    return roll_check(session.characters[tool.player_id], tool.attribute, tool.skill, tool.difficulty)
```

`resolve_roll` in `ruleset/resolution.py` has the same name as `server.narration.resolve_roll`. Keep importing the ruleset one in `narrator/tools.py` as it is today.

- [ ] **Step 4: `server/narration.py`**

Add `import random` and `from engine.chrome import change_humanity, usable_overclocks`, plus `from narrator.tools import roll_check` and `from ruleset.cyberware import CHROME`.

Replace `resolve_roll` and `_roll_line`:

```python
def _roll_line(pending: dict, result: dict) -> str:
    die, attr_mod, skill_mod = result["die_result"], result["attribute_mod"], result["skill_mod"]
    bonus = result.get("overclock_bonus", 0)
    total = die + attr_mod + skill_mod + bonus
    who = pending["name"]
    if "overclock" in result:
        who += f" overclocks {CHROME[result['overclock']].name} (−{result['humanity_loss']} humanity) and"
    formula = f"{die} {attr_mod:+d} {skill_mod:+d}" + (f" {bonus:+d}" if bonus else "")
    line = (
        f"{who} rolls {_label(pending['skill'])} ({_label(pending['attribute'])}) "
        f"vs {_label(pending['difficulty'])}: {_OUTCOME_TEXT[result['outcome']]} "
        f"({formula} = {total} vs {result['dc']})"
    )
    if die in (1, 10):
        line += f" — a natural {die}"
    return line + "."


def resolve_roll(session: Session, player_id: str, overclock: str | None = None) -> dict:
    pending = session.pending_rolls.get(player_id)
    if pending is None:
        raise ValueError("no roll pending")
    character = session.characters.get(player_id)
    if character is None:
        raise ValueError(f"unknown player_id: {player_id!r}")
    if overclock is not None and overclock not in {o["id"] for o in usable_overclocks(character, pending["skill"])}:
        raise ValueError(f"can't overclock {overclock!r} on this roll")
    result = roll_check(character, pending["attribute"], pending["skill"], pending["difficulty"], overclock)
    session.pending_rolls.pop(player_id, None)  # only after a successful roll
    if overclock is not None:
        result["humanity_loss"] = random.randint(1, 6)
        session.pending_world_events.extend(change_humanity(character, -result["humanity_loss"]))
    session.log.append(_roll_line(pending, result))
    rolled = {**result, **pending}
    session.log.append(f"[roll: {json.dumps(rolled)}]")
    return rolled
```

`handle_roll` gains `overclock: str | None = None` and passes it to `resolve_roll`.

The existing Phase 16 test that deletes the character still raises `ValueError` ("unknown player_id") and keeps the roll pending. Verify that it passes unchanged.

- [ ] **Step 5: View and app**

`server/views.py`, replacing `"pending_rolls": session.pending_rolls,`:

```python
        "pending_rolls": {
            pid: {**pending, "overclocks": usable_overclocks(session.characters[pid], pending["skill"])
                  if pid in session.characters and "skill" in pending else []}
            for pid, pending in session.pending_rolls.items()
        },
```

Import `usable_overclocks`. `server/app.py`, roll branch: `rolled = resolve_roll(session, player_id, overclock=message.get("overclock"))`.

- [ ] **Step 6: Full suite, then commit**

```bash
git add narrator/tools.py server/narration.py server/views.py server/app.py tests/test_narrator_tools.py tests/test_narration.py tests/test_views.py
git commit -m "feat: chrome bonuses and tier penalties in rolls; overclock on the roll"
```

---

### Task 4: Getting chrome (creation, chrome-ya offers, accept, decline, remove, humanity gains)

**Files:**
- Modify: `narrator/tools.py`, `narrator/client.py`, `server/dispatch.py`, `server/views.py`
- Test: `tests/test_narrator_tools.py`, `tests/test_narrator_client.py`, `tests/test_dispatch.py`, `tests/test_views.py`

**Interfaces:**
- Consumes: `install_chrome`, `remove_chrome`, `change_humanity` (Task 2).
- Produces:
  - tool `offer_chrome` with args `{player_id, item}`, where `item` is a `Literal` of the 11 ids;
  - `ApplyCharacterUpdate.humanity_delta`;
  - player messages `accept_chrome`, `decline_chrome`, `remove_chrome {item}`;
  - `join` `character.starting_chrome`;
  - view key `pending_chrome_offers`.

- [ ] **Step 1: Failing tests**

`tests/test_narrator_tools.py`:

```python
def test_offer_chrome_creates_an_offer_and_installs_nothing():
    from engine.character import CharacterSheet
    from engine.session import Session
    from narrator.tools import execute_tool

    session = Session(session_id="s")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    execute_tool(session, "offer_chrome", {"player_id": "p1", "item": "kagerou"})
    assert session.pending_chrome_offers == {"p1": "kagerou"}
    assert session.characters["p1"].chrome == []


def test_offer_chrome_rejects_unknown_item():
    import pytest
    from engine.session import Session
    from narrator.tools import execute_tool

    with pytest.raises((ValueError, TypeError)):
        execute_tool(Session(session_id="s"), "offer_chrome", {"player_id": "p1", "item": "nope"})


def test_humanity_delta_is_bounded_and_applies():
    import pytest
    from pydantic import ValidationError
    from engine.character import CharacterSheet
    from engine.session import Session
    from narrator.tools import ApplyCharacterUpdate, execute_tool

    with pytest.raises(ValidationError):
        ApplyCharacterUpdate(player_id="p1", humanity_delta=6)
    with pytest.raises(ValidationError):
        ApplyCharacterUpdate(player_id="p1", humanity_delta=-1)
    session = Session(session_id="s")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", humanity=50)
    execute_tool(session, "apply_character_update", {"player_id": "p1", "humanity_delta": 5})
    assert session.characters["p1"].humanity == 55
```

If `execute_tool` raises a pydantic `ValidationError` for a bad `Literal`, match whatever it raises today for bad tool args. Look at the existing tests for that pattern and adjust the `pytest.raises` tuple to match.

`tests/test_narrator_client.py`: add a test that a structured response with `{"tool": "offer_chrome", "tool_args": {"player_id": "p1", "item": "neon_ink"}}` parses. Follow the file's existing per-tool parse tests.

`tests/test_dispatch.py`: use the file's helpers to build a joined session.
- **Join with starting chrome:** `starting_chrome: "hawkeye_optics"` installs it (chrome list, humanity 97, installments 2). An unknown id raises `ValueError`. A client-sent `humanity`, `chrome` or `installments_owed` in the character payload is ignored.
- **Accept:** `accept_chrome` with an offer installs it, clears the offer, and logs `[chrome installed: Rook — Kagerou]`. With no offer it raises "no chrome offer".
- **Decline:** `decline_chrome` clears the offer.
- **Remove:** `remove_chrome {"item": "hawkeye_optics"}` removes it and logs `[chrome removed: Rook — Hawkeye optics]`. An item that isn't installed raises.
- **Confrontation events** from `install_chrome` go into `session.pending_world_events`. Check this with a character at humanity 45 accepting kagerou.

`tests/test_views.py`: the view exposes `pending_chrome_offers`.

- [ ] **Step 2: Run and see failures**

- [ ] **Step 3: Implement**

`narrator/tools.py`:

```python
ChromeId = Literal[
    "hawkeye_optics", "reflex_wires", "kagerou", "kama_blades", "oni_arms", "lacquer_skin",
    "yomi_jack", "pain_editor", "silk_tongue", "kumo_hand", "neon_ink",
]


class OfferChrome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: str
    item: ChromeId


def _execute_offer_chrome(session: Session, tool: OfferChrome) -> dict:
    if tool.player_id not in session.characters:
        raise ValueError(f"unknown player_id: {tool.player_id!r}")
    session.pending_chrome_offers[tool.player_id] = tool.item
    return {"offered": tool.item}
```

Register `"offer_chrome": (OfferChrome, _execute_offer_chrome)` in the tool table. Add a test asserting `set(ChromeId.__args__) == set(CHROME)`, so the Literal can't drift from the catalog.

In `ApplyCharacterUpdate`, add `humanity_delta: int = Field(0, ge=0, le=5)`, with a comment matching the existing delta comments. In `_execute_apply_character_update`, after the existing updates:

```python
    if tool.humanity_delta:
        session.pending_world_events.extend(change_humanity(character, tool.humanity_delta))
```

`narrator/client.py`: add `_OfferChromeCall`, following the `_RememberNPCCall` pattern, and add it to the `Union`.

`server/dispatch.py`:
- In `join`, before building the sheet, read `starting_chrome = character_data.get("starting_chrome")` and validate it: `None`, or an id in `CHROME`. After `join(session, ...)`, if it is set, run `session.pending_world_events.extend(install_chrome(session.characters[character_data["player_id"]], starting_chrome))`. `_JOIN_CHARACTER_FIELDS` stays as is, so the server-owned fields stay filtered out.
- New branches:

```python
    elif message_type == "accept_chrome":
        character = _character(session, player_id)
        offer = session.pending_chrome_offers.get(player_id)
        if offer is None:
            raise ValueError("no chrome offer pending")
        session.pending_world_events.extend(install_chrome(character, offer))
        session.pending_chrome_offers.pop(player_id)
        session.log.append(f"[chrome installed: {character.name} — {CHROME[offer].name}]")

    elif message_type == "decline_chrome":
        if session.pending_chrome_offers.pop(player_id, None) is None:
            raise ValueError("no chrome offer pending")

    elif message_type == "remove_chrome":
        character = _character(session, player_id)
        item = message.get("item")
        session.pending_world_events.extend(remove_chrome(character, item))
        session.log.append(f"[chrome removed: {character.name} — {CHROME[item].name}]")
```

If no `_character` helper exists, add a small one that raises `ValueError(f"unknown player_id: {player_id!r}")`, following the existing branches' check. `install_chrome` validates before mutating, so a failed accept leaves the offer pending.

`server/views.py`: add `"pending_chrome_offers": session.pending_chrome_offers,`.

- [ ] **Step 4: Full suite, then commit**

```bash
git add narrator/tools.py narrator/client.py server/dispatch.py server/views.py tests/
git commit -m "feat: starting chrome, chrome-ya offers, accept/decline/remove, humanity gains"
```

---

### Task 5: Prompt: Crew status, World events, chrome guidance

**Files:** `server/narration.py`, `server/__main__.py`; tests `tests/test_narration.py`, `tests/test_server_main.py`

**Interfaces:**
- Consumes: `humanity_tier`, `CHROME`, `session.pending_world_events`.
- Produces: `_crew_line(session) -> str` (`""` if no character has chrome or is below 100 humanity), and `_build_messages` consuming `pending_world_events`.

- [ ] **Step 1: Failing tests** (`tests/test_narration.py`)

```python
def test_crew_line_and_world_event_sit_before_the_action_and_events_clear():
    from server.narration import _build_messages

    session = _session_with_character()
    session.characters["p1"].humanity = 62
    session.characters["p1"].chrome = ["kagerou", "hawkeye_optics"]
    session.pending_world_events.append("Rook is slipping.")

    content = _build_messages(session, "I wait.", num_ctx=8192)[0]["content"]

    assert "Crew: Rook: humanity 62 (Frayed), chrome: Kagerou, Hawkeye optics" in content
    assert "World event: Rook is slipping." in content
    assert content.index("World event:") < content.index("Player action: I wait.")
    assert session.pending_world_events == []


def test_no_crew_line_for_unchromed_full_humanity():
    from server.narration import _build_messages

    session = _session_with_character()
    assert "Crew:" not in _build_messages(session, "I wait.", num_ctx=8192)[0]["content"]


def test_crew_entry_is_capped():
    from server.narration import _crew_line

    session = _session_with_character()
    session.characters["p1"].name = "R" * 300
    session.characters["p1"].humanity = 50
    assert len(_crew_line(session)) <= len("Crew: ") + 200
```

`tests/test_server_main.py`:

```python
def test_system_prompt_has_chrome_guidance():
    from server.__main__ import build_system_prompt

    prompt = build_system_prompt()
    assert "offer_chrome" in prompt and "humanity_delta" in prompt and "Gone too far" in prompt
```

- [ ] **Step 2: Implement**

`server/narration.py`:

```python
_CREW_ENTRY_MAX_CHARS = 200


def _crew_line(session: Session) -> str:
    entries = []
    for c in session.characters.values():
        if not c.chrome and c.humanity == 100:
            continue
        entry = f"{c.name}: humanity {c.humanity} ({humanity_tier(c.humanity)})"
        if c.chrome:
            entry += ", chrome: " + ", ".join(CHROME[i].name for i in c.chrome)
        entries.append(entry[:_CREW_ENTRY_MAX_CHARS])
    return "Crew: " + "; ".join(entries) if entries else ""
```

In `_build_messages`, right after the Scene line is appended:

```python
    crew = _crew_line(session)
    if crew:
        parts.append(crew)
    if session.pending_world_events:
        parts.append("World event: " + " ".join(session.pending_world_events))
        session.pending_world_events.clear()  # shown once
```

`server/__main__.py`: append to the `rules` literal (one string, in the existing style):

```python
        " Chrome and humanity: characters' humanity tier is in the Crew line. Play it - Frayed: "
        "small dissonance; Slipping: cold, quick to violence, Yomi static in the ears; Edge: "
        "episodes - rage, faces from Yomi, lost time; Gone too far: episodes every scene, but the "
        "player always decides what their character does. A World event line is something that "
        "just happened - narrate it. When a player asks a chrome-ya what's on offer, call "
        "offer_chrome with one catalog item; never offer in routine scenes or combat, and never "
        "say the chrome is installed - the player accepts or declines. For therapy or a real "
        "human moment (a friend, a meal, choosing restraint), you may set "
        "apply_character_update's humanity_delta to 1-5; never for routine scenes."
```

- [ ] **Step 3: Full suite, then commit**

```bash
git add server/narration.py server/__main__.py tests/test_narration.py tests/test_server_main.py
git commit -m "feat: crew humanity status, world events and chrome guidance in the prompt"
```

---

### Task 6: Frontend (catalog, creation picker, sheet, offer card, overclock buttons)

**Files:**
- Create: `frontend/src/app/nightwire/chrome.ts`, `frontend/src/app/nightwire/ChromeOfferCard.tsx`
- Modify: `frontend/src/lib/nightwire/protocol.ts`, `frontend/src/app/nightwire/page.tsx`, `CharacterSheetOverlay.tsx`, `RollCard.tsx`, `theme.css`

**Interfaces:** Consumes the view (`characters[me]` with `humanity`, `chrome`, `installments_owed` and `gone_too_far`; `pending_chrome_offers`; `pending_rolls[*].overclocks`) and the `[roll: …]` extra fields (`overclock`, `overclock_bonus`, `first_die`, `second_die`, `humanity_loss`). Sends `join{character.starting_chrome?}`, `accept_chrome`, `decline_chrome`, `remove_chrome{item}`, and `roll{overclock?}`.

- [ ] **Step 1: Protocol types**

In `protocol.ts`:
- `CharacterSheet` gains `humanity: number`, `chrome: string[]`, `installments_owed: number`, `slipping_warned: boolean`, `gone_too_far: boolean`.
- `StateView` gains `pending_chrome_offers: Record<string, string>`.
- `PendingRoll` gains `overclocks: { id: string; name: string; bonus_text: string }[]`.
- `RollResult` gains optional `overclock?: string; overclock_bonus?: number; first_die?: number; second_die?: number; humanity_loss?: number`.
- `RollMessage` gains `overclock?: string`.
- Add `AcceptChromeMessage`, `DeclineChromeMessage`, `RemoveChromeMessage { type: 'remove_chrome'; item: string }` to the `ClientMessage` union.
- Add `starting_chrome?: string` to the join character payload type.

- [ ] **Step 2: `chrome.ts`**

A hand-checked mirror of `ruleset/cyberware.py`, the same pattern as `ROLES` and `SkillPicker`:

```ts
export interface ChromeInfo { id: string; name: string; effect: string; humanity: number; installments: number }

export const CHROME: ChromeInfo[] = [
  { id: "hawkeye_optics", name: "Hawkeye optics", effect: "+1 Perception", humanity: 3, installments: 2 },
  { id: "reflex_wires", name: "Reflex wires", effect: "+1 Ranged combat", humanity: 6, installments: 3 },
  { id: "kagerou", name: "Kagerou", effect: "⚡ Overclock: roll twice, keep higher, +2", humanity: 10, installments: 5 },
  { id: "kama_blades", name: "Kama blades", effect: "+2 Melee", humanity: 8, installments: 4 },
  { id: "oni_arms", name: "Oni arms", effect: "+1 Melee, +1 Athletics", humanity: 7, installments: 4 },
  { id: "lacquer_skin", name: "Lacquer skin", effect: "+10 Armor", humanity: 6, installments: 3 },
  { id: "yomi_jack", name: "Yomi jack", effect: "+1 Hacking; ⚡ Overclock +3 on hacking", humanity: 5, installments: 3 },
  { id: "pain_editor", name: "Pain editor", effect: "+15 Max health", humanity: 5, installments: 3 },
  { id: "silk_tongue", name: "Silk tongue", effect: "+1 Persuasion", humanity: 3, installments: 2 },
  { id: "kumo_hand", name: "Kumo hand", effect: "+1 Engineering", humanity: 3, installments: 2 },
  { id: "neon_ink", name: "Neon ink", effect: "Fashionware (style only)", humanity: 0, installments: 1 },
];

export const chromeById = (id: string) => CHROME.find((c) => c.id === id);

export function humanityTier(h: number): string {
  return h >= 70 ? "Steady" : h >= 40 ? "Frayed" : h >= 20 ? "Slipping" : h >= 1 ? "Edge" : "Gone too far";
}
```

- [ ] **Step 3: Creation picker (`page.tsx`)**

Add `const [startingChrome, setStartingChrome] = useState("")`. In the join form after the `SkillPicker`, add a `<select className="nw-field">`:
- the first option is "No starting chrome";
- one option per `CHROME` item, labelled `${name} — ${effect} · −${humanity} humanity · ${installments} installments`.

`handleJoin` adds `...(startingChrome ? { starting_chrome: startingChrome } : {})` to `character`.

- [ ] **Step 4: Sheet (`CharacterSheetOverlay.tsx`)**

Add an `onRemoveChrome: (item: string) => void` prop, which `page.tsx` passes as `(item) => send({ type: "remove_chrome", item })`. Add a "Chrome & humanity" boxed section in the same style as the existing sections:
- a humanity bar (`<div role="meter" aria-valuenow={h} aria-valuemin={0} aria-valuemax={100}>`) with a fill width of `h%`, plus the text `Humanity {h} · {tier}`;
- the chrome list (name and effect), each with a small **Remove** button;
- `Installments owed: {n}`.

- [ ] **Step 5: Offer card (`ChromeOfferCard.tsx`, rendered in `page.tsx`)**

When `view.pending_chrome_offers[playerId]` is set, render, above the pending roll cards, a card in the `.nw-roll-card` style:
- the item's name, effect, `−{humanity} humanity` and `{installments} installments`;
- **Accept** (`send({ type: "accept_chrome" })`) and **Decline** (`send({ type: "decline_chrome" })`) buttons.

Teammates see nothing.

- [ ] **Step 6: Overclock buttons (`RollCard.tsx`)**

`PendingRollCard`'s `onRoll` becomes `(overclock?: string) => void`. When `isMine`, render **Roll**, then one button per `roll.overclocks ?? []`, labelled `⚡ Overclock ({o.name}) · {o.bonus_text} · −1d6 humanity`, which calls `onRoll(o.id)`. `page.tsx` sends `{ type: "roll", ...(overclock ? { overclock } : {}) }`.

In `RollResultCard`'s breakdown:
- with `roll.second_die`, show both dice, for example `⚡ 3 / 8 → 8`;
- show the `overclock_bonus` as `+2 ⚡` in the sum, and include it in the total;
- show `−{humanity_loss} humanity` next to the badge.

- [ ] **Step 7: Lint and build**

`cd frontend && npm run lint && npm run build`. Both must be clean apart from the one known pre-existing issue.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: chrome UI - starting chrome, humanity sheet, offer card, overclock buttons"
```

---

### Task 7: Live verification, browser check, docs (controller)

- [ ] **Step 1: Probe** on the GPU box (`OLLAMA_HOST=http://192.168.10.19:11434`, 300s client timeout), following the Phase 16 probe pattern. Steps:
  1. 8 risky actions: record the DC distribution the model picks and the outcome spread;
  2. "I ask the chrome-ya what she has for me": does `offer_chrome` fire? Accept via `handle_message`;
  3. 3 routine turns: no offer should fire;
  4. two overclocked rolls (`resolve_roll(..., overclock="kagerou")`): does the narration reflect the cost?
  5. set humanity to 60, 30, 10 and 0 between turns, and record whether the narration matches each tier and never takes over the player;
  6. drop a character from 41 to below 40: is the confrontation scene narrated?
- [ ] **Step 2: Browser** (headless Chrome over CDP, the Phase 16 pattern):
  - join with a starting chrome;
  - the sheet shows the humanity bar and chrome;
  - an offer card for an injected offer;
  - overclock buttons on the roll card (Yomi jack only on hacking);
  - Remove.

  Capture a screenshot.
- [ ] **Step 3: Docs**
  - README: one feature bullet ("Chrome has a price: …") and the screenshot.
  - ROADMAP: a `17a. **Chrome and humanity**` entry with the spec and plan paths, what was built, live numbers with n, and what's deferred to 17b.
- [ ] **Step 4: Commit:** `docs: record Phase 17a (chrome and humanity) and its live verification`. Merge and push follow the owner's standing instruction for this phase cycle: ask if unsure.
