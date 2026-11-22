# Liked turns: 👍/👎 that teach the narrator now and train it later

Status: draft for owner review (Nightwire Reviews, batch "Liked turns").

## Why

The owner wants Nightwire to get better the more it is played. Today nothing the player thinks of a turn is kept. A
single 👍 or 👎 per turn is the cheapest signal there is. It can be used right away, as example writing for the
narrator and a list of things the player dislikes. Later it becomes training data for the 4U box.

## Prior art

These are from research pass 2 (`2026-11-22-research-backend-intelligence-2.md`).

- **KTO** (Ethayarajh et al., ICML 2024, arXiv:2402.01306, verified) trains a model from a single "good" or "bad"
  label on each output, with no need for paired answers to the same prompt. That is exactly what a 👍 or 👎 on one
  turn gives us, so the saved records keep the full prompt with each label.
- **Using liked turns as examples before any training** is ordinary in-context example picking. There is no special
  citation for it, and it needs no extra model calls.
- **The copy risk is the one already handled for voices.** Small models copy example text when it fits the scene
  (arXiv:2402.09954). So only one example is shown per turn, and copies of it are cut by the existing 8-word repeat
  check.

## Goals

- Under the newest narration turn, the player sees 👍 and 👎. They can rate it, and change their rating until they
  send their next action.
- A 👎 can carry one optional reason, picked from: *repeats itself*, *acted for me*, *dull*, *got facts wrong*, *too
  long*.
- Every rating is saved, with the full prompt and the reply, to a shared file that all saves add to.
- Liked turns feed the narrator one example per turn. The reasons behind 👎 ratings feed the narrator a short list of
  things to avoid.

## Non-goals

- Rating older turns.
- Any training run. That waits for the 4U box; this design only makes sure the data is ready for it.
- Rating images or phone messages.

## Design

**Rating.**
- Only the newest turn can be rated: the player's action plus the narration after it, up to the next action.
- The client sends `{"type": "rate_turn", "like": true|false, "reason": str|null}`.
- The server ties the rating to that turn, using the prompt it kept from narrating it.
  - After each narration, `session.last_turn` is set to `{"prompt", "action", "narration", "location", "present"}`.
    It is persisted and overwritten every turn.
- A second rating of the same turn replaces the first, so the record is rewritten rather than added again.
- `rate_turn` is not an action. It takes no turn and calls no model.

**Saving.**
- Ratings go to `design-data/turn-ratings.jsonl`, one JSON line per rating:
  `{"at", "session", "like", "reason", "prompt", "action", "narration", "location", "present"}`.
- This file is the training set: prompt and reply for KTO.
- It is git-ignored, as play data.

**Example bank.**
- Liked turns become examples, picked in this order:
  - same location, with at least one of the same people present;
  - then same location;
  - then the most recent liked turn.
- One example is shown, at most 600 characters of narration.
- It never shows a turn from the last 20 log lines. That would just repeat recent events.
- Prompt line, just before the voices block:

```
A turn this player liked (match its feel and pacing; never reuse its words):
<action> → <narration>
```

- The example's sentences join `session.voice_lines` for the turn, so the existing cut removes any 8-word copy.

**Avoid list.**
- Built from the two most frequent 👎 reasons, counted over the last 30 ratings.
- It appears only when a reason was given at least twice:
  `The player has disliked: repeating yourself; deciding what they do.`

**Player view.**
- 👍 and 👎 show as two small buttons at the end of the newest turn in the feed.
- After 👎, the five reasons appear as chips, and picking one is optional.
- The chosen state stays visible until the next action. Nothing else in the feed changes.

## How we'll know it worked

- Tests cover saving and replacing a rating, picking the example, the avoid list, and old saves.
- Live: rate a few turns in a short probe. The next prompt should carry the example and the avoid line, and no
  example sentence should be copied word for word.

## Left to the builder

The button styling, and the exact wording of the reasons as shown to the narrator.
