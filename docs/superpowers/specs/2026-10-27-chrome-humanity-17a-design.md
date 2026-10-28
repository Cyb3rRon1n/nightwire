# Nightwire Chrome and Humanity Design: Phase 17a

Status: designed, not yet implemented. Revised with the owner on 2026-10-27 from `2026-10-27-cyberware-humanity-design.md`. That earlier spec's research, its catalog and its humanity tiers carry over. Its debt and torite sections become the input for Phase 17b.

## Why this revision

After the original cyberware spec was written, three things shipped:
- Phase 15, the NPC cast and utsusemi;
- Phase 16, two-step player rolls with a roll card.

Phase 16's live probe also exposed a balance problem: the model chose **Hard (DC 16) for all 8 rolls**. With starting modifiers around +2, a d10 can't reach 16, so Hard was winnable only on a natural 10. Chrome's +1 and +2 bonuses are the core of this phase, and they would mean nothing against an unwinnable DC.

## Owner decisions (2026-10-27)

- **Retune the DCs** in this phase.
- **⚡ Overclock lives on the roll card.** You decide at the moment of risk, with the DC in view. There is no separate "arm" step.
- **NPC tie-ins.** All four were chosen (Saeko leads the repos, Old Hara unthrottles, Arakawa pays the debt, and an utsusemi mechanic). They belong to the debt side, so they go to 17b.
- **Split.**
  - 17a (this spec): chrome, humanity, retuned DCs, the overclock card.
  - 17b (designed after 17a ships): installments and the repo clock, the torite escalation led by Saeko Kirigaya, Arakawa's gigs as the main way to pay, Old Hara's off-the-books unthrottle, and an utsusemi mechanic.
- Unchanged from the original spec:
  - story pressure, never a takeover;
  - creation chrome plus the chrome-ya;
  - approach A (a humanity meter, slots and a catalog);
  - Edgerunners as an influence, not a template (the "Lucy moment" became a confrontation scene).

## Research grounding

All of it carries over from `2026-10-27-cyberware-humanity-design.md`: Cyberpunk RED humanity, Shadowrun Essence, CP2077 2.0 capacity and no player cyberpsychosis, Edgerunners, Deus Ex Neuropozyne, Call of Cthulhu sanity, LLM games keeping state in code, and the catalog size.

**For the DC retune.** A d10 system with flat modifiers needs DCs inside the die's range. Cyberpunk RED pairs a d10 with stat plus skill sums around 10–14, and its DVs scale to match (general knowledge, consistent with the engine's existing "1d10 + attribute + skill" core from Phase 1). Nightwire's starting totals are smaller (attribute modifiers −1 to +3 and skill ranks 0–3), so its ladder has to sit lower.

## Design

### 1. Retuned difficulty (`ruleset/difficulty.py`)

`Difficulty` becomes **EASY 6, MODERATE 9, HARD 12, EXTREME 15** (was 8/12/16/20).

The natural 10 and natural 1 rules are unchanged. Roll bands are unchanged: a clean success is DC+5 or more, a complication is DC to DC+4, and anything lower is a failure.

With +2 total, success (including complications) is roughly:
- Easy 90%;
- Moderate 60%;
- Hard 30%;
- Extreme 10% (a natural 10 is always a clean success).

A chrome +1 or +2 moves each of those by 10–20 points.

One system-prompt line goes next to the roll rule:

> Most risks are Moderate; Hard is for real danger; Extreme is rare.

