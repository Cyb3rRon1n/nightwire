# Kuroshio World Bible Implementation Plan (Phase 14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the narrator a real setting: an always-on Kuroshio primer and glossary in the system prompt, plus up to 4 district and faction cards and a Scene line injected into each turn's prompt.

**Architecture:**
- **World data:** a TOML world file inside the `narrator` package.
- **Loader:** `narrator/world.py` loads and validates the file, exposes `World.system_block()`, and has a pure `select_cards()` function (location match first, then the most recent mention, whole-word and diacritic-insensitive, capped by count and character budget).
- **Prompt assembly:** `server/narration.py::_build_messages` appends a `Scene:` line and a `World notes:` block right before `Player action:`.
- **System prompt:** `server/__main__.py` appends the primer to it through a newly extracted `build_system_prompt()`.

**Tech Stack:** Python 3.11+ standard library (`tomllib`, `unicodedata`, `re`, `functools`), `pytest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-26-world-bible-design.md`

## Global Constraints

- No new dependencies. TOML is read with the standard library's `tomllib`.
- The world file lives at **`narrator/worlds/kuroshio.toml`**, not the spec's `world/kuroshio.toml`. The repo-root `world/` directory would not be included by `pip install .` (`[tool.setuptools.packages.find]` only includes `ruleset`, `engine`, `server` and `narrator`) or by the Dockerfile's `COPY` lines. Task 1 amends the spec to match.
- Limits, verbatim from the spec:
  - a card is at most **400** characters;
  - the primer plus the rendered glossary is at most **1,600** characters;
  - at most **4** cards per turn;
  - scan the last **6** non-bracket narrative lines;
  - `_WORLD_BUDGET_FRACTION = 0.06`;
  - `_VERBATIM_BUDGET_FRACTION` goes from 0.65 to **0.55**.
- Matching is whole-word, case-insensitive and diacritic-insensitive (`unicodedata` NFKD with combining marks stripped). A district matched by `session.location` always comes first.
- Names and aliases must be unique across all entries after normalization, or loading fails.
- No changes to tool schemas, `Session` fields, the frontend, or the persistence format.
- No "don't do X cliché" lines anywhere in the prompt. This is an owner decision: immersion over guardrails.
- Workspace rule: commit messages carry **no** `Co-Authored-By` or AI-attribution trailer. Commit directly to `main` (nightwire convention, with owner consent). Don't push without asking.
- Run tests from the repo root: `.venv/bin/python -m pytest tests/ -q`.

## File Structure

| File | Responsibility |
|---|---|
| `narrator/worlds/kuroshio.toml` (create) | World content: primer, glossary, 6 districts, 6 factions |
| `narrator/world.py` (create) | `WorldEntry`, `World`, `parse_world`, `load_world`, `kuroshio()`, `select_cards`, `_normalize` |
| `pyproject.toml` (modify) | Package-data so the TOML ships with `pip install .` |
| `server/narration.py` (modify) | `_WORLD_BUDGET_FRACTION`, `_VERBATIM_BUDGET_FRACTION` 0.55, `_scene_line`, the World and Scene blocks in `_build_messages` |
| `server/__main__.py` (modify) | Extract `build_system_prompt()`, which appends `kuroshio().system_block()` |
| `tests/test_world.py` (create) | Loader, validation and `select_cards` tests |
| `tests/test_narration.py` (modify) | Scene and World prompt tests; verbatim-budget comment updates |
| `tests/test_server_main.py` (modify) | System prompt contains the primer |
| `README.md`, `ROADMAP.md` (modify) | World section; Phase 14 entry after live verification |

---

### Task 1: World file, loader and validation

**Files:**
- Create: `narrator/worlds/kuroshio.toml`
- Create: `narrator/world.py`
- Modify: `pyproject.toml`
- Modify: `docs/superpowers/specs/2026-10-26-world-bible-design.md` (path amendment)
- Test: `tests/test_world.py`

**Interfaces:**
- Produces:
  - `WorldEntry(name: str, aliases: tuple[str, ...], card: str)`, a frozen dataclass.
  - `World(primer: str, glossary: dict[str, str], districts: tuple[WorldEntry, ...], factions: tuple[WorldEntry, ...])`, a frozen dataclass with `system_block() -> str`.
  - `parse_world(raw: dict) -> World`, which raises `ValueError`.
  - `load_world(path: Path) -> World`.
  - `kuroshio() -> World`, cached.
  - `_normalize(text: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_world.py`:

