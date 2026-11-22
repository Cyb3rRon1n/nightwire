# NPC memory that keeps what matters

Status: approved 2026-11-22 (cards kept; the problem card marked Fix, read as "fix this"). Item 4 on the roadmap.

## Why

NPCs forget the wrong things.

- Today `session.npc_memory` keeps the newest 5 facts per NPC. Every known NPC is listed early in the prompt as
  "Known NPCs", ahead of the recent events.
- A promise made 20 turns ago is pushed out by "ordered noodles".
- Facts about people who aren't in the scene take up room, and the ones that matter sit in the middle of the prompt.
- The facts are only written when the narrator calls `remember_npc`. That is one tool among several, and the narrator
  can make only one call per turn, so the important moments often go unrecorded.

## Prior art

- **Generative Agents** (Park et al., UIST '23, arXiv:2304.03442, verified). Memories are ranked by the sum of three
  scores, each scaled to 0-1:
  - recency: decays by 0.995 per game hour since the memory was last retrieved;
  - importance: the model rates each memory 1-10 when it is written;
  - relevance: embedding similarity to the current situation.

  The top memories that fit go into the prompt. We keep the shape, but replace both model-driven parts with rules: no
  model call for importance, and no embeddings for relevance.
- **Lost in the Middle** (Liu et al., TACL 2023, arXiv:2307.03172, verified). Models use information best when it sits
  at the start or end of a long context, and worst in the middle. So memories go late, next to the action.

## Goals

- **What gets recorded.** Each NPC keeps up to 12 facts. Each fact is `{text, turn, last_used, weight}`.
- **The engine writes the facts that matter itself**, with no model call, for that NPC:
  - a promise made, kept or broken: "{name} promised: {what}", "{name} kept their word: {what}", "{name} broke their
    word: {what}";
  - a lie the NPC discovered: "{name} lied to them";
  - trust going up or down on the phone: "{name} came through for them" or "{name} let them down";
  - a debt paid.

  These get weight 3. The narrator's own `remember_npc` facts get weight 2 if they name the player, or use a word from
  a short list (owe, promise, lied, saved, betrayed, paid, killed, helped, family). Otherwise they get weight 1.
- **Ranking.** Score = recency + importance + relevance:
  - recency is 0.9 per player turn since the fact was last shown;
  - importance is weight / 3;
  - relevance is 1 when the fact shares a word of 4 or more letters with the player's action, else 0.
- **What the narrator sees.** Only NPCs in the scene (`session.present`) or named in the action, at most 3 of them, and
  for each the top 3 facts. They are shown late in the prompt, just before the world event, as:
  `What Mama Sato remembers: Rin promised to find Kenta; Rin lied about the money.`
- Showing a fact refreshes its recency, as in Generative Agents.
- **When an NPC is full,** the lowest-scored fact is dropped, not the oldest. So a broken promise outlives small talk.
- The early "Known NPCs" block goes away. Its job moves to the late block, limited to the people who matter right now.

## Non-goals

- Embeddings or any model call to rank memories.
- Reflections (Generative Agents' summaries of summaries). That waits for the 4U box.
- Gossip between NPCs. That is roadmap item 5.

## Design notes

- **Old saves.** Facts stored as plain strings load as `{text, turn: 0, last_used: 0, weight: 1}`.
- **Hooks.** The engine's facts are written from `promises.record` / `close` / `call_in` and from the referee's trust and
  lie paths. `phone.change_trust` gets one more line.
- **Scorecard.** The soak summary records each NPC's facts at the end. `soak_score` adds `npc_facts` (total) and
  `npc_facts_weighted` (weight 3 facts), so we can see whether the important ones stick.

## How we'll know it worked

- Tests check:
  - the engine writes a promise fact;
  - a weight-3 fact survives 12 turns of small talk;
  - only present or named NPCs are shown, at most 3 × 3, after voices and before the world event;
  - showing a fact refreshes it;
  - old saves load.
- Soak: in the voices soak, Mama Sato should recall the Kenta promise when Rin comes back to the izakaya.

## Left to the builder

The exact numbers, and the word list.
