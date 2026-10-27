# Nightwire World v2: Kumoi and the NPC Cast, Phase 15

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-27. This extends Phase 14's world bible (`docs/superpowers/specs/2026-10-26-world-bible-design.md`, `narrator/worlds/kuroshio.toml`).

## The actual gap

Phase 14 gave the narrator places and factions, but **no people**.
- Every session the narrator invents throwaway NPCs: a nameless fixer, a generic barkeep.
- Nothing recurs between sessions, and nobody has an agenda that pushes play forward.

The 8-turn Phase 14 probe showed this directly. The model invented "Mama Sato" from the primer's example location and then made her an NPC, because it had nobody else.

The world also had only a street-level view. The people the debt flows *to* are named, but they don't exist as a place or as faces.

The owner's goal for this phase, in their words: the references should help in *"fleshing and creating the world and environment that essentially players are being brought into as well as the NPCs to drive gameplay and immersion."*

## Owner decisions (2026-10-27)

- **Altered Carbon colors only the rich side of the world.** That means the decadent, near-immortal, untouchable elite and the gulf between them and the street.
- **No sleeves, stacks or resleeving.** Cyberpunk stays the foundation: chrome, debt, the street. The elite's long life comes from private life-extension chrome and cloned organs, which is the same chrome economy taken to its extreme.
- **Edgerunners is an influence, not a template.** The cyberware phase (renumbered to Phase 16) drops Edgerunners-specific framing.
- **Order:** this phase (world v2 plus the NPC cast) comes first. The cyberware, humanity and debt spec (`2026-10-27-cyberware-humanity-design.md`) is revised and built afterwards as Phase 16.
- The rich-side layer and the NPC cast were approved as presented.

## Research grounding