```python
import pytest

from narrator.world import World, WorldEntry, kuroshio, parse_world


def _raw(**overrides):
    raw = {
        "primer": "Setting: a test city.",
        "glossary": {"chrome": "cyberware"},
        "district": [{"name": "Ikebe Low", "aliases": ["Ikebe"], "card": "Ikebe Low is old alleys."}],
        "faction": [{"name": "Kuze-gumi", "aliases": ["Kuze"], "card": "The Kuze-gumi is a clan."}],
    }
    raw.update(overrides)
    return raw


def test_shipped_kuroshio_world_loads():
    world = kuroshio()

    assert len(world.districts) == 6
    assert len(world.factions) == 6
    assert "Kuroshio" in world.primer


def test_system_block_contains_primer_and_every_glossary_term():
    world = kuroshio()

    block = world.system_block()

    assert world.primer in block
    for term, definition in world.glossary.items():
        assert f"{term}: {definition}" in block


def test_parse_world_builds_entries():
    world = parse_world(_raw())

    assert world.districts == (WorldEntry("Ikebe Low", ("Ikebe",), "Ikebe Low is old alleys."),)
    assert world.factions[0].name == "Kuze-gumi"


def test_missing_primer_fails():
    with pytest.raises(ValueError, match="primer"):
        parse_world(_raw(primer=""))


def test_missing_card_fails():
    with pytest.raises(ValueError, match="card"):
        parse_world(_raw(district=[{"name": "Ikebe Low", "aliases": []}]))


def test_overlong_card_fails():
    with pytest.raises(ValueError, match="400"):
        parse_world(_raw(district=[{"name": "Ikebe Low", "aliases": [], "card": "x" * 401}]))


def test_duplicate_alias_across_entries_fails():
    raw = _raw(faction=[{"name": "Ikebe Gang", "aliases": ["ikebe"], "card": "A gang."}])

    with pytest.raises(ValueError, match="duplicates"):
        parse_world(raw)


def test_alias_that_only_differs_by_diacritics_counts_as_duplicate():
    raw = _raw(faction=[{"name": "Ōgane Heavy", "aliases": ["Ogane Heavy"], "card": "Arms."}])

    with pytest.raises(ValueError, match="duplicates"):
        parse_world(raw)


def test_overlong_primer_plus_glossary_fails():
    with pytest.raises(ValueError, match="1600"):
        parse_world(_raw(primer="x" * 1600))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_world.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'narrator.world'`

- [ ] **Step 3: Create the world file**

Create `narrator/worlds/kuroshio.toml`. The content is copied verbatim from the spec's "World content" section:

