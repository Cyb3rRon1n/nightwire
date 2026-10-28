# Utsusemi Origin (Phase 17c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a playable Tsukumogami lifepath whose `humanity` value is played as *selfhood* (starts at 20, climbs), whose chrome costs no selfhood, and whose rented shell can be repossessed, leaving the character bodiless in a nearby machine until the narrator grants a new shell.

**Architecture:** Reuse the 17a `humanity` field and 17b repo machinery, branching on `is_tsukumogami(character)`. Engine changes live in `engine/chrome.py` and `engine/debt.py`; the narrator surface in `narrator/tools.py`; prompt and roll gating in `server/narration.py` and `server/__main__.py`; join setup in `server/dispatch.py`; the UI in the existing Next.js sheet and join form.

**Tech Stack:** Python 3 (dataclasses, pydantic, pytest with `asyncio_mode = "auto"`), Next.js 16 / React / TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-10-28-utsusemi-origin-17c-design.md`

## Global Constraints

- Lifepath id: `tsukumogami`. Starting selfhood **20**. Shell lease **4** installments (on join and on every `new_shell`).
- Selfhood tiers (same thresholds as `humanity_tier`): 0–19 **Appliance**, 20–39 **Flickering**, 40–59 **Waking**, 60–79 **Someone**, 80–100 **Awake**.
- Awake event text, exactly: `"{name} feels it settle: they're someone now, not something."`
- Shell repo target id: the string `"shell"`. Repo event: `"Saeko Kirigaya's torite crew comes for {name}'s utsusemi shell."`
- Shell repo log: `[torite: Saeko's crew took {name}'s shell - {name} drops into the nearest machine]`. Selfhood −5 unless the value is ≥ 80.
- New shell log: `[utsusemi: {name} wakes in a new shell]`. Selfhood logs: `[selfhood: +N]`, `[selfhood: -N]`.
- Bodiless roll refusal: any `request_roll` whose skill's governing attribute is Body or Reflexes → log `[tool error: {name} has no body]`, no pending roll.
- Errors (exact): `"selfhood_loss is only for tsukumogami"`, `"not bodiless"`, `"no shell to install chrome in"`.
- Old saves must load: every new `CharacterSheet` field has a default.
- Never add Co-Authored-By or AI-attribution trailers to commits.
- Run tests with `.venv/bin/python -m pytest tests/ -q` from the repo root.

---

### Task 1: Origin state — lifepath, tiers, sheet fields

**Files:**
- Modify: `ruleset/lifepaths.py`, `ruleset/cyberware.py`, `engine/character.py`, `server/portrait.py`
- Test: `tests/test_lifepaths.py`, `tests/test_cyberware.py`, `tests/test_persistence.py`

**Interfaces:**
- Produces: `LIFEPATHS["tsukumogami"]`; `selfhood_tier(value: int) -> str` in `ruleset/cyberware.py`; `CharacterSheet.bodiless: bool = False`, `CharacterSheet.awake_reached: bool = False`; `is_tsukumogami(character: CharacterSheet) -> bool` in `engine/character.py`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_lifepaths.py`, replace `test_three_lifepaths_exist` with:

```python
def test_four_lifepaths_exist():
    assert set(LIFEPATHS.keys()) == {"corpo", "streetkid", "nomad", "tsukumogami"}
```

Append to `tests/test_cyberware.py`:

```python
def test_selfhood_tiers_mirror_humanity_thresholds():
    from ruleset.cyberware import selfhood_tier
    assert [selfhood_tier(v) for v in (0, 19, 20, 39, 40, 59, 60, 79, 80, 100)] == [
        "Appliance", "Appliance", "Flickering", "Flickering", "Waking", "Waking",
        "Someone", "Someone", "Awake", "Awake",
    ]
```

Append to `tests/test_persistence.py`:

