# Research pass 3: places that grow, and gossip (2026-11-22)

This pass gathers prior art for roadmap item 5, parts 2 and 3. Each source is marked **verified** (the page was read)
or **unverified** (a search snippet only).

## Places that grow

- **Emily Short, "Beyond Branching: Quality-Based and Salience-Based Narrative Structures"** (2016) — verified.
  - Link: https://emshort.blog/2016/04/12/beyond-branching-quality-based-and-salience-based-narrative-structures/
  - In Fallen London-style quality-based narrative, a location is itself a quality.
  - Salience systems pick the content that matches the most conditions.
  - She warns that players forget the causes behind a change. So whatever changed a place must be said back to them.
- **John Harper, Blades in the Dark SRD: Heat** — verified.
  - Link: https://bladesinthedark.com/heat
  - A job adds heat by how loud it was: 0, 2, 4 or 6.
  - It adds +1 for a hostile or high-profile target, and +2 if anyone died.
  - At 9 heat the crew gains a wanted level, and heat resets.
  - Downtime decay: not verified.
- **Grinblat & Bucklew, "Subverting Historical Cause & Effect: Generation of Mythic Biographies in Caves of Qud"**
  (FDG 2017) — verified.
  - Link: https://pcgworkshop.com/archive/grinblat2017subverting.pdf
  - Events change the properties of places.
  - The text explaining why is written afterwards, from the current state.
  - The player meets it one piece at a time.
- **Skyrim crime** (UESP) — unverified.
  - Bounties are kept per hold.

## Gossip

- **Ryan, Summerville, Mateas & Wardrip-Fruin, "Toward Characters Who Observe, Tell, Misremember, and Lie"**
  (AIIDE 2015 EXAG workshop) — verified.
  - Link: https://cdn.aaai.org/ojs/12825/12825-52-16341-1-2-20201228.pdf
  - **Beliefs:** a belief carries the evidence behind it and a strength. Evidence decays over time, and being told
    counts for less than seeing.
  - **Who tells whom:** characters who meet swap their most salient beliefs.
  - **Mutation:** details mutate following an authored table.
  - **Lies and belief revision:** lies depend on how a character feels about the listener. A belief is replaced only
    by stronger evidence.
- **Max Kreminski, "Toward Better Gossip Simulation in Emergent Narrative Systems"** (Gossamer; IEEE CoG 2023) —
  verified.
  - Link: https://mkremins.github.io/publications/Gossamer_CoG2023.pdf
  - Gossip runs through four steps: witness, reflect, propagate, decay.
  - A memory whose weight falls below a threshold is dropped.
  - The paper also mentions City of Gangsters, where reputation spreads only to the target's direct contacts.
- **Dwarf Fortress rumours** — known only second-hand, through Ryan et al.
  - Rumours are tied to an event and have a local or regional scope.

## Takeaways for Nightwire

All of these run with no model calls: counters, flags and decay.

- **Places:**
  - each place carries a little state;
  - the narrator is told what changed and why, in one short line;
  - the player sees a mood word.
- **Gossip:**
  - a deed has witnesses;
  - word of it spreads one hop at a time, weakening as it goes, and may get exaggerated;
  - the narrator hedges second-hand news ("they say...");
  - making amends clears it.