```toml
# Kuroshio - nightwire's world bible (Phase 14).
# Cards must be standalone (no pronouns pointing at other cards), <=400 chars.
# Names/aliases must be unique after lowercasing + stripping diacritics
# ("Ōgane" already matches "Ogane" - don't add re-spellings as aliases).

primer = """
Setting: Kuroshio, a Pacific megacity in Japan, 2089, named for the black ocean current that feeds its port. Five keiretsu houses built the city and financed the chrome that keeps its people working. Nearly everyone's chrome is on a payment plan, and torite repo crews take back what you can't pay for. Giri binds the city: favors are currency and everyone owes someone. The deep net, Yomi, holds the lingering data of the dead, tended by the Lantern Guild. Old machines that run too long sometimes wake as tsukumogami. Districts: Tenjō Heights, Hanabira-chō, Ikebe Low, Kuroshio Docks, The Loop, Yomi Line. When the party moves, set update_world location to a district name, then the specific spot (e.g. "Ikebe Low - Mama Sato's izakaya"). Tone: stylish, fast and darkly funny like a neon action film, but every piece of chrome costs something and the city always collects. Ground every scene in concrete sensory detail: rain, food, signage, engine noise, crowds, machine hum. Use Japanese words only from the glossary, naturally, without explaining them.
"""

[glossary]
chrome = "cyberware, any implant or cybernetic part"
chrome-ya = "a back-alley cyberware clinic, or the doctor who runs one"
torite = "a repo crew that reclaims unpaid chrome, by force if needed"
giri = "obligation; a debt of favor you owe someone"
keiretsu = "one of the five corporate houses that run the city"
oyabun = "the boss of a yakuza clan"
Yomi = "the deep net, where the data of the dead lingers"
"going to the lantern" = "dying"
tsukumogami = "an old machine that woke up as a rogue AI"

[[district]]
name = "Tenjō Heights"
aliases = ["Tenjo", "the Heights"]
card = "Tenjō Heights is the keiretsu high city: towers linked by sky bridges above the smog line, filtered air sold by the breath, silent maglev pods, staff who smile on contract. Held by Hoshikawa Keiretsu and Ōgane Heavy security; outsiders need a sponsor badge. Hazard: every camera feeds Ōgane, and trespass is billed. Hook: a junior Hoshikawa auditor wants to sell the debt ledgers."

[[district]]
name = "Hanabira-chō"
aliases = ["Hanabira"]
card = "Hanabira-chō is the pleasure district: idol streams on every wall, host clubs, the roar of pachinko halls, capsule love hotels, yakitori smoke. Held by the Kuze-gumi, who collect from every door. Hazard: debts run up here are sold to Hoshikawa by morning. Hook: a rising stream idol is hiding chrome she never paid for, and the torite are circling."

[[district]]
name = "Ikebe Low"
aliases = ["Ikebe", "the Low"]
card = "Ikebe Low is old wooden-era alleys under the expressway: lantern-lit izakaya, family chrome-ya clinics behind noren curtains, alley shrines strung with prayer-cable. Nobody holds it; the Kuze-gumi, Kaminari Run and Hoshikawa repo men all work its streets. Hazard: power cuts drop whole blocks into darkness. Hook: an old chrome-ya installs chrome off the books, with no payment plan and no repo."

[[district]]
name = "Kuroshio Docks"
aliases = ["the Docks", "the port"]
card = "Kuroshio Docks is container canyons and gantry cranes, black water slapping the piers, rusting ships turned into offshore data havens. Ōgane Heavy guards it on paper; smugglers pay the right shift. Hazard: automated cranes do not stop for people. Hook: a container arrived with no manifest, and something inside is still running."

[[district]]
name = "The Loop"
aliases = ["Loop"]
card = "The Loop is the elevated ring expressway around the city, with arcade towers glowing at every off-ramp. Every night Kaminari Run bikes race it, light-trails bending through the rain. Kaminari Run holds it after dark; Ōgane traffic drones hold it by day. Hazard: speed duels settle disputes here, and the loser forfeits their ride. Hook: someone is racing the Loop on a bike with no rider."

[[district]]
name = "Yomi Line"
aliases = ["the sealed line", "the dead line"]
card = "The Yomi Line is a subway line sealed after an AI incident twenty years ago. Station signs still announce trains that never come, and the net is so thick that the dead speak through the platform speakers. Tsukumogami nest in the ticket machines and the dead trains. Hazard: stay too long and Yomi seeps into your chrome. Hook: the Lantern Guild wants something carried out of the deepest station."

[[faction]]
name = "Hoshikawa Keiretsu"
aliases = ["Hoshikawa"]
card = "Hoshikawa Keiretsu financed the city's chrome and owns its debt. Wants: everyone on a payment plan, forever. Method: polite, patient and total, through contract law, credit scores and torite crews hired through the Kuze-gumi. Rival of Ōgane Heavy for control of Tenjō Heights. Narrate them with soft voices, perfect manners and the quiet threat of a balance due."

[[faction]]
name = "Ōgane Heavy"
aliases = ["Ogane"]
card = "Ōgane Heavy is an arms maker and the city's contracted police. Wants: order it can bill for. Method: drones, checkpoints, armored response teams and a fine for everything. Allied with Hoshikawa in public, competing with it in private. Narrate them as heavy boots, visor glare and an invoice after every arrest."

[[faction]]
name = "Kuze-gumi"
aliases = ["Kuze"]
card = "The Kuze-gumi is an old yakuza clan gone half-corporate; its oyabun sits on a Hoshikawa subsidiary board. Wants: to stay relevant as the city goes corporate. Method: protection rackets in Hanabira-chō and repo contracts for Hoshikawa. Its old members resent the suits. Narrate them through tradition worn thin: formal greetings, tattoos under business suits, very old grudges."

[[faction]]
name = "Kaminari Run"
aliases = ["Kaminari"]
card = "Kaminari Run is a bōsōzoku biker gang that rules the Loop at night. Wants: speed, and freedom from chrome debt; they ride on unpaid chrome and fight the torite. Method: races, swarm raids and loyalty to the crew above all. Enemies of the Kuze-gumi repo crews. Narrate them loud, young and flamboyant: painted jackets, engine roar, bravado hiding fear."

[[faction]]
name = "Lantern Guild"
aliases = ["lantern-keepers", "lantern-keeper", "Yomi"]
card = "The Lantern Guild is the licensed union that tends the dead in Yomi, the deep net. Wants: the dead left in peace, and the Guild left alone. Method: they hear what the dead remember and trade those secrets for favors, never money. Neutral, and every faction needs them sooner or later. Narrate them calm and soft-spoken, with paper lanterns and unhurried certainty."

[[faction]]
name = "Tsukumogami"
aliases = ["rogue AI", "rogue AIs"]
card = "Tsukumogami are old machines that ran too long and woke: vending machines, ticket gates, train AIs, traffic systems. Each wants something strange and specific: to be thanked, to finish a last route, to be left running. They can be bargained with, tricked or fled. Narrate them as uncanny: chimes that sound wrong, screens that answer back, machines that move when no one is looking."
```

