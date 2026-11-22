# NPC voices: sample lines and a conversational move per turn

Status: approved 2026-11-22 (owner picked approach A, kept all 21 drafted items, and handed remaining calls to Claude).

## Why

Soaks 2026-11-21: named characters fall back on one register and one catchphrase ("Child, you're not the only
one…" four times; Hoshikawa staff "You're not supposed to be here" three times in four turns), and unnamed people
(the auditor, the vendor) have no voice at all. The 8-word repeat cut removes copies after the fact; this gives the
narrator something better to say in the first place. Zero extra model calls, so it stays cheap on CPU and keeps paying
off on the 4U box's bigger model.

## Prior art (verified 2026-11-21)

- **Versu** (Evans & Short, IEEE TCIAIG 2014; Short, "Versu: Conversation Implementation", emshort.blog 2013): the
  conversation state includes a selected speech-act — what kind of thing the next speaker should do. Our per-turn move.
- **Dynamic dialogue / barks** (Ruskin, Valve, GDC 2012): the most specific matching rule wins, general ones are the
  fallback. Our order: named character sheet, then type sheet, then nothing.
- **Character-card example dialogue** (SillyTavern "Examples of dialogue"; Character Card V2 `mes_example`): sample
  lines show how a character speaks.
- **Risk:** in-context persona demos get reproduced verbatim when they fit the scene, more so with more demos
  (arXiv 2402.09954, GPT-3.5/4). Hence one line per character per turn, and copies of sample lines are cut.

## Goals

- Each named character present gets a move for this turn and the one sample line that shows it.
- A character never gets the same move two turns running.
- Unnamed people the scene mentions get their type's voice and one sample line.
- A sentence that copies a sample line (shares an 8-word run with it) is cut like any repeat.

## Non-goals

- Strangers growing into named characters (next project; this one gives them a starting voice).
- Trust or relationship scores; a model call to choose the move; new moves beyond each character's three.

## Design

**Data** — `narrator/worlds/voices.toml`, separate from the world cards (cards stay ≤400 chars and unchanged; their
"Voice:" description stays). Owner-approved content from `2026-11-21-npc-voices-draft-lines.md`:

```toml
[[character]]
name = "Mama Sato"            # must match a world npc name
lines = [ { move = "feed first", text = "Sit. Eat the eel while it's hot, child. ..." }, ... ]   # 3 lines

[[type]]
name = "Street vendor"
match = ["vendor", "noodle stall", "food stall", "stall owner"]   # words in the scene that mean this type
voice = "busy, practical, gossipy; wants a sale and a quiet night"
lines = [ "Noodles, three hundred. ...", ... ]   # 3 lines
```

A character's moves are the moves of its three lines. Loading validates: every `character.name` is a world NPC, each
has exactly 3 lines with distinct moves, every type has ≥1 match word and 3 lines.

**Picking** — `narrator/voices.py`, run in `_build_messages` after the cast refresh:
- For each named character in `session.present` with a sheet: pick a move uniformly from its moves minus
  `session.last_moves[name]`; record it. (Random, seeded by nothing special; the test seeds `random`.)
- Types: those whose match words appear in the action or the last 6 story lines (normalized, whole words), at most 2,
  most recently mentioned first. The line shown rotates: `session.type_turns[type] % 3`, then increments.
- Named characters come first; at most 3 characters plus 2 types in the block.

**Prompt** — one block after the Present line:

```
Voices this turn (how they sound; never repeat these lines word for word):
- Mama Sato will feed first, like: "Sit. Eat the eel while it's hot, child. Questions taste better on a full stomach."
- A street vendor (busy, practical, gossipy; wants a sale and a quiet night) sounds like: "You want news, buy two bowls. One bowl gets you weather."
```

Nothing is added when nobody with a sheet is present or mentioned.

**Copy cut** — `_drop_repeated_lines` adds every sample line in this turn's block to its 8-word-run reference set,
so a copied sample line is cut even on first use. The block's lines are stored on the session for the turn
(`session.voice_lines`), set in `_build_messages` and read by the filter.

**State** — `Session.last_moves: dict[str, str]`, `Session.type_turns: dict[str, int]`, `Session.voice_lines:
list[str]`; persisted like the other session fields (defaults when absent).

## How we'll know it worked

Same fixed 33-turn soak (`tools/soak_test.py --chips`) before and after, compared on: NPC speech sentences cut as
repeats (lower), distinct NPC speech openings (higher), sample lines copied (logged by the cut; should be rare),
and no new errors or empty turns. Builder's call how to count; a few lines in the soak summary is enough.

## Left to the builder

Exact prompt wording within the shape above; the match-word lists for each type (start from the draft's own
nouns); where the block sits relative to world notes if a test shows the order matters.
