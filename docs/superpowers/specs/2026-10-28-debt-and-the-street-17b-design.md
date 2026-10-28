# Nightwire Debt and the Street Design: Phase 17b

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-28.

**Inputs:**
- the debt and torite sections of `2026-10-27-cyberware-humanity-design.md` (superseded for implementation; its debt-loop sections were approved there);
- Phase 17a (`2026-10-27-chrome-humanity-17a-design.md`), which already records `installments_owed` on each install.

## Owner decisions (2026-10-28)

- **NPC hooks:**
  - Saeko Kirigaya leads the repos.
  - Jun Arakawa's gigs are the main way to pay.
  - Old Hara can unthrottle chrome off the books.
- **Split.** The utsusemi "play as an AI" origin (a tsukumogami in a rented shell, with selfhood as a mirror of humanity and the shell itself repossessable) is **Phase 17c**, designed after this one ships on top of this repo system.
- **Clock pace** as originally approved: a pip every 10 of your actions while you owe, and a strike at 6 pips (about 60 actions per strike).

## Research grounding

Carried over from the original spec:
- **Blades in the Dark** heat and entanglements: consequence events rolled from past choices, so debt creates missions rather than bookkeeping ([Roll20](https://roll20.net/compendium/BITD/Rules:Entanglements)).
- **Deus Ex: Human Revolution**'s Neuropozyne: company-controlled, ongoing dependency ([wiki](https://deusex.fandom.com/wiki/Neuropozyne)).
- **Cyberpunk 2077 and RED** fixers as the recurring source of paid work, which is where Arakawa comes from.
- **LLM-game state discipline:** the engine decides events and the narrator stages them. Phase 16 and 17a hold to this throughout.

## Design

### State (`CharacterSheet`; all fields default, so old saves load)

- `repo_clock: int = 0`, with a range of 0–6.
- `repo_actions: int = 0`
- `repo_strikes: int = 0`
- `throttled: str | None = None`, one chrome id.
- `pending_repo: str | None = None`, one chrome id.

### The clock (`engine/debt.py`, called from `handle_action`)

`tick_debt(character) -> list[str]` returns world events. On each action by a player whose `installments_owed > 0`:
1. `repo_actions += 1`.
2. At 10, set `repo_actions = 0` and `repo_clock += 1`.
3. At 6, set `repo_clock = 0`, then `repo_strikes += 1`, then fire:
   - **Strike 1, notice:** *"Hoshikawa sends {name} a polite final notice; Saeko Kirigaya's torite crew has been asking about {name}."*
   - **Strike 2, throttle:** the newest installed chrome that isn't already throttled becomes `throttled`. Its stats are removed with the 17a `_apply_stats(-1)`. Its roll bonus and overclock stop counting. *"{name}'s {Chrome} locks up: remote-throttled by Hoshikawa for missed payments."*
   - **Strike 3 and after, repo:** `pending_repo` = the throttled item if there is one, otherwise the newest item. *"Saeko Kirigaya's torite crew comes for {name}'s {Chrome}."*
   - **No chrome installed:** a strike is only a notice.

Each event is queued on `session.pending_world_events` and also logged as `[torite: …]`.

### Ways out (`narrator/tools.py` `ApplyCharacterUpdate`)

- **`installments_paid: int = Field(0, ge=0, le=1)`.** When at least 1:
  - `installments_owed` drops by that amount (floored at 0);
  - `repo_clock` and `repo_actions` reset to 0;
  - any throttle clears and its stats come back;
  - `pending_repo` clears;
  - if `installments_owed` reaches 0, `repo_strikes` resets to 0.
- **`repossess: bool = False`.** Only valid while `pending_repo` is set; otherwise `ValueError`, which surfaces as a tool error. It runs the 17a `remove_chrome(pending_repo)` (half the humanity back; installments stay), clears `pending_repo` and `throttled` if they match, and logs `[torite: Saeko's crew took {name}'s {Chrome}]`.
- **`unthrottle: bool = False`** (Old Hara). Only valid while something is throttled; otherwise `ValueError`. It clears the throttle, brings the stats back, and appends the objective **"Owe Old Hara a favor"** to `session.active_objectives` (no duplicates). The clock and the debt are untouched.

### Rolls and overclock

- `chrome_roll_bonus` and `usable_overclocks` skip the throttled id. That means a `throttled` parameter, or reading `character.throttled`.
- `remove_chrome` (17a) clears `throttled` and `pending_repo` if they point at the removed item.

### Prompt

- **Crew line**, per character:
  - it adds `owes {n}, repo clock {c}/6` when `installments_owed > 0`;
  - plus `throttled: {Chrome}` and `repo crew coming for: {Chrome}` when those are set;
  - the 200-character cap per entry still applies.
- **Card selection** also scans the pending World event text, so naming Saeko in an event loads her NPC card.
- **System-prompt block:**
  - **Paying:** when a character owes installments and asks for work, Jun Arakawa in Hanabira-chō has paid gigs; when a gig pays out, set `installments_paid` to 1.
  - **Repo encounter:** when a repo is pending, stage Saeko's crew. Set `repossess: true` only if the character loses or gives the chrome up.
  - **Old Hara:** if a character asks Old Hara to unlock throttled chrome, he can (`unthrottle: true`), but they'll owe him.

### UI

- **Character sheet:** installments owed, the repo clock as 6 pips, a "throttled" tag on the locked chrome, and a "repo crew coming" marker.
- **Log:** `[torite: …]` lines render as notices.
- **Roll card:** throttled chrome has no overclock button. The server already omits it.

## Testing

**Unit tests:**
- **Clock:**
  - the clock ticks only while owing, every 10 actions;
  - a strike at 6 resets the clock;
  - strikes 1/2/3+ produce the right events and state;
  - a throttle removes stats and its bonus and overclock;
  - a repo picks the throttled item first.
- **Paying:** a payment resets the clock, unthrottles with stats restored, clears the repo, and resets strikes when the debt reaches 0.
- **Repossess:** removes only the pending item and raises without a pending repo.
- **Unthrottle:**
  - restores stats and adds the objective once;
  - raises when nothing is throttled;
  - the debt and clock are untouched.
- **`remove_chrome`:** clears matching throttle and repo.
- **Persistence:** a round trip, plus a pre-17b save.
- **Crew line:** shows the debt fields.
- **Card selection:** a Saeko event loads her card.
- **Schema:** bounds on the new fields.

**Live** on `qwen3:8b` (GPU box, 300s):
- force each strike by setting the state directly and check the narration: Saeko appears and is named, and the repo is staged;
- while owing, ask for work in Hanabira-chō: does Arakawa offer a gig, and does the narrator grant `installments_paid` when it pays?
- ask Old Hara to unlock throttled chrome;
- record errors and n.

**Browser** (headless Chrome over CDP, scripted narrator): the sheet's debt fields, the pips, the throttled tag, the repo marker, and the torite notices.

## Not in this phase

- Phase 17c: the utsusemi player origin, selfhood, and shell repossession.
- Money.
- Interest.
- Selling chrome.
- Engine-generated gigs: Arakawa's gigs are narrative, paid through `installments_paid`.
- The open follow-ups from 17a: the model picking Hard on every roll, weak tier narration, and the narrator voicing the player.