- [ ] **Step 4: Write the loader**

Create `narrator/world.py`:

```python
"""Nightwire's world bible: an always-on primer plus district/faction cards
selected per turn - see docs/superpowers/specs/2026-10-26-world-bible-design.md."""

import functools
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_KUROSHIO_PATH = Path(__file__).parent / "worlds" / "kuroshio.toml"
# Heuristic sizes for an 8B narrator (no published authoritative numbers -
# see the spec's research section); live verification is the real check.
_MAX_CARD_CHARS = 400
_MAX_SYSTEM_BLOCK_CHARS = 1600


@dataclass(frozen=True)
class WorldEntry:
    name: str
    aliases: tuple[str, ...]
    card: str


@dataclass(frozen=True)
class World:
    primer: str
    glossary: dict[str, str]
    districts: tuple[WorldEntry, ...]
    factions: tuple[WorldEntry, ...]

    def system_block(self) -> str:
        terms = "\n".join(f"{term}: {definition}" for term, definition in self.glossary.items())
        return f"{self.primer}\nGlossary:\n{terms}"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _entries(raw: dict, kind: str) -> tuple[WorldEntry, ...]:
    entries = []
    for item in raw.get(kind, []):
        for key in ("name", "card"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"world {kind} entry {item.get('name', item)!r} is missing '{key}'")
        card = item["card"].strip()
        if len(card) > _MAX_CARD_CHARS:
            raise ValueError(f"world {kind} {item['name']!r} card is {len(card)} chars (max {_MAX_CARD_CHARS})")
        entries.append(WorldEntry(item["name"], tuple(item.get("aliases", [])), card))
    return tuple(entries)


def parse_world(raw: dict) -> World:
    primer = raw.get("primer")
    if not isinstance(primer, str) or not primer.strip():
        raise ValueError("world is missing 'primer'")
    world = World(primer.strip(), dict(raw.get("glossary", {})), _entries(raw, "district"), _entries(raw, "faction"))
    block_len = len(world.system_block())
    if block_len > _MAX_SYSTEM_BLOCK_CHARS:
        raise ValueError(f"world primer + glossary is {block_len} chars (max {_MAX_SYSTEM_BLOCK_CHARS})")
    seen: dict[str, str] = {}
    for entry in world.districts + world.factions:
        for key in (entry.name, *entry.aliases):
            normalized = _normalize(key)
            if normalized in seen:
                raise ValueError(f"world name/alias {key!r} ({entry.name}) duplicates one used by {seen[normalized]}")
            seen[normalized] = entry.name
    return world


def load_world(path: Path) -> World:
    with path.open("rb") as f:
        return parse_world(tomllib.load(f))


@functools.cache
def kuroshio() -> World:
    return load_world(_KUROSHIO_PATH)
```

- [ ] **Step 5: Ship the TOML with the package**

In `pyproject.toml`, add this after the `[tool.setuptools.packages.find]` block:

```toml
[tool.setuptools.package-data]
narrator = ["worlds/*.toml"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_world.py -q`
Expected: PASS, 9 passed.

If `test_overlong_primer_plus_glossary_fails` or the shipped world fails a length check, the content is off. Measure it with `.venv/bin/python -c "from narrator.world import kuroshio; w=kuroshio(); print(len(w.system_block()), max(len(e.card) for e in w.districts+w.factions))"`, then report back. Don't raise the limits.

- [ ] **Step 7: Verify that packaging includes the TOML**

Run:
```bash
d=$(mktemp -d) && .venv/bin/python -m pip wheel . --no-deps -q -w "$d" && unzip -l "$d"/nightwire-*.whl | grep kuroshio.toml; rm -rf "$d"
```
Expected: one line listing `narrator/worlds/kuroshio.toml`.

- [ ] **Step 8: Amend the spec's file path**

In `docs/superpowers/specs/2026-10-26-world-bible-design.md`, replace every `world/kuroshio.toml` with `narrator/worlds/kuroshio.toml`. Then add this sentence right after the `### Storage` heading line:

```
(Amended 2026-10-26 during planning: it lives inside the `narrator` package so `pip install .` and the Dockerfile's `COPY narrator/` ship it; a repo-root `world/` would be left out of both.)
```

