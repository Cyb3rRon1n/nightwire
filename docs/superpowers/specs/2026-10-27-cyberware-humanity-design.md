# Nightwire Cyberware, Humanity and Chrome Debt Design: Phase 17

Status: designed, not yet implemented; to be revised before planning. Brainstormed with the owner on 2026-10-27, against the Kuroshio world (Phase 14: `narrator/worlds/kuroshio.toml`). Renumbered from 15 to 16, then 17, on 2026-10-27 (two-step rolls became Phase 16): the owner chose to build World v2 (the NPC cast and utsusemi, `2026-10-27-world-v2-npc-cast-utsusemi-design.md`) first. Owner note: Edgerunners is an influence, not a template, and the Altered Carbon pass was rolled back: the elite are plain corporate royalty, and sleeves exist only as utsusemi, rented AI shells (which a debt loop could also repossess). Revisit this spec's framing against World v2 before writing its plan, for example tying the debt loop to Jun Arakawa's gigs and to Old Hara's ability to unthrottle.

## The actual gap

Kuroshio's premise is that **chrome is on credit**: the keiretsu finance everyone's cyberware, and torite repo crews take it back. But nightwire has no cyberware at all.
- `CharacterSheet` has HP, armor, free-text conditions, inventory, attributes and skills, and nothing else.
- The Techie role's description promises "repairs damaged equipment and cyberware" for a system that doesn't exist.

So the setting's central idea is narrative decoration with nothing behind it. This phase adds three things:
- **Cyberware** that does something mechanically.
- **A humanity cost** that delivers the Edgerunners arc.
- **A light debt loop** that turns "chrome on credit" into missions.

## Owner decisions (2026-10-27)

- **When humanity runs out: story pressure, never a takeover.** The player always keeps control. The narrator plays the slide, and there is always a way back.
- **Debt: a light loop.** Debt is counted in installments plus an engine repo clock that escalates into torite events. There is no money system (nightwire has none).
- **Acquiring chrome:** one optional implant at character creation (already on a payment plan), and more in play at a chrome-ya. The narrator offers; the player accepts; the engine validates and installs.
- **Approach A:** a humanity meter, slots, an 11-item catalog, and installment debt with a repo clock. Risky actions are player buttons.
- The sections below were approved as presented.

## Research grounding

A researcher pass on 2026-10-27. Labels follow that report: [S] is sourced; [G] is general knowledge, unverified.