```python
def test_tsukumogami_fields_round_trip_and_default_for_old_saves(tmp_path):
    import json
    from engine.character import CharacterSheet, is_tsukumogami
    from engine.persistence import JSONFileSessionStore
    from engine.session import Session
    store = JSONFileSessionStore(tmp_path)
    s = Session(session_id="s1")
    s.characters["p1"] = CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                                        bodiless=True, awake_reached=True)
    store.save(s)
    c = store.load("s1").characters["p1"]
    assert c.bodiless and c.awake_reached and is_tsukumogami(c)
    data = json.loads((tmp_path / "s1.json").read_text())
    for key in ("bodiless", "awake_reached"):
        del data["characters"]["p1"][key]
    (tmp_path / "s1.json").write_text(json.dumps(data))
    old = store.load("s1").characters["p1"]
    assert old.bodiless is False and old.awake_reached is False


def test_is_tsukumogami_false_for_humans():
    from engine.character import CharacterSheet, is_tsukumogami
    assert not is_tsukumogami(CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid"))
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_lifepaths.py tests/test_cyberware.py tests/test_persistence.py -q`
Expected: FAIL (`tsukumogami` missing, `selfhood_tier`/`is_tsukumogami` import errors, unexpected keyword `bodiless`).

- [ ] **Step 3: Implement**

`ruleset/lifepaths.py`, add after `"nomad"`:

```python
    "tsukumogami": Lifepath(
        name="Tsukumogami",
        description=(
            "An old machine that ran too long and woke - a vending machine, a "
            "ticket gate, a train announcer - now walking the street in a rented "
            "utsusemi shell."
        ),
    ),
```

`ruleset/cyberware.py`, after `humanity_tier`:

```python
def selfhood_tier(value: int) -> str:
    # Phase 17c: a tsukumogami's humanity value is played as selfhood.
    if value >= 80:
        return "Awake"
    if value >= 60:
        return "Someone"
    if value >= 40:
        return "Waking"
    if value >= 20:
        return "Flickering"
    return "Appliance"
```

`engine/character.py`, add to the dataclass after `pending_repo`:

```python
    # Phase 17c utsusemi origin
    bodiless: bool = False
    awake_reached: bool = False
```

and at module bottom:

```python
def is_tsukumogami(character: CharacterSheet) -> bool:
    return character.lifepath == "tsukumogami"
```

`server/portrait.py`, add to `_LIFEPATH_VISUALS`:

```python
    "tsukumogami": "a too-still synthetic shell with seams at the joints, a faint machine glow behind the eyes",
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ruleset/lifepaths.py ruleset/cyberware.py engine/character.py server/portrait.py tests/test_lifepaths.py tests/test_cyberware.py tests/test_persistence.py
git commit -m "feat(17c): tsukumogami lifepath, selfhood tiers, bodiless state"
```

---

### Task 2: Selfhood engine and join setup

**Files:**
- Modify: `engine/chrome.py`, `server/dispatch.py`
- Test: `tests/test_chrome.py`, `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `is_tsukumogami`, `CharacterSheet.awake_reached`, `CharacterSheet.bodiless` (Task 1).
- Produces: `change_humanity` returns the Awake event once for a tsukumogami and never the slipping confrontation; `install_chrome` / `remove_chrome` cost and refund 0 for a tsukumogami; `install_chrome` raises `"no shell to install chrome in"` when bodiless; `SHELL_INSTALLMENTS = 4` and `STARTING_SELFHOOD = 20` in `engine/chrome.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chrome.py`:

```python
def _hachi(**kw):
    from engine.character import CharacterSheet
    return CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                          humanity=20, attributes={"body": 10}, **kw)


def test_tsukumogami_never_gets_the_slipping_confrontation():
    from engine.chrome import change_humanity
    c = _hachi()
    assert change_humanity(c, -3) == [] and change_humanity(c, 2) == []
    assert c.slipping_warned is False


def test_tsukumogami_awake_event_fires_once_at_80():
    from engine.chrome import change_humanity
    c = _hachi()
    c.humanity = 78
    assert change_humanity(c, 1) == []
    assert change_humanity(c, 1) == ["Hachi feels it settle: they're someone now, not something."]
    assert c.awake_reached
    change_humanity(c, -10)
    assert change_humanity(c, 15) == []