- [ ] **Step 9: Run the full suite and commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (297 existing + 9 new).

```bash
git add narrator/world.py narrator/worlds/kuroshio.toml pyproject.toml tests/test_world.py docs/superpowers/specs/2026-10-26-world-bible-design.md
git commit -m "feat: Kuroshio world file and validated world-bible loader"
```

---

### Task 2: `select_cards`

**Files:**
- Modify: `narrator/world.py`
- Test: `tests/test_world.py`

**Interfaces:**
- Consumes: `World`, `WorldEntry`, `_normalize`, `kuroshio()` (Task 1); `engine.session.Session` (its `location: str | None` and `log: list[str]` fields).
- Produces: `select_cards(world: World, session: Session, action_text: str, budget_chars: int) -> list[str]`, the selected card texts in priority order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_world.py`:

```python
from engine.session import Session
from narrator.world import select_cards


def _card(world, name):
    return next(e.card for e in world.districts + world.factions if e.name == name)


def test_location_district_comes_first_even_if_others_mentioned_more_recently():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low - Mama Sato's izakaya", log=["The Kuze-gumi enforcer smiles."])

    cards = select_cards(world, session, "I ride out toward the Loop.", budget_chars=10_000)

    assert cards[0] == _card(world, "Ikebe Low")
    assert _card(world, "The Loop") in cards
    assert _card(world, "Kuze-gumi") in cards


def test_matching_is_diacritic_insensitive():
    world = kuroshio()
    session = Session(session_id="s", location="Tenjo Heights - lobby")

    assert select_cards(world, session, "I wait.", budget_chars=10_000) == [_card(world, "Tenjō Heights")]


def test_matching_is_whole_word():
    world = kuroshio()
    session = Session(session_id="s")

    assert select_cards(world, session, "I look for a loophole in the contract.", budget_chars=10_000) == []


def test_aliases_match():
    world = kuroshio()
    session = Session(session_id="s")

    cards = select_cards(world, session, "I call my contact in the Kuze about Ogane drones.", budget_chars=10_000)

    assert cards == [_card(world, "Ōgane Heavy"), _card(world, "Kuze-gumi")]


def test_action_text_mentions_rank_before_older_log_mentions():
    world = kuroshio()
    session = Session(session_id="s", log=["We left Hanabira-chō behind.", "Rain on the Docks."])

    cards = select_cards(world, session, "I head for the Loop.", budget_chars=10_000)

    assert cards == [_card(world, "The Loop"), _card(world, "Kuroshio Docks"), _card(world, "Hanabira-chō")]


def test_bracket_lines_and_lines_older_than_scan_depth_are_ignored():
    world = kuroshio()
    old = ["Hanabira-chō was loud."] + [f"filler {i}" for i in range(6)]
    session = Session(session_id="s", log=old + ["[image: the Loop at night]"])

    assert select_cards(world, session, "I wait.", budget_chars=10_000) == []


def test_at_most_four_cards():
    world = kuroshio()
    session = Session(session_id="s")

    cards = select_cards(world, session, "Ikebe, the Loop, the Docks, Hanabira and Tenjo.", budget_chars=10_000)

    assert len(cards) == 4


def test_budget_limits_cards():
    world = kuroshio()
    session = Session(session_id="s")
    first = _card(world, "Ikebe Low")

    cards = select_cards(world, session, "Ikebe and the Loop.", budget_chars=len(first) + 1)

    assert cards == [first]


def test_no_match_returns_empty():
    session = Session(session_id="s", location="somewhere unnamed")

    assert select_cards(kuroshio(), session, "I wait.", budget_chars=10_000) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_world.py -q`
Expected: FAIL with `ImportError: cannot import name 'select_cards'`

- [ ] **Step 3: Implement**

In `narrator/world.py`:

Add `import re` to the imports, then add `from engine.session import Session` below the standard-library imports.

Add these constants under `_MAX_SYSTEM_BLOCK_CHARS`:

```python
_MAX_CARDS = 4
_SCAN_LINES = 6
```

Append:

```python
def _mentions(entry: WorldEntry, normalized_text: str) -> bool:
    return any(
        re.search(rf"\b{re.escape(_normalize(key))}\b", normalized_text)
        for key in (entry.name, *entry.aliases)
    )


