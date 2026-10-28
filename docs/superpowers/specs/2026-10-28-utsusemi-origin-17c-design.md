# Nightwire Utsusemi Origin Design: Phase 17c

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-28.

**Inputs:**
- Phase 15 (`2026-10-27-world-v2-npc-cast-utsusemi-design.md`): utsusemi are rented synthetic shells that woken machines (tsukumogami) wear, leased on payment plans and repossessable.
- Phase 17a (`2026-10-27-chrome-humanity-17a-design.md`): the humanity meter, tiers, social penalty, overclock and the 0-lock.
- Phase 17b (`2026-10-28-debt-and-the-street-17b-design.md`): the repo clock, strikes, `repossess`, Old Hara.

## Owner decisions (2026-10-28)

- **Selfhood mirrors humanity.** One 0–100 meter. A tsukumogami starts low and climbs through human moments. Machine-like acts lower it.
- **Losing the shell is a bodiless scene, not a sideline.** You drop into the nearest machine and keep playing (talk, sense, hack) until the crew gets you a new shell.
- **Chrome costs a tsukumogami no selfhood.** It's hardware in the shell, and goes with the shell on a repo. ⚡ Overclock still costs selfhood.
- **Tiers mirror 17a plus one milestone.** Low selfhood gives the same social penalty. At 80+ ("Awake") a shell repo stops costing selfhood.
- **Approach:** reuse the `humanity` field and 17a/17b machinery, flipped in labels and narration by lifepath. A separate `selfhood` field was rejected (duplicate tier, penalty and lock logic).

## Research grounding

