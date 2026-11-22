# Places that grow, and word that spreads

Status: draft for owner review (Nightwire Reviews, batch "Places and gossip"). Roadmap item 5, parts 2 and 3. Sources:
`2026-11-22-research-places-gossip-3.md`.

## Why

Today the city forgets what the player did as soon as they leave. A bar you brawled in is the same bar next time. A
shopkeeper you saved has no idea the dockworkers you beat up exist, and their friends never hear about it. The owner
wants a world that keeps evolving. Both parts below reuse signals the game already has (rolls, combat, the referee's
answers), so neither costs a model call.

## Part 2: places that grow

**State.** Each place the player has been to keeps:
- `heat`, from 0 to 9;
- `warmth`, from -3 to +3;
- up to 3 `marks`, each `{text, turn}`.

A place is keyed by its known place name; otherwise by its district.

**Heat** follows Blades in the Dark.
- What raises it at the current place:
  - a fight: +2;
  - combat: +4;
  - someone hurt: +2.
- Heat falls by 1 for every 5 player turns spent elsewhere.
- **At 9:** the director fires an owner-written lockdown event for that district (for example, an Ōgane patrol sweeps
  the block), and heat drops to 5.

**Warmth** moves one step per turn.
- **Up:** the referee sees a human moment, the player helps someone at a cost, or keeps a promise there.
- **Down:** a broken promise or a discovered lie there, or violence against someone in the scene.
- It drifts one step back toward 0 for every 30 turns away.

**Marks.** The referee gets one new text question:

> `left_mark`: a lasting, visible change the player caused to this place this turn (broken window, burned stall,
> blood on the counter), under 8 words; otherwise empty.

It is grounded the same way as `new_lead`. A mark lasts 30 player turns. If the player returns while it is still there,
it becomes permanent. Only 3 marks are kept per place, and the oldest temporary one goes first.

**What the narrator sees** when the player is at a place with any state, one line placed just before the memories:

> `This place: the window is still boarded (Rin broke it 12 turns ago); people here are wary.`

The mood words:
- **Heat:** 0-2 calm, 3-5 wary, 6-8 tense, 9 locked down.
- **Warmth:** hostile, cool, neutral, friendly, welcoming.

**What the player sees.** The Status panel gets a "Here" line: the place's mood word and its newest mark.

## Part 3: word that spreads

**Deeds.** A deed is recorded from signals that already exist. Each one is
`{what, place, district, good|bad, turn, knows: {name: strength}}`:
- violence in a scene;
- helping at a cost;
- a promise broken or kept;
- a lie discovered;
- a walk-on's "what happened".

**Who knows.** Everyone present when it happened witnessed it, at strength 3.

**Spreading** (Ryan et al.; Gossamer):
- Every 5 player turns, each person who knows a deed tells one other: a world NPC, or one of the player's people, from
  the same district. That listener knows it at strength minus 1, so a deed travels at most 2 hops.
- Each hop has a 1 in 5 chance of being exaggerated, from an owner-written table. For example, a scuffle becomes a
  brawl, and "hit someone" becomes "put someone in the clinic".
- Strength drops by 1 for every 30 turns.
- At most 20 deeds are kept, and the weakest goes first.

**Making amends.** Keeping a promise to someone, or helping them at a cost, clears the bad deeds that person knows about
the player.

**What the narrator sees.** It goes into the "What X remembers" line for each present NPC who heard a deed rather than
saw it:

> `Mama Sato has heard (second-hand, maybe exaggerated): Rin put a dockworker in the clinic.`

**What the player sees.** The Status panel gets a "Word on the street" line per district: the strongest good deed and
the strongest bad one that people there know.

## Non-goals

- Lies told by NPCs.
- NPC-to-NPC relationships beyond sharing a district.
- Any model call.

## How we'll know it worked

- Tests cover:
  - heat, warmth and marks rising and decaying;
  - a mark becoming permanent;
  - the lockdown event;
  - a deed spreading 2 hops, then stopping;
  - exaggeration;
  - amends;
  - the prompt lines;
  - old saves loading.
- Soak: the punch on turn 25 should leave Ikebe Low wary. By the end, Mama Sato or Old Hara should have heard about it.

## Left to the builder

- The exaggeration table's wording (the owner reviews it on a card).
- The exact decay numbers.
