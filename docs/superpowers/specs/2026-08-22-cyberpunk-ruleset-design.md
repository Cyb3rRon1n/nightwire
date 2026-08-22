# Nightwire Ruleset Design — Phase 1

Status: designed, not yet implemented. This is the new project's "SRD" — homebrew, original, no adapted-system content (see `ROADMAP.md`'s "Ruleset decision" for why). First-pass numbers below are deliberately concrete rather than left as placeholders, matching oracle's own established pattern of shipping a reasonable default and tuning it after real play rather than blocking on getting every number right up front — anything marked "first pass" is expected to move once this is actually played.

## Setting & tone

- **Far-future, pulpy, neon-max** — closer to Cyberpunk 2077's aesthetic than a grounded near-future noir. Megacorps, arcologies, heavy body modification, chrome-and-neon streets.
- **Content**: full genre-typical grit by default — graphic violence, body horror from cyberware, drug culture, corporate brutality, sex/nudity as the story calls for it. This is a private tool for the owner and friends; the narrator's system prompt should not add safety hedging beyond what the backend itself enforces.
- **Backend policy**: local-first (Ollama), with a hosted API as a secondary option. A hosted backend's own safety layer isn't something the system prompt can override — pursued deliberately anyway for quality/speed flexibility, with the known tradeoff that hosted play may refuse content local play wouldn't.
- **Multiplayer scope**: solo, or same-machine/LAN — no requirement to be reachable over the open internet.

## Core resolution mechanic

**`1d10 + attribute + skill` vs. a Difficulty Class (DC), three outcome bands:**

| Result | Band |
|---|---|
| Total ≥ DC + 5 | Clean success |
| Total ≥ DC (but < DC+5) | Success with a complication |
| Total < DC | Failure |

Same tool-call shape as a flat "roll, add two numbers, compare to one target" system (the lowest-complexity class found in the Phase 1 research pass) — the second threshold is an extra comparison, not additional dice or pooled counting, so it doesn't add the kind of complexity oracle's own reliability testing found costly for small local models.

**DC bands, first pass** (same "named bands" convention CY_BORG uses, tune after real play):

| DC | Difficulty |
|---|---|
| 8 | Easy |
| 12 | Moderate |
| 16 | Hard |
| 20 | Extreme |

**Critical results**: a natural 10 is always at least a success (even against a DC the modified total wouldn't otherwise beat) and narrates as a clean success regardless of margin; a natural 1 is always a failure and narrates as a complication-laden one, mirroring the crit-success/crit-fail convention CY_BORG and Cyberpunk RED both already use.

## Attributes

Six, deliberately the same shape as D&D's six ability scores (same `(score - 10) // 2`-style modifier formula and standard-array-style generation oracle already validated) — familiar to the owner, and a proven, simple mechanic to reuse rather than reinvent:

| Attribute | Covers |
|---|---|
| **Body** | Physical power, toughness, melee damage |
| **Reflexes** | Speed, agility, ranged/melee accuracy, initiative |
| **Tech** | Hacking, engineering, hardware, cyberware interfacing |
| **Cool** | Composure under pressure, intimidation, resisting fear/manipulation |
| **Intellect** | Knowledge, reasoning, perception-adjacent checks |
| **Presence** | Charisma, social skill, persuasion/deception |

## Roles

Four to start (mirroring oracle's own Fighter/Wizard/Rogue/Cleric first slice, not Cyberpunk RED's full ten) — each maps to a primary attribute and a starting-kit flavor:

| Role | Primary attribute | Fills the niche of (D&D analogue) |
|---|---|---|
| **Solo** | Reflexes | Fighter — front-line combat specialist |
| **Netrunner** | Tech | Wizard — hacking is this role's "spellcasting" |
| **Fixer** | Presence | Rogue — skills, social, connections, contraband access |
| **Tech** | Tech/Body | Cleric — support, repairs, cyberware installation/maintenance, field medicine |

Each role gets a small set of starting features at creation (mirroring `level_1_features` in oracle) — exact feature text is implementation-detail work for the engine-building phase, not blocking this spec.

## Gear & cyberware

- **Structured items**, same shape as oracle's `InventoryItem` (`{name, quantity, magic_bonus}` generalized to a genre-neutral bonus field) — a mundane and an upgraded copy of the same base item are separate stacks, same precedent oracle already established.
- **Equip slots**: weapon, armor, and a new **cyberware install slots** concept (e.g. neural, ocular, arm, dermal) — a piece of cyberware occupies a slot and grants a real mechanical bonus (an attribute or skill bonus, an armor/HP bonus, or unlocks an action), the same "bonus lives on the item, engine reads it" pattern oracle's `magic_bonus` already uses for weapons/armor.
- **No cybernetic corruption/humanity-loss subsystem in this first slice** — Cyberpunk RED's Empathy-loss-from-cyberware mechanic is a real, deliberate omission here, not an oversight: it's an extra resource-tracking system layered on top of the core loop, and the "smallest real slice" principle argues for shipping without it first and adding it later only if actual play shows the game needs that tension.

## Hacking (Netrunner's core action)

A skill check, not a separate resource-managed subsystem: `Tech + Hacking skill` vs. a target's DC, using the same tiered d10 roll as everything else. Deliberately **not** modeled as its own spell-slot-equivalent economy — that would be new resource-tracking complexity mirroring D&D's spell slots, and there's no evidence yet (matching oracle's own "don't build what hasn't been shown necessary" discipline) that hacking needs its own economy distinct from a normal skill check.

## Combat

- Same tiered d10 resolution applied to attack rolls (attacker's roll vs. defender's DC, typically a flat Armor-derived DC rather than a rolled defense — simpler, one less roll per exchange).
- **Health** (Nightwire's HP-equivalent) + **Armor Rating** (Nightwire's AC-equivalent, flat DC contribution rather than D&D's "roll to hit vs. AC" — functionally the same shape, renamed for genre fit).
- Weapon damage: a die size per weapon category (melee/pistol/rifle/heavy), same convention as oracle's real SRD weapon table, homebrewed rather than copied from a licensed source.
- Initiative: `1d10 + Reflexes`, same formal-initiative shape oracle already built and validated (rolled once at combat start, cycles a turn order) — this piece ports conceptually cleanly regardless of the from-scratch engine rebuild, since it's genre-agnostic in oracle's own implementation already.

## Advancement

**Milestone leveling** — the GM (LLM narrator) advances a character's level at story beats/major accomplishments, not from an XP-per-kill table. Chosen specifically to avoid needing to invent and tune an XP-by-threat-level table for every enemy archetype from scratch (unlike oracle, which could source real numbers from the D&D SRD's own CR-to-XP table) — milestone leveling needs no such table at all, matching "don't build what a real license would have given you for free, when nothing forces you to design it from scratch."

## What's deliberately not in this first slice

- Cyberware corruption/humanity loss (see "Gear & cyberware" above).
- A skill list finalized in detail — each attribute needs 2-4 named skills (e.g. Reflexes → Melee, Ranged, Stealth), left for the engine-building phase since it's mechanical plumbing, not a design fork.
- Exact starting Health/Armor formulas and the full weapon/gear catalog — same "real content, designed alongside the engine that will consume it" reasoning oracle's own SRD data followed, not a gap in this spec.
- NPC/enemy stat block catalog — structurally will mirror oracle's monster entries (name, stats, HP, actions, traits), populated once there's an engine to test them against.