Every test that asserts the old numbers (Phase 16's `dc` 16 and "vs 16" expectations, plus any ruleset or difficulty tests) is updated to the new values. **No other behavior changes.**

### 2. Humanity


- `humanity` starts at **100** and never goes above 100 or below 0.
- **Loss:** each install costs that item's fixed cost. Each overclock costs **1d6**, rolled by the engine when the overclocked roll resolves (see §5).
- **Gain:**
  - The narrator may set `apply_character_update.humanity_delta` (schema-bounded to **0 to +5**, gains only) for therapy or a real human moment: a friend, a meal, a choice to stay human.
  - Removing chrome returns **half its install cost, rounded down**.

| Humanity | Tier | Effect |
|---|---|---|
| 70–100 | Steady | none |
| 40–69 | Frayed | narrative only: small symptoms |
| 20–39 | Slipping | overclocks +1; persuasion and performance rolls −1 |
| 1–19 | Edge | overclocks +1; persuasion and performance rolls −2; the narrator plays episodes |
| 0 | Gone too far | as Edge, plus no new installs and no overclocking until humanity is back above 20 |

- **The lock at 0.** When humanity reaches 0, the engine sets `gone_too_far = True`. While it is set, installs and overclocks are refused. It clears when humanity rises above 20.
- **The confrontation scene.** The first time a character drops below 40, the engine sets `slipping_warned = True` and adds a one-turn `World event:` line telling the narrator that someone close notices and confronts them. It fires once per character.
- **Tier text** for the narrator is a short line per tier in the system prompt (see Prompt), not a rules list.

### 3. Slots

Capacity is **3 + Body modifier, minimum 2**. Body uses the existing `modifier()`. Each item uses 1 slot.

### 4. Catalog (`ruleset/cyberware.py`)

`Chrome` is a frozen dataclass with these fields:
- `id`
- `name`
- `description`
- `roll_bonus: dict[skill, int]`
- `armor: int`
- `max_health: int`
- `humanity_cost`
- `installments`
- `overclock: Overclock | None`

`CHROME: dict[str, Chrome]`:

| id | Name | Effect | Humanity cost | Installments |
|---|---|---|---|---|
| hawkeye_optics | Hawkeye optics | +1 perception | 3 | 2 |
| reflex_wires | Reflex wires | +1 ranged_combat | 6 | 3 |
| kagerou | Kagerou | ⚡ overclock: roll 2d10 and keep the higher, +2 to the roll | 10 | 5 |
| kama_blades | Kama blades | +2 melee | 8 | 4 |
| oni_arms | Oni arms | +1 melee, +1 athletics | 7 | 4 |
| lacquer_skin | Lacquer skin | +10 armor | 6 | 3 |
| yomi_jack | Yomi jack | +1 hacking; ⚡ overclock (deep dive): +3 hacking | 5 | 3 |
| pain_editor | Pain editor | +15 max health | 5 | 3 |
| silk_tongue | Silk tongue | +1 persuasion | 3 | 2 |
| kumo_hand | Kumo hand | +1 engineering | 3 | 2 |
| neon_ink | Neon ink | fashionware, style only | 0 | 1 |

Rules for the catalog:
- Skill names are the existing 14 in `ruleset/skills.py`.
- A character cannot install the same item twice.
- **Kagerou's overclock** applies to any roll.
- **Yomi jack's overclock** applies only when the roll's skill is `hacking`. Its overclock button only appears on hacking rolls.
- The tier bonus (+1 at Slipping and Edge) adds to either overclock's flat bonus.

Effects:
- **Roll bonuses** apply in `_execute_request_roll`: `skill_mod` = rank + chrome bonus for that skill + tier penalty (persuasion and performance only).
- **Armor and max health** change the stored values through one helper, `_apply_chrome_stats(character, chrome, sign)`: `+1` on install, `−1` on removal. On removal, health is clamped to the new maximum and armor is floored at 0.

### 5. ⚡ Overclock on the roll card

- The `roll` message gains an optional `"overclock": "<chrome id>"`.
- **Validation:** the item is installed, has an overclock, and applies to this roll (Kagerou to any roll; Yomi jack only when the pending roll's skill is `hacking`), and `gone_too_far` is not set. Otherwise the roll is refused with a clear `ValueError` and stays pending.
- **Effect** (in `resolve_roll`):
  - **Kagerou:** roll a second d10 and keep the higher, then add +2.
  - **Yomi jack:** +3.
  - Both get +1 at the Slipping or Edge tier.
  - The natural 10 and 1 rules apply to the kept die.
- **The cost:** the engine rolls 1d6 and subtracts it from humanity. This can set `gone_too_far` or fire the confrontation scene.
- **The roll line** names it: *"Rook overclocks Kagerou (−4 humanity) and rolls Stealth (Reflexes) vs Hard: success with a complication (8 +2 +1 +2 = 13 vs 12)."*
- The `[roll: …]` JSON gains `overclock`, `overclock_bonus`, `second_die` (Kagerou) and `humanity_loss`.
- **The pending view** gains `overclocks: [{id, name, bonus_text}]`, listing the overclocks usable on *this* roll, so the card knows which buttons to show.
- **The card:** next to **Roll**, one **⚡ Overclock ({name}) · −1d6 humanity** button per usable overclock. The result card shows the second die when there is one.

### 6. Getting chrome

- **At creation:** `join` accepts an optional `starting_chrome` (one catalog id). It is validated server-side, installed through the normal install path, and `starting_chrome` is input only. The client can never set the humanity, chrome or debt fields.
- **At a chrome-ya:**
  - A new narrator tool `offer_chrome(player_id, item)`. `item` is a `Literal` of the catalog ids. It sets `session.pending_chrome_offers[player_id]` and logs `[chrome offer: …]`. It **never installs**. The system prompt gets a positive and a negative example: offer it when the player asks a chrome-ya what's available, not in routine scenes.
  - New player messages:
    - `accept_chrome` checks for a free slot, a pending offer, and that `gone_too_far` is not set. It then installs: humanity cost, stats, and `installments_owed += item.installments`.
    - `decline_chrome` clears the offer.
  - **Removal:** a `remove_chrome {item}` player message returns half the humanity cost, reverses the stats and keeps the installments owed.
- **Humanity gains:** `apply_character_update.humanity_delta: int = Field(0, ge=0, le=5)`.

### 7. Debt is recorded only

`installments_owed` accrues on install and is shown on the sheet. Nothing ticks, collects or throttles in 17a; the clock, the torite and payments are 17b. There is no `installments_paid` field yet.

### 8. Data model

**`CharacterSheet` gains** (all with defaults, so old saves load as 100 humanity, no chrome, no debt):
- `humanity: int = 100`
- `chrome: list[str]` (in install order)
- `installments_owed: int = 0`
- `slipping_warned: bool = False`
- `gone_too_far: bool = False`

**`Session` gains:**
- `pending_chrome_offers: dict[str, str]`
- `pending_world_events: list[str]` (transient; consumed by the next prompt build)

### 9. Prompt

- **Scene line:** a per-character status, capped at 200 characters each, for example `Rook: humanity 62 (Frayed), chrome: Kagerou, Hawkeye optics`.
- **`World event:` line:** appears for the turn on which the confrontation scene fires, via `pending_world_events`.
- **System prompt block:**
  - how each tier plays:
    - Frayed: small dissonance;
    - Slipping: cold, quick to violence, Yomi static;
    - Edge: episodes such as rage, hallucinated faces from Yomi, lost time;
    - Gone too far: episodes every scene, but the player still decides;
  - the `offer_chrome` examples;
  - when to grant `humanity_delta`;
  - the DC guidance line.
- No anti-cliché rules.

### 10. UI

- `CHROME` is mirrored in TypeScript.
- **Creation:** an optional starting-chrome picker showing effect, humanity cost and installments.
- **Character sheet:** a humanity bar with the tier name; the chrome list with a Remove button on each; installments owed (display only).
- **Offer card:** Accept / Decline.
- **Roll card:** the overclock buttons from §5.
- `[chrome offer: …]` lines render as small system notices.

## Testing

**Unit tests:**
- the new DC values, and updated Phase 16 expectations;
- catalog integrity;
- the slot formula;
- install:
  - humanity, stats, installments and order;
  - rejects a duplicate, a full slot count, and an install while `gone_too_far` is set;
- removal: half refund, stats reversed, installments stay;
- chrome roll bonuses;
- tier penalties on persuasion and performance only;
- the overclock:
  - Kagerou keeps the higher die and adds +2;
  - Yomi jack is offered only on hacking rolls and is refused otherwise;
  - the +1 tier bonus;
  - the 1d6 cost;
  - refused while `gone_too_far` is set;
  - the roll line text;
  - the extra `[roll:]` JSON fields;
  - the view's `overclocks` list;
- `gone_too_far` is set at 0 and cleared above 20;
- the confrontation scene fires once;
- `join` validates `starting_chrome` and the client can't set server fields;
- `offer_chrome` creates an offer and installs nothing; accept and decline;
- `humanity_delta` bounds;
- persistence round-trip, plus a pre-17a save file;
- the Scene status line and the `World event:` line, consumed once;
- the system prompt contains the tier block and the DC line.

**Live** on `qwen3:8b` (GPU box, 300s timeout):
- **Rolls:** 8 risky actions. Record the DC distribution the model now picks, and the outcome spread.
- **Chrome-ya visit:** does `offer_chrome` fire when asked and stay silent otherwise?
- **Overclocks:** narration reflects the cost.
- **Tier narration:** at humanity 60, 30, 10 and 0.
- **The confrontation scene.**
- Record errors and n.

**Browser** (headless Chrome over CDP, two players):
- the starting-chrome picker;
- the offer card;
- the overclock buttons on the roll card (Yomi jack only on hacking);
- the humanity bar;
- Remove.

## Not in this phase (→ 17b)

- The installments clock.
- Paying the debt (Arakawa's gigs).
- Torite escalation: notice → throttle → Saeko Kirigaya's crew.
- Old Hara's unthrottle.
- The utsusemi mechanic.

Also out of scope:
- Money.
- Chrome grades.
- A netrunning mini-game.
- NPC cyberpsychos.
- Techie repair rules.
- The Phase 16 follow-ups: resolution framed as "Player action:", odd attribute picks, the narrator voicing the player. These are tracked in ROADMAP.
