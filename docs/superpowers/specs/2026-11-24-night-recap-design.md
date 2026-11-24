# Night recap: a storyboard of a played night

Status: draft 2026-11-24, waiting on the review card "Night recap". Candidate from the studio track in `ROADMAP.md`
("storyboard and animatic export from session logs"). It is a step toward the owner's goal of shorts about the
characters' daily lives.

## Why

A played night only exists as a scrolling log. A recap turns it into something you can look at and share: 8 to 12
panels of approved art, one line each, plus a silent animatic. It needs no new images and no model calls. Every soak
gets one too, so reviewing a soak becomes looking at a comic instead of reading 36 turns of JSON.

## Prior art

- **Wildermyth** (wildermyth.com/wiki/Event_Types, verified). Its comic-panel stories fire on structural beats
  (first arrival, first fall, victory, recruiting), with a cap per beat type (one mid-mission story per fight). There
  is no ranking by significance. Lesson: quotas per kind of beat, not only a score.
- **Felt, a simple story sifter** (Kreminski et al., ICIDS 2019, verified). Story sifting picks event sequences of
  narrative interest using authored patterns: a causal chain, a recurring character, a relationship that changes.
  The paper offers no general "storyfulness" measure. So ours is a short, written list of beats the engine already
  records.
- **The Alexandrian on campaign journals** (search snippets; the full page 404'd). The skill is "deciding what not
  to write about", and secrets stay out. Lesson: leave out bookkeeping, hidden clocks and anything the player didn't
  see.
- **Players' recap wishes** (forum snippets, unverified). They want a short factual list of who they met, what they
  owe and what's still open. That becomes the "facts" box under the panels.
- **AI Dungeon** (help-site snippets). It has no built-in recap; players write their own. That's a gap this fills.
- **McCloud's panel transitions** (secondary sources only). Moving to a new place is a scene-to-scene cut and needs
  an establishing shot. That gives one establishing panel per new district.

## Design

### Where the turns' places come from

`Session.trail: list[str]` gains the location at the end of each player turn. The director's `tick` appends it.
Old saves have no trail, so their recap uses the current location for every panel.

### Picking panels (`narrator/recap.py`, deterministic)

The log is cut into turns at each player action line. Each turn scores what the engine logged for it:

| beat | score |
|---|---|
| a roll with a clean success or a failure | 2 (complication 1) |
| a promise made, kept or broken | 3 |
| a director event, or a pressure clock's portent or full | 2 |
| a new person met, or one coming back | 2 |
| a liked turn (👍) | 3 |
| a place mark left | 1 |

- **Opening:** the first turn of the night, always.
- **Closing:** the last turn, always, plus an open-promise line as a "next time" hook.
- **Establishing:** the first turn in each new district is kept.
- **The rest:** the highest scores, at most 3 panels in a row in one place, with ties going to the earlier turn.
- **Total:** at most 12 panels, at least 3 (a short night shows every turn).

### A panel

- **Art.** In order: a scene image made that turn (`[image: ...]`), the place art, the district art, a dark card.
- **Caption,** top left: "Ikebe Low · small hours".
- **One line.** If an NPC spoke that turn, their shortest line of 4 to 20 words becomes a speech panel with their
  approved portrait inset. Otherwise it is the narration's first sentence, cut at 160 characters.
- **Left out:** engine lines in brackets, hidden clocks, rolls' numbers, and the player's own action text. The
  action is what the player did, so the panel shows what the city did back.

### Outputs (`python -m tools.recap <session.json> [--out DIR]`)

- `recap.html`: a page of panels in a grid, then a facts box (people met, promises open or kept, leads still open,
  night and stretch reached). It is self-contained, with images copied beside it, and opens from disk.
- `recap.mp4`: each panel held 3.5 s with the animatic's push-in, the caption and line as a lower third, and 0.5 s
  fades. It reuses `tools/shorts/animatic.py`'s camera and caption helpers. It is silent, at 1216×832.
- The soak test saves its session JSON beside the soak file and builds a recap for it.

### Testing

- Unit tests:
  - a quiet night gives at least 3 panels
  - the opening, the closing and every new district are kept
  - no more than 12 panels, and no more than 3 in a row in one place
  - a speech panel uses the NPC's line and portrait
  - bracket lines never reach a panel
  - a hidden clock's name never appears
  - an old save with no trail still works
- An end-to-end run on soak 17's session to check the HTML and an mp4 that ffprobe reads.

## Not doing (yet)

- An in-game "Last night" button at daybreak. That's the next step once the owner likes the sheets.
- Turning a recap into a real short (`short.toml` with cast and grey-box figures). The recap's panel list is the
  natural input for it later.
- Model-written captions. The lines come from what was actually said and narrated.
- Sound and voice.

## Open for the owner

- 12 panels at most, 3.5 s each (about 45 s of animatic). Longer or shorter?
- Should the player's own action show as a small line under each panel ("Rin: I punch the guy who bumps into me")?
  This draft leaves it out.
