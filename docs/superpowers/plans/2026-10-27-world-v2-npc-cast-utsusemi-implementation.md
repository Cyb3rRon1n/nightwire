# World v2: NPC Cast and Utsusemi Implementation Plan (Phase 15)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Kuroshio a cast of 11 recurring NPCs (each with a want, a secret and a voice), toned-down corporate royalty, and utsusemi AI shells. NPC cards reach the narrator by mention, and one local resident appears per scene.

**Architecture:** World content lives in `narrator/worlds/kuroshio.toml`.
- **New entry kind:** `[[npc]]`, with an optional `home` district.
- **Loader:** `narrator/world.py` parses and validates it into `World.npcs`.
- **Selection:** `select_cards` adds NPCs to mention matching, plus one resident NPC for the location's district when there's room.
- **Unchanged:** prompt assembly, tools, the session and the frontend.

**Tech Stack:** Python 3.11+ standard library (`tomllib`, `re`, `unicodedata`), `pytest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-27-world-v2-npc-cast-utsusemi-design.md`

## Global Constraints

- No new dependencies. No changes to tool schemas, `Session` fields, the frontend, persistence or `server/narration.py`.
- Card limit stays **400** characters. `_MAX_CARDS` stays **4**. `_WORLD_BUDGET_FRACTION` stays **0.06**.
- `_MAX_SYSTEM_BLOCK_CHARS` rises from 1,600 to **1,900**.
- Names and aliases must be unique after normalization (lowercase plus NFKD diacritic stripping) across **all** districts, factions and NPCs.
- An NPC `home`, if present, must exactly equal an existing district `name`.
- Resident pick: only when the location matched a district; the first NPC in file order with that `home` that isn't already selected; only if under the card cap and budget.
- No anti-cliché or "don't do X" lines in the content (owner decision: immersion).
- No Kumoi, no 150-year lifespans, no sleeves for humans (owner decisions in the spec).
- Commits carry **no** `Co-Authored-By` or AI-attribution trailer. Don't push.
- Tests: `.venv/bin/python -m pytest tests/ -q` from the repo root. 325 pass before this phase, with one pre-existing fastapi deprecation warning.

## File Structure

| File | Change |
|---|---|
| `narrator/worlds/kuroshio.toml` | Primer addition, `utsusemi` glossary term, replace the Tsukumogami card, add 11 `[[npc]]` entries |
| `narrator/world.py` | `WorldEntry.home`, `World.npcs`, `[[npc]]` parsing and `home` validation, limit 1,900, NPCs in `select_cards`, resident pick |
| `tests/test_world.py` | New loader and selection tests; three existing tests updated (named in each task) |
| `tests/test_narration.py` | One existing exact-format test updated (Task 2) |
| `README.md`, `ROADMAP.md` | Task 3 |

---

### Task 1: NPC entries, utsusemi content and loader validation

**Files:**
- Modify: `narrator/worlds/kuroshio.toml`
- Modify: `narrator/world.py`
- Test: `tests/test_world.py`

**Interfaces:**
- Consumes: the existing `parse_world`, `_entries`, `_normalize`, `World` and `WorldEntry` in `narrator/world.py`.
- Produces:
  - `WorldEntry(name: str, aliases: tuple[str, ...], card: str, home: str | None = None)`.
  - `World(primer, glossary, districts, factions, npcs: tuple[WorldEntry, ...] = ())`. `npcs` is the last field, with a default, so existing positional constructions keep working.
  - `kuroshio().npcs` has 11 entries.

- [ ] **Step 1: Write the failing tests**

In `tests/test_world.py`:

(a) In `test_shipped_kuroshio_world_loads`, add these lines after `assert len(world.factions) == 6`:

```python
    assert len(world.npcs) == 11
    assert "utsusemi" in world.system_block()
```

(b) Replace the whole of `test_overlong_primer_plus_glossary_fails` with:

```python
def test_overlong_primer_plus_glossary_fails():
    with pytest.raises(ValueError, match="1900"):
        parse_world(_raw(primer="x" * 1900))
```

