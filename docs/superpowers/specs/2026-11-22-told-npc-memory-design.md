# NPCs remember what the player tells them

Status: approved 2026-11-23 (card kept). Follows roadmap item
4 (NPC memory).

## Why

On turn 11 of soak 7 Rin told the collector, Wataru Ono, "I already paid this week". Nobody remembered it.
- NPC facts are written only by the engine's own hooks (promises, trust, lies found out) or when the narrator calls
  `remember_npc`.
- The narrator can make only one tool call per turn, and it rarely uses it on talk.
- So the things a player *says* to people (claims, offers, threats, lies) vanish. The collector probe has failed in
  every soak for this reason, not because of the scene.

## Prior art

- **Generative Agents** (Park et al., UIST '23, arXiv:2304.03442, verified for the NPC memory spec). Every observation
  goes into the memory stream, and ranking decides what comes back. Being told something is an observation.
- **Our own NPC memory spec** (2026-11-22). The engine writes the big moments itself, with no model call, because the
  narrator's single tool call misses them. This change does the same for talk, through the referee, which already runs
  every turn.

## Design

- **One more referee text field, `told_npc`, at no extra model call:**
  > "what {name} told a named person in the scene this turn that they would remember (a claim, an offer, a threat, a
  > lie), as `Name: what was said, a few words`; empty if nothing."
- **Grounding:**
  - the name must be someone present, or named in the action or the narration;
  - every real word (3+ letters) of "what" must be in the action, the same rule now used for promises. The player
    said it, so it must be in the player's words.
- **Write:** `"{player} told them: {what}"` at weight 2 (NOTABLE), so ranking can drop it for something bigger.
- **Probe:** `collector_remembers_paid` stays. It checks any NPC's facts for "paid", so it passes whoever the narrator
  made the collector.

## Non-goals

- Judging whether it was true. The lie path already handles a lie that is found out.
- Recording what NPCs say to the player. The narration log already holds that.

## How we'll know it worked

- Tests:
  - "Wataru Ono: already paid this week" with that action writes the fact;
  - an unnamed or absent person is ignored;
  - words the player never said are ignored.
- Soak: the collector probe passes.
