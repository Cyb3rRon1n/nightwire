# The night clock: time that moves in a city that is always night

Status: approved 2026-11-23 (all three cards kept). The owner chose
"night segments" over a minute clock or Blades-style phases (2026-11-23).

## Why

Nightwire has no in-game time. Time is only the count of player turns.
- Sleeping moves nothing. In the soak, "I go home and sleep" then "I wake up and check the news" happen in the same
  moment.
- The phone spec deferred contact availability by time of day "because there is no game clock" (ROADMAP, phone
  phase). So Jun answers at any hour.
- The narrator and voice lines say "tonight" and "midnight at the north gate", but nothing knows when that is.
- The city is always night by owner rule (no daytime images), so time can't be shown by daylight. It has to be shown
  by the city's rhythm.

## Prior art

- **"You Have Thirteen Hours in Which to Solve the Labyrinth"** (Song, Zhu & Callison-Burch, Wordplay @ ACL 2024,
  arXiv:2409.06949; abstract verified). An AI game master gets more consistent state updates when game state is
  controlled through engine functions, not the model. So the engine owns the clock and the narrator is only told it.
- **Blades in the Dark downtime** (bladesinthedark.com/downtime-activities, verified). Time is a budget: two free
  downtime activities per phase, and more cost coin or rep. Our version: a night has a fixed number of stretches, and
  turns spend them.
- **Persona's calendar** (time slots per day, with actions using a slot) and **Disco Elysium's clock** (time passes
  with talk; some people are only around at certain hours; sleeping moves the day on). Both are second-hand only,
  from walkthroughs and guides. They show the same shape: named slots, and people who keep hours.
- **City rhythm instead of light.** This is our own design idea, not taken from any source: Japanese cities run on
  real hours, such as the last train, shutters coming down, and the first train.

## Design

**The clock.** `session.night` starts at 1. `session.stretch` is one of five, in order:

| Stretch | Feel the narrator is told |
|---|---|
| evening | the city filling up, shops and stalls open |
| last train | the last Ring Line trains, people heading home or heading out |
| shutters down | shops shut, izakaya and the illegal places still open |
| small hours | empty streets, only night people |
| first train | the first trains, the night giving out |

**What moves it (engine only, no model call):**
- Every 3 player turns in a stretch, it moves to the next stretch.
- A Ring Line ride to another district costs one stretch, on top of that.
- Sleeping jumps to `evening` of the next night. This needs one more referee true/false question: "did {name} go to
  sleep?". Sleep always works, because Disco Elysium players report getting stuck when sleep is blocked.
- After `first train`, the next stretch is `evening` of the next night. The day happens off-screen, which keeps the
  no-daytime rule. A world event says so: "The sky greys, the city shutters for the day, and the next night comes on."

**The narrator sees** one line, late in the prompt next to the world event: `Time: night 2, small hours`, plus that
stretch's feel. Nothing else changes in the prompt.

**People keep hours:**
- World NPCs and phone contacts may have an `asleep` list of stretches in `worlds/*.toml`. Example: Old Hara sleeps
  in the small hours; Mama Sato's izakaya shuts at first train.
- A text sent to a contact who is asleep is delivered when they wake, which reuses the phone's existing `deliver_at`.
- An NPC who is asleep isn't added to the scene's cast.
- With no list, a person is around at all hours, which is today's behaviour.

**Events keep hours.** An event in `events.toml` may have `stretches = [...]`. The director only picks it in those
stretches. Example: the torite van in the small hours, a stall rush at evening.

**The Ring Line.** From `shutters down` until `first train` there are no trains. The narrator is told "no trains:
walk or pay for a taxi". The engine does not block the move.

**Player view.** The Status panel header shows "Night 2 · small hours".

## Non-goals

- Minutes or hours on a clock face. The owner chose stretches.
- Daytime scenes, or any daytime image.
- Blocking travel, or making the player wait out a stretch. A "wait until..." action can come later if play asks for
  it.
- Changing the repo clock, which still counts actions.

## How we'll know it worked

- Tests:
  - 3 turns move a stretch;
  - a Ring Line ride costs one;
  - sleep jumps to the next evening;
  - first train rolls over to the next night with its event;
  - a sleeping contact's reply waits until they wake;
  - an asleep NPC isn't in the cast;
  - an event only fires in its stretches;
  - old saves load at night 1, evening.
- Soak: the "go home and sleep" turn moves to night 2. A new probe, `night_moved`, checks that the night counter went
  up.

## Left to the builder

The exact feel lines, which NPCs get hours (a few, picked from their world cards), and the Status styling.
