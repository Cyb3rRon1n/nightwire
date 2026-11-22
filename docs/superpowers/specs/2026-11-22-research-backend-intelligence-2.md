# Research: making the narrator smarter on a CPU budget (2026-11-22)

This is research pass 2 on the game's "backend intelligence". Each source below is marked **verified** (the page was
fetched and confirmed) or **unverified** (cited from memory; check it before using it in a spec).

## Findings

1. **Learning from 👍/👎.**
   - KTO learns from a single good/bad label per output, so it needs no chosen-versus-rejected pairs. It reports
     matching or beating DPO at sizes from 1B to 30B (Ethayarajh et al., ICML 2024, arXiv:2402.01306, verified).
   - Before any training, liked turns can be pulled in as example writing, and a "don't" list can be built from
     disliked turns. Neither needs a model call.
   - No source gives a minimum amount of data.
2. **Scoring narrators.**
   - What to measure, taken from *Dungeons and Dragons as a Dialog Challenge for AI* (Callison-Burch et al.,
     EMNLP 2022, arXiv:2210.07109, verified): next-turn plausibility and state tracking.
   - Memory probes of the form "does X still know Y at turn N", as in LoCoMo (Maharana et al., arXiv:2402.17753,
     verified).
   - Judge biases: when a model judges output, it favours position, length and itself (MT-Bench, arXiv:2306.05685,
     unverified). Never let the model judge its own output.
   - Checks that need no model:
     - repetition;
     - naming something the game state doesn't have;
     - the narrator deciding for the player;
     - promises left to go stale.
3. **NPC memory.**
   - Generative Agents ranks memories by recency, importance and relevance (Park et al., UIST 2023, arXiv:2304.03442,
     unverified). There, importance is judged by the model each time; here, fixed rules can do that job instead.
   - Keep 3 to 5 facts per NPC.
   - Put those facts late in the prompt ("Lost in the Middle", arXiv:2307.03172, unverified).
   - MemGPT's agent loop doesn't fit an 8B model running on CPU.
4. **Pacing.**
   - Left 4 Dead's AI Director tracks how intense things are for the player. It builds pressure up to a peak, then
     forces a calm stretch (Booth, Valve 2009 slides, verified).
   - Storylets are events with preconditions, chosen by how relevant they are right now (Kreminski & Wardrip-Fruin,
     ICIDS 2018, unverified; Emily Short's posts on storylets).
   - Façade uses a library of beats, each with preconditions (Mateas & Stern, AIIDE 2005, unverified).
5. **Gossip and reputation.**
   - Talk of the Town has NPCs who observe events, tell others, misremember and lie, all simulated without a model
     (Ryan, Mateas & Wardrip-Fruin, AIIDE 2015/2016, verified).
   - Gossamer (Kreminski et al., CoG 2023, snippet only).
6. **Small-model reliability.**
   - Constrain the output format only for the referee. Leave narration free, because format restrictions hurt
     reasoning ("Let Me Speak Freely?", Tam et al., arXiv:2408.02442, verified).
   - Outlines and Ollama's JSON schema guarantee the output's shape, not that it is correct (Outlines,
     arXiv:2307.09702, verified).
   - Run a critic pass only when a cheap check fires.
   - A 14B model on the 4070 needs about 4-bit quantization. Decide between it and the current model by A/B testing
     on the soak.

## Ranked for Nightwire

1. Liked turns: an example bank, a "don't" list, and data for later training. **CPU now.**
2. A narrator scorecard in the soak: repetition, state contradiction, the narrator deciding for the player, and
   memory probes. **CPU now.**
3. A director: an intensity counter in the style of Left 4 Dead, plus world events chosen as storylets. **CPU now.**
4. NPC memory salience: recency × times recalled × rule flags, at most 5 facts each. **CPU now.**
5. Emerging characters, then places that grow, then gossip in the style of Talk of the Town. **CPU now.**
6. Train KTO on 👍/👎 and A/B a 14B model on the scorecard. **Needs the 4U box.**