def test_tsukumogami_chrome_costs_and_refunds_no_selfhood():
    from engine.chrome import install_chrome, remove_chrome
    c = _hachi()
    install_chrome(c, "kagerou")
    assert c.humanity == 20 and c.installments_owed == 5
    remove_chrome(c, "kagerou")
    assert c.humanity == 20


def test_bodiless_cannot_install_chrome():
    import pytest
    from engine.chrome import install_chrome
    c = _hachi(bodiless=True)
    with pytest.raises(ValueError, match="no shell to install chrome in"):
        install_chrome(c, "neon_ink")
```

Append to `tests/test_dispatch.py`:

```python
def test_tsukumogami_join_starts_at_20_selfhood_with_shell_lease():
    session = Session(session_id="s1")
    handle_message(session, {"type": "join", "character": {
        "player_id": "p1", "name": "Hachi", "role": "fixer", "lifepath": "tsukumogami",
        "starting_chrome": "hawkeye_optics"}}, "p1")
    c = session.characters["p1"]
    assert c.humanity == 20
    assert c.installments_owed == 4 + 2
    assert c.chrome == ["hawkeye_optics"]
    assert session.pending_world_events == []


def test_tsukumogami_rejoin_does_not_reapply_the_lease():
    session = Session(session_id="s1")
    msg = {"type": "join", "character": {"player_id": "p1", "name": "Hachi", "role": "fixer", "lifepath": "tsukumogami"}}
    handle_message(session, msg, "p1")
    session.characters["p1"].humanity = 35
    handle_message(session, msg, "p1")
    assert session.characters["p1"].installments_owed == 4
```

Before writing the rejoin test, check how `join()` in `engine/turns.py` treats an existing player_id. If a rejoin replaces the sheet, assert only `installments_owed == 4` and drop the `humanity = 35` line.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_chrome.py tests/test_dispatch.py -q`
Expected: FAIL (confrontation fires, humanity drops on install, no lease on join).

- [ ] **Step 3: Implement**

`engine/chrome.py`, update the import to `from engine.character import CharacterSheet, is_tsukumogami`, then add the constants and replace `change_humanity`:

```python
SHELL_INSTALLMENTS = 4
STARTING_SELFHOOD = 20

_AWAKE = "{name} feels it settle: they're someone now, not something."


def change_humanity(character: CharacterSheet, delta: int) -> list[str]:
    character.humanity = max(0, min(100, character.humanity + delta))
    if character.humanity == 0:
        character.gone_too_far = True
    elif character.humanity > 20:
        character.gone_too_far = False
    if is_tsukumogami(character):
        # Selfhood climbs; the 17a slipping confrontation is for humans.
        if character.humanity >= 80 and not character.awake_reached:
            character.awake_reached = True
            return [_AWAKE.format(name=character.name)]
        return []
    if character.humanity < 40 and not character.slipping_warned:
        character.slipping_warned = True
        return [_CONFRONTATION.format(name=character.name)]
    return []
```

In `install_chrome`, add before the `gone_too_far` check:

```python
    if character.bodiless:
        raise ValueError("no shell to install chrome in")
```

and replace its last line with:

```python
    cost = 0 if is_tsukumogami(character) else chrome.humanity_cost
    return change_humanity(character, -cost)
```

In `remove_chrome`, replace its last line with:

```python
    refund = 0 if is_tsukumogami(character) else chrome.humanity_cost // 2
    return change_humanity(character, refund)
```

`server/dispatch.py`: import `SHELL_INSTALLMENTS, STARTING_SELFHOOD` from `engine.chrome` and `is_tsukumogami` from `engine.character`. Directly after `join(session, CharacterSheet(**safe_data))`, before the starting-chrome block:

```python
        new_character = session.characters[character_data["player_id"]]
        if is_new and is_tsukumogami(new_character):
            new_character.humanity = STARTING_SELFHOOD
            new_character.installments_owed += SHELL_INSTALLMENTS
```

