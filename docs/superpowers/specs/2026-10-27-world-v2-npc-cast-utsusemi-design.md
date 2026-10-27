# Nightwire World v2: The NPC Cast and Utsusemi, Phase 15

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-27. This extends Phase 14's world bible (`docs/superpowers/specs/2026-10-26-world-bible-design.md`, `narrator/worlds/kuroshio.toml`).

## The actual gap

Phase 14 gave the narrator places and factions, but **no people**.
- Every session the narrator invents throwaway NPCs: a nameless fixer, a generic barkeep.
- Nothing recurs between sessions, and nobody has an agenda that pushes play forward.

The 8-turn Phase 14 probe showed this directly. The model invented "Mama Sato" from the primer's example location and then made her an NPC, because it had nobody else.

The owner's goal for this phase, in their words: the references should help in *"fleshing and creating the world and environment that essentially players are being brought into as well as the NPCs to drive gameplay and immersion."*

## Owner decisions (2026-10-27)

**Keep the original world.** The Edgerunners-and-2077-style street world from Phase 14 stays the foundation. Edgerunners is an influence, not a template.

**An Altered Carbon pass was considered, then mostly rolled back.** The rejected parts:
- a sky district ("Kumoi") for 150-year-old elites;
- sleeves for the rich.

What remains is a toned-down elite: **ordinary cyberpunk corporate royalty** (the Hoshikawa family) on the penthouse floors of Tenjō Heights. They have no extended lifespans.

**Sleeves exist, but for AIs: *utsusemi*** (空蝉, "cicada shell", the Buddhist image of the empty, transient body).
- Synthetic bodies that AIs, chiefly woken tsukumogami, rent to walk the street.
- They are leased by Hoshikawa on the same payment plans as human chrome, so the torite repossess shells too.
- This mirrors the core theme instead of replacing it. Chrome asks how much machine before a person stops being human. Utsusemi ask how much body before a machine starts being someone.

**Order.** This phase comes first. The cyberware, humanity and debt spec (`2026-10-27-cyberware-humanity-design.md`) is revised and built afterwards as Phase 16.

## Research grounding

**NPC cards.**
- Phase 14's research found that SillyTavern World Info and AI Dungeon Story Cards inject character entries by keyword the same way as place entries ([SillyTavern World Info](https://docs.sillytavern.app/usage/core-concepts/worldinfo/), [AI Dungeon Story Cards](https://latitudegames.notion.site/What-are-Story-Cards-12227c6d39214d7b850b828dd6ef3c4e)).
- Blades in the Dark's faction and NPC structure is: who they are, what they want, how they act.
- This phase adds a **secret** and a **voice** to each card. A secret gives the narrator something to reveal, and a voice keeps the NPC consistent across sessions.

**Recurring NPCs as the engine of play.** In Cyberpunk 2077 and RED, fixers are the recurring faces that hand out gigs. In Blades in the Dark, factions and their people generate the jobs. The cast includes a fixer, Jun Arakawa, as the default source of paid work. That also gives Phase 16's debt loop a ready place to work off installments.

**AI bodies.** Ghost in the Shell is already a Phase 14 touchstone: its "shell" is the body a ghost inhabits, and AIs and cyborgs move between them. Ghostwire: Tokyo, also a Phase 14 touchstone, layers folklore into modern machines. Utsusemi combine the two, following tsukumogami folklore (objects that gain a spirit after long use) into a rented body. (General knowledge, not freshly sourced.)

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
   **Amended 2026-10-27 (fix `3a7bab1`):** the resident now ranks directly after the location district, ahead of other mentions, instead of after them. Reason: a live probe showed stale faction mentions filled the 4-card cap in Hanabira-chō and at the Docks, so the resident was dropped and the narrator invented unnamed NPCs. The resident is still skipped when a local NPC is already mentioned, and the budget can still drop it.
4. **The 4-card cap and the character budget are unchanged.** 4 × 400 characters fits the existing `_WORLD_BUDGET_FRACTION = 0.06`, which is about 1,966 characters at `num_ctx=8192`.

