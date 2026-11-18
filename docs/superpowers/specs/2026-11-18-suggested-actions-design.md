# Suggested Actions with Skill Chips: Design

Date: 2026-11-18. Status: design approved by the owner in chat on 2026-11-18. Not yet planned or built. Needs no GPU to build; the CPU narrator is enough for tests.

From ROADMAP "candidate future phases": *Suggested actions with skill/DC chips — a BG3 dialogue-wheel feel.*

## Goal

After each story turn, show up to 3 suggested moves as chips above the text box. Some are plain moves; some carry the roll they would cause, how hard it is and this character's chance: `Persuasion · Moderate · 60%`. They do two jobs equally (owner's answer): help a player who is stuck, and show the risk before acting. Free typing stays the core and never needs a chip.

## Decisions (owner, 2026-11-18)

| Question | Answer |
|---|---|
| Main purpose | Both equally: ideas when stuck and visible risk |
| Is a tagged chip a promise? | Yes. Clicking it rolls exactly that skill, attribute and difficulty |
| How is difficulty shown? | Label plus this character's chance |
| What does a click do? | Sends at once |
| Where do chips come from? | A separate small structured call after the narration (approach A) |

Rejected: chips inside the narrator reply (bigger schema for an 8B model, risks the tuned narrator prompt, chips wait for the whole reply); engine templates without a model (generic, not about the scene).

## Flow

1. **When.** After every story turn (typed action, chip click, roll result), never while a roll is pending. Only after the prose and voices are sent, so the story is never delayed.
2. **Call.** `suggest()` in new `narrator/suggestions.py`, through the existing `NarratorBackend.judge()` (no thinking, temperature 0, JSON schema). Input: the last few story log lines, the place, the character's name, role and top skills. Output: up to 3 `{text, skill?, attribute?, stakes?}`.
3. **Engine checks** (the model's output is never trusted as is):
   - `skill` and `attribute` must be real (`RequestRoll`'s literals). A bad tag turns the chip plain; an empty chip is dropped.
   - At most 3 chips; at least one plain. If none came back plain, keep the first 2 tagged chips and add the plain chip "I look around."
   - Stakes go through `ruleset.difficulty.difficulty_for` now, so the promised difficulty is final.
   - Chance from new `ruleset` function `roll_chance(character, attribute, skill, difficulty) -> int` (percent). It shares the modifier code with `roll_check` (attribute modifier, skill, chrome bonus, social penalty), so the shown chance is the real one. Counted over the ten d10 faces: 10 always succeeds, 1 always fails, success includes a complication.
4. **Storage.** `session.suggestions[player_id]` holds the checked chips. The player gets `{id, text, skill, attribute, difficulty, chance}` (no tag fields for a plain chip). Only that player sees their chips.
5. **Click.** The browser sends `{type: "action", text, chip: id}`. The server looks the id up; the browser never sends tag fields.
   - **Tagged chip:** the risk check (`assess`) is skipped. The turn runs as a must-roll turn, but the engine sets the pending roll from the chip's skill, attribute and difficulty, whatever the narrator's `request_roll` said, or if it asked none. The outcome check (`narrator/risk.py`) still guards the set-up.
   - **Plain chip:** a no-roll turn (the plain tag is a promise too); a narrator `request_roll` is dropped, as a `no_roll` turn already does.
6. **Clearing.** Chips are cleared on any action, text, roll or reconnect. A stale or unknown id is refused with "those options have expired" and the row disappears.

## The suggest prompt

- One plain move (talk, look, leave) and up to two risky moves using different approaches (social, tech, stealth, force), leaning on the character's skills where the scene allows.
- First person, like a typed action ("I talk the doorman down"), 12 words at most.
- Only what the scene has shown; invent no people or objects.
- Never say how the move turns out (same rule as the outcome check).

## Frontend

- A chip row directly above the text box in `FeedPanel.tsx`. Plain chip: a plain pill. Tagged chip: skill, the difficulty label in the existing roll-card colours, chance. Hover/long-press shows `Presence + Persuasion`.
- The text box keeps focus; typing works as today.
- On a phone the row scrolls sideways (no page scroll).
- Click sends at once and hides the row. The next set arrives with the next turn.
- A small toggle hides chips; the choice is kept in `localStorage` (a per-player convenience).

## Errors and cost

- Any `suggest()` failure (timeout, bad JSON, every chip rejected) means no chips that turn, logged as `[chips error: ...]` (bracket lines are hidden from the feed). The turn itself is never affected.
- About 60–80 output tokens per turn: roughly 3 s on the 4070, about 20 s on this box's CPU. Hosted backends already implement `judge()`.

## Measure

Log each action's source as `[action source: chip|typed]`. The soak summary reports the chip share. If nearly every action comes from a chip, the suggestions are taking over (Smart Reply research below) and need adjusting.

## Testing

- `roll_chance`: against hand-counted d10 faces, with and without chrome bonus and social penalty.
- Chip checks: fake skill turns plain, empty chip dropped, "I look around." added when no plain chip came back, at most 3, the difficulty cap applied.
- Chip turns with a scripted narrator: a tagged chip leaves exactly its roll pending even when the narrator asks for another skill or none; a plain chip gives no roll even when the narrator asks for one; `assess` is not called; a stale id is refused.
- Clearing on roll, text and action; never sent while a roll is pending.
- `tools/soak_test.py --chips`: click a chip every few turns.
- Frontend: CI lint and build, plus one live browser check on the dev server.

## Not in this version

Disco Elysium-style retry after levelling up; Cyberpunk 2077-style greyed-out locked options; chips in phone texts. Add if players ask.

## Research basis

Research pass 2026-11-18, search results only, no pages opened, so treat as pointers:

- **Baldur's Gate 3:** checks are tagged by skill in brackets, and the roll screen shows the DC actually rolled; patch 5 changed it to show the true DC instead of a modifier-adjusted one (https://gamingrespawn.com/?p=54148, https://gog.com/forum/baldurs_gate_series/feedbacksuggestion_conversation_skill_checksdice_rolls_improvement_alternative). Basis for binding the shown check to the real roll.
- **Disco Elysium:** active checks show a difficulty label and a success percentage computed from skill and modifiers (https://www.gamepressure.com/disco-elysium/skill-tests/zfe3e2); players distrust it when a 90%+ check fails (https://steamcommunity.com/app/632470/discussions/0/1609400247630935590). The owner chose to show the chance anyway; computing it from the exact roll code keeps it honest.
- **Cyberpunk 2077:** locked options stay visible, greyed out, to show another build could pass (https://dev.holdtoreset.com/?p=44993). Deferred.
- **Blades in the Dark:** the GM sets position and effect after the player declares the action and before the roll, so the risk is known before committing (https://bladesinthedark.com/effect).
- **Suggested replies:** Gmail Smart Reply shows 3 options; suggestions make writing more generic and more alike across groups (https://news.cornell.edu/node/330798, arXiv:2210.06470). Basis for 3 chips, a mandatory plain chip, the hide toggle and the chip-share metric.
- Not found: how AI text adventures (AI Dungeon, NovelAI and others) generate suggestions, or whether players use them.
