# Where people are, and waiting

Status: approved 2026-11-23 (review card "Next round: where people are, and waiting", kept). Builds on the night
clock (`2026-11-23-night-clock-design.md`).

## Why

The night clock moves time, but people only sleep or don't. Jun is in his karaoke box at every hour, so the hour
never changes who you can find. And if you want to meet someone in the small hours, all you can do is spend turns.

## Prior art

- **Majora's Mask timetables.** Game Developer, "Majora's Mask and the crisis of failure" (gamedeveloper.com,
  verified). Every character keeps a timetable and the player sees only part of it. Missing someone is part of the
  appeal, but the author's missed event "was really sad". From search snippets only: players found remembering the
  timetables daunting even with the Bombers' Notebook. Lesson: missing someone should be fair and recoverable.
- **Stardew Valley schedule data** (stardewvalleywiki.com Modding:Schedule_data; search snippets only, the fetch was
  blocked). Each NPC's schedule is data: a time mapped to a place, with a fallback when no entry fits. Lesson: keep
  it as a small table, with a default.
- **Skyrim's wait** (elderscrolls.fandom.com/wiki/Wait; snippet only). You can wait 1-24 hours, but not with enemies
  near. Players complain when the refusal has no visible reason. Lesson: refuse waiting in a fight, and say why.
- **Song, Zhu & Callison-Burch 2024** (arXiv:2409.06949, verified). The engine owning state keeps an AI game master
  consistent. So the engine decides where people are and when the wait ends; the narrator is told.
- **Generative Agents** (Park et al. 2023, arXiv:2304.03442, abstract verified). Agents plan daily routines with an
  LLM per agent. That is too costly for an 8B model on a CPU, so ours are fixed tables.

## Design

**Where people are.** `worlds/hours.toml` gets a `[where]` table: an NPC, then a place for some stretches.

```toml
[where."Jun Arakawa"]
"small hours" = "Pachinko back room"
```

- The place must be a place card in `kuroshio.toml`; the loader rejects anything else.
- In any stretch not listed, the NPC is where they are today: at their own venue if they keep one, otherwise
  nowhere fixed.
- On arrival somewhere (the cast reset), anyone scheduled here now joins the cast. A keeper scheduled elsewhere is
  not at their venue, the same as when they are asleep. Someone the action names still shows up, as today.
- Only a few NPCs get a schedule, picked from their world cards.

**Asking around.** When the action asks where a scheduled NPC is (the word "where" plus their name), the narrator
is told: `If asked: Jun Arakawa is usually at the Pachinko back room in the small hours.` This covers the current
stretch and the next one. Missing someone is never a dead end.

**Waiting.** An action like "I wait until the small hours", "I wait for the last train" or "I kill time" skips
time. The engine reads it with a regex, not a referee question.
- A named stretch jumps to the start of that stretch. A bare wait jumps one stretch. A stretch that has already
  passed tonight means the next night's.
- The narrator is told `You waited until <stretch>: tell the wait in one sentence, then the new hour.` The Time line
  already shows the new stretch, and an event due then fires on arrival, as it does today.
- Waiting is refused in combat (`in_combat`). The narrator is told `No waiting: there's a fight on.`, so the player
  sees why.
- Waiting past first train rolls to the next night, with the daybreak event, like any other rollover.

## Non-goals

- NPCs walking between places, or plans written by the model.
- A notebook screen of known schedules. Asking around is enough for now.
- Refusing waits while being chased. There is no chase state yet.

## How we'll know it worked

- Tests:
  - a scheduled NPC is in the cast at their place in their stretch, and not at their venue;
  - asking where someone is gives the usual-place line;
  - "wait until the small hours" lands there, and a past stretch rolls to the next night;
  - a wait in combat is refused with a reason;
  - the loader rejects an unknown place or stretch.
- Soak: add one wait action to the script, and check the clock moved and the narration tells the wait.

## Left to the builder

Which NPCs get schedules and where, the exact regex words, and the line wording.