**Primer and glossary.**
- Two sentences are appended to the primer (below), and `utsusemi` joins the glossary.
- The primer plus glossary grows from about 1,536 to about 1,800 characters, so **`_MAX_SYSTEM_BLOCK_CHARS` rises from 1,600 to 1,900** (about +65 tokens).

**Naming.** "Mama Sato" becomes canonical, since the narrator already invented her. The primer's example location ("Ikebe Low - Mama Sato's izakaya") now points at a real NPC.

**Alias safety.** Ordinary words are left out as aliases ("Ledger", "Static"); they appear only inside cards. Earlier cards and the tier text use phrases like "debt ledgers" and "Yomi static", and those words would otherwise trigger NPC cards.

No changes to tools, Session fields, the frontend or persistence.

## World content

### Primer addition

Appended to the primer:

> Atop Tenjō Heights the keiretsu families live as corporate royalty. Some woken machines rent utsusemi, synthetic shells leased on the same payment plans, and the torite repossess those too.

### Glossary addition

| Term | Definition |
|---|---|
| utsusemi | a rented synthetic body that an AI wears to walk the street |

### Changed and new entries

**Tsukumogami** (Faction, **replaces** the Phase 14 card): aliases `rogue AI`, `rogue AIs`
> Tsukumogami are old machines that ran too long and woke: vending machines, ticket gates, trains. The lucky ones rent utsusemi shells from Hoshikawa and walk the street, owing installments like anyone. Each wants something strange and specific: to be thanked, to finish a last route, to keep its shell. Narrate them as uncanny: chimes that sound wrong, screens that answer back, shells too still.

**Mama Sato** (NPC): aliases `Sato`; home `Ikebe Low`
> Mama Sato runs the lantern-lit izakaya in Ikebe Low and hears everything said over her counter. Wants: to keep Ikebe neutral ground. Secret: she pays protection to both the Kuze-gumi and Kaminari Run. Voice: warm, scolding, calls everyone 'child', feeds you before she answers. Trades rumors for favors, never for money.

**Old Hara** (NPC): aliases `Hara`; home `Ikebe Low`
> Old Hara is an off-the-books chrome-ya behind a noren curtain in Ikebe Low: no payment plan, no repo, cash or favors only. Wants: to undo the harm he has done. Secret: decades ago he designed Hoshikawa's remote-throttle killswitch. Voice: tired, gentle, precise, hands that never shake. Can quietly unlock throttled chrome, at a price.

**Jun Arakawa** (NPC): aliases `Arakawa`; home `Hanabira-chō`
> Jun 'Ledger' Arakawa is a fixer working out of a Hanabira-chō karaoke box, handing out gigs to crews who need the money. Wants: to clear his own debt to the Kuze-gumi. Secret: he sells crews' movements to Hoshikawa. Voice: fast, friendly, always counting; every favor goes in his ledger. The usual source of paid work.

**Saeko Kirigaya** (NPC): aliases `Kirigaya`, `Saeko`; no home (never auto-selected as a resident)
> Saeko Kirigaya leads a torite repo crew on Kuze-gumi contract, working anywhere in the city. Wants: to make quota. Secret: her own chrome is on a throttle lock she cannot pay off. Voice: polite, unhurried, apologetic while her crew takes your arm. Can be bargained with if it helps her quota.

**Hoshikawa Tadamori** (NPC): aliases `Tadamori`; home `Tenjō Heights`
> Hoshikawa Tadamori is the patriarch of the Hoshikawa Keiretsu, living in the penthouse floors of Tenjō Heights. Wants: a legacy no one can repossess. Secret: he has not left his tower in years and rules through proxies and audits. Voice: soft, formal, unhurried; treats threats as poor manners. Hires street crews for jobs his own security cannot be seen doing.

