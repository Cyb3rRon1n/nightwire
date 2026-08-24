# Nightwire Skill System Design

Status: designed, not yet implemented. Closes a gap flagged since Phase 1 and tracked in `ROADMAP.md`'s "Explicitly not doing (yet)" section — `RequestRoll.skill_mod` (`narrator/tools.py`) is currently clamped/trusted from the model instead of looked up against real character data, because Phase 1's ruleset never designed a skill list. First-pass numbers below (starting budget, rank range, the gating formula) are deliberately concrete rather than left as placeholders — same "ship a reasonable default, tune after real play" convention the original ruleset spec (`docs/superpowers/specs/2026-08-22-cyberpunk-ruleset-design.md`) already established. The one number deliberately left unfixed is how many points a milestone grants — that's a narrator judgment call by design (see "Leveling" below), not an oversight.

## Research: real precedent, not invention

Four comparable systems were checked directly (not from memory/assumption):

- **Cyberpunk RED** (R. Talsorian): 9 stats, 46 skills, ranked 1–10, resolved as `stat + skill + 1d10 vs DV` — nearly the same formula shape nightwire already committed to. Notably splits **Cool** (social-dominance skills: Persuasion, Streetwise, Leadership) from **Empathy** (Human Perception, Conversation) — this independently validates nightwire's own Cool/Presence split as a real, sound distinction rather than an invented one (nightwire's own six-attribute list predates this check).
- **Cyberpunk 2077, patch 2.0+** (nightwire's own stated aesthetic touchstone, already the deciding factor for the Roles/Lifepath split in the original ruleset spec): moved *away* from strict skill-per-attribute ownership. Attribute scores now just gate which perks/skill investment is unlockable; which attribute a check actually uses is decided contextually, not fixed per skill. This is the touchstone's own real design decision, at real content scale — the owner chose to follow it here rather than Cyberpunk RED's tighter 1:1 binding.
- **The Sprawl** and **CY_BORG** (base game): neither has a discrete skill layer at all — checks resolve directly off a raw attribute. Real evidence a lean cyberpunk system can validly skip skills; not the direction chosen here, but confirms skills are a deliberate addition, not a default every comparable system needs.
- The original spec's "2-4 skills per attribute" guess (`docs/superpowers/specs/2026-08-22-cyberpunk-ruleset-design.md`) was never validated against real source material — Cyberpunk RED's actual per-stat skill counts range 2–8. The list below (14 skills, 2-3 per attribute) is a deliberate middle ground: real per-attribute grouping for legibility and gating, without Cyberpunk RED's 46-skill sprawl (too much surface for an LLM narrator picking one via structured output on every roll — the same reliability concern that led to removing `start_combat`/`end_combat` from the narrator's tool surface, `ROADMAP.md` Phase 3).

## The key design translation: gating vs. rolling

Cyberpunk 2077 2.0's real change was splitting one relationship into two:

1. **Gating** — how far a character can invest skill points into a given skill. Still attribute-owned in a loose sense (an attribute governs a cluster of skills).
2. **Rolling** — which attribute a specific check actually uses. Fully contextual, decided per situation.

Nightwire's `RequestRoll` tool already decides an `attribute` per check independently (`Literal["body", "reflexes", ...]`, chosen by the narrator based on the fictional situation) — the rolling side of this split already exists in the codebase today. This design adds the gating side without touching the rolling side at all: a skill's rank is capped by its *governing* attribute, but nothing stops the narrator from testing that skill against a *different* attribute if the fiction calls for it (e.g. `Perception` mostly pairs with Intellect, but a narrator could reasonably roll it against Reflexes for a fast-reaction spot check — the tool schema doesn't restrict this, matching CP2077 2.0's own loosened binding).

## The skill list

14 skills, each tagged with one governing attribute (used only for the point-gating cap below — never for restricting which attribute a roll uses):

| Attribute | Skills |
|---|---|
| Body | Melee, Athletics |
| Reflexes | Ranged Combat, Stealth, Piloting |
| Tech | Hacking, Engineering, Demolitions |
| Cool | Intimidation, Streetwise |
| Intellect | Perception, Deduction |
| Presence | Persuasion, Performance |

