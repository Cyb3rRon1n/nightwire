# NPC Voices Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each turn, the narrator sees one sample line and a chosen move for every named character present, and one
sample line for each unnamed type the scene mentions; copies of those lines are cut.

**Architecture:** Owner-approved lines live in `narrator/worlds/voices.toml`; `narrator/voices.py` loads and validates
them and builds the per-turn "Voices this turn" block from the session cast and recent story. `server/narration.py`
appends the block in `_build_messages` and feeds its lines to the existing 8-word-run repeat cut.

**Tech Stack:** Python 3, tomllib, pytest (asyncio auto).

**Spec:** `docs/superpowers/specs/2026-11-22-npc-voices-design.md` (lines: `2026-11-21-npc-voices-draft-lines.md`)

## Global Constraints

- Zero extra model calls.
- One sample line per character per turn; never the same move for a character two turns running.
- At most 3 named characters plus 2 types in the block; nothing added when no one with a sheet is present/mentioned.
- Block header exactly: `Voices this turn (how they sound; never repeat these lines word for word):`
- Lines copied verbatim from the approved draft; no rewording.
- No Co-Authored-By or AI trailers in commits.

## Review Focus

- A present NPC with no voice sheet (e.g. none written yet) → skipped silently, no crash. (Task 2 test)
- A `last_moves` entry for a name that has no sheet any more → ignored. (Task 2 test)
- An old saved session without the new fields loads with defaults. (Task 2 test)
- A type match word inside another word ("stall" in "install") → no match. (Task 2 test)
- Copy cut must never empty a turn made only of a copied sample line. (Task 3 test)

---

### Task 1: Voice data and loader

**Files:**
- Create: `narrator/worlds/voices.toml` (all 12 characters, 8 types, from the draft doc, verbatim)
- Create: `narrator/voices.py`
- Test: `tests/test_voices.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Line: move: str; text: str`;
  `@dataclass(frozen=True) class Sheet: name: str; lines: tuple[Line, ...]`;
  `@dataclass(frozen=True) class TypeSheet: name: str; match: tuple[str, ...]; voice: str; lines: tuple[str, ...]`;
  `@dataclass(frozen=True) class Voices: characters: dict[str, Sheet]; types: tuple[TypeSheet, ...]`;
  `load_voices(path: Path, world: World) -> Voices` (raises `ValueError` on bad data);
  `voices() -> Voices` (functools.cache, loads `narrator/worlds/voices.toml` against `kuroshio()`).

- [ ] **Step 1: Failing tests** — `test_the_shipped_voices_load`: `len(voices().characters) == 12`,
  `len(voices().types) == 8`, `voices().characters["Mama Sato"].lines[2] == Line("warn", "Kuze boys drink at that
  table. Kaminari boys drink at this one. You drink at the counter.")`.
  `test_bad_voice_data_is_refused` (tmp_path files): unknown character name; 2 lines; duplicate moves; type with no
  match words → each `pytest.raises(ValueError)`.
- [ ] **Step 2:** `python -m pytest tests/test_voices.py -q` → FAIL (module missing).
- [ ] **Step 3:** Write `voices.toml` (types' `match`: street vendor = vendor, noodle stall, food stall, stall owner,
  noodle vendor; dockworker = dockworker, dock worker, docker, longshoreman; Kuze-gumi enforcer = enforcer, kuze
  enforcer, yakuza, kuze-gumi man; torite crew member = torite, repo man, repo crew; Kaminari Run racer = racer,
  kaminari runner, biker; Ōgane Heavy officer = ogane officer, ōgane officer, precinct officer, cop, officer; Hoshikawa
  auditor = auditor; Lantern Guild acolyte = acolyte, lantern bearer) and `narrator/voices.py`.
- [ ] **Step 4:** tests pass.
- [ ] **Step 5:** commit "NPC voices: approved sample lines and loader".

### Task 2: Per-turn picking

**Files:**
- Modify: `narrator/voices.py`, `engine/session.py`, `engine/persistence.py`
- Test: `tests/test_voices.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `voice_block(session: Session, action_text: str) -> str` — returns the block (header + one line per
  entry) or `""`; sets `session.voice_lines` to the sample texts shown and updates `session.last_moves` /
  `session.type_turns`. Session fields: `last_moves: dict[str, str]`, `type_turns: dict[str, int]`,
  `voice_lines: list[str]` (all default empty; persistence loads with `data.get(..., default)`).
- Entry formats (exact): `- {name} will {move}, like: "{text}"` and
  `- A {type name lowercased} ({voice}) sounds like: "{text}"`.
- Types scanned in the action plus the last 6 non-`[` log lines, whole-word on normalized text (`_normalize` from
  `narrator/world.py`), most recent mention first, at most 2.

- [ ] **Step 1: Failing tests** —
  `test_a_present_character_gets_one_line_and_never_the_same_move_twice` (seed `random`; present Mama Sato; call 6
  times; consecutive moves differ; each call's block has exactly one Mama Sato line and that line's text is one of hers);
  `test_a_mentioned_type_gets_its_voice_and_lines_rotate` (log line "A noodle vendor waves you over."; three calls show
  the vendor's lines 0,1,2 in order);
  `test_nobody_with_a_sheet_means_no_block` (present [], no mentions → `""` and `voice_lines == []`);
  `test_caps_and_unknowns` (present 5 names incl. "Kenta" with no sheet → ≤3 character entries, no Kenta, no crash;
  `last_moves={"Gone": "warn"}` ignored; "install" does not match "stall");
  `test_the_new_session_fields_load_from_an_old_save` (save, strip the three keys from the JSON, load → defaults).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** pass. **Step 5:** commit "NPC voices: pick a move and line per turn".

### Task 3: Prompt and copy cut

**Files:**
- Modify: `server/narration.py` (`_build_messages` after `present_line`; `_drop_repeated_lines` reference set)
- Modify: `tools/soak_test.py` (notes filter adds `"[sample line cut"`)
- Test: `tests/test_narration.py`

**Interfaces:**
- Consumes: `voice_block`, `session.voice_lines`.
- `_drop_repeated_lines` treats each `session.voice_lines` text as reference (runs and ≥5-word keys) and, when it
  cuts a sentence matching a voice line, appends `[sample line cut: {first 60 chars}]` to `session.log`.

- [ ] **Step 1: Failing tests** — `test_the_prompt_carries_this_turns_voices` (present Mama Sato → prompt contains the
  exact header and `- Mama Sato will `); update the existing prompt-order test so the voices block follows the Present
  line when present (unchanged when absent); `test_a_copied_sample_line_is_cut_and_logged` (voice_lines = Old Hara's
  "I don't take payment plans. I've seen where payment plans go."; reply speech repeats it plus "Sit down." → only
  "Sit down." kept, log has `[sample line cut: `); `test_a_reply_that_is_only_a_sample_line_is_kept` (never empty).
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** full suite passes (`python -m pytest tests/ -q`).
- [ ] **Step 5:** commit "NPC voices: show them to the narrator and cut copies".

### Task 4: Live check

- [ ] Run the full soak (`NIGHTWIRE_OLLAMA_TIMEOUT=600 NIGHTWIRE_THINK=off python -m tools.soak_test --chips`) and
  compare with `design-data/soak/20261121-133143.jsonl`: NPC speech repeats, sample lines cut, errors, empty turns.
