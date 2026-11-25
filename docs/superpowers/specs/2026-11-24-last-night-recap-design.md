# Last night: the recap in the game

Status: approved 2026-11-24 (card `last-night` kept; owner: "go with your pick", so the chip only, nothing opens by itself). This is the follow-on named in
`2026-11-24-night-recap-design.md` ("Not doing (yet)"). The owner saw soak 17's recap sheet and said "looks good".

## Why

The recap sheet only exists after a soak, as a file. Players who come back the next evening, or a party picking up a
game, should be able to see what happened last night without scrolling the feed. It reuses the recap's panel
picking, with no new images and no model calls.

## Prior art (researcher, 2026-11-24)

- **Life is Strange** (GOG forum thread, verified). "Previously on" clips play between episodes and can't be
  skipped. Posters call them jarring, and the only workaround is deleting the video files. Lesson: never force it.
- **Game Developer, "Previously on..."** (Allins, 2009, verified). It argues for a short recap at level start for
  players returning after a gap, and says it should be optional.
- **Game Developer, "Improving narrative accessibility"** (verified). It describes three recaps: a slideshow of the
  last few events, one that scales with time away, and a menu synopsis. Menu summaries often work better than
  in-world ones.
- **Baldur's Gate 3 "Recent Events", Stardew's journal** (a returning-players list, verified). Both are opened from
  a menu, not shown on their own.
- **Telltale's choice-aware montages.** Search snippets only, so unverified.

## Design

### Engine

- `narrator/recap.py`: `turns()` tags each turn with the night it was played in. The night is the one current when
  the player's action line came, so the sleep turn belongs to the night it ended. The night is read from the
  `[clock: night N, …]` and `[clock: slept; night N, …]` lines. A save with no clock lines counts every turn as
  night 1.
- `panels(session, night=None)` picks from that night's turns only, with the same rules (3 to 12 panels).
- `server/views.py` gains `last_night`:
  - `night`: the night before this one
  - `panels`: those panels, with each art path made servable. Place and character art keep their root paths, and
    scene images get `media/`.
  - `open`: the open promises and leads
- It is `None` on night 1, or when last night has no turns.

### Frontend

- `StatusPanel`: a "Last night" chip beside "Night 2 · evening". During the new night's first stretch, and until
  this player opens it, the chip is marked as new: a cyan dot, and `aria-label` "Last night, new". The seen night is
  saved in localStorage per game.
- `LastNightOverlay.tsx`: a Radix dialog like the gallery, with Escape, the focus trap, and focus back on the chip.
  It shows the panels in a grid: art, the NPC portrait inset, the caption, the line, and the player's action as a
  small line. Below them sits "Still open" with promises and leads. One Close button.
- Nothing opens by itself, and the turn never waits on it.

## Not doing

- The video in the game. The mp4 stays a soak and studio output.
- Recaps of older nights (night 3 shows only night 2).
- A recap scaled to time away from the game.

## Testing

- Unit tests:
  - turns get the right night, and the sleep turn stays in the old night
  - `panels(night=1)` never shows night 2's turns
  - an old save with no clock lines works
  - `last_night` is `None` on night 1, and filled with servable paths on night 2
- Frontend: tsc, eslint and node tests pass. A browser check at 1280 and 390 px against a saved soak session that
  reached night 2.

## Owner question

- Should it open by itself once at daybreak (with one tap to close), or only from the chip? My pick is the chip
  only. Daybreak often lands mid-scene for a party, and the research's one strong signal is against recaps that
  get in the way.