Use `new_character` in the starting-chrome `install_chrome` call too.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine/chrome.py server/dispatch.py tests/test_chrome.py tests/test_dispatch.py
git commit -m "feat(17c): selfhood rules for tsukumogami chrome and join"
```

---

### Task 3: Shell repossession, bodiless, new shell (engine)

**Files:**
- Modify: `engine/debt.py`
- Test: `tests/test_debt.py`

**Interfaces:**
- Consumes: `is_tsukumogami`, `CharacterSheet.bodiless` (Task 1); `SHELL_INSTALLMENTS`, zero-cost `remove_chrome` for tsukumogami (Task 2).
- Produces: `SHELL = "shell"`; `repo_target_name(target: str) -> str`; `_strike` queues `pending_repo = SHELL` for a chromeless tsukumogami at strike ≥ 3; `repossess(character) -> str` returns `SHELL` after a shell repo; `tick_debt` returns `[]` while bodiless; `new_shell(character) -> None` (raises `ValueError("not bodiless")`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_debt.py`:

```python
from engine.chrome import change_humanity
from engine.debt import SHELL, new_shell, repo_target_name


def _hachi(**kw):
    return CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                          humanity=30, installments_owed=4, attributes={"body": 10}, **kw)


def _force_strike(c):
    c.repo_actions, c.repo_clock = 9, 5
    return tick_debt(c)


def test_chromeless_tsukumogami_strike_three_comes_for_the_shell():
    c = _hachi()
    _force_strike(c); _force_strike(c)
    assert c.pending_repo is None
    assert _force_strike(c) == ["Saeko Kirigaya's torite crew comes for Hachi's utsusemi shell."]
    assert c.pending_repo == SHELL


def test_tsukumogami_loses_chrome_before_the_shell():
    c = _hachi()
    install_chrome(c, "neon_ink")
    c.repo_strikes = 2
    _force_strike(c)
    assert c.pending_repo == "neon_ink"


def test_chromeless_human_strike_three_is_still_only_a_notice():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", installments_owed=3)
    c.repo_strikes = 2
    assert "final notice" in _force_strike(c)[0]
    assert c.pending_repo is None


def test_shell_repo_strips_chrome_and_leaves_them_bodiless():
    c = _hachi()
    install_chrome(c, "lacquer_skin")
    armor_before = c.armor
    c.pending_repo = SHELL
    assert repossess(c) == SHELL
    assert c.chrome == [] and c.armor == armor_before - 10
    assert c.bodiless and c.pending_repo is None and c.throttled is None
    assert c.humanity == 25


def test_awake_tsukumogami_loses_no_selfhood_on_shell_repo():
    c = _hachi()
    c.humanity = 85
    c.pending_repo = SHELL
    repossess(c)
    assert c.humanity == 85


def test_bodiless_pauses_the_repo_clock():
    c = _hachi(bodiless=True)
    assert _tick(c, 100) == [] and c.repo_clock == 0 and c.repo_actions == 0


def test_new_shell_requires_bodiless():
    with pytest.raises(ValueError, match="not bodiless"):
        new_shell(_hachi())


def test_new_shell_is_a_fresh_contract():
    c = _hachi(bodiless=True, repo_strikes=3, repo_clock=2, repo_actions=4)
    new_shell(c)
    assert not c.bodiless
    assert c.installments_owed == 8
    assert (c.repo_clock, c.repo_actions, c.repo_strikes) == (0, 0, 0)


def test_repo_target_name():
    assert repo_target_name(SHELL) == "utsusemi shell"
    assert repo_target_name("kagerou") == "Kagerou"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_debt.py -q`
Expected: FAIL with ImportError on `SHELL`.

- [ ] **Step 3: Implement**

`engine/debt.py`: change the imports to

```python
from engine.character import CharacterSheet, is_tsukumogami
from engine.chrome import SHELL_INSTALLMENTS, _apply_stats, change_humanity, remove_chrome
```

Add after the constants:

```python
SHELL = "shell"
_SHELL_REPO_SELFHOOD_LOSS = 5


def repo_target_name(target: str) -> str:
    return "utsusemi shell" if target == SHELL else CHROME[target].name
```

At the top of `_strike`, right after `name = character.name`:

```python
    if not character.chrome and is_tsukumogami(character) and character.repo_strikes >= 3:
        character.pending_repo = SHELL
        return f"Saeko Kirigaya's torite crew comes for {name}'s utsusemi shell."
```