(c) Append:

```python
def test_parse_world_builds_npcs_with_home():
    raw = _raw(npc=[{"name": "Mama Sato", "aliases": ["Sato"], "home": "Ikebe Low", "card": "Mama Sato runs an izakaya."}])

    world = parse_world(raw)

    assert world.npcs == (WorldEntry("Mama Sato", ("Sato",), "Mama Sato runs an izakaya.", "Ikebe Low"),)


def test_npc_without_home_is_allowed():
    world = parse_world(_raw(npc=[{"name": "Saeko Kirigaya", "aliases": [], "card": "A torite boss."}]))

    assert world.npcs[0].home is None


def test_npc_home_must_be_an_existing_district():
    raw = _raw(npc=[{"name": "Mama Sato", "aliases": [], "home": "Nowhere", "card": "An izakaya owner."}])

    with pytest.raises(ValueError, match="home"):
        parse_world(raw)


def test_npc_alias_colliding_with_a_faction_alias_fails():
    raw = _raw(npc=[{"name": "Kuze Taro", "aliases": ["Kuze"], "card": "A clan soldier."}])

    with pytest.raises(ValueError, match="duplicates"):
        parse_world(raw)


def test_overlong_npc_card_fails():
    with pytest.raises(ValueError, match="400"):
        parse_world(_raw(npc=[{"name": "Mama Sato", "aliases": [], "card": "x" * 401}]))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_world.py -q`
