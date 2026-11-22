# Unfinished business: promises, debts and favours that come back

Status: draft for owner review (Nightwire Reviews, batch "Unfinished business").

## Why

The owner wants Nightwire to feel alive and to grow the more it is played. Today a promise made in a scene ("I'll bring
your nephew home", "you owe me one, Hara") lives only in the log. Once it scrolls out of the recent-events window the
narrator forgets it. The only tracking is a trust nudge for phone contacts (`kept_promise_to` / `broke_promise_to` in
`narrator/referee.py`), and that runs only when the player already has contacts. In a debt society, the debts people
owe each other should be the thing that comes back.

## Prior art (verified 2026-11-22)

- **Blades in the Dark** (John Harper, 2017; SRD "Entanglements"): between jobs, the trouble the crew made comes back
  to them. Each entanglement lists ways to get rid of it, some at a cost. Our idea: old business returns on its own
  schedule, not only when the player remembers it.
- **Monsterhearts** (Avery Alder, 2012): "Strings" record who has emotional leverage over whom. They are gained in
  play and spent later. Our idea: a favour owed is leverage that the narrator can spend.

## Goals

- When a scene makes a promise, debt or favour between the player and a named person, it is recorded.
- When that person is in the scene again, the narrator is reminded of it.
- A promise left open too long is called in once, as a world event.
- When a promise is kept or broken, it is closed. A broken promise is remembered: the narrator hears about it once.

## Non-goals

- Money amounts or a debt ledger UI. Installments already cover money.
- Promises between two NPCs.
- A new model call. The referee that already runs gains one question.

## Design

**Recording.** The referee always asks one more text question:

> `promise_made`: a new promise, debt or favour agreed this turn between {name} and one named person, written as
> "Who: what" in under 12 words (for example: "Mama Sato: bring back her nephew Kenta"); otherwise empty.

The answer is checked the same way the referee checks a new lead. "Who" must appear in the action or the narration,
and "what" must quote the scene or name something in it. If either check fails, the answer is logged and ignored.

Accepted answers are stored in `Session.promises: list[dict]`, one entry per promise:
`{"who", "what", "turn", "called_in": false}`. Here `turn` is the player-turn count (`narrator/cast._player_turns`).
At most 6 promises are kept open; when a 7th comes in, the oldest is dropped. The same who + what is never stored
twice.

**Closing.** `kept_promise_to` and `broke_promise_to` are now asked whenever any promise is open, as well as when the
player has phone contacts. A match on "who" closes the oldest open promise to that person:

- Kept: logged as `[promise kept: Who: what]`. The existing phone-trust change still applies.
- Broken: logged the same way, and one world event goes out: "{Who} remembers {name} broke their word: {what}."

**Bringing it back.** A prompt line sits just before the voices block:

```
Unfinished business: Mama Sato: bring back her nephew Kenta (9 turns ago).
```

The line lists every open promise whose "who" is in `session.present`. When nobody listed is present, it shows the
single oldest promise, once that promise is at least 8 turns old. It shows at most 2 entries. When nothing qualifies,
there is no line.

**Called in.** Once a promise is 16 turns old and still open, it goes out once as a world event: "{Who} hasn't
forgotten: {what}." The promise is then marked `called_in`, so it is never called in again.

**State.** `Session.promises` is saved like the other session fields; older saves load with an empty list.

## How we'll know it worked

A scripted soak that includes a promise ("I promise Mama Sato I'll find Kenta"), then 20 turns elsewhere. Pass if:

- the promise is recorded;
- the "Unfinished business" line appears;
- the promise is called in once around turn 16;
- returning to the izakaya brings it up;
- there are no new errors or empty turns.

## Left to the builder

The exact wording inside the shapes above, and how the "what" grounding reuses `_names_something_in` /
`_quotes_the_scene`.