**Hoshikawa Rei** (NPC): aliases `Rei`; home `Tenjō Heights`
> Hoshikawa Rei is the twenty-four-year-old heir of the Hoshikawa Keiretsu, who goes slumming in Hanabira-chō for thrills. Wants: something that feels real. Secret: she wants her father, Tadamori, out of the way. Voice: bored, curious, cruel when amused, generous on a whim. Pays crews absurdly well for strange jobs.

**Brother Tōru** (NPC): aliases `Toru`; home `Yomi Line`
> Brother Tōru is a Lantern Guild keeper who tends the dead along the sealed Yomi Line. Wants: to keep the dead at peace. Secret: the dead in Yomi keep asking for him by name, and he does not know why. Voice: soft, slow, kind, never surprised. Knows what the dead remember, and trades it for favors.

**Kenji Moro** (NPC): aliases `Moro`, `Kenji`; home `The Loop`
> Kenji 'Static' Moro, nineteen, leads Kaminari Run on the Loop. Wants: to wipe the gang's chrome debt in one big score. Secret: his own chrome is already throttled, and he races on borrowed reflexes. Voice: loud, quick, grinning, all bravado until it cracks. Always recruiting for something reckless.

**Captain Ide** (NPC): aliases `Ide`; home `Kuroshio Docks`
> Captain Ide runs the Ōgane Heavy precinct at Kuroshio Docks. Wants: promotion to Tenjō Heights security. Secret: his invoices quietly fund a private army loyal only to him. Voice: courteous, bureaucratic, every threat phrased as a fee. Looks the other way for a price, and always sends the bill.

**Mitsu** (NPC): aliases none; home `Hanabira-chō`
> Mitsu is a rising stream idol whose face covers every wall in Hanabira-chō. Wants: to stay famous. Secret: the chrome that makes her voice perfect was never paid for, and the torite are circling. Voice: bright and practiced on stream, frightened and sharp off it. Desperate enough to hire anyone who can make the debt disappear.

**Hachi** (NPC): aliases none; home `Kuroshio Docks`
> Hachi was the announcer AI on the Yomi Line before it was sealed, and now wears a cheap rented utsusemi shell, running courier jobs from Kuroshio Docks, two installments behind. Wants: to see the sea from the pier, every day. Secret: it still hears the line's lost passengers. Voice: cheerful station-announcement cadence, perfectly polite, occasionally announces stops that no longer exist.

## Testing

**Unit tests:**
- The shipped world loads with 6 districts, 6 factions and 11 NPCs.
- `[[npc]]` with an unknown `home` fails to load.
- NPC names and aliases collide with district and faction names under the uniqueness check.
- The 1,900-character system-block limit holds.
- The system block contains `utsusemi`.

**`select_cards`:**
- An NPC is matched by mention, including through an alias.
- With location Ikebe Low and nobody named, the result is the Ikebe Low card plus Mama Sato (the resident).
- A resident NPC is not added twice when it was also mentioned.
- The resident outranks other mentions when the cap is full, and is still dropped when the budget is full.
- No resident is picked when there is no location match.
- NPCs without a `home` are never picked as residents.

**Live verification** on real `qwen3:8b`, using the Phase 14 probe pattern against a Phase 14 baseline:
- Does the narrator **use the resident NPC by name** and in their voice?
- Do the NPCs' wants and secrets surface as story pressure (offering gigs, hinting at secrets) without being recited?
- Does an utsusemi or tsukumogami NPC (Hachi at the Docks) read as uncanny but personal?
- Does a Hoshikawa family scene read as corporate royalty, distinct from the street?

Record:
- recitation, using the same 12-gram check;
- invented throwaway NPCs versus cast use;
- prompt size;
- schema and tool errors;
- n.

## Not in this phase

- Cyberware, humanity and debt (Phase 16). Utsusemi as a *mechanic* (an AI player character, shell slots, shell repossession) also belongs there or later; here utsusemi are world content only.
- NPC relationship or reputation tracking (Phase 13 memory covers history).
- NPC schedules or movement.
- Engine-generated gigs from NPCs (a natural follow-up once the debt loop exists).
- A UI for browsing the cast.
- Rotation among resident NPCs.