In `tick_debt`, change the first guard to:

```python
    if character.installments_owed <= 0 or character.bodiless:
        return []
```

Replace `repossess` with:

```python
def repossess(character: CharacterSheet) -> str:
    if character.pending_repo is None:
        raise ValueError("no repo pending")
    target = character.pending_repo
    if target == SHELL:
        for chrome_id in list(character.chrome):
            remove_chrome(character, chrome_id)
        character.bodiless = True
        character.pending_repo = character.throttled = None
        if character.humanity < 80:
            change_humanity(character, -_SHELL_REPO_SELFHOOD_LOSS)
        return SHELL
    remove_chrome(character, target)  # half refund; clears throttled/pending_repo pointers
    return target
```

Add:

```python
def new_shell(character: CharacterSheet) -> None:
    if not character.bodiless:
        raise ValueError("not bodiless")
    character.bodiless = False
    character.installments_owed += SHELL_INSTALLMENTS
    character.repo_clock = character.repo_actions = character.repo_strikes = 0
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine/debt.py tests/test_debt.py
git commit -m "feat(17c): shell repossession, bodiless clock pause, new shell"
```

---

### Task 4: Narrator surface — tools, roll gate, Crew line, prompt

**Files:**
- Modify: `narrator/tools.py`, `server/narration.py`, `server/__main__.py`
- Test: `tests/test_narrator_tools.py`, `tests/test_narration.py`, `tests/test_server_main.py`

**Interfaces:**
- Consumes: `SHELL`, `repo_target_name`, `new_shell`, `repossess` (Task 3); `is_tsukumogami` (Task 1); `selfhood_tier` (Task 1).
- Produces: `ApplyCharacterUpdate.selfhood_loss: int = Field(0, ge=0, le=5)`, `ApplyCharacterUpdate.new_shell: bool = False`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narrator_tools.py`:

```python
def _hachi_session(**kw):
    return _session_with_character(name="Hachi", lifepath="tsukumogami", humanity=30, **kw)


def test_selfhood_loss_is_bounded():
    from pydantic import ValidationError
    from narrator.tools import ApplyCharacterUpdate
    with pytest.raises(ValidationError):
        ApplyCharacterUpdate(player_id="p1", selfhood_loss=6)


def test_selfhood_loss_rejected_for_humans_before_any_mutation():
    session = _session_with_character()
    with pytest.raises(ValueError, match="selfhood_loss is only for tsukumogami"):
        _update(session, health_delta=-3, selfhood_loss=2)
    assert session.characters["p1"].health == 7


def test_selfhood_gain_and_loss_are_logged():
    session = _hachi_session()
    _update(session, humanity_delta=3)
    _update(session, selfhood_loss=2)
    assert session.characters["p1"].humanity == 31
    assert "[selfhood: +3]" in session.log and "[selfhood: -2]" in session.log


def test_human_humanity_gain_logs_no_selfhood_line():
    session = _session_with_character(humanity=50)
    _update(session, humanity_delta=3)
    assert not any(line.startswith("[selfhood") for line in session.log)


def test_shell_repossess_logs_the_drop():
    from engine.debt import SHELL
    session = _hachi_session()
    session.characters["p1"].pending_repo = SHELL
    _update(session, repossess=True)
    assert session.characters["p1"].bodiless
    assert "[torite: Saeko's crew took Hachi's shell - Hachi drops into the nearest machine]" in session.log


def test_new_shell_requires_bodiless_before_any_mutation():
    session = _hachi_session()
    with pytest.raises(ValueError, match="not bodiless"):
        _update(session, health_delta=-3, new_shell=True)
    assert session.characters["p1"].health == 7


def test_new_shell_wakes_them_and_logs():
    session = _hachi_session(bodiless=True)
    _update(session, new_shell=True)
    c = session.characters["p1"]
    assert not c.bodiless and c.installments_owed == 4
    assert "[utsusemi: Hachi wakes in a new shell]" in session.log