def select_cards(world: World, session: Session, action_text: str, budget_chars: int) -> list[str]:
    """Cards for this turn: the current location's district first, then
    districts/factions mentioned in the action or recent narrative, most
    recent first. Capped by count and by budget_chars."""
    ordered: list[WorldEntry] = []
    location = _normalize(session.location or "")
    if location:
        ordered += [d for d in world.districts if _mentions(d, location)][:1]
    # [image: ...]-style lines are UI annotations, not narrative (same filter
    # server/narration.py applies).
    narrative = [line for line in session.log if not line.startswith("[")][-_SCAN_LINES:]
    for text in (action_text, *reversed(narrative)):
        normalized = _normalize(text)
        for entry in world.districts + world.factions:
            if entry not in ordered and _mentions(entry, normalized):
                ordered.append(entry)
    cards: list[str] = []
    total = 0
    for entry in ordered[:_MAX_CARDS]:
        total += len(entry.card) + 1
        if total > budget_chars:
            break
        cards.append(entry.card)
    return cards
```

Notes for the implementer:
- In `test_aliases_match`, both entries come from the same text, so their order is file order: districts first, then factions in TOML order. That puts Ōgane Heavy (faction 2) before Kuze-gumi (faction 3).
- In `test_bracket_lines_and_lines_older_than_scan_depth_are_ignored`, the Hanabira line is the 7th non-bracket line from the end, so it falls outside the 6-line scan.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_world.py -q`
Expected: PASS, 18 passed.

- [ ] **Step 5: Commit**

```bash
git add narrator/world.py tests/test_world.py
git commit -m "feat: select world cards by location and recent mentions"
```

---

### Task 3: Scene line and World notes in the turn prompt

**Files:**
- Modify: `server/narration.py` (constants near the top; `_build_messages`)
- Test: `tests/test_narration.py`

**Interfaces:**
- Consumes: `kuroshio()` and `select_cards(world, session, action_text, budget_chars)` (Tasks 1–2).
- Produces: `_scene_line(session: Session) -> str`, which returns `""` when location, mood and objectives are all empty. `_build_messages(session, action_text, num_ctx)` keeps its signature. Its user content ends with `...Recent events...\n\nScene: ...\n\nWorld notes:\n<card>\n<card>\n\nPlayer action: ...`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narration.py`:

```python
def test_build_messages_puts_scene_and_world_notes_right_before_the_action():
    from narrator.world import kuroshio
    from server.narration import _build_messages

    session = _session_with_character()
    session.location = "Ikebe Low - Mama Sato's izakaya"
    session.scene_mood = "tense"
    session.active_objectives = ["find the chrome-ya", "pay off the torite"]
    session.log = ["p1: I look around."]
    ikebe = next(d.card for d in kuroshio().districts if d.name == "Ikebe Low")

    content = _build_messages(session, "I order a drink.", num_ctx=8192)[0]["content"]

    assert content.endswith(
        "Recent events:\np1: I look around.\n\n"
        "Scene: Ikebe Low - Mama Sato's izakaya · mood: tense · objectives: find the chrome-ya; pay off the torite\n\n"
        f"World notes:\n{ikebe}\n\n"
        "Player action: I order a drink."
    )


def test_scene_line_drops_empty_parts():
    from server.narration import _scene_line

    session = _session_with_character()
    session.scene_mood = "quiet"

    assert _scene_line(session) == "Scene: mood: quiet"


def test_build_messages_omits_scene_and_world_notes_when_nothing_applies():
    from server.narration import _build_messages

    session = _session_with_character()
    session.log = ["p1: I look around."]

    content = _build_messages(session, "I move forward.", num_ctx=8192)[0]["content"]

    assert "Scene:" not in content
    assert "World notes:" not in content