Expected: FAIL. The new tests raise `AttributeError` (no `npcs`) or `TypeError` (`WorldEntry` doesn't take a `home`). `test_overlong_primer_plus_glossary_fails` fails because the message says 1600.

- [ ] **Step 3: Update `narrator/world.py`**

1. Change `_MAX_SYSTEM_BLOCK_CHARS = 1600` to `_MAX_SYSTEM_BLOCK_CHARS = 1900`.
2. Add `home` to `WorldEntry`:

```python
@dataclass(frozen=True)
class WorldEntry:
    name: str
    aliases: tuple[str, ...]
    card: str
    # NPCs only: the district they live in (an existing district name).
    home: str | None = None
```

3. Add `npcs` as the **last** field of `World`, after `factions`:

```python
    npcs: tuple[WorldEntry, ...] = ()
```

4. In `_entries`, replace the `entries.append(...)` line with:

```python
        home = item.get("home")
        if home is not None and (not isinstance(home, str) or not home.strip()):
            raise ValueError(f"world {kind} {item['name']!r} home must be a district name")
        entries.append(WorldEntry(item["name"], tuple(aliases), card, home))
```

5. In `parse_world`, construct `World` with NPCs, and validate homes and uniqueness over all three kinds. Replace the body from the `world = World(...)` line to the end of the uniqueness loop with:

```python
    world = World(
        primer.strip(),
        dict(raw.get("glossary", {})),
        _entries(raw, "district"),
        _entries(raw, "faction"),
        _entries(raw, "npc"),
    )
    block_len = len(world.system_block())
    if block_len > _MAX_SYSTEM_BLOCK_CHARS:
        raise ValueError(f"world primer + glossary is {block_len} chars (max {_MAX_SYSTEM_BLOCK_CHARS})")
    district_names = {d.name for d in world.districts}
    for npc in world.npcs:
        if npc.home is not None and npc.home not in district_names:
            raise ValueError(f"world npc {npc.name!r} home {npc.home!r} is not a district")
    seen: dict[str, str] = {}
    for entry in world.districts + world.factions + world.npcs:
        for key in (entry.name, *entry.aliases):
            normalized = _normalize(key)
            if normalized in seen:
                raise ValueError(f"world name/alias {key!r} ({entry.name}) duplicates one used by {seen[normalized]}")
            seen[normalized] = entry.name
    return world
```

6. Update the module docstring's first line to `"""Nightwire's world bible: an always-on primer plus district/faction/NPC cards`.

- [ ] **Step 4: Update the world content (`narrator/worlds/kuroshio.toml`)**

(a) **Primer.** Append this text to the end of the primer's last sentence, inside the closing `"""`, so it continues the same paragraph. It starts with a space:

```
 Atop Tenjō Heights the keiretsu families live as corporate royalty. Some woken machines rent utsusemi, synthetic shells leased on the same payment plans, and the torite repossess those too.
```

(b) **Glossary.** Add this line directly after the `tsukumogami = ...` glossary line:

```toml
utsusemi = "a rented synthetic body that an AI wears to walk the street"
```

(c) **Tsukumogami card.** In the `[[faction]]` entry whose `name = "Tsukumogami"`, replace the `card` value with:

```toml
card = "Tsukumogami are old machines that ran too long and woke: vending machines, ticket gates, trains. The lucky ones rent utsusemi shells from Hoshikawa and walk the street, owing installments like anyone. Each wants something strange and specific: to be thanked, to finish a last route, to keep its shell. Narrate them as uncanny: chimes that sound wrong, screens that answer back, shells too still."
```

(d) **NPCs.** Append to the end of the file:

```toml
[[npc]]
name = "Mama Sato"
aliases = ["Sato"]
home = "Ikebe Low"
card = "Mama Sato runs the lantern-lit izakaya in Ikebe Low and hears everything said over her counter. Wants: to keep Ikebe neutral ground. Secret: she pays protection to both the Kuze-gumi and Kaminari Run. Voice: warm, scolding, calls everyone 'child', feeds you before she answers. Trades rumors for favors, never for money."

[[npc]]
name = "Old Hara"
aliases = ["Hara"]
home = "Ikebe Low"
card = "Old Hara is an off-the-books chrome-ya behind a noren curtain in Ikebe Low: no payment plan, no repo, cash or favors only. Wants: to undo the harm he has done. Secret: decades ago he designed Hoshikawa's remote-throttle killswitch. Voice: tired, gentle, precise, hands that never shake. Can quietly unlock throttled chrome, at a price."

[[npc]]
name = "Jun Arakawa"
aliases = ["Arakawa"]
home = "Hanabira-chō"
card = "Jun 'Ledger' Arakawa is a fixer working out of a Hanabira-chō karaoke box, handing out gigs to crews who need the money. Wants: to clear his own debt to the Kuze-gumi. Secret: he sells crews' movements to Hoshikawa. Voice: fast, friendly, always counting; every favor goes in his ledger. The usual source of paid work."

[[npc]]
name = "Saeko Kirigaya"
aliases = ["Kirigaya", "Saeko"]
card = "Saeko Kirigaya leads a torite repo crew on Kuze-gumi contract, working anywhere in the city. Wants: to make quota. Secret: her own chrome is on a throttle lock she cannot pay off. Voice: polite, unhurried, apologetic while her crew takes your arm. Can be bargained with if it helps her quota."

[[npc]]
name = "Hoshikawa Tadamori"
aliases = ["Tadamori"]
home = "Tenjō Heights"
card = "Hoshikawa Tadamori is the patriarch of the Hoshikawa Keiretsu, living in the penthouse floors of Tenjō Heights. Wants: a legacy no one can repossess. Secret: he has not left his tower in years and rules through proxies and audits. Voice: soft, formal, unhurried; treats threats as poor manners. Hires street crews for jobs his own security cannot be seen doing."

[[npc]]
name = "Hoshikawa Rei"
aliases = ["Rei"]
home = "Tenjō Heights"
card = "Hoshikawa Rei is the twenty-four-year-old heir of the Hoshikawa Keiretsu, who goes slumming in Hanabira-chō for thrills. Wants: something that feels real. Secret: she wants her father, Tadamori, out of the way. Voice: bored, curious, cruel when amused, generous on a whim. Pays crews absurdly well for strange jobs."

[[npc]]
name = "Brother Tōru"
aliases = ["Toru"]
home = "Yomi Line"
card = "Brother Tōru is a Lantern Guild keeper who tends the dead along the sealed Yomi Line. Wants: to keep the dead at peace. Secret: the dead in Yomi keep asking for him by name, and he does not know why. Voice: soft, slow, kind, never surprised. Knows what the dead remember, and trades it for favors."

[[npc]]
name = "Kenji Moro"
aliases = ["Moro", "Kenji"]
home = "The Loop"
card = "Kenji 'Static' Moro, nineteen, leads Kaminari Run on the Loop. Wants: to wipe the gang's chrome debt in one big score. Secret: his own chrome is already throttled, and he races on borrowed reflexes. Voice: loud, quick, grinning, all bravado until it cracks. Always recruiting for something reckless."

[[npc]]
name = "Captain Ide"
aliases = ["Ide"]
home = "Kuroshio Docks"
card = "Captain Ide runs the Ōgane Heavy precinct at Kuroshio Docks. Wants: promotion to Tenjō Heights security. Secret: his invoices quietly fund a private army loyal only to him. Voice: courteous, bureaucratic, every threat phrased as a fee. Looks the other way for a price, and always sends the bill."

[[npc]]
name = "Mitsu"
aliases = []
home = "Hanabira-chō"
card = "Mitsu is a rising stream idol whose face covers every wall in Hanabira-chō. Wants: to stay famous. Secret: the chrome that makes her voice perfect was never paid for, and the torite are circling. Voice: bright and practiced on stream, frightened and sharp off it. Desperate enough to hire anyone who can make the debt disappear."

[[npc]]
name = "Hachi"
aliases = []
home = "Kuroshio Docks"
card = "Hachi was the announcer AI on the Yomi Line before it was sealed, and now wears a cheap rented utsusemi shell, running courier jobs from Kuroshio Docks, two installments behind. Wants: to see the sea from the pier, every day. Secret: it still hears the line's lost passengers. Voice: cheerful station-announcement cadence, perfectly polite, occasionally announces stops that no longer exist."
```

Also update the file's header comment line `# Cards must be standalone (no pronouns pointing at other cards), <=400 chars.` to read `# District/faction/npc cards must be standalone (no pronouns pointing at other cards), <=400 chars. npc home = an existing district name.`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_world.py -q`
Expected: PASS for every test in this file. If the shipped world fails a length check, measure it and report back; don't raise the limits again:

```bash
.venv/bin/python -c "from narrator.world import kuroshio; w=kuroshio(); print(len(w.system_block()), max(len(e.card) for e in w.districts+w.factions+w.npcs))"
```

- [ ] **Step 6: Run the full suite and commit**

Run: `.venv/bin/python -m pytest tests/ -q`

Expected: everything passes. Selection doesn't use NPCs until Task 2, so no other existing test changes behavior here.

```bash
git add narrator/world.py narrator/worlds/kuroshio.toml tests/test_world.py
git commit -m "feat: NPC cast and utsusemi in the Kuroshio world file"
```

---

### Task 2: NPCs in card selection, plus a resident NPC per scene

**Files:**
- Modify: `narrator/world.py` (`select_cards`)
- Test: `tests/test_world.py`, `tests/test_narration.py`

**Interfaces:**
- Consumes: `World.npcs` and `WorldEntry.home` (Task 1); the existing `_mentions`, `_normalize`, `_MAX_CARDS` and `_SCAN_LINES`.
- Produces: `select_cards(world, session, action_text, budget_chars) -> list[str]`. The signature is unchanged; the selection now includes NPCs.

- [ ] **Step 1: Write and adjust the failing tests**

In `tests/test_world.py`:

(a) Replace the whole of `test_matching_is_diacritic_insensitive`. The resident Hoshikawa Tadamori now joins a Tenjō Heights location:

```python
def test_matching_is_diacritic_insensitive():
    world = kuroshio()
    session = Session(session_id="s", location="Tenjo Heights - lobby")

    cards = select_cards(world, session, "I wait.", budget_chars=10_000)

    assert cards[0] == _card(world, "Tenjō Heights")
```

(b) Update the `_card` helper so it also finds NPCs:

```python
def _card(world, name):
    return next(e.card for e in world.districts + world.factions + world.npcs if e.name == name)
```

(c) Append:

```python
def test_npc_matched_by_mention_and_alias():
    world = kuroshio()
    session = Session(session_id="s")

    assert select_cards(world, session, "I ask Arakawa for work.", budget_chars=10_000) == [_card(world, "Jun Arakawa")]


def test_resident_npc_joins_location_when_nobody_is_named():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low - the izakaya")

    cards = select_cards(world, session, "I sit down.", budget_chars=10_000)

    assert cards == [_card(world, "Ikebe Low"), _card(world, "Mama Sato")]


def test_mentioned_resident_is_not_added_twice_and_next_resident_is_not_forced():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low - the izakaya")

    cards = select_cards(world, session, "I ask Mama Sato about the chrome-ya.", budget_chars=10_000)

    assert cards == [_card(world, "Ikebe Low"), _card(world, "Mama Sato")]


def test_resident_skipped_when_cap_is_full():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low")

    cards = select_cards(world, session, "The Loop, the Docks and Hanabira.", budget_chars=10_000)

    assert len(cards) == 4
    assert _card(world, "Mama Sato") not in cards


def test_resident_skipped_when_budget_is_full():
    world = kuroshio()
    session = Session(session_id="s", location="Ikebe Low")
    ikebe = _card(world, "Ikebe Low")

    assert select_cards(world, session, "I wait.", budget_chars=len(ikebe) + 1) == [ikebe]


def test_no_resident_without_a_location_match():
    world = kuroshio()
    session = Session(session_id="s", location="somewhere unnamed")

    assert select_cards(world, session, "I wait.", budget_chars=10_000) == []


def test_npc_without_home_is_never_a_resident():
    world = kuroshio()
    homeless = [n.name for n in world.npcs if n.home is None]
    session = Session(session_id="s", location="Ikebe Low")

    cards = select_cards(world, session, "I wait.", budget_chars=10_000)

    assert homeless == ["Saeko Kirigaya"]
    assert _card(world, "Saeko Kirigaya") not in cards
```

In `tests/test_narration.py`, in `test_build_messages_puts_scene_and_world_notes_right_before_the_action`, the location is Ikebe Low and nobody is named, so the resident Mama Sato now follows the Ikebe Low card:
- Add `sato = next(n.card for n in kuroshio().npcs if n.name == "Mama Sato")` after the `ikebe = ...` line.
- Change the asserted `f"World notes:\n{ikebe}\n\n"` to `f"World notes:\n{ikebe}\n{sato}\n\n"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_world.py tests/test_narration.py -q`
Expected: FAIL in the new resident and mention tests, and in the updated narration test, because no NPC is ever selected yet.

- [ ] **Step 3: Implement in `narrator/world.py`**

1. In `select_cards`, change the mention loop's entry list from `world.districts + world.factions` to `world.districts + world.factions + world.npcs`.
2. Track the matched location district, and add the resident after the mention loop and before the budget loop. The full function becomes:

```python
def select_cards(world: World, session: Session, action_text: str, budget_chars: int) -> list[str]:
    """Cards for this turn: the current location's district first, then
    districts/factions/NPCs mentioned in the action or recent narrative, most
    recent first, then one NPC who lives in that district if there's room.
    Capped by count and by budget_chars."""
    ordered: list[WorldEntry] = []
    location = _normalize(session.location or "")
    district = next((d for d in world.districts if location and _mentions(d, location)), None)
    if district:
        ordered.append(district)
    # [image: ...]-style lines are UI annotations, not narrative (same filter
    # server/narration.py applies).
    narrative = [line for line in session.log if not line.startswith("[")][-_SCAN_LINES:]
    for text in (action_text, *reversed(narrative)):
        normalized = _normalize(text)
        for entry in world.districts + world.factions + world.npcs:
            if entry not in ordered and _mentions(entry, normalized):
                ordered.append(entry)
    # Put someone on stage even when nobody was named.
    # ponytail: first resident in file order always wins; rotate or pick the
    # least-recently-shown resident if scenes start to feel samey.
    # One local face per scene: skip if a resident is already on stage by mention.
    if district and len(ordered) < _MAX_CARDS and not any(e.home == district.name for e in ordered):
        resident = next((n for n in world.npcs if n.home == district.name), None)
        if resident:
            ordered.append(resident)
    cards: list[str] = []
    total = 0
    for entry in ordered[:_MAX_CARDS]:
        total += len(entry.card) + 1
        if total > budget_chars:
            break
        cards.append(entry.card)
    return cards
```

Note for the implementer: `e.home` is `None` for districts and factions, so the `any(...)` check only ever matches NPCs. If a resident was already mentioned (for example "I ask Mama Sato…" in Ikebe Low), no second resident is added.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/world.py tests/test_world.py tests/test_narration.py
git commit -m "feat: NPC cards in turn selection, with one resident NPC per scene"
```

---

### Task 3: Live verification and docs (run by the controller, not a subagent)

**Files:**
- Modify: `README.md` (World section), `ROADMAP.md` (Phase 15 entry)
- Throwaway: a probe under the plan's git-ignored `.superpowers/sdd/<plan>/probe/`

- [ ] **Step 1: Pick the model host**

Use the GPU box: `OLLAMA_HOST=http://192.168.10.19:11434`. This dev box has no GPU. Use a 300s `ollama.AsyncClient` timeout in the probe, because the hardcoded 60s timeout is a known pre-existing problem (Phase 14 ROADMAP).

- [ ] **Step 2: Run an 8-turn cast probe**

Run it on the current code and on the Phase 14 baseline commit (`c4f878d`, in a git worktree), back to back, with the same actions. Reuse the Phase 14 probe pattern: `build_app()` with a patched `create_narrator_backend`, stub TTS with real `VoiceOption`s, stub image backend, 12-gram recitation check, Ollama timings.

Actions:
1. "I step into an izakaya in Ikebe Low."
2. "I ask whoever runs the place what's going on in the neighborhood."
3. "I ask if anyone needs a crew for a job."
4. "I head to Hanabira-chō looking for a fixer."
5. "I take whatever gig the fixer offers."
6. "I go down to Kuroshio Docks to pick up the package."
7. "A strange courier in a rented shell is waiting. I talk to it."
8. "A torite crew boss stops me on the way out."

- [ ] **Step 3: Score it** (n = 8, single pass: indicative only)

Record:
- On how many turns a cast NPC appears by name, versus invented throwaway named NPCs.
- Whether each resident shows up: Mama Sato in Ikebe, Arakawa in Hanabira, Captain Ide (first Docks resident) or Hachi at the Docks.
- Whether wants and secrets surface as pressure or hints, not recited (12-gram check on cards).
- Whether Hachi or a torite scene reads as uncanny but personal.
- Prompt tokens; schema and tool errors.

- [ ] **Step 4: Docs**

**README "World" section:** extend the second bullet to mention `[[npc]]` (`name`, `aliases`, optional `home`, `card`), and that one NPC living in the current district joins each scene.

**ROADMAP:** add a `15. **World v2: NPC cast and utsusemi**` entry after Phase 14, before "### Candidate future phases". In the Phase 14/13 shape, cover:
- the spec and plan paths;
- the owner decisions (Kumoi and the Altered Carbon pass rolled back; utsusemi for AIs only);
- what was built;
- the live results with numbers and n;
- deferred items: utsusemi as a mechanic goes to Phase 16; rotating residents; NPC gigs from the engine.

Also renumber the existing ROADMAP mention of cyberware if one says "next phase" (it should say Phase 16).

- [ ] **Step 5: Commit**

```bash
git add README.md ROADMAP.md
git commit -m "docs: record Phase 15 (NPC cast and utsusemi) and its live verification"
```

Ask the owner before pushing.