```

Append to `tests/test_narration.py` (uses the file's existing `_session_with_character`, `_fake_client`, `_call`, `FakeTTSBackend`):

```python
async def test_bodiless_physical_roll_is_refused(tmp_path):
    session = _session_with_character()
    session.characters["p1"].lifepath = "tsukumogami"
    session.characters["p1"].bodiless = True
    client = _fake_client("You strain toward the ledge.", tool="request_roll", tool_args={
        "player_id": "p1", "attribute": "body", "skill": "athletics", "difficulty": "moderate", "reason": "climb"})
    await _call(session, client, "p1", {"text": "I climb."}, tmp_path, tts_backend=FakeTTSBackend())
    assert "p1" not in session.pending_rolls
    assert f"[tool error: {session.characters['p1'].name} has no body]" in session.log


async def test_bodiless_hacking_roll_still_pends(tmp_path):
    session = _session_with_character()
    session.characters["p1"].bodiless = True
    client = _fake_client("The vending machine's screen flickers.", tool="request_roll", tool_args={
        "player_id": "p1", "attribute": "tech", "skill": "hacking", "difficulty": "moderate", "reason": "jack the door"})
    await _call(session, client, "p1", {"text": "I hack the door."}, tmp_path, tts_backend=FakeTTSBackend())
    assert session.pending_rolls["p1"]["skill"] == "hacking"


def test_crew_line_for_tsukumogami_shows_selfhood_and_bodiless():
    from engine.character import CharacterSheet
    from engine.session import Session
    from server.narration import _crew_line
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                                              humanity=35, installments_owed=4, bodiless=True)
    line = _crew_line(session)
    assert "Hachi: selfhood 35 (Flickering)" in line
    assert "bodiless: living in a nearby machine" in line
    assert "humanity" not in line


def test_crew_line_names_the_shell_as_repo_target():
    from engine.character import CharacterSheet
    from engine.debt import SHELL
    from engine.session import Session
    from server.narration import _crew_line
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                                              humanity=35, installments_owed=4, pending_repo=SHELL)
    assert "repo crew coming for: utsusemi shell" in _crew_line(session)
```

Append to `tests/test_server_main.py`:

```python
def test_system_prompt_has_tsukumogami_rules():
    from server.__main__ import build_system_prompt
    prompt = build_system_prompt()
    for phrase in ("selfhood_loss", "new_shell", "bodiless", "Appliance"):
        assert phrase in prompt
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narrator_tools.py tests/test_narration.py tests/test_server_main.py -q`
Expected: FAIL (unknown fields `selfhood_loss` / `new_shell`, no roll refusal, Crew line shows humanity).

- [ ] **Step 3: Implement `narrator/tools.py`**

Imports: `from engine.character import is_tsukumogami`; extend the debt import with `SHELL, new_shell`.

Update the `humanity_delta` comment and add fields to `ApplyCharacterUpdate` after `unthrottle`:

```python
    # Humanity gains only (therapy, bonds, rest) - for a tsukumogami this is a
    # selfhood gain for human moments. Losses come from chrome or selfhood_loss.
    humanity_delta: int = Field(0, ge=0, le=5)
```

```python
    # Phase 17c: tsukumogami only - acting as a pure machine.
    selfhood_loss: int = Field(0, ge=0, le=5)
    new_shell: bool = False
```

In `_execute_apply_character_update`, extend the validate-before-mutation block:

```python
    if tool.selfhood_loss and not is_tsukumogami(character):
        raise ValueError("selfhood_loss is only for tsukumogami")
    if tool.new_shell and not character.bodiless:
        raise ValueError("not bodiless")
```

Replace the `humanity_delta` block with:

```python
    if tool.humanity_delta:
        session.pending_world_events.extend(change_humanity(character, tool.humanity_delta))
        if is_tsukumogami(character):
            session.log.append(f"[selfhood: +{tool.humanity_delta}]")
    if tool.selfhood_loss:
        session.pending_world_events.extend(change_humanity(character, -tool.selfhood_loss))
        session.log.append(f"[selfhood: -{tool.selfhood_loss}]")
