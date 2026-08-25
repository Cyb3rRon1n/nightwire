# Nightwire Attribute Point-Buy Design — Phase 9

Status: designed, not yet implemented. Closes a gap Phase 1's own ruleset spec explicitly flagged as open ("Not independently researched against alternative attribute-count/generation schemes") and Phase 7's skill system spec flagged again as a known, security-relevant gap. Every choice below is grounded in independent external research — no oracle-precedent citations.

## The actual requirement

`CharacterSheet.attributes` defaults to `{}` today — no character-creation step ever sets real scores, so every attribute reads as a uniform placeholder everywhere it's consumed (`ruleset/attributes.py`'s `modifier()`, `narrator/tools.py`'s `request_roll` attribute lookup, `engine/turns.py`'s `roll_initiative`). Two real consequences: every skill's cap (`skill_cap = min(5, modifier(attribute_score)+3)`, Phase 7) is uniformly 3 for every character since its input never varies, and `server/dispatch.py`'s `join` handler validates skill ranks/budget server-side but never validates the client-supplied `attributes` dict at all — a dishonest client can already inflate scores today to unlock higher skill caps.

This adds a point-buy allocation step to character creation, server-validated the same way skill allocation already is, so attribute scores become real, player-chosen, and trustworthy.

## Precedent: CP2077's flat-cost model, not D&D/BG3's escalating one

The existing `modifier(score) = (score - 10) // 2` formula is literally D&D's ability-modifier formula — already disclosed and accepted in Phase 1's spec as a deliberate, honest compromise, not up for revisiting here. But the *allocation mechanic* that produces those scores is a separate design axis, and here real precedent points the other way:

- **D&D 5e's own point-buy** (the system Baldur's Gate 3 runs unmodified) spends a 27-point budget across a 8-15 range with an *escalating* cost — flat 1-point-per-1-score up to 13, then 2 points per step at 14 and 15 ([Roll for Two](https://www.rollfortwo.com/articles/point-buy-5e/)). That curve exists specifically to discourage dumping points into one stat — it's a balance lever for a class-and-multiclass game with very different tuning needs than nightwire's.
- **Cyberpunk 2077 itself** (this project's own stated aesthetic touchstone, per `CLAUDE.md`) uses flat-cost attribute spending — every point costs the same regardless of current score, so specializing hard in one stat costs exactly what spreading evenly costs. No escalating penalty.
- Nightwire's own ruleset spec already committed to matching **CY_BORG/Cyberpunk RED's lowest-complexity class**, explicitly contrasted against Shadowrun/Genesys-style crunch. An escalating cost curve is exactly the kind of bookkeeping that principle argues against.

**Decision: flat cost**, matching CP2077's actual mechanic and nightwire's own already-established complexity target — not D&D/BG3's escalating curve, even though the modifier formula both systems share came from the same place.

Cyberpunk RED's own stat range (a "Complete Package" build spends 62 points across 10 STATs, range 2-8, flat cost — [StartPlaying](https://startplaying.games/blog/posts/how-do-you-create-character-cyberpunk-red)) was considered and rejected on a concrete technical ground, not a style preference: run through nightwire's existing 10-centered modifier formula, a 2-8 range produces only negative modifiers (-4 to -1) — a real mismatch, not a complexity judgment call.

## Role bonus: a flat stat bump, not a discount

Every role already has a documented "primary attribute" (`ruleset/roles.py`): Solo→Reflexes, Netrunner→Tech, Techie→Tech, Fixer→Presence. Confirmed with the project owner: this should become mechanically real, not stay flavor text.

**CY_BORG** — the rules-lightest system surveyed, explicitly the low-complexity comparison class nightwire already targets — has the exact precedent needed even without point-buy: "if you have a class, you roll your key ability with a bonus modifier" ([StartPlaying](https://startplaying.games/blog/posts/how-to-build-a-cy-borg-character)). A flat bonus on the role's key attribute, not a variable per-attribute discount, is simpler to implement and explain, and matches this precedent directly.

**Decision**: the role's primary attribute starts at 11 (base 10, +1 role bonus) before any points are spent. The 12-point budget then applies on top, identically for every role — no per-role budget table, matching the flat-8-points-for-every-role precedent Phase 7 already established for skills (explicitly left as a possible future gap there, kept consistent here rather than solved differently in two adjacent systems).

## The numbers

- **Base score**: 10 for all six attributes (matches the modifier formula's centerpoint — `modifier(10) == 0`).
- **Role bonus**: the role's primary attribute starts at 11, not 10.
- **Budget**: 12 points.
- **Range**: 6-14 per attribute (deviation of at most 4 in either direction from the post-role-bonus starting value) — `modifier(6) == -2`, `modifier(14) == 2`, a real but bounded swing.
- **Cost**: flat, 1 point of budget per 1 point of score, in either direction — raising an attribute above its starting value spends budget; lowering one below its starting value refunds budget (the CP2077-style "no penalty for specializing" mechanic this whole design is grounded in).

Worked example matching the assassin/hacker playstyle raised during brainstorming: pick Netrunner (Tech starts at 11). Raise Tech to 14 (+3, spending 3 of the 12-point budget) and Cool to 14 (+4, spending 4) — 7 spent, 5 left. Lower Body to 6 (-4, refunding 4) to help cover it, or just leave the remaining 5 unspent (banked budget doesn't have to be used) and spread it across the other attributes instead. Either way, the floor/ceiling bound how far any single stat can go, but nothing in the cost curve penalizes going there.

## Server-side validation

New validation in `server/dispatch.py`'s `join` handler, same shape and same file as the existing skill-allocation validation it sits beside:

- Reject any attribute name outside the real six (`ruleset/attributes.py`'s `Attribute` enum).
- Reject any score outside 6-14.
- Reject a total spend (summed deviation from each attribute's correct starting value — 11 for the role's primary attribute, 10 for the other five) that exceeds the 12-point budget.
- Missing attributes in the payload default to their starting value (10, or 11 for the primary) rather than erroring — a player who doesn't touch the allocator at all still gets a valid character.

This closes the exact trust gap Phase 7 flagged: attribute scores become as server-authoritative as skill ranks already are.

## UI flow

A new allocation step in `page.tsx`'s pre-join character-creation form, positioned **before** the existing `SkillPicker` (confirmed with the project owner) — skill caps shown in that picker become the real, attribute-driven numbers instead of a uniform 3 for everyone, which is the whole point of building this. Role selection happens first (already the case), so the primary-attribute bonus and its starting-value implications are known before the player starts spending attribute points.

## What's deliberately deferred

- Exact frontend component shape/props for the new allocator — implementation-phase work, same as every prior phase's UI has deferred it.
- Post-creation attribute growth (an attribute-side equivalent to `skill_points_delta`'s milestone spends) — not touched here; Phase 7 already left the broader leveling economy as an open gap, and this design doesn't need to solve it to make starting attributes real.
- Role-weighted *budgets* (different total points per role, not just a starting bonus on one attribute) — the flat-budget-every-role choice here deliberately matches Phase 7's skill-budget precedent rather than diverging from it; revisit both together if this ever becomes a real balance problem, not preemptively.
- Any attribute range/cap changes beyond starting-character generation (e.g. a wider ceiling unlocked by later advancement) — out of scope until the leveling economy above actually exists.