Internal (snake_case) names: `melee`, `athletics`, `ranged_combat`, `stealth`, `piloting`, `hacking`, `engineering`, `demolitions`, `intimidation`, `streetwise`, `perception`, `deduction`, `persuasion`, `performance`.

Lives in a new `ruleset/skills.py`, same shape as `ruleset/roles.py`/`ruleset/lifepaths.py` — a `Skill` dataclass (`name`, `governing_attribute`, `description`) in a `SKILLS: dict[str, Skill]` module-level dict.

## Ranks and the gating cap

- Ranks run **0–5** (0 = untrained, 5 = master) — scaled down from Cyberpunk RED's 1–10, since nightwire's attribute modifier (`(score - 10) // 2`) already produces a small range (roughly -1 to +3 for realistic starting scores); a rank going to 10 would dwarf the attribute term the formula already committed to, unbalancing `1d10 + attribute + skill`.
- **Gating cap**: `min(5, modifier(governing_attribute_score) + 3)`. A new `ruleset/skills.py` function: `skill_cap(attribute_score: int) -> int`.
- **Honest current-state caveat**: no character ever has real attribute scores today — `CharacterSheet.attributes` defaults to `{}` and every read falls back to `.get(x, 10)` (confirmed: only test files ever populate `attributes`, no production path does — attribute point-buy is a separate, explicitly out-of-scope gap per this brainstorm's own scoping). With every attribute reading as 10, `modifier(10) == 0`, so every skill's cap is uniformly 3 until that gap is closed. This is a real, working first pass — it just means today's caps don't yet differentiate by role/build. Attribute point-buy (when it's designed) plugs directly into this same formula with no rework needed here.
- **Untrained use**: rank 0 contributes 0 to the roll — same as an unset `skill_mod` behaves today, so this isn't a new penalty, just a real source for the number instead of a model-invented one.

## Storage — `CharacterSheet` (`engine/character.py`)

Two new fields:

```python
skills: dict[str, int] = field(default_factory=dict)
unspent_skill_points: int = 0
```

Persists via the existing `asdict`/`json.dumps` round-trip in `engine/persistence.py` automatically; `load()` needs `.get("skills", {})` / `.get("unspent_skill_points", 0)` defaults for backward compatibility with session files saved before this change (same pattern already used for `speaker_voices`/`pending_initiative`).

## Roll mechanic — `narrator/tools.py`

`RequestRoll.skill_mod: int` is replaced with `RequestRoll.skill: Literal[<14 skill names>]`. `_execute_request_roll` looks up `character.skills.get(tool.skill, 0)` instead of clamping a model-supplied integer — the `# ponytail:` comment documenting the old clamp-as-a-workaround gets deleted along with the workaround itself, not just left stale.

## Acquisition

**Starting points** — a flat budget of **8 points**, spent via a new frontend skill picker at character creation (same join-flow pattern as today's Role/Lifepath dropdowns). The client computes the allocation locally against the same `skill_cap()` rule (mirrored in TypeScript, same duplication precedent `frontend/src/app/nightwire/page.tsx`'s `ROLES`/`LIFEPATHS` constants and `server/portrait.py`'s `_ROLE_VISUALS` already established for ruleset content) and sends it as a new optional `skills?: Record<string, number>` field on `JoinMessage` — mirroring the existing (currently unused in the frontend) optional `attributes?` field already on that message type.

`server/dispatch.py`'s `join` handling validates server-side before trusting it (never trust client-computed budget math over the wire): total spent ≤ 8, and each `skills[name] ≤ skill_cap(attributes.get(governing_attribute, 10))`. Reject with `ValueError` on violation — same validate-at-the-boundary convention `roll_initiative`'s `unknown player_id` check already uses.

**Leveling** — the narrator's existing `ApplyCharacterUpdate` tool gets one new optional field: `skill_points_delta: int = 0`. A milestone judgment call, trusted at the same level `ApplyCharacterUpdate` already trusts HP/armor/condition/inventory changes — no new reliability risk introduced (unlike the removed `start_combat`/`end_combat` narrator tools, this doesn't ask the model to pick a *specific* skill to bump, just a point count, so there's no "did the model apply this to the wrong slot" failure mode to probe for). Points land in `unspent_skill_points`, not auto-assigned — the player decides where they go.

**Spending** — a new player-initiated WebSocket message, mirroring `roll_initiative`'s pattern (a small, single-purpose message handled in `server/dispatch.py`, no narrator/LLM involvement):

```json
{"type": "allocate_skill_points", "skill": "hacking", "amount": 2}
```

Validated: `amount > 0`, `character.unspent_skill_points >= amount`, and `character.skills.get(skill, 0) + amount <= skill_cap(...)`. On success: increments `skills[skill]`, decrements `unspent_skill_points`. No respec/decrease path — spend-only, matching the ruleset's existing bias toward the simplest mechanic that works (no rule anywhere in nightwire currently supports undoing a character-build choice).

The same allocation UI serves both the character-creation picker (spending the starting budget before `join`) and later milestone spends (reachable from the existing `Ctrl+K` character sheet overlay, `frontend/src/app/nightwire/CharacterSheetOverlay.tsx`) — one component, two call sites, since both ultimately just call the same client-side "spend N points into this skill" action (the only difference is whether it's expressed as part of the `join` message or as a standalone `allocate_skill_points` message after the character already exists server-side).

## Frontend touchpoints

- `frontend/src/lib/nightwire/protocol.ts`: `JoinMessage.character.skills?: Record<string, number>`; new `AllocateSkillPointsMessage` added to `ClientMessage`; `CharacterSheet.skills`/`unspent_skill_points` added to the server-pushed view type.
- `frontend/src/app/nightwire/page.tsx`: a skill picker in the pre-join form (budget counter + steppers, same `nw-field`/`nw-btn-*` theme classes from today's Neon Noir pass), gated the same way Role/Lifepath selects are today.
- `frontend/src/app/nightwire/CharacterSheetOverlay.tsx`: shows current skill ranks (already has an "Attributes" section with the exact same `dict[str, int]` shape — skills render the same way), plus the same picker component when `unspent_skill_points > 0`.

## Testing

Follows the project's existing TDD/pytest convention, verifiable with zero GPU/live-model calls (same stubbed-narrator pattern already used for this session's combat-controls and theming work):

- `ruleset/skills.py`: `skill_cap()` unit tests (boundary values, the min(5, ...) clamp).
- `narrator/tools.py`: `_execute_request_roll` looks up a real skill rank instead of trusting a supplied number; unknown/untrained skill defaults to 0.
- `server/dispatch.py`: `join` accepts a valid starting allocation, rejects an over-budget or over-cap one; `allocate_skill_points` accepts a valid spend, rejects insufficient points or an over-cap spend.
- `narrator/tools.py`'s `_execute_apply_character_update`: `skill_points_delta` lands in `unspent_skill_points`.
- `engine/persistence.py`: round-trip test for `skills`/`unspent_skill_points`, plus a legacy-file-missing-the-field default test (same pattern `speaker_voices`/`pending_initiative` already have).

## Explicitly out of scope (this pass)

- **Attribute point-buy** — attributes keep defaulting to 10 everywhere, as they do today. The gating cap formula already accepts real attribute scores the moment that gap is closed; no rework needed here.
- **Skill respec/decrease** — spend-only, no mechanism to move points after they're spent.
- **Role-weighted starting budgets** — a flat 8 points for every role. Roles already differentiate outcomes indirectly (a Solo's high Reflexes, once attribute point-buy exists, raises the cap on Reflexes-governed skills) without a second parallel role→budget table.
- **The rest of the leveling system** — what triggers a "milestone" beyond the narrator's own judgment, whether milestones also affect HP/attributes, etc. `ApplyCharacterUpdate.skill_points_delta` gives the narrator a trusted way to *grant* skill points using a mechanism that already exists; the broader leveling economy stays an open gap, same as it is today.
