# The director: tension, breathers, and events that fit the moment

Status: approved 2026-11-22 (all event cards kept). The owner's note on the mechanism card: "it can be world events or
something that at least drives the story". So every event now leaves a lead on the objectives list, and the two
events that were scenery only (the rain, the charm kid) were rewritten to carry one. Item 3 on the approved roadmap.

## Why

The world only acts when the player acts, so long sessions go flat. Nothing happens on a quiet street until the player
pokes it. The opposite also happens: after a fight, the narrator keeps piling on threats. The owner asked for
something that keeps play immersive and evolving, and costs no AI calls while the game runs on CPU only.

## Prior art (research pass 2)

- **Left 4 Dead's AI Director** (Booth, Valve 2009 slides, verified). It estimates how intense things are for the
  player, builds pressure to a peak, then forces a relax period.
- **Storylets** (Kreminski & Wardrip-Fruin, ICIDS 2018; Emily Short's posts). An event is a small card with
  preconditions on the game state. The game picks among the cards whose preconditions are met, preferring the most
  relevant, and avoids repeats.
- **Façade** (Mateas & Stern, AIIDE 2005). It drew from a library of beats with preconditions, aiming at a target
  tension. We take only the "library with preconditions" part.

## Goals

- A tension number from 0 to 10 that the engine keeps itself, with no model call:
  - +2 when the turn had a roll;
  - +2 more when that roll failed or the player lost health;
  - +3 while in combat;
  - −1 on any other turn.
- **Breather.** When tension reaches 8 or more, the next 2 turns carry a pacing note and the director starts no
  events.
- **Quiet spell.** After 4 calm player turns in a row (no roll, not hurt, not in combat), one event fires. (Changed 2026-11-22 after the soak: "tension 1 or below" took 8 calm turns after a breather, so it never fired.) It only fires if no other
  world event is waiting, and only if the last director event was at least 6 turns ago.
- **Event choice.** Events come from an owner-approved list (`narrator/worlds/events.toml`):
  - only events whose conditions match;
  - an event for the current district beats one that can happen anywhere;
  - an event tied to the player's state (debt, an open promise, throttled chrome) beats a generic one;
  - no event repeats within 40 turns.
- The event goes out as a world event, the same channel used by calls-in, chrome changes and phone lies, so the
  narrator works it into the scene.

## Non-goals

- Choosing events with a model.
- Spawning fights or rolls. Events are things happening in the city that give the player something to chase.
- Scenery-only events. Every event either carries a lead or is tied to the player's own state (a promise, a debt).
- Changing the time of day (Nightwire is always night).

## Design

**State.** Four new fields on the session:

| Field | Type | Meaning |
|---|---|---|
| `Session.tension` | int | the current tension |
| `Session.quiet_turns` | int | calm player turns in a row |
| `Session.breather` | int | breather turns left |
| `Session.events_used` | dict[str, int] | event id → the player turn it fired |

All four load with defaults from older saves.

**When the director runs.** At the end of each player turn, after the referee: `narrator/director.py: tick(session,
rolled, failed, hurt)`. A roll-resolution turn counts as the turn with the roll.

**Event data.**

```toml
[[event]]
id = "torite-van"
text = "A torite van idles at the corner, engine running, someone inside checking a list."
lead = "Find out whose name is on the torite van's list outside the Torite office"
where = ["Ikebe Low"]       # districts; empty = anywhere
needs = ["owes"]            # owes | promise_open | throttled; empty = always
```

**Leads.** When an event fires, its `lead` joins `active_objectives` through the same path as the referee's
`new_lead` (deduped, capped at 5, the oldest journaled as "set aside"). So the player sees it in the Status panel and
the narrator sees it in the scene line. A lead may be empty only when `needs` ties the event to the player's state.
The location may be a place; its district is the place's `home` in `kuroshio.toml`.

`{who}` and `{what}` fill from the oldest open promise.

**Prompt.**
- During a breather, a line before the voices block reads: `Pacing: let this moment breathe - no new threats or
  arrivals this turn.`
- Events go to `pending_world_events`, which is already shown as `World event: ...`.

## How we'll know it worked

- Tests check:
  - tension rises and falls by the rules;
  - a breather lasts 2 turns;
  - a quiet spell fires exactly one matching event;
  - the order of preference is followed;
  - no repeat within 40 turns;
  - a fired event's lead lands in the objectives;
  - every event without `needs` has a lead;
  - old saves load.
- In a soak, the quiet middle stretch (the walk home, sleeping, waking) should get one event, and the turns after the
  crane climb and the punch should get breathers.

## Left to the builder

The exact numbers may be tuned after the first soak. Wording of the pacing note.