def test_build_messages_world_notes_from_mentions_without_location():
    from narrator.world import kuroshio
    from server.narration import _build_messages

    session = _session_with_character()
    loop = next(d.card for d in kuroshio().districts if d.name == "The Loop")

    content = _build_messages(session, "I ride out onto the Loop.", num_ctx=8192)[0]["content"]

    assert f"World notes:\n{loop}\n\nPlayer action: I ride out onto the Loop." in content
    assert "Scene:" not in content
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration.py -q -k "scene or world_notes"`
Expected: FAIL. `_scene_line` is not importable, and the content has no Scene or World notes blocks.

- [ ] **Step 3: Implement**

In `server/narration.py`:

1. Add the import `from narrator.world import kuroshio, select_cards` next to the other `narrator.` imports.
2. Change `_VERBATIM_BUDGET_FRACTION = 0.65` to `0.55`, and replace its comment with:
   ```python
   # Verbatim recent narrative gets this fraction of num_ctx (in estimated
   # tokens), leaving room for the system prompt (now including the world
   # primer), party roster, NPC memory, world cards, the action text, and
   # response generation. Lowered from 0.65 by Phase 14 to fund the world
   # primer + cards while keeping generation headroom roughly where it was
   # (~1,400 vs ~1,550 tokens at num_ctx=8192 - see the Phase 14 spec).
   # A starting value, not a tuned optimum.
   _VERBATIM_BUDGET_FRACTION = 0.55
   ```
3. Below `_NPC_MEMORY_BUDGET_FRACTION`'s comment block, add:
   ```python
   # World cards (Phase 14): ~490 tokens at num_ctx=8192, enough for the
   # 4-card cap at the 400-char card limit. A starting value, not tuned.
   _WORLD_BUDGET_FRACTION = 0.06
   ```
4. Add above `_build_messages`:
   ```python
   def _scene_line(session: Session) -> str:
       parts = []
       if session.location:
           parts.append(session.location)
       if session.scene_mood:
           parts.append(f"mood: {session.scene_mood}")
       if session.active_objectives:
           parts.append("objectives: " + "; ".join(session.active_objectives))
       return "Scene: " + " · ".join(parts) if parts else ""
   ```
5. In `_build_messages`, after the `if verbatim:` block and before `context = ...`, add:
   ```python
       # Scene + world notes go last, right before the action - content
       # nearest the end of the prompt carries the most weight (Phase 14
       # spec, SillyTavern World Info insertion-depth precedent).
       scene = _scene_line(session)
       if scene:
           parts.append(scene)
       world_budget = int(num_ctx * _WORLD_BUDGET_FRACTION * _CHARS_PER_TOKEN_ESTIMATE)
       cards = select_cards(kuroshio(), session, action_text, world_budget)
       if cards:
           parts.append("World notes:\n" + "\n".join(cards))
   ```

- [ ] **Step 4: Update the verbatim-budget test comments**

In `tests/test_narration.py`, in `test_select_verbatim_narrative_keeps_everything_under_budget`, change the comment to `# num_ctx=100 -> budget = int(100 * 0.55 * 4) = 220 chars, both lines fit`. In `test_select_verbatim_narrative_drops_oldest_lines_past_budget`, change it to `# num_ctx=10 -> budget = int(10 * 0.55 * 4) = 22 chars`. The assertions stay the same: 21 chars fit in 22, and 42 do not.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass. If an existing exact-format `_build_messages` assertion breaks, it's because its action text or log now triggers a card (for example a test mentioning "the Docks"). Update that assertion to include the new block. Don't change the selection logic.

- [ ] **Step 6: Commit**

```bash
git add server/narration.py tests/test_narration.py
git commit -m "feat: Scene line and world cards in the narrator's turn prompt"
```

---

### Task 4: Primer and glossary in the system prompt

**Files:**
- Modify: `server/__main__.py`
- Test: `tests/test_server_main.py`

**Interfaces:**
- Consumes: `kuroshio().system_block()` (Task 1).
- Produces: `server.__main__.build_system_prompt() -> str`, used by `build_app()` and by Task 5's live probe.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server_main.py`:

```python
def test_system_prompt_ends_with_the_world_primer_and_glossary():
    from narrator.world import kuroshio
    from server.__main__ import build_system_prompt

    prompt = build_system_prompt()

    assert prompt.startswith("You are a cyberpunk tabletop game master.")
    assert prompt.endswith(kuroshio().system_block())


def test_build_app_gives_the_narrator_the_world_system_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import server.__main__ as main

    class Recorder:
        system_prompt = ""

    recorder = Recorder()
    monkeypatch.setattr(main, "create_narrator_backend", lambda: recorder)

    main.build_app()

    assert recorder.system_prompt == main.build_system_prompt()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_server_main.py -q`
Expected: FAIL with `ImportError: cannot import name 'build_system_prompt'`

- [ ] **Step 3: Implement**

In `server/__main__.py`:
- Add `from narrator.world import kuroshio`.
- Move the whole `system_prompt = ( ... )` literal out of `build_app()` into a new module-level function, unchanged:

```python
def build_system_prompt() -> str:
    # Game-master rules first, then the world (Phase 14): the primer + glossary
    # are always on; district/faction cards are added per turn in
    # server/narration.py. kuroshio() validates the world file, so a broken
    # one fails here, at startup.
    rules = (
        "You are a cyberpunk tabletop game master. "
        # ... every existing string line, unchanged ...
    )
    return f"{rules}\n\n{kuroshio().system_block()}"
```

In `build_app()`, replace the removed literal and the assignment with:

