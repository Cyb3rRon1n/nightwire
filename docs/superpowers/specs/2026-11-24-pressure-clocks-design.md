# Pressure clocks

Status: approved 2026-11-24 (review card "pressure-clocks", kept with no notes); built 81bbd1b. Builds on the director
(`2026-11-22-director-design.md`), places and heat (`2026-11-22-places-gossip-design.md`) and the night clock
(`2026-11-23-night-clock-design.md`).

## Why

Today the city only reacts. Heat locks a place down, the director fires an event when play goes quiet, and the repo
clock counts one player's debt. Nothing in the city wants something and moves toward it while the player does other
things. The roadmap lists Blades-style clocks as a candidate. The Sprawl, one of the games this project cites, runs
its missions on clocks.

## Prior art

- **Blades in the Dark SRD, progress clocks** (bladesinthedark.com/progress-clocks, verified). A clock is a circle
  of 4, 6 or 8 segments, named after the obstacle or threat. A danger clock fills when the crew gets consequences
  from missed or partial rolls, 1 to 3 segments by how bad they are. A tug-of-war clock can fill and empty. Faction
  clocks are long-term goals the GM ticks in downtime. "Not every situation requires a clock."
- **Blades SRD, heat** (bladesinthedark.com/heat, verified). Heat is a 9-segment meter that rolls into a wanted
  level. We already have this as place heat and lockdown, and it stays as it is.
- **Dungeon World fronts** (roll20.net/compendium/dw/Fronts, verified). A danger has 1 to 3 grim portents ("bad to
  worse to much worse") and an impending doom when the last one comes to pass. "When you're not sure what to do next,
  push your danger towards resolving a grim portent." Lesson: each stage of a clock is a fixed, written beat.
- **The Sprawl** (Indie Game Reading Club critique, secondhand; the book wasn't fetched). The mission clock runs
  from 1200 to 0000, and each segment has a meaning in the story. The legwork clock ticks on missed legwork rolls.
- **Citizen Sleeper** (Infinite Backlog, verified). Ending a cycle advances clocks in the world, so pressure moves
  even when the player stalls.
- **Indie Game Reading Club, "Clocks"** (verified). Keep three or four campaign clocks at once. Show them, because
  a visible clock keeps the threat in mind. One tick can stand in for several stacked penalties.
- **datashaman/ai-ttrpg** (GitHub README, verified). An LLM narrator with engine-owned Danger and Resistance clocks.
  "Code owns truth." The narrator can't end a scene, and each clock fills only from validated outcomes. This is the
  closest match to how we want to build it.

## Design

### The clocks are written data, like events

`worlds/clocks.toml` holds a short list of clocks. Each one has:

- `id` and `name`. The name is the threat, as Blades says: "Ōgane crackdown on the Docks".
- `size`: 4, 6 or 8.
- `where`: the districts it belongs to.
- `shown`: true puts it on the Status panel as pips. False keeps it hidden, so only its portents reach play.
- `ticks`: what moves it, from a fixed list the engine can see (below).
- `eases`: what moves it back. That makes it tug-of-war, so the player can push back.
- `portents`: one line for each stage, at the segments the clock lists (for example `[2, 4]`). When the clock
  crosses a stage, that line goes to the narrator as a `World event:`. That uses the same path director events
  already use.
- `full`: the line for when it fills, plus a `lead` added to the objectives, the same as director events.

The loader rejects unknown triggers, districts that don't exist, stages past the size, and a clock with no `full`.

### What moves a clock (engine facts only)

These are the triggers. Each is a fact the engine already has, so there's no new referee question.

| trigger | fires when |
|---|---|
| `fight` | a fight roll in the clock's district this turn |
| `miss` | a failed roll, or a success with a complication, in its district |
| `heat` | the current place's heat rose this turn, in its district |
| `night` | a new night begins (the night clock), anywhere |
| `lead_done` | the clock's own lead, or its `eases_lead`, is marked done |

A clock moves at most one segment per turn, however many triggers fire. A brawl adds one segment, not three.
Blades' "1 to 3 by how bad it is" is left for later, because the referee has no severity to give. `eases` takes
the same triggers and moves the clock back one segment. It never goes below 0.

### When it fills

The `full` line goes to the narrator as a `World event:`, the lead joins the objectives, and the log gets
`[pressure: <id> full]`. Then the clock resets to 0 and rests for 40 turns, the same no-repeat window director
events use. A clock never ends the game, kills anyone or removes chrome. Those stay with the engine's own rules,
such as the repo clock.

### Showing it

- **Narrator:** one line, only while the player is in a clock's district and only for shown clocks:
  `Pressure: Ōgane crackdown on the Docks 4/6.` Prompt budget is the real limit, so hidden clocks add nothing
  until a portent fires.
- **Status panel:** a "Pressure" block reusing the repo clock's pips, one row per shown clock, with the district
  name. Hidden clocks never show.
- **Cap:** at most 3 clocks in the world file at first, and at most 2 shown (the Indie Game Reading Club's three
  or four).

### The first three clocks (for the owner to approve)

1. **Ōgane crackdown on the Docks** (6, shown, Kuroshio Docks). Ticks on `fight`, `heat` and `night`. Eases when
   the crane-jam lead is done. Portents at 2 and 4: extra drones over the cranes, then checkpoints at the gates
   fining everyone. Full: an armored response team sweeps the container canyons. Lead: "Find out who sold the
   Docks out to Ōgane".
2. **The no-manifest container** (4, hidden, Kuroshio Docks). Ticks on `night` only, so it's a Citizen
   Sleeper-style cycle clock. Portents at 2 and 3: its light flickers in a pattern, then a crane moves it to the
   outbound stack by itself. Full: it ships out, and whatever was running inside is gone. Lead: "Find out where the
   no-manifest container went". It's built from the Docks card's own hook.
3. **Kuze-gumi squeeze on Ikebe Low** (6, shown, Ikebe Low). Ticks on `miss` and `night`. Eases when the player
   finishes a lead in Ikebe Low (`lead_done` on any lead whose text names Ikebe Low or one of its places). Portents
   at 2 and 4: shop shutters with protection stickers, then a clinic behind a noren curtain closed "for
   renovation". Full: the Kuze-gumi takes over a block, and Mama Sato's izakaya gets a visit. Lead: "Find out who
   in Ikebe Low is paying the Kuze-gumi".

### Testing

- Unit tests: loader validation, one segment a turn at most, ease to 0, stage crossing queues its portent once,
  full fires a lead and rests.
- Soak: two new probes, `clock_moved` (any clock above 0, or filled, by the end) and `clock_portent` (a portent
  reached the narrator). The soak already fights in Ikebe Low, sleeps and goes to the Docks, so it needs no new
  turns.

## Not doing

- Folding the repo clock or heat into this. They work and the soaks check them.
- Clocks the model creates or ticks. The referee and narrator only ever see a clock's state.
- Racing and linked clocks, a wanted level, and severity-sized ticks. Each waits until a real need shows up.
- Faction clocks for every faction. Three written clocks first, then see whether players notice them.

## Open for the owner

- The three clocks above: keep, change, or swap any.
- Whether hidden clocks are fair. Dungeon World keeps fronts secret, Blades shows its clocks, and the portents
  already tell the player something is coming.
