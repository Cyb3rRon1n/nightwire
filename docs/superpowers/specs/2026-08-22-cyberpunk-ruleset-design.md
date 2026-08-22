# Nightwire Ruleset Design — Phase 1

Status: designed, not yet implemented. This is the new project's "SRD" — homebrew, original, no adapted-system content (see `ROADMAP.md`'s "Ruleset decision" for why). First-pass numbers below are deliberately concrete rather than left as placeholders — ship a reasonable default, tune it after real play, rather than blocking on getting every number right up front. Anything marked "first pass" is expected to move once this is actually played.

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

Same tool-call shape as a flat "roll, add two numbers, compare to one target" system (the lowest-complexity class found in the cyberpunk-systems survey — CY_BORG and Cyberpunk RED both flat single-die-plus-modifiers, versus Shadowrun/Neon City Overdrive/Interface Zero/Genesys all flagged medium/high for variable pool sizes and success-counting) — the second threshold is an extra comparison, not additional dice or pooled counting, so it stays in the same low-complexity class.

**DC bands, first pass** (same "named bands" convention CY_BORG uses, tune after real play):

| DC | Difficulty |
|---|---|
| 8 | Easy |
| 12 | Moderate |
| 16 | Hard |
| 20 | Extreme |

**Critical results**: a natural 10 is always at least a success (even against a DC the modified total wouldn't otherwise beat) and narrates as a clean success regardless of margin; a natural 1 is always a failure and narrates as a complication-laden one, mirroring the crit-success/crit-fail convention CY_BORG and Cyberpunk RED both already use.

## Attributes

Six, deliberately the same shape as D&D's six ability scores (a `(score - 10) // 2`-style modifier formula, point-buy/array-style generation) — familiar to the owner. **Not independently researched against alternative attribute-count/generation schemes** (flagged honestly, same as the earlier role-count gap) — CP2077 itself uses five, no Presence-equivalent, because scripted dialogue doesn't need a social attribute the way a dice-driven TTRPG does; six was kept here on the reasoning that Nightwire's Fixer role needs a real attribute to key off, not from a researched comparison of attribute-count schemes generally:

| Attribute | Covers |
|---|---|
| **Body** | Physical power, toughness, melee damage |
| **Reflexes** | Speed, agility, ranged/melee accuracy, initiative |
| **Tech** | Hacking, engineering, hardware, cyberware interfacing |
| **Cool** | Composure under pressure, intimidation, resisting fear/manipulation |
| **Intellect** | Knowledge, reasoning, perception-adjacent checks |
| **Presence** | Charisma, social skill, persuasion/deception |

## Roles

**Four, locked in after real research — not an analogy to any other project.** The path here: a first pass proposed 4 by loose analogy (unresearched); a TTRPG-focused deep-dive (Cyberpunk RED's 10 Role Abilities, Shadowrun's archetypes, The Sprawl's playbooks) argued for 6, finding Medtech mechanically distinct from Tech (zero-overlap specialty trees) and Infiltrator a real gap (The Sprawl splits stealth from direct combat); checking Cyberpunk 2077 itself — Nightwire's own explicit aesthetic touchstone — pulled the other way: CDPR's own developers name exactly **three** official archetypes (Solo, Netrunner, Techie), the game has **no dedicated medic build at all** (healing is items — Blood Pump, MaxDoc injectors, not a skill tree), and stealth is an explicitly **cross-cutting** perk tree ("combine stealth perks with quickhacks"), not a fourth hard class.

Final call: weight the explicit aesthetic touchstone for the "hard class" question (drop Medtech and Infiltrator as separate roles), keep **Fixer** as a fourth role for a reason CP2077 itself never had to solve — a TTRPG rolls real dice for persuasion/negotiation, a video game just branches scripted dialogue, so the social-mechanic role earns its slot independent of the game's own choices.

| Role | Primary attribute | What it does | Genre precedent |
|---|---|---|---|
| **Solo** | Reflexes | Front-line combat; best attack rolls, highest Health, a passive Initiative/Awareness edge | CP2077's own Solo archetype; Cyberpunk RED's Combat Sense ability |
| **Netrunner** | Tech (Hacking skill) | Hacking — this role's "spellcasting equivalent," both out-of-combat (bypass locks, pull data) and in-combat support (disable a weapon/camera/drone) | CP2077's Netrunner (quickhacks); Cyberpunk RED's Interface ability |
| **Techie** | Tech (Repair/Engineering skill) | Repairs damaged gear/cyberware, installs upgrades, crafts — keeps the party's equipment working, not a healer | CP2077's own official name for this exact archetype; Cyberpunk RED's Maker ability |
| **Fixer** | Presence | Negotiation, contacts, contraband access, talking past trouble instead of shooting through it | Folds Cyberpunk RED's Fixer + Media and Shadowrun's Face — all three lean on the same Charisma-adjacent mechanics |

**Healing is item-based** (stims/med-kits, no skill check), matching CP2077's own approach exactly rather than inventing a dedicated medic role the touchstone itself doesn't have.

Each role gets a small set of starting features at creation — exact feature text is implementation-detail work for the engine-building phase, not blocking this spec.

## Lifepath — a separate character-creation axis

**Nomad / Streetkid / Corpo** (CP2077's own terms, already genre-perfect) — confirmed via research to be a clean, separate system in CP2077: pure narrative background (opening scenario, dialogue/opportunity hooks), **zero mechanical stat effect**, cleanly split from the build/skill system. Nightwire adopts the same split rather than folding background flavor into the Role list:

| Lifepath | Flavor |
|---|---|
| **Corpo** | Came from megacorp life — contacts inside corporate structures, insider knowledge, expects to be listened to |
| **Streetkid** | Grew up in the sprawl — gang contacts, street cred, knows how things really work at ground level |
| **Nomad** | Raised outside the city in a clan/family — vehicle know-how, an outsider's read on the corps, strong found-family loyalty |

No stat bonuses — a player picks a Role (what you're mechanically good at) and a Lifepath (where you came from) independently, same as CP2077 itself does.

## Gear & cyberware

- **Structured items** (`{name, quantity, bonus}`) — a mundane and an upgraded copy of the same base item are separate stacks, not merged, so a character carrying both a plain pistol and a modded one doesn't lose the distinction. Standard stacking-with-a-variant-bonus pattern in loot-bearing games generally, not a novel design.
- **Equip slots**: weapon, armor, and a new **cyberware install slots** concept (e.g. neural, ocular, arm, dermal) — a piece of cyberware occupies a slot and grants a real mechanical bonus (an attribute or skill bonus, an armor/HP bonus, or unlocks an action). Not independently verified against CP2077's own actual slot taxonomy in the research passes so far (those focused on attributes/archetypes/medic/stealth/lifepath, not the cyberware-slot system specifically) — general genre knowledge that cyberware occupies body-location slots, not a researched citation. Worth a dedicated check before finalizing exact slot names.
- **No cybernetic corruption/humanity-loss subsystem in this first slice** — Cyberpunk RED's Empathy-loss-from-cyberware mechanic is a real, deliberate omission here, not an oversight: it's an extra resource-tracking system layered on top of the core loop, and the "smallest real slice" principle argues for shipping without it first and adding it later only if actual play shows the game needs that tension.

## Hacking (Netrunner's core action)

A skill check, not a separate resource-managed subsystem: `Tech + Hacking skill` vs. a target's DC, using the same tiered d10 roll as everything else. Deliberately **not** modeled as its own spell-slot-equivalent economy — that would be new resource-tracking complexity mirroring D&D's spell slots, and nothing in the research so far shows hacking needs its own resource economy distinct from a normal skill check (a standard YAGNI call, not project-specific).

## Combat

- Same tiered d10 resolution applied to attack rolls (attacker's roll vs. defender's DC, typically a flat Armor-derived DC rather than a rolled defense — simpler, one less roll per exchange).
- **Health** (Nightwire's HP-equivalent) + **Armor Rating** (Nightwire's AC-equivalent, flat DC contribution rather than D&D's "roll to hit vs. AC" — functionally the same shape, renamed for genre fit).
- Weapon damage: a die size per weapon category (melee/pistol/rifle/heavy) — a near-universal TTRPG convention (D&D, Cyberpunk RED, and most others all scale damage by weapon category), homebrewed numbers rather than copied from a licensed source.
- Initiative: `1d10 + Reflexes`, rolled once at combat start, cycles a turn order — consistent with Cyberpunk RED's own general approach (its initiative is REF-based), though the exact formula wasn't independently re-verified in the research passes so far; flagged rather than presented as a confirmed citation.

## Advancement

**Milestone leveling** — the GM (LLM narrator) advances a character's level at story beats/major accomplishments, not from an XP-per-kill table. Chosen specifically to avoid needing to invent and tune an XP-by-threat-level table for every enemy archetype from scratch (unlike oracle, which could source real numbers from the D&D SRD's own CR-to-XP table) — milestone leveling needs no such table at all, matching "don't build what a real license would have given you for free, when nothing forces you to design it from scratch."

## What's deliberately not in this first slice

- Cyberware corruption/humanity loss (see "Gear & cyberware" above).
- A skill list finalized in detail — each attribute needs 2-4 named skills (e.g. Reflexes → Melee, Ranged, Stealth), left for the engine-building phase since it's mechanical plumbing, not a design fork.
- Exact starting Health/Armor formulas and the full weapon/gear catalog — real content, designed alongside the engine that will actually consume it, not a gap in this spec.
- NPC/enemy stat block catalog (name, stats, HP, actions, traits) — populated once there's an engine to test them against.