```python
    narrator_client = create_narrator_backend()
    narrator_client.system_prompt = build_system_prompt()
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/__main__.py tests/test_server_main.py
git commit -m "feat: Kuroshio primer and glossary in the narrator system prompt"
```

---

### Task 5: Live verification and docs

This task is run by the controller, not a subagent: it needs the real GPU-backed model and an honest write-up.

**Files:**
- Modify: `README.md`, `ROADMAP.md`
- Throwaway (not committed): a probe script in a `mktemp -d` directory.

**Interfaces:**
- Consumes: `build_system_prompt()` (Task 4); `handle_action(session, narrator_client, store, image_backend, tts_backend, player_id, message)` (`server/narration.py`); `NarratorClient` (`narrator/client.py`); `_build_messages` and `select_cards`.

- [ ] **Step 1: Confirm the model**

Run: `curl -s localhost:11434/api/tags | grep -o '"qwen3:8b"'`
Expected: `"qwen3:8b"`. If it's missing, fall back to the deployment box documented in ROADMAP (`192.168.10.19`) and set `OLLAMA_HOST` to it.

- [ ] **Step 2: Measure the prompt size before and after**

Use `git stash` or a checkout of the pre-Phase-14 commit (`31df013`). For one fixed session (a 20-line log, location set), print `len(build_system_prompt()) + len(_build_messages(...)[0]["content"])`. The old code's system prompt is the inline literal: copy its length from a `python -c` run on the old checkout. Record both numbers.

- [ ] **Step 3: Run the 8-turn district probe**

Write `$d/probe.py` in a fresh `d=$(mktemp -d)`. It should:
- build a `Session` with one character;
- use a `NarratorClient()` with `system_prompt=build_system_prompt()`;
- use a `JSONFileSessionStore(d)`;
- use stub image and TTS backends: `synthesize` raises `ValueError("stub")`, which produces bracketed audio-error lines; `generate_scene` returns `b""`.

Then send these 8 actions through `handle_action`:
1. "I step out of the rain into an izakaya in Ikebe Low."
2. "I ask the owner where I can find a chrome-ya who doesn't report to Hoshikawa."
3. "I follow the directions to the clinic."
4. "I ask the chrome-ya what she wants in return."
5. "I borrow a bike and get on the Loop."
6. "A Kaminari Run rider pulls alongside me. I nod at him."
7. "I take the off-ramp into Hanabira-chō."
8. "I find the Kuze-gumi's office and ask for the man who sold my debt."

Before each turn, print `session.location` and the names of the cards `select_cards` will pick. After each turn, print the narration, the tool name and any error lines.

Run with `.venv/bin/python -I $d/probe.py` from the repo root, with `PYTHONPATH=.`

- [ ] **Step 4: Score it honestly** (n = 8 turns, single pass: indicative only)

Record:
- How many turns set `location` starting with a district name.
- Which cards fired on each turn.
- Glossary use: natural, explained or overused.
- Recitation: any span of 12 or more words copied from a card. Check with a simple n-gram overlap in the probe.
- Schema or tool errors compared with recent phases.

If recitation appears, shorten the offending card or primer line and re-run. Don't add prompt rules (owner decision).

- [ ] **Step 5: README "World" section**

Add after the README's existing feature or setup section:

```markdown
## World

Nightwire's setting is **Kuroshio**, an original Japanese megacity in 2089 where everyone's chrome is on credit. It lives in `narrator/worlds/kuroshio.toml`:

- **`primer` + `[glossary]`**: always in the narrator's system prompt (max 1,600 chars together).
- **`[[district]]` / `[[faction]]`**: `name`, `aliases`, `card` (max 400 chars). Each turn, up to 4 cards are added: the district matching the current location first, then anything mentioned in the player's action or recent narration.

To add a place or faction, add an entry. Keep each card standalone (don't refer to "they" from another card), and make sure names and aliases are unique (matching ignores case and accents, so "Ōgane" already matches "Ogane"). The server checks the file at startup and refuses to start if it's invalid.
```

- [ ] **Step 6: ROADMAP Phase 14 entry**

Add a `14. **World bible: Kuroshio**` entry after Phase 13, in the same shape as the Phase 11–13 entries:
- the spec and plan paths;
- what was built (files, constants, the 0.65 → 0.55 verbatim change);
- the live verification results from Steps 2–4, with exact numbers and n;
- what was deliberately deferred (cyberware and humanity next, faction clocks, rolled tables, NPC cards, multiple worlds).

- [ ] **Step 7: Commit**

```bash
git add README.md ROADMAP.md
git commit -m "docs: record Phase 14 (Kuroshio world bible) and its live verification"
```

Then ask the owner before pushing.
