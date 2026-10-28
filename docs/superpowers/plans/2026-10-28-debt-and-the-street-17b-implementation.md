# Debt and the Street Implementation Plan (Phase 17b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make chrome debt bite. A repo clock ticks while you owe, and its strikes escalate: notice → throttle → Saeko Kirigaya's repo crew. You can pay (Arakawa's gigs), get Old Hara to unthrottle you off the books, or run.

**Architecture:**
- **`engine/debt.py`** owns the clock and all throttle/repo/pay state changes. Its functions return world-event strings, and callers queue them, the same pattern as 17a's `engine/chrome.py`.
- **`handle_action`** ticks the clock.
- **`apply_character_update`** gains three bounded fields that route into `engine/debt.py`.
- **Rolls and overclocks** ignore throttled chrome.
- **Prompt:** the Crew line shows debt state, and card selection scans World events so Saeko's card loads.
- **Sheet:** shows the debt.

**Tech Stack:** Python 3.11+ (pydantic, pytest), Next.js/React/TypeScript. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-28-debt-and-the-street-17b-design.md`

## Global Constraints

- New `CharacterSheet` fields, all defaulted: `repo_clock=0` (range 0–6), `repo_actions=0`, `repo_strikes=0`, `throttled: str | None = None`, `pending_repo: str | None = None`.
- **Tick:** only while `installments_owed > 0`, one tick per action by that player. Every 10 actions the clock gets +1. At 6 the clock resets to 0 and a strike fires.
- **Strikes:**
  - **1, notice:** `"Hoshikawa sends {name} a polite final notice; Saeko Kirigaya's torite crew has been asking about {name}."`
  - **2, throttle:** the newest installed, non-throttled chrome, with its stats removed. `"{name}'s {Chrome} locks up: remote-throttled by Hoshikawa for missed payments."`
  - **3 and after, repo:** `pending_repo` = the throttled item, else the newest. `"Saeko Kirigaya's torite crew comes for {name}'s {Chrome}."`
  - **No chrome:** the notice text only.
  - Each strike is queued on `pending_world_events` **and** logged as `[torite: <event text>]`.
- **`installments_paid: int = Field(0, ge=0, le=1)`.** When ≥ 1: reduce owed (floor 0), reset clock and actions, unthrottle with stats restored, clear `pending_repo`, and reset strikes if owed reaches 0.
- **`repossess: bool = False`.** Requires `pending_repo`, else `ValueError`. Runs `remove_chrome(pending_repo)` and logs `[torite: Saeko's crew took {name}'s {Chrome}]`.
- **`unthrottle: bool = False`.** Requires a throttle, else `ValueError`. Restores stats and appends `"Owe Old Hara a favor"` to `session.active_objectives` (no duplicates). Debt and clock unchanged.
- **Throttled chrome** gives no roll bonus and no overclock. `remove_chrome` clears `throttled` / `pending_repo` when they point at the removed item.
- **Out of scope (17c):** no utsusemi player mechanics. **No money.**
- **Commits:** no `Co-Authored-By` or AI-attribution trailer. Don't push.
- **Checks:**
  - backend: `.venv/bin/python -m pytest tests/ -q` (401 pass before, with 1 pre-existing fastapi warning);
  - frontend: `cd frontend && npm run lint && npm run build`.

---

### Task 1: Debt engine (clock, strikes, throttle, repo, pay, unthrottle)

**Files:**
- Create: `engine/debt.py`, `tests/test_debt.py`
- Modify: `engine/character.py`, `engine/chrome.py`, `narrator/tools.py` (the `roll_check` bonus line only), `tests/test_persistence.py`, `tests/test_chrome.py`

**Interfaces (Produces):**
- `engine.debt.tick_debt(character) -> list[str]`
- `engine.debt.pay_installment(character, amount) -> None`
- `engine.debt.repossess(character) -> str`, which returns the removed chrome id
- `engine.debt.unthrottle(character) -> None`
- `engine.debt.active_chrome(character) -> list[str]`, the installed ids minus the throttled one
- `engine.chrome._apply_stats` is reused (import it).

- [ ] **Step 1: Failing tests** in `tests/test_debt.py`:

```python
import pytest