- **Detroit: Become Human**: Connor's Software Instability is one hidden meter moved by choices, and a high value unlocks deviation. It is a gate, not a grind ([wiki](https://detroit-become-human.fandom.com/wiki/Software_Instability)).
- **Mothership** community rules make an android "becoming human" a downtime activity, not a combat reward ([Becoming Human](https://ultansdoor.substack.com/p/becoming-human-mothership-downtime)).
- **Eclipse Phase**: losing a body (morph) isn't death; the ego persists, and the cost is stress and memory ([Resleeving](https://eclipsephase.github.io/en/15/02-resleeving.html), [Beyond Death](https://eclipsephase.github.io/en/07/01-beyond-death.html)). Basis for "the repo costs a little selfhood, never the character".
- **Tsukumogami folklore**: tools that serve about a century gain a spirit; in the Tsukumogami Emaki, discarded tools rise up in resentment at being thrown away ([Wikipedia](https://en.wikipedia.org/wiki/Tsukumogami), [yokai.jp](https://yokai.jp/en/saga/tsukumogami)). Being repossessed back into a machine is that fear made literal.
- **LLM-game state discipline** (Phases 16–17b): the engine decides events and the narrator stages them.

## Design

### Origin and state

- **Lifepath** `tsukumogami` in `ruleset/lifepaths.py`: *"An old machine that ran too long and woke - a vending machine, a ticket gate, a train announcer - now walking the street in a rented utsusemi shell."* Any role.
- **Join as a tsukumogami** (`server/dispatch.py`, new characters only):
  - `humanity = 20` (shown as selfhood);
  - `installments_owed += 4` (the shell lease, on the 17b clock);
  - starting chrome is allowed and costs 0 selfhood.
- **New `CharacterSheet` fields** (default, so old saves load): `bodiless: bool = False`, `awake_reached: bool = False`.
- `is_tsukumogami(character)` = `character.lifepath == "tsukumogami"`.
- **Tier names** (`ruleset/cyberware.py`, `selfhood_tier`), same thresholds as `humanity_tier`: 0–19 **Appliance**, 20–39 **Flickering**, 40–59 **Waking**, 60–79 **Someone**, 80–100 **Awake**.
- **Unchanged and shared with humans**: the social penalty on persuasion and performance by value, the +1 overclock bonus below 40, and the 0-lock (`gone_too_far` until back above 20; the narrator plays it as "gone dark").

### Gaining and losing selfhood

- **`change_humanity`** for a tsukumogami:
  - never fires the 17a "slipping" confrontation (a tsukumogami starts below 40);
  - the first time the value reaches **80**, sets `awake_reached` and returns the one-time event *"{name} feels it settle: they're someone now, not something."*
- **`apply_character_update.selfhood_gain: int = Field(0, ge=0, le=5)`**:
  - tsukumogami only; otherwise `ValueError("selfhood_gain is only for tsukumogami")` (validated before any mutation);
  - raises the value, capped at 100; one tool call per turn already limits it to one gain per turn;
  - logs `[selfhood: +N]`.
- **Losses**: the existing `humanity_delta` (0–5) is a selfhood loss for a tsukumogami. ⚡ Overclock still costs 1d6.
- **Chrome**: `install_chrome` charges 0 humanity for a tsukumogami; `remove_chrome` refunds 0.

### Losing the shell

- **Repo order** (17b `_strike`, strike 3+): throttled chrome, then the newest chrome. When a tsukumogami has no chrome left, `pending_repo = "shell"` and the event is *"Saeko Kirigaya's torite crew comes for {name}'s utsusemi shell."* A human with no chrome still only gets a notice.
- **`repossess` on `"shell"`**:
  - removes all remaining chrome (stats reversed, no refund);
  - sets `bodiless = True` and clears `throttled` and `pending_repo`;
  - lowers selfhood by **5**, unless the value is 80 or more;
  - debt stays;
  - logs `[torite: Saeko's crew took {name}'s shell - {name} drops into the nearest machine]`.
- **While bodiless**:
  - `tick_debt` does nothing (the clock pauses);
  - a `request_roll` whose skill is governed by **Body or Reflexes** (melee, athletics, ranged_combat, stealth, piloting) is refused with the tool error `"{name} has no body"`, and no pending roll is created;
  - every other skill works;
  - `install_chrome` raises `"no shell to install chrome in"`.
- **`apply_character_update.new_shell: bool = False`**:
  - valid only while bodiless; otherwise `ValueError("not bodiless")`;
  - clears `bodiless`, adds **4** installments, and resets `repo_clock`, `repo_actions` and `repo_strikes` (a fresh contract);
  - logs `[utsusemi: {name} wakes in a new shell]`.
- **Combat**: a bodiless character stays in turn order; the roll refusal is the only restriction.

### Prompt

- **Crew line** for a tsukumogami: `selfhood {n} ({Tier})` in place of humanity, plus `bodiless: living in a nearby machine` when set, and `repo crew coming for: shell` when `pending_repo == "shell"`. The 200-character cap still applies.
- **System-prompt block**:
  - **Selfhood:** grant `selfhood_gain` 1–5 for human moments (being thanked, sharing food, keeping a promise, an unprompted kindness, a choice made for no reason); use `humanity_delta` for acting as a pure machine (cold calculation, following an owner's script, treating people as inputs). Never for routine scenes.
  - **Tiers:** Appliance = stock phrases, wrong chimes, frozen stillness; Flickering and Waking = a voice breaking through; Someone and Awake = fully themselves.
  - **Bodiless:** play them speaking through vending machines, speakers, signs and ticket gates; they can hack and talk but not move or fight. Old Hara has used shells, Hoshikawa leases new ones, or they can steal one; set `new_shell: true` when they get one.
  - **Repo encounter:** reuse 17b's guidance; when the target is the shell, `repossess: true` drops them into a machine.

### UI

- **Join**: a Tsukumogami lifepath option; picking it shows *"Selfhood 20 · shell lease +4 installments"*.
- **Character sheet**: the meter is labeled **Selfhood** with the tier name; chrome is listed under **Shell**; **[Bodiless]** replaces the chrome list with *"Living in a nearby machine"*; **[Repo crew coming: shell]** when the shell is pending.
- **Log**: `[selfhood: …]` and `[utsusemi: …]` render as notices, like `[torite: …]`.

## Testing

**Unit tests:**
- **Join**: a tsukumogami starts at 20 with +4 owed; starting chrome costs 0; a human join is unchanged.
- **Selfhood**: `selfhood_gain` bounds, rejected for humans before any mutation, capped at 100; no slipping confrontation for a tsukumogami; the Awake event fires once at 80.
- **Chrome**: install and remove cost and refund 0 for a tsukumogami.
- **Repo order**: the shell is queued only when no chrome is left; a human with no chrome gets only a notice.
- **Shell repo**: strips chrome with stats reversed, sets bodiless, applies −5 (0 at 80+), clears pointers.
- **Bodiless**: the clock pauses; Body/Reflexes rolls are refused with no pending roll; hacking and persuasion work; chrome install raises.
- **`new_shell`**: only while bodiless; +4 owed and a reset.
- **Persistence**: a round trip, plus a pre-17c save.
- **Prompt**: the Crew line fields and the system-prompt rules.

**Live** on `qwen3:8b` (GPU box, 300s):
- human-moment turns (sharing food, being thanked): is `selfhood_gain` granted?
- cold-machine turns: is a loss applied?
- a forced shell repo and handover: is the bodiless scene played through machines, and is `repossess` set?
- a bodiless physical action: is the roll refused and narrated sensibly?
- asking Old Hara for a shell: is `new_shell` granted?
- record errors and n.

**Browser** (headless Chrome over CDP, scripted narrator): the join option, the Selfhood meter and tier, the bodiless sheet, and the notices.

## Not in this phase

- Backups or memories as items.
- Stealing a shell as an engine mechanic (narrative only, via `new_shell`).
- Shell models with different stats.
- AI-only skills.
- The open follow-ups from 17a/17b (the model picking Hard on every roll, weak tier narration, the narrator voicing the player, the repo handover getting a roll instead of `repossess`).
