# Story thread, opening scene, scene images and fixer pacing (owner-approved 2026-11-07)

Source: a full UI playthrough on 2026-11-07 (19 turns, Kaito Arai, streetkid solo). Atmosphere held, but the plot didn't move:
- **Riddles, not leads.** Three NPCs answered direct questions with riddles and warnings for six turns.
- **No objectives.** Objectives stayed empty all game.
- **Wrong character.** Old Hara, the kind ripperdoc, was named as a villain "with a taste for blood".
- **Blank start.** The first screen was blank.
- **Generated images.** They came on nearly every other turn, in a near-photoreal style that didn't match the approved art, and pushed the text off screen.
- **Slow fixer.** Jun took 6 turns to answer a request for work.

The owner approved the four recommendations below on 2026-11-07.

## 1. Leads, not riddles (story thread)
**Research.**
- GUMSHOE's core-clue rule: the clue that moves the story forward is never gated behind a roll. Pelgrane later refined this to "the players always get the *lead*": the fun is in interpreting clues, not finding them ([Clues vs. Leads](https://pelgranepress.com/2020/02/21/clues-vs-leads), [Giving out clues](https://pelgranepress.com/2020/09/16/see-page-xx-give-a-clue-giving-out-clues-in-gumshoe)).
- Justin Alexander's Three Clue Rule: give every conclusion several routes to it, so one missed clue can't stall the game ([The Alexandrian](https://thealexandrian.net/creations/misc/three-clue-rule.html)).
- SillyTavern World Info: an entry is injected when its keyword appears in recent chat. The scan depth is configurable, and a shallow scan misses mentions from earlier turns ([ST docs](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)).

**Decisions.**
- **Narrator rule.** A direct question to someone gets a concrete lead: a name, a place, or a thing to find.
  - A character may lie, bargain or set a price, but may never only warn or speak in riddles.
  - No roll gates a lead.
- **Engine objectives.** The referee gets one more field, `new_lead`. It is the next step the scene handed the player, in a few words.
  - It counts only if it names a known place or a named character, or is quoted from the scene.
  - Each lead becomes an objective (five at most, oldest dropped first).
  - The narrator's `update_world` objectives still work.
- **World cards for mentioned characters.** The card scan now covers the last two turns of story as well as the action. A character who is only mentioned, like Old Hara in Mama Sato's line, still brings their card.

## 2. Opening scene
**Research.** The researcher could not fetch sources for these; they are background knowledge, marked here as such:
- Cyberpunk 2077's lifepath prologues start each character in their own world.
- Cyberpunk RED's starter adventures begin with a fixer handing out a job.
- Blades in the Dark's "start in the action" is commonly cited for the same advice.

**Decision.** When a new character joins, the engine places them by lifepath, then runs one narration turn: a short arrival scene that ends on a moment to act.
- Streetkid starts in Ikebe Low, Corpo in Tenjō Heights, Nomad at the Kuroshio Docks, and Tsukumogami on the Ring Line.
- Jun's first job text arrives on the next phone turn, and its next step becomes the first objective.

## 3. Scene images
**Research.** Visual novels keep one background per location and save special CG art for key moments. This is a widely known convention; no source was fetched.

**Decisions.**
- **Known places.** A place with approved art shows that art, and no image is generated there.
- **Other places.** At most one new image per 6 player turns.
- **In the feed.** A generated image shows at a modest height and opens the gallery when clicked, instead of filling the feed.

## 4. Fixer pacing
**Research.** Player reports (forum anecdotes only) describe Cyberpunk 2077 fixers answering promptly. The researcher's recommendation was a quick reply to a work request, with long delays saved for messages nobody asked for.

**Decision.** A fixer asked about work, a job, a gig or pay replies on the next phone turn.

## Testing
- Unit tests for each rule.
- Soak runs and a UI replay, compared with the 2026-11-07 playthrough.