from engine.character import CharacterSheet
from engine.chrome import install_chrome
from engine.debt import active_chrome, pay_installment, repossess, tick_debt, unthrottle


def _rook():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"body": 10})
    install_chrome(c, "lacquer_skin")  # owes 3, armor 10
    install_chrome(c, "kagerou")       # owes 8 total
    return c


def _tick(c, n):
    events = []
    for _ in range(n):
        events += tick_debt(c)
    return events


def test_no_tick_without_debt():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    assert _tick(c, 100) == [] and c.repo_clock == 0


def test_clock_ticks_every_ten_and_strike_one_is_a_notice():
    c = _rook()
    assert _tick(c, 9) == [] and c.repo_clock == 0
    assert _tick(c, 1) == [] and c.repo_clock == 1
    events = _tick(c, 50)
    assert c.repo_clock == 0 and c.repo_strikes == 1
    assert events == ["Hoshikawa sends Rook a polite final notice; Saeko Kirigaya's torite crew has been asking about Rook."]


def test_strike_two_throttles_newest_and_removes_stats():
    c = _rook()
    c.chrome = ["kagerou", "lacquer_skin"]  # make lacquer_skin the newest
    events = _tick(c, 120)
    assert c.repo_strikes == 2 and c.throttled == "lacquer_skin" and c.armor == 0
    assert events[-1] == "Rook's Lacquer skin locks up: remote-throttled by Hoshikawa for missed payments."
    assert active_chrome(c) == ["kagerou"]


def test_strike_three_targets_the_throttled_item():
    c = _rook()
    events = _tick(c, 180)
    assert c.repo_strikes == 3 and c.pending_repo == c.throttled == "kagerou"
    assert events[-1] == "Saeko Kirigaya's torite crew comes for Rook's Kagerou."


def test_strike_without_chrome_is_a_notice():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", installments_owed=2)
    assert "final notice" in _tick(c, 120)[-1] and c.throttled is None


def test_payment_resets_unthrottles_and_clears_repo():
    c = _rook()
    c.chrome = ["kagerou", "lacquer_skin"]
    _tick(c, 185)
    pay_installment(c, 1)
    assert (c.installments_owed, c.repo_clock, c.repo_actions) == (7, 0, 0)
    assert c.throttled is None and c.pending_repo is None and c.armor == 10
    assert c.repo_strikes == 3  # still owes
    c.installments_owed = 1
    pay_installment(c, 1)
    assert c.installments_owed == 0 and c.repo_strikes == 0


def test_repossess_removes_pending_item_only():
    c = _rook()
    _tick(c, 180)
    removed = repossess(c)
    assert removed == "kagerou" and "kagerou" not in c.chrome and "lacquer_skin" in c.chrome
    assert c.pending_repo is None and c.throttled is None and c.installments_owed == 8
    with pytest.raises(ValueError, match="no repo"):
        repossess(c)


def test_unthrottle_restores_stats_keeps_debt():
    c = _rook()
    c.chrome = ["kagerou", "lacquer_skin"]
    _tick(c, 120)
    clock, owed = c.repo_clock, c.installments_owed
    unthrottle(c)
    assert c.throttled is None and c.armor == 10 and (c.repo_clock, c.installments_owed) == (clock, owed)
    with pytest.raises(ValueError, match="nothing is throttled"):
        unthrottle(c)