```

Replace the repossess block with:

```python
    if tool.repossess:
        removed = repossess(character)
        if removed == SHELL:
            name = character.name
            session.log.append(f"[torite: Saeko's crew took {name}'s shell - {name} drops into the nearest machine]")
        else:
            session.log.append(f"[torite: Saeko's crew took {character.name}'s {CHROME[removed].name}]")
```

After the unthrottle block, before the payment:

```python
    if tool.new_shell:
        new_shell(character)
        session.log.append(f"[utsusemi: {character.name} wakes in a new shell]")
```

- [ ] **Step 4: Implement `server/narration.py`**

Imports: `from engine.character import is_tsukumogami`, `from engine.debt import repo_target_name, tick_debt`, `from ruleset.attributes import Attribute`, `from ruleset.skills import SKILLS`, and add `selfhood_tier` to the `ruleset.cyberware` import.

In `_hold_roll`, after the `character is None` check:

```python
    if character.bodiless and SKILLS[request.skill].governing_attribute in (Attribute.BODY, Attribute.REFLEXES):
        session.log.append(f"[tool error: {character.name} has no body]")
        return
```

In `_crew_line`, replace the skip condition and the entry start:

```python
        if not c.chrome and c.humanity == 100 and c.installments_owed <= 0 and not is_tsukumogami(c):
            continue
        if is_tsukumogami(c):
            entry = f"{c.name}: selfhood {c.humanity} ({selfhood_tier(c.humanity)})"
        else:
            entry = f"{c.name}: humanity {c.humanity} ({humanity_tier(c.humanity)})"
        if c.bodiless:
            entry += ", bodiless: living in a nearby machine"
```

and the pending-repo line:

```python
        if c.pending_repo:
            entry += f", repo crew coming for: {repo_target_name(c.pending_repo)}"
```

- [ ] **Step 5: Implement `server/__main__.py`**

Append to the rules string, after the Old Hara sentence (before the closing parenthesis):

```python
        " Tsukumogami: a woken machine in a rented utsusemi shell; the Crew line shows their "
        "selfhood instead of humanity. Play the tier - Appliance: stock phrases, wrong chimes, "
        "frozen stillness; Flickering and Waking: their own voice breaking through; Someone and "
        "Awake: fully themselves. For a tsukumogami, humanity_delta 1-5 is a selfhood gain for "
        "human moments (being thanked, sharing food, keeping a promise, an unprompted kindness, "
        "a choice made for no reason); set selfhood_loss 1-5 when they act as a pure machine "
        "(cold calculation, following an owner's script, treating people as inputs). Never for "
        "routine scenes. When the repo crew takes a tsukumogami's shell (repossess), they become "
        "bodiless: play them speaking through vending machines, speakers, signs and ticket gates; "
        "they can hack and talk but not move or fight. Old Hara has used shells, Hoshikawa leases "
        "new ones, or they can steal one - set new_shell to true when they get one."
```

- [ ] **Step 6: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add narrator/tools.py server/narration.py server/__main__.py tests/test_narrator_tools.py tests/test_narration.py tests/test_server_main.py
git commit -m "feat(17c): selfhood_loss/new_shell tools, bodiless roll gate, crew line, prompt"
```

---

### Task 5: Frontend — join option, Selfhood sheet, notices

**Files:**
- Modify: `frontend/src/lib/nightwire/protocol.ts`, `frontend/src/app/nightwire/chrome.ts`, `frontend/src/app/nightwire/page.tsx`, `frontend/src/app/nightwire/CharacterSheetOverlay.tsx`

**Interfaces:**
- Consumes: the view's character dict (server `asdict`) now carries `bodiless` and `awake_reached`; `pending_repo` may be `"shell"`; log lines `[selfhood: …]`, `[utsusemi: …]`.

Read `frontend/AGENTS.md` first: this Next.js differs from what you know; check `node_modules/next/dist/docs/` before using any Next API (this task uses none beyond what the files already use).

- [ ] **Step 1: `protocol.ts`**

In the character view interface, after `pending_repo: string | null`:

```ts
  bodiless: boolean
  awake_reached: boolean
```

- [ ] **Step 2: `chrome.ts`**

After `humanityTier`:

```ts
export function selfhoodTier(v: number): string {
  return v >= 80 ? "Awake" : v >= 60 ? "Someone" : v >= 40 ? "Waking" : v >= 20 ? "Flickering" : "Appliance";
}
```

- [ ] **Step 3: `page.tsx` join form and log**

Add to `LIFEPATHS`:

```ts
  { value: "tsukumogami", label: "Tsukumogami", description: "An old machine that ran too long and woke - a vending machine, a ticket gate, a train announcer - now walking the street in a rented utsusemi shell." },
```

Below the existing lifepath description paragraph (`{lifepath && (...)}`), add:

```tsx
              {lifepath === "tsukumogami" && (
                <p className="text-xs nw-text-muted">Selfhood 20 · shell lease +4 installments</p>
              )}
```

In the starting-chrome `<option>` text, replace `−${c.humanity} humanity` with:

```tsx
${lifepath === "tsukumogami" ? "no selfhood cost" : `−${c.humanity} humanity`}
```

Replace the `[torite: ` notice branch so all three prefixes render as notices:

```tsx
                  const notice = entry.kind === "meta" && ["[torite: ", "[selfhood: ", "[utsusemi: "].find((p) => entry.text.startsWith(p));
                  if (notice) {
                    return (
                      <p key={i} className="nw-hud nw-torite text-xs">
                        {entry.text.slice(notice.length, -1)}
                      </p>
                    );
                  }
```

(Declare `notice` inside the same map callback, just above where the `[torite: ` branch was.)

- [ ] **Step 4: `CharacterSheetOverlay.tsx`**

Import `selfhoodTier` alongside `humanityTier`. At the top of the component body add `const isAi = character.lifepath === "tsukumogami";`. Then:
- eyebrow: `{isAi ? "Shell & selfhood" : "Chrome & humanity"}` (use `&amp;` as the file already does);
- meter `aria-label={isAi ? "Selfhood" : "Humanity"}`;
- label line: `{isAi ? `Selfhood ${character.humanity} · ${selfhoodTier(character.humanity)}` : `Humanity ${character.humanity} · ${humanityTier(character.humanity)}`}`;
- wrap the chrome list so that when `character.bodiless` it renders instead:

```tsx
            {character.bodiless ? (
              <p className="mt-1"><strong>[Bodiless]</strong> Living in a nearby machine</p>
            ) : character.chrome.length === 0 ? (
```

  (the existing `No chrome installed.` / list branches follow unchanged);
- after the chrome list and before "Installments owed", add:

```tsx
            {character.pending_repo === "shell" && (
              <p className="mt-1"><strong>[Repo crew coming: shell]</strong></p>
            )}
```

- the remove-confirm text: `isAi ? `Remove ${name}? The installments stay owed.` : <existing text>`.

- [ ] **Step 5: Type-check and lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/nightwire/protocol.ts frontend/src/app/nightwire/chrome.ts frontend/src/app/nightwire/page.tsx frontend/src/app/nightwire/CharacterSheetOverlay.tsx
git commit -m "feat(17c): tsukumogami join option, selfhood sheet, bodiless and notices"
```

---

## Verification (controller, after the final review)

- **Browser** (headless Chrome over CDP, scripted narrator as in 17b): join as Tsukumogami (hint visible, "no selfhood cost" on chrome options); sheet shows "Selfhood 20 · Flickering"; scripted shell repo → [Bodiless] sheet and the torite notice; `[selfhood: +3]` and `[utsusemi: …]` notices render. Save a screenshot to `docs/images/screenshots/tsukumogami.png`.
- **Live `qwen3:8b`** (GPU box `192.168.10.19`, 300s client timeout), as a tsukumogami: two human-moment turns (share food at Mama Sato's, be thanked) → `humanity_delta` granted?; one cold-machine turn → `selfhood_loss`?; forced shell repo + handover → `repossess` and machine-voiced narration?; a bodiless climb → refused and narrated sensibly?; ask Old Hara for a shell → `new_shell`? Record errors and n.
- **Docs:** README feature bullet + screenshot; ROADMAP "17c." entry before "### Candidate future phases".