**Altered Carbon (Richard K. Morgan's 2002 novel and the 2018 Netflix series), general knowledge.** The "Meths" are centuries-old elites who live in towers above the clouds, Aerium in the series. They are bored, decadent and above the law, and they treat lower-city lives as entertainment and collections. This phase takes **only** that class layer: the vertical gulf, the decadence, and the patriarch-and-heir dynamic of Laurens and Miriam Bancroft and their children. It leaves out the stack and sleeve technology, per the owner's decision.

**NPC cards.**
- Phase 14's research found that SillyTavern World Info and AI Dungeon Story Cards inject character entries by keyword the same way as place entries ([SillyTavern World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/), [AI Dungeon Story Cards](https://latitudegames.notion.site/What-are-Story-Cards-12227c6d39214d7b850b828dd6ef3c4e)).
- Blades in the Dark's faction and NPC structure is: who they are, what they want, how they act.
- This phase adds a **secret** and a **voice** to each card. A secret gives the narrator something to reveal, and a voice keeps the NPC consistent across sessions.

**Recurring NPCs as the engine of play.** In Cyberpunk 2077 and RED, fixers are the recurring faces that hand out gigs. In Blades in the Dark, factions and their people generate the jobs. The cast includes a fixer, Jun Arakawa, as the default source of paid work. That also gives Phase 16's debt loop a ready place to work off installments.

**Living alongside Phase 13.** Phase 13's NPC memory (`remember_npc`) records what happened with *this* crew. World NPC cards define *who the person is*. Both can be in context at once, and they don't duplicate each other: one is identity, the other is history.

## Mechanism (small code change)

**A new `[[npc]]` entry kind** in the world TOML:
- `name`, `aliases` and `card` follow the same rules as districts and factions: a card is at most 400 characters, and names and aliases are unique after normalization across **all** entries.
- An optional `home` must be the name of an existing district, or loading fails.

`World` gains `npcs: tuple[WorldEntry, ...]`. `WorldEntry` gains `home: str | None = None`.

**Changes to `select_cards`:**
1. **Priority 1 is unchanged:** the district matched by `session.location`.
2. **Priority 2:** mentions in the action and recent narration now scan districts, factions **and NPCs**, most recent first.
3. **Priority 3 (new): one resident NPC.** If the location matched a district and there is room, add the first NPC (in file order) whose `home` is that district and who isn't already selected. This puts someone on stage even when nobody was named. It is deterministic. Ceiling: the first resident in file order always wins the slot when nobody is named. Upgrade path: rotate residents or pick the least recently shown.
4. **The 4-card cap and the character budget are unchanged.** 4 × 400 characters fits the existing `_WORLD_BUDGET_FRACTION = 0.06`, which is about 1,966 characters at `num_ctx=8192`.

**Primer.** One sentence is added for Kumoi and the Houses, and Kumoi joins the district list. This takes the primer plus glossary from about 1,536 to about 1,750 characters, so **`_MAX_SYSTEM_BLOCK_CHARS` rises from 1,600 to 1,900** (about +75 tokens).

**Naming.** "Mama Sato" becomes canonical, since the narrator already invented her. The primer's example location ("Ikebe Low - Mama Sato's izakaya") now points at a real NPC.

**Alias safety.** Ordinary words are left out as aliases ("Ledger", "Static"); they appear only inside cards. Earlier cards and the tier text use phrases like "debt ledgers" and "Yomi static", and those words would otherwise trigger NPC cards.

No changes to tools, Session fields, the frontend or persistence.

## World content

### Primer addition

Appended to the primer:

> Above the cloud line floats Kumoi, where the five founding families of the Kumoi Houses have lived for a century and more on private life-extension; every installment the street pays funds their forever.

`Kumoi` is also added to the primer's district list.

### New entries

**Kumoi** (District): aliases `the sky estates`
> Kumoi is the sky estates above the cloud line, reached only by private aircar: silent moss gardens, real rain filtered through glass, servants who never look up, ancient tea rooms. From the street it is only a field of underside lights. Held by the Kumoi Houses. Hazard: a guest who refuses a gift is never invited back, or never leaves. Hook: an heir wants a street crew for a private game.

**Kumoi Houses** (Faction): aliases `the Houses`
> The Kumoi Houses are the five keiretsu founding families, kept alive 150 years and more by private life-extension chrome and cloned organs. Wants: to stay forever, and to not be bored. Method: patronage, proxies, poetry and old court etiquette; they collect interesting people like art. Narrate them as unhurried, exquisitely polite and utterly untouchable: lower-city lives are their entertainment.

**Mama Sato** (NPC): aliases `Sato`; home `Ikebe Low`
> Mama Sato runs the lantern-lit izakaya in Ikebe Low and hears everything said over her counter. Wants: to keep Ikebe neutral ground. Secret: she pays protection to both the Kuze-gumi and Kaminari Run. Voice: warm, scolding, calls everyone 'child', feeds you before she answers. Trades rumors for favors, never for money.

**Old Hara** (NPC): aliases `Hara`; home `Ikebe Low`
> Old Hara is an off-the-books chrome-ya behind a noren curtain in Ikebe Low: no payment plan, no repo, cash or favors only. Wants: to undo the harm he has done. Secret: decades ago he designed Hoshikawa's remote-throttle killswitch. Voice: tired, gentle, precise, hands that never shake. Can quietly unlock throttled chrome, at a price.

**Jun Arakawa** (NPC): aliases `Arakawa`; home `Hanabira-chō`
> Jun 'Ledger' Arakawa is a fixer working out of a Hanabira-chō karaoke box, handing out gigs to crews who need the money. Wants: to clear his own debt to the Kuze-gumi. Secret: he sells crews' movements to Hoshikawa. Voice: fast, friendly, always counting; every favor goes in his ledger. The usual source of paid work.

**Saeko Kirigaya** (NPC): aliases `Kirigaya`, `Saeko`; no home (never auto-selected as a resident)
> Saeko Kirigaya leads a torite repo crew on Kuze-gumi contract, working anywhere in the city. Wants: to make quota. Secret: her own chrome is on a throttle lock she cannot pay off. Voice: polite, unhurried, apologetic while her crew takes your arm. Can be bargained with if it helps her quota.

**Hoshikawa Tadamori** (NPC): aliases `Tadamori`; home `Kumoi`
> Hoshikawa Tadamori is the 163-year-old patriarch of House Hoshikawa in Kumoi. Wants: to be surprised, once more. Secret: he has not left his estate in forty years and rules the city through proxies. Voice: amused, archaic, speaks in poetry, treats threats as charming. Hires street crews for his own private tests.

**Hoshikawa Rei** (NPC): aliases `Rei`; home `Kumoi`
> Hoshikawa Rei is the heir of House Hoshikawa, sixty years old in a twenty-year-old face, who goes slumming in Hanabira-chō for thrills. Wants: something that feels real. Secret: she wants her father, Tadamori, dead. Voice: bored, curious, cruel when amused, generous on a whim. Pays crews absurdly well for strange jobs.

**Brother Tōru** (NPC): aliases `Toru`; home `Yomi Line`
> Brother Tōru is a Lantern Guild keeper who tends the dead along the sealed Yomi Line. Wants: to keep the dead at peace. Secret: the dead in Yomi keep asking for him by name, and he does not know why. Voice: soft, slow, kind, never surprised. Knows what the dead remember, and trades it for favors.

**Kenji Moro** (NPC): aliases `Moro`, `Kenji`; home `The Loop`
> Kenji 'Static' Moro, nineteen, leads Kaminari Run on the Loop. Wants: to wipe the gang's chrome debt in one big score. Secret: his own chrome is already throttled, and he races on borrowed reflexes. Voice: loud, quick, grinning, all bravado until it cracks. Always recruiting for something reckless.

**Captain Ide** (NPC): aliases `Ide`; home `Kuroshio Docks`
> Captain Ide runs the Ōgane Heavy precinct at Kuroshio Docks. Wants: promotion to Kumoi security. Secret: his invoices quietly fund a private army loyal only to him. Voice: courteous, bureaucratic, every threat phrased as a fee. Looks the other way for a price, and always sends the bill.

**Mitsu** (NPC): aliases none; home `Hanabira-chō`
> Mitsu is a rising stream idol whose face covers every wall in Hanabira-chō. Wants: to stay famous. Secret: the chrome that makes her voice perfect was never paid for, and the torite are circling. Voice: bright and practiced on stream, frightened and sharp off it. Desperate enough to hire anyone who can make the debt disappear.

## Testing

**Unit tests:**
- The shipped world loads with 7 districts, 7 factions and 10 NPCs.
- `[[npc]]` with an unknown `home` fails to load.
- NPC names and aliases collide with district and faction names under the uniqueness check.
- The 1,900-character system-block limit holds.

**`select_cards`:**
- An NPC is matched by mention, including through an alias.
- With location Ikebe Low and nobody named, the result is the Ikebe Low card plus Mama Sato (the resident).
- A resident NPC is not added twice when it was also mentioned.
- The resident is skipped when the cap or the budget is full.
- No resident is picked when there is no location match.
- NPCs without a `home` are never picked as residents.

**Live verification** on real `qwen3:8b`, using the Phase 14 probe pattern against a Phase 14 baseline:
- Does the narrator **use the resident NPC by name** and in their voice?
- Do the NPCs' wants and secrets surface as story pressure (offering gigs, hinting at secrets) without being recited?
- Over about 8 turns, does a Kumoi or Rei scene read as the decadent rich side, distinct from the street?

Record:
- recitation, using the same 12-gram check;
- invented throwaway NPCs versus cast use;
- prompt size;
- schema and tool errors;
- n.

## Not in this phase

- Cyberware, humanity and debt (Phase 16).
- NPC relationship or reputation tracking (Phase 13 memory covers history).
- NPC schedules or movement.
- Engine-generated gigs from NPCs (a natural follow-up once the debt loop exists).
- A UI for browsing the cast.
- Rotation among resident NPCs.