**Humanity costs in other systems.**
- Cyberpunk RED: Humanity = EMP×10. Implants carry a Humanity Loss cost, and fashionware and medical replacements cost 0. Therapy restores some Humanity but never fully; removing chrome is the only full recovery [S, [Astral Review](https://www.d20radio.com/main/?p=23254)].
- Shadowrun: Essence, starting at 6, drops with each implant. Grade multipliers apply, and Essence never recovers [S, [rules](https://www.pvv.ntnu.no/~leirbakk/rpg/shadowrun/rules/shadowrun_rules_cyberwarerules.html)].
- Cyberpunk 2077 2.0 uses a hard **capacity** cap. CDPR deliberately did not ship player cyberpsychosis; overloading gives debuffs instead [S, [progameguides](https://progameguides.com/cyberpunk-2077/how-cyberpsychosis-works-in-cyberpunk-2077-2-0/)]. This is precedent for "the player never loses the character" and for slots.

**Cyberpunk: Edgerunners.**
- David's decline comes from heavy Sandevistan use, framed as dependency.
- Lucy confronts him with symptoms and urges a downgrade; he chooses to refuse [S, [Looper](https://looper.com/1036614/the-ending-of-cyberpunk-edgerunners-explained)].
- This is the template for the one-time confrontation scene: a choice, not a punishment.

**Debt and dependency.**
- **Deus Ex: Human Revolution.** Neuropozyne is ongoing, company-controlled dependency, and missing it means rejection [S, [wiki](https://deusex.fandom.com/wiki/Neuropozyne)]. This is the closest precedent for chrome on credit.
- **Blades in the Dark.** Heat and entanglements turn past choices into rolled consequence events [S, [Roll20](https://roll20.net/compendium/BITD/Rules:Entanglements)]. This is the shape of the repo clock and torite escalation: debt creates missions, not accounting.

**Meter design.**
- Call of Cthulhu's sanity narrows the options a character has rather than just subtracting [S, [GamingBolt](https://gamingbolt.com/call-of-cthulhu-developers-discuss-how-sanity-mechanic-and-phobias-work-in-the-game)].
- Loss should follow player decisions such as installing and overclocking [S].
- Avoid punishment spirals by giving power back as humanity falls ("stronger but narrower") [G].

**LLM games.** State lives in code, and the LLM proposes while the engine validates. CALYPSO documents LLMs hallucinating game details [S, [arXiv](https://arxiv.org/pdf/2308.07540)]. This is nightwire's own established rule, and its own history shows the same thing: `start_combat` was removed from the narrator's tools after it over-fired, so risky mechanical triggers become **player buttons**.

**Catalog size.** About 10 items, each with one clear effect [G]. That keeps an 8B model from inventing items, and the schema enforces the catalog anyway.

## Mechanics

### Humanity

- `humanity` starts at **100** and never goes above 100 or below 0.
- **Loss:** each install costs that item's fixed cost. Each overclock costs **1d6**, rolled by the engine when the overclocked roll resolves.
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

### Slots

Capacity is **3 + Body modifier, minimum 2**. Body uses the existing `modifier()`, `(score − 10) // 2`. Each item uses 1 slot.

### Catalog: `ruleset/cyberware.py`

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
- **Yomi jack's overclock** applies only when the roll's skill is `hacking`. Otherwise it stays armed.
- The tier bonus (+1 at Slipping and Edge) adds to either overclock's flat bonus.

### Rolls (`narrator/tools.py::_execute_request_roll`)

`skill_mod` becomes:

```
rank + chrome bonus for that skill (from non-throttled items) + tier penalty (persuasion/performance only)
```

If the character has an **armed overclock** that applies to this roll:
- Kagerou rolls a second d10 and keeps the higher, then adds +2 (plus the tier bonus).
- Yomi jack adds +3 (plus the tier bonus) on hacking.

Then:
- The engine rolls 1d6 and subtracts it from humanity (which can set `gone_too_far` and fire the confrontation scene).
- It clears `overclock_armed`.
- It adds `overclock` and `humanity_loss` to the returned result dict, so the roll's log line shows them.

The natural 10 and natural 1 rules are unchanged: they apply to the kept die.

### Armor and max health

Lacquer skin's armor and the Pain editor's max health change the stored `armor` and `max_health` through one helper, `_apply_chrome_stats(character, chrome, sign)`. It runs:
- `+1` on install and unthrottle;
- `−1` on remove and throttle.

On `−1`, health is clamped to the new `max_health`, and armor is floored at 0.

### Debt and the repo clock

- **Installing** adds the item's `installments` to `installments_owed`. That includes the starting implant, which begins on a payment plan.
- **Paying:** `apply_character_update.installments_paid` is schema-bounded to **0–1** per turn. The narrator uses it when a gig pays out or a debt job is done. The engine subtracts it, flooring at 0. Any payment of 1 or more:
  - resets `repo_clock` to 0;
  - unthrottles the throttled item.
- **The clock** ticks in `server/narration.py::handle_action`. On each action by a player whose `installments_owed > 0`:
  - `repo_actions += 1`;
  - every **10** such actions, `repo_clock += 1` and `repo_actions = 0`.
- **When `repo_clock` reaches 6:** `repo_strikes += 1`, `repo_clock = 0`, and the engine fires an event by strike number:
  1. **Notice.** `World event:` "Hoshikawa sends {name} a polite final notice; a torite crew has been seen asking questions."
  2. **Throttle.** The newest installed item is remotely locked. Its roll bonus and overclock are off, and its armor or health is removed through the helper. `World event:` "{name}'s {item} locks up: remote-throttled for missed payments."
  3. **Repo crew (strike 3 and every strike after).** `World event:` "A torite crew comes for {name}'s {item}." The narrator stages the encounter, and the engine sets `pending_repo` = that item. The repossession resolves only through the existing tools: if the narrator calls `apply_character_update` with `remove_chrome: true` (see Tools) for that player, the engine removes the item (half its humanity back; installments stay owed). Any payment clears `pending_repo`.
- Each event also writes a `[torite: …]` log line for the UI.
- With nothing owed, the clock doesn't tick, and `repo_strikes` resets to 0 when `installments_owed` reaches 0.

### Starting chrome

`join` accepts an optional `starting_chrome` (one catalog id, or omitted). It is validated server-side: unknown ids are rejected, and the slot count must allow it. The engine installs it with the normal install path, so it costs humanity and adds installments. `starting_chrome` is added to `_JOIN_CHARACTER_FIELDS` handling as an input only. The client can never set `humanity`, `chrome`, debt or clock fields, because they are not in the allowlist.

## Data model

New `CharacterSheet` fields, all with defaults, so sessions saved before Phase 15 load unchanged (100 humanity, no chrome, no debt):

- `humanity: int = 100`
- `chrome: list[str]`, catalog ids in install order. "Newest" is the last.
- `installments_owed: int = 0`, `repo_clock: int = 0`, `repo_actions: int = 0`, `repo_strikes: int = 0`
- `throttled: str | None = None`, `overclock_armed: str | None = None`, `pending_repo: str | None = None`
- `slipping_warned: bool = False`, `gone_too_far: bool = False`

New `Session` fields: `pending_chrome_offers: dict[str, str]` (player_id → catalog id) and `pending_world_events: list[str]` (transient; consumed by the next prompt build).

Persistence round-trips all of these, following the existing JSON pattern and its tests.

## Narrator tools

The set stays small. The lesson behind this is that model-triggered mechanics are the least reliable part of the system.

**New tool: `offer_chrome(player_id, item)`.**
- `item` is a `Literal` of the 11 catalog ids.
- It sets `session.pending_chrome_offers[player_id] = item` and logs `[chrome offer: {name} → {item name}]`.
- It installs **nothing**.
- The system prompt gets a positive and a negative example (the same technique that fixed `image_request` and `remember_npc`):
  - Positive: "the player asks a chrome-ya what's available → offer_chrome".
  - Negative: "routine scenes, combat, or a chrome-ya just mentioned in passing → no offer".

**`ApplyCharacterUpdate` gains three fields:**
- `humanity_delta: int = Field(0, ge=0, le=5)`
- `installments_paid: int = Field(0, ge=0, le=1)`
- `remove_chrome: bool = False`. This only acts when that player has a `pending_repo`, and removes exactly that item. It is how a lost repo encounter resolves, so the model never picks an item.

## Player messages (`server/dispatch.py`)

The engine does all the math for each of these, and they all broadcast the updated view as existing messages do.

- **`accept_chrome`:** requires a pending offer for this player, a free slot, and `gone_too_far` not set. Installs the item: adds it to `chrome`, subtracts humanity, adds installments, applies stats, and fires the confrontation scene if the install crosses below 40. Then clears the offer.
- **`decline_chrome`:** clears the offer.
- **`overclock {item}`:** the item must be installed, have an overclock, not be throttled, and `gone_too_far` must not be set. Sets `overclock_armed = item`, replacing any previously armed one.
- **`remove_chrome {item}`:** the item must be installed. Removes it, returns half its humanity cost, reverses its stats, and clears `throttled`, `overclock_armed` or `pending_repo` if they pointed at it. Installments stay owed.

Every validation failure raises `ValueError`, which uses the existing error path.

## Prompt

**Scene line.** It gains one status entry per character, each capped at 200 characters (the same read-side capping idea as Phase 14's scene caps):

```
Rook: humanity 62 (Frayed), chrome: Kagerou, Hawkeye optics, owes 3, repo clock 4/6
```

Throttled and pending-repo items are marked inline. Characters with no chrome and no debt get no entry.

**`World event:` line.** It is added right after the Scene line, for the turn on which an engine event fired (confrontation scene, notice, throttle, repo). It is held in a transient `session.pending_world_events` list that `_build_messages` consumes and clears.

**System prompt.** It gets a short chrome-and-humanity block alongside the existing rules:
- what each tier looks like in play:
  - Frayed: small physical and emotional dissonance;
  - Slipping: cold, quick to violence, Yomi static in the ears;
  - Edge: full episodes, such as rage, hallucinated faces from Yomi, losing time;
  - Gone too far: episodes every scene, but the player still decides what their character does;
- the `offer_chrome` examples;
- when to grant `humanity_delta` and `installments_paid`.

As in Phase 14, there are no anti-cliché rules.

## UI (frontend)

- `CHROME` is mirrored in TypeScript, the same hand-verified pattern as `ROLES` and `SkillPicker`.
- **Creation form:** an optional starting-chrome picker showing each item's effect, humanity cost and installments.
- **Character sheet:** a humanity bar with the tier name; the chrome list, where each item has an ⚡ Overclock button (if it has one) and a Remove button; throttled and pending-repo markers; installments owed; and the repo clock as 6 pips.
- **Offer card:** when the player has a pending offer, a card with the item, its effect and cost, and Accept / Decline buttons.
- `[torite: …]` and `[chrome offer: …]` log lines render as small system notices.

## Testing

**Unit tests (pytest):**
- **Catalog:** integrity (skill names valid, costs non-negative, overclock items correct).
- **Slot formula:** at Body 6, 10 and 16.
- **Install:** humanity, installments, stats and order; rejects duplicates, a full slot count, and installs at humanity 0.
- **Removal:** half refund, stats reversed, pointers cleared, installments stay.
- **Rolls:**
  - chrome bonus applied, and not applied when throttled;
  - tier penalties applied to persuasion and performance only;
  - Kagerou keeps the higher die and charges 1d6;
  - Yomi jack only applies on hacking and stays armed otherwise;
  - tier +1 at Slipping;
  - overclock refused while `gone_too_far` is set, and allowed again once humanity is above 20.
- **Clock:** ticks only while owing; 10 actions per tick; 6 ticks per strike.
- **Escalation:** notice, then throttle (the newest item, with stats removed), then repo. Payment resets the clock and unthrottles.
- **`remove_chrome`:** only acts on a `pending_repo`.
- **confrontation scene:** fires once.
- **Join:** `starting_chrome` is validated; the client can't set humanity, chrome or debt fields.
- **Persistence:** round-trip, plus loading a pre-Phase-15 session file.
- **Prompt:** the status line and the `World event:` line appear and are consumed once.
- **Tool schema bounds:** `humanity_delta`, `installments_paid` and the offer item `Literal`.

**Live verification** against the real `qwen3:8b`, using the Phase 14 probe pattern with baseline comparison where meaningful:
1. **Chrome-ya visit:** does `offer_chrome` fire when asked, and stay silent in routine turns? Report the counts.
2. **Overclock turns:** does the narration reflect the cost?
3. **A forced repo event:** set the clock state directly. Does the narrator stage the torite?
4. **Tier narration:** set humanity to 60, 30, 10 and 0. Does the narration match the tier without anyone losing control?
5. **The confrontation scene.**

Record schema and tool error rates, and report n honestly.

## Not in this phase

- Money or yen and prices.
- Chrome grades and upgrades.
- Netrunning or a Yomi dive mini-game (the Yomi jack overclock stands in).
- Therapy as its own mechanic (the narrator's `humanity_delta` covers it).
- NPC cyberpsychos as a mechanic.
- Techie-specific repair or install rules (a natural follow-up: Techie unthrottle or cheaper installs).
- Faction clocks.
- Selling chrome.