```

In `tests/test_chrome.py`, append a test that `remove_chrome` clears a matching `throttled` and `pending_repo`. Set them first and don't re-apply stats: set `c.throttled = "kagerou"` on a sheet that has kagerou installed. In `tests/test_persistence.py`, add a round trip for the five new fields plus an old-file default test (delete the keys).

Also add a roll test: a character with `chrome=["kama_blades"]` and `throttled="kama_blades"` gets `skill_mod == rank` for melee (no +2) from `narrator.tools.roll_check`. And `usable_overclocks` omits a throttled kagerou.

- [ ] **Step 2: Run, see failures.**

- [ ] **Step 3: Implement.**

`engine/character.py`, append:

```python
    # Phase 17b debt loop
    repo_clock: int = 0
    repo_actions: int = 0
    repo_strikes: int = 0
    throttled: str | None = None
    pending_repo: str | None = None
```

`engine/debt.py`:

```python
"""Phase 17b chrome debt loop: the repo clock and its escalation. Functions
return world-event strings; callers queue them on session.pending_world_events.
See docs/superpowers/specs/2026-10-28-debt-and-the-street-17b-design.md."""

from engine.character import CharacterSheet
from engine.chrome import _apply_stats, remove_chrome
from ruleset.cyberware import CHROME

_ACTIONS_PER_PIP = 10
_PIPS_PER_STRIKE = 6


def active_chrome(character: CharacterSheet) -> list[str]:
    return [c for c in character.chrome if c != character.throttled]


def _strike(character: CharacterSheet) -> str:
    character.repo_strikes += 1
    name = character.name
    if not character.chrome or character.repo_strikes == 1:
        return (f"Hoshikawa sends {name} a polite final notice; Saeko Kirigaya's torite crew "
                f"has been asking about {name}.")
    if character.repo_strikes == 2 and character.throttled is None:
        character.throttled = character.chrome[-1]
        _apply_stats(character, CHROME[character.throttled], -1)
        return f"{name}'s {CHROME[character.throttled].name} locks up: remote-throttled by Hoshikawa for missed payments."
    character.pending_repo = character.throttled or character.chrome[-1]
    return f"Saeko Kirigaya's torite crew comes for {name}'s {CHROME[character.pending_repo].name}."


def tick_debt(character: CharacterSheet) -> list[str]:
    if character.installments_owed <= 0:
        return []
    character.repo_actions += 1
    if character.repo_actions < _ACTIONS_PER_PIP:
        return []
    character.repo_actions = 0
    character.repo_clock += 1
    if character.repo_clock < _PIPS_PER_STRIKE:
        return []
    character.repo_clock = 0
    return [_strike(character)]


def _clear_throttle(character: CharacterSheet) -> None:
    if character.throttled is not None:
        _apply_stats(character, CHROME[character.throttled], +1)
        character.throttled = None


def pay_installment(character: CharacterSheet, amount: int) -> None:
    if amount <= 0:
        return
    character.installments_owed = max(0, character.installments_owed - amount)
    character.repo_clock = character.repo_actions = 0
    _clear_throttle(character)
    character.pending_repo = None
    if character.installments_owed == 0:
        character.repo_strikes = 0


def repossess(character: CharacterSheet) -> str:
    if character.pending_repo is None:
        raise ValueError("no repo pending")
    chrome_id = character.pending_repo
    remove_chrome(character, chrome_id)  # half refund; clears throttled/pending_repo pointers
    return chrome_id


def unthrottle(character: CharacterSheet) -> None:
    if character.throttled is None:
        raise ValueError("nothing is throttled")
    _clear_throttle(character)
```

`engine/chrome.py` `remove_chrome`: a throttled item's stats were already removed by the throttle, so skip the stat reversal for it, then clear the pointers. The body after the not-installed check becomes:

```python
    chrome = CHROME[chrome_id]
    character.chrome.remove(chrome_id)
    if character.throttled != chrome_id:
        _apply_stats(character, chrome, -1)
    if character.throttled == chrome_id:
        character.throttled = None
    if character.pending_repo == chrome_id:
        character.pending_repo = None
    return change_humanity(character, chrome.humanity_cost // 2)
```

`engine/chrome.py` `usable_overclocks`: skip `chrome_id == character.throttled`. `narrator/tools.py` `roll_check`: replace `chrome_roll_bonus(character.chrome, skill)` with `chrome_roll_bonus([c for c in character.chrome if c != character.throttled], skill)`. Inline it rather than importing `engine.debt`, to avoid an import cycle.

- [ ] **Step 4: Full suite, then commit:** `feat: chrome debt engine - repo clock, throttle, repo, payment, unthrottle`

---

### Task 2: Wire the debt loop into turns and narrator tools

**Files:** `server/narration.py` (`handle_action`), `narrator/tools.py` (`ApplyCharacterUpdate` + executor), tests in `tests/test_narration.py` and `tests/test_narrator_tools.py`.

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `ApplyCharacterUpdate.installments_paid: int = Field(0, ge=0, le=1)`, `repossess: bool = False`, `unthrottle: bool = False`;
  - `handle_action` ticks the actor's debt before the turn.

- [ ] **Step 1: Failing tests**

`tests/test_narrator_tools.py`:
- `installments_paid` bounds: 2 raises a `ValidationError`;
- `installments_paid=1` calls through: owed −1, clock reset;
- `repossess=True` without a pending repo → `ValueError`, using `execute_tool`'s existing error behavior;
- `repossess=True` with a pending repo → the item is gone and the log gains `[torite: Saeko's crew took Rook's Kagerou]`. Pass the session and check `session.log`;
- `unthrottle=True` → stats restored and `"Owe Old Hara a favor"` in `session.active_objectives` exactly once, even when called twice with a re-throttle in between;
- `unthrottle=True` with nothing throttled → `ValueError`.

`tests/test_narration.py`: with a fake client, a character owing installments and `repo_actions=9, repo_clock=5` (one action from a strike), one `handle_action` call results in:
- `repo_strikes == 1`;
- a `[torite: Hoshikawa sends Rook a polite final notice…]` log line;
- the notice text present in `session.pending_world_events` at prompt-build time. Capture the messages sent, the way the existing roster test does, and assert `World event: Hoshikawa sends Rook` is in the content.

- [ ] **Step 2: Implement**

In `narrator/tools.py` `ApplyCharacterUpdate`, add:

```python
    # Phase 17b debt loop - bounded like the other narrator deltas.
    installments_paid: int = Field(0, ge=0, le=1)
    repossess: bool = False
    unthrottle: bool = False
```

In `_execute_apply_character_update`, after the existing updates:

```python
    if tool.installments_paid:
        pay_installment(character, tool.installments_paid)
    if tool.repossess:
        removed = repossess(character)
        session.log.append(f"[torite: Saeko's crew took {character.name}'s {CHROME[removed].name}]")
    if tool.unthrottle:
        unthrottle(character)
        if "Owe Old Hara a favor" not in session.active_objectives:
            session.active_objectives.append("Owe Old Hara a favor")
```

Validate `repossess` and `unthrottle` **before** any other mutation in that executor. Raise early if `tool.repossess and character.pending_repo is None`, or `tool.unthrottle and character.throttled is None`, so a bad call changes nothing.

In `server/narration.py` `handle_action`, after the `"roll first"` check and before `_run_turn`:

```python
    character = session.characters.get(player_id)
    if character is not None:
        for event in tick_debt(character):
            session.pending_world_events.append(event)
            session.log.append(f"[torite: {event}]")
```

- [ ] **Step 3: Full suite, then commit:** `feat: debt clock ticks on actions; narrator can take payments, repossess, unthrottle`

---

### Task 3: Prompt (Crew debt state, Saeko's card from events, guidance)

**Files:** `server/narration.py` (`_crew_line`, `_build_messages`), `server/__main__.py`; tests in `tests/test_narration.py` and `tests/test_server_main.py`.

- [ ] **Step 1: Failing tests**
- `_crew_line` for a character owing 3 with clock 4, throttled kagerou and a pending repo on kagerou contains `owes 3, repo clock 4/6, throttled: Kagerou, repo crew coming for: Kagerou`.
- A character with no chrome and humanity 100 but **owing installments** still gets an entry.
- `_build_messages` with `session.pending_world_events = ["…Saeko Kirigaya's torite crew…"]` includes Saeko Kirigaya's NPC card text, from `narrator.world.kuroshio()`, in `World notes:`.
- `build_system_prompt()` contains `"Jun Arakawa"`, `"installments_paid"`, `"repossess"` and `"unthrottle"`.

- [ ] **Step 2: Implement**

`_crew_line`:
- include a character if it has chrome **or** humanity < 100 **or** `installments_owed > 0`;
- after the chrome part, add `, owes {n}, repo clock {c}/6` when owed > 0;
- then `, throttled: {Chrome}` and `, repo crew coming for: {Chrome}` when those are set;
- keep the 200-character cap.

In `_build_messages`, pass the action text plus the pending World events to `select_cards`:

```python
    scan_text = " ".join([action_text, *session.pending_world_events])
    cards = select_cards(kuroshio(), session, scan_text, world_budget)
```

`server/__main__.py`: append to the `rules` literal:

```python
        " Chrome debt: the Crew line shows who owes installments and their repo clock. When "
        "someone in debt asks for work, Jun Arakawa (a fixer in Hanabira-chō) has paid gigs; "
        "when a gig pays out, set apply_character_update's installments_paid to 1. When a repo "
        "crew is coming, stage Saeko Kirigaya's crew; set repossess to true only if the "
        "character loses or gives the chrome up. If a character asks Old Hara to unlock "
        "throttled chrome, he can - set unthrottle to true - but they'll owe him."
```

- [ ] **Step 3: Full suite, then commit:** `feat: debt state in the Crew line, Saeko from torite events, debt guidance`

---

### Task 4: Frontend (debt on the sheet)

**Files:** `frontend/src/lib/nightwire/protocol.ts`, `frontend/src/app/nightwire/CharacterSheetOverlay.tsx`, `theme.css` (only if needed).

- [ ] **Step 1:** `CharacterSheet` gains `repo_clock: number`, `repo_actions: number`, `repo_strikes: number`, `throttled: string | null`, `pending_repo: string | null`.
- [ ] **Step 2:** In the "Chrome & humanity" section:
  - replace the plain installments line with `Installments owed: {n}`, plus a repo clock of 6 pips (`●`/`○`, with `aria-label="Repo clock {c} of 6"`) when owed > 0;
  - in the chrome list, show a `Throttled` tag next to the throttled item and `Repo crew coming` next to `pending_repo`. Use text, not just colour.
- [ ] **Step 3:** `cd frontend && npm run lint && npm run build`, both clean.
- [ ] **Step 4: Commit:** `feat: debt, repo clock and throttle markers on the character sheet`

---

### Task 5: Live check, browser check, docs (controller)

- [ ] **Live** (GPU box, 300s): set a character to owe 5 with chrome. Force each strike (set `repo_actions=9, repo_clock=5`, act; repeat for strikes 2 and 3+) and check that Saeko is named in the narration and the repo is staged. Then, while owing, ask for work in Hanabira-chō: does Arakawa offer a gig and is `installments_paid` granted when it pays? Then ask Old Hara to unlock throttled chrome: is `unthrottle` used? Record n and errors.
- [ ] **Browser** (headless Chrome over CDP, scripted narrator that emits a throttle state via the fake turn): the sheet shows owed, the pips, and the Throttled and Repo markers. Take a screenshot.
- [ ] **Docs:** a README note on chrome debt; a ROADMAP `17b. **Debt and the street**` entry with results and n; deferred to 17c: utsusemi.
- [ ] **Commit:** `docs: record Phase 17b (debt and the street) and its verification`. Merge and push per the owner's standing instruction.
