# Nightwire World Bible Design: Phase 14 (Kuroshio)

Status: designed, not yet implemented. Brainstormed with the owner on 2026-10-26.

## The actual gap

The narrator has no setting at all. Its entire world is one clause in `server/__main__.py`'s system prompt, `"You are a cyberpunk tabletop game master."`. So every session improvises a generic city from scratch: no district persists, no faction comes back, and nothing adds the Japanese-cyberpunk flavor the owner wants. Separately, `Session.location`, `scene_mood` and `active_objectives` are written by `update_world` but never read back into the prompt (`server/narration.py`'s `_build_messages`). That is part of the long-standing "narrator narrates blind to engine state" gap.

## Owner decisions (2026-10-26)

- **One original Japanese megacity.** It must not use trademarked IP: no Night City and no Arasaka, since the repo is public.
- **Tone:** Edgerunners tragedy mixed with Cyberpunk 2077 neon action. Fun, stylish gigs and fights, but chrome is a debt that comes due.
- **Japanese layer:** keiretsu and yakuza, shrines and a yokai-haunted net, and street and youth culture. The disaster-built city was not chosen.
- **Scope:** the world bible plus how it gets into the prompt. Cyberware and a humanity track are the next phase, designed against this world. Faction clocks and engine-rolled tables are later candidates.
- **Immersion over guardrails.** The narration rules cover tone and glossary use only. There are no explicit "don't do X cliché" lines in the prompt.

## Research grounding

A research pass on 2026-10-26 (researcher subagent) covered three things:

**Lore injection for small context windows.**
- SillyTavern World Info ([docs](https://docs.sillytavern.app/usage/core-concepts/worldinfo/)):
  - keyword-triggered entries, whole-word and case-insensitive by default;
  - a token budget;
  - insertion near the end of the prompt has the most influence;
  - entries must be standalone, because titles and keys are not sent to the model.
- AI Dungeon ([context](https://latitudegames.notion.site/How-do-I-manage-my-Context-302105b8a63280dca963e53200a40a2b), [Story Cards](https://latitudegames.notion.site/What-are-Story-Cards-12227c6d39214d7b850b828dd6ef3c4e)) uses always-on Plot Essentials plus trigger-only Story Cards.
- No published source gives authoritative entry-size or entry-count numbers. The sizes below (a primer of about 250–400 tokens, cards of 50–80 tokens, at most 4 active) are heuristics for an 8B model. Live verification checks them.

**Tabletop structure.**
- Blades in the Dark-style faction cards (want, method, rivals) give the most usable structure per token.
- The Sprawl creates corporations at setup with a public-facing area of expertise ([actual play](https://pbta.gplusarchive.online/?p=58962)). Its corp clocks are deferred to a later phase.

**Touchstones.**
- Cyberpunk: Edgerunners: found family, and chrome as a cost.
- Cyberpunk 2077 and RED: single-identity districts, and the fixer → gig → district → consequence loop.
- Ghost in the Shell: the net as a quasi-spiritual space.
- Ghostwire: Tokyo: folklore leaking through modern infrastructure.
- Akira: bōsōzoku street culture.
- The research also surfaced the techno-orientalism critiques ([Median](https://iopn.library.illinois.edu/journals/median/article/download/877/769/3095), [Sabukaru](https://sabukaru.online/articles/techno-orientalism-decoding-japans-misrepresentation-as-a-cyberpunk-utopia)). The world below addresses them through its content: Japanese culture is structural (debt and obligation, a union for the dead, tsukumogami folklore), not set dressing. The owner chose not to put rules about this in the prompt.
- Caveat: the touchstone details for Edgerunners, Shadowrun, Ghostwire and Blades come from general knowledge, not verified sources.

## Architecture: approach B, primer plus triggered cards

Three approaches were considered:
- **A. The whole bible always on.** About 1,500 tokens or more every turn, and small models recite lore they see constantly.
- **B. A primer plus triggered cards.** Chosen.
- **C. A `recall_lore` tool.** It needs a multi-round tool loop, which Phase 13 already rejected for `recall_npc`, and small models are unreliable at deciding when to look things up. Rejected.

### Storage: `world/kuroshio.toml`

The file is TOML, which Python reads with the standard library's `tomllib`, so there is no new dependency. Shape:

```toml
primer = """..."""                 # always on
[glossary]
chrome-ya = "..."                  # term = short definition
[[district]]
name = "Ikebe Low"
aliases = ["Ikebe", "the Low"]
card = """..."""                   # standalone, no pronouns referring to other cards
[[faction]]
name = "Kuze-gumi"
aliases = ["Kuze"]
card = """..."""
```

### Loader: `narrator/world.py`

The loader:
- loads the file once at startup;
- returns a frozen `World` dataclass (`primer`, `glossary`, `districts`, `factions`);
- validates the content, and fails startup with a clear message on any of the conditions below.

Validation fails when:
- a required field is missing;
- a name or alias is duplicated across all entries (after normalization);
- a card is over 400 characters;
- the primer plus the rendered glossary is over 1,600 characters.

Two functions:
- `World.system_block() -> str` returns the primer followed by the glossary as `term: definition` lines. It is appended to the existing system prompt in `server/__main__.py`.
- `select_cards(world, session, action_text, budget_chars) -> list[str]`:
  - **Normalization.** Text is lowercased and diacritics are stripped (`unicodedata` NFKD), so "Tenjō" matches "Tenjo". Matching is whole-word (a `\b` regex on the escaped alias), so "Loop" does not match "loophole".
  - **Priority 1.** The district whose name or alias appears in `session.location`.
  - **Priority 2.** Districts and factions mentioned in `action_text` or in the last 6 non-bracket narrative lines, most recent mention first.
  - **Limits.** Each card is included at most once. At most 4 cards. Selection stops when the next card would exceed `budget_chars`.
  - **No match** returns an empty list.

The world file path is a module constant (`world/kuroshio.toml`). There is no environment variable, because only one world exists. A `WORLD_FILE` setting can be added if a second world ever does.

### Prompt assembly (`server/narration.py`)

`_build_messages` keeps its current order and adds two blocks immediately before `Player action:`, where content has the most influence:

```
Party (use these exact player_ids): ...
Summary of earlier events: ...
Known NPCs: ...
Recent events: ...

Scene: Ikebe Low - Mama Sato's izakaya · mood: tense · objectives: find the chrome-ya; pay off the torite
World notes:
<card>
<card>

Player action: ...
```

- **Scene line.** Each part is left out when it is empty, and the whole line is left out when all three are empty.
- **World notes block.** Left out when `select_cards` returns nothing.

**Budget.** `_WORLD_BUDGET_FRACTION = 0.06` of `num_ctx` in estimated tokens, which is about 490 tokens at 8192. It is converted to characters with the existing `_CHARS_PER_TOKEN_ESTIMATE`, the same pattern as `_NPC_MEMORY_BUDGET_FRACTION`.

To keep generation headroom about where it is today, **`_VERBATIM_BUDGET_FRACTION` drops from 0.65 to 0.55**. Estimated per-turn input at `num_ctx=8192`:

| | Tokens |
|---|---|
| Today: system prompt (~660) + verbatim (~5,325) + NPCs (~410) + action (≤250) | ~6,650 |
| After: system prompt + primer (~1,060) + verbatim (~4,500) + NPCs (~410) + world (~490) + scene and action (~310) | ~6,770 |

That leaves about 1,400 tokens of generation headroom, against about 1,550 today. Phase 11's compaction absorbs the smaller verbatim window, since more history moves into the summary sooner. All of these are starting values. Live verification measures the real prompt size.

### Narrator guidance

The primer tells the narrator to set `update_world.location` to a district name, optionally followed by the specific spot (for example `"Ikebe Low - Mama Sato's izakaya"`). Location matching depends on this, and it also keeps locations consistent across turns. No tool schema changes.

### Not in this phase

- Cyberware and a humanity or cyberpsychosis track (the next phase).
- Faction clocks and engine-rolled job, rumor and complication tables.
- NPC cards (Phase 13's NPC memory already covers named NPCs).
- A world-picker UI.
- Multiple worlds.
- Any change to tools or session fields.

## World content (initial `world/kuroshio.toml`)

### Primer

> Setting: Kuroshio, a Pacific megacity in Japan, 2089, named for the black ocean current that feeds its port. Five keiretsu houses built the city and financed the chrome that keeps its people working. Nearly everyone's chrome is on a payment plan, and torite repo crews take back what you can't pay for. Giri binds the city: favors are currency and everyone owes someone. The deep net, Yomi, holds the lingering data of the dead, tended by the Lantern Guild. Old machines that run too long sometimes wake as tsukumogami. Districts: Tenjō Heights, Hanabira-chō, Ikebe Low, Kuroshio Docks, The Loop, Yomi Line. When the party moves, set update_world location to a district name, then the specific spot (e.g. "Ikebe Low - Mama Sato's izakaya"). Tone: stylish, fast and darkly funny like a neon action film, but every piece of chrome costs something and the city always collects. Ground every scene in concrete sensory detail: rain, food, signage, engine noise, crowds, machine hum. Use Japanese words only from the glossary, naturally, without explaining them.

### Glossary

| Term | Definition |
|---|---|
| chrome | cyberware, any implant or cybernetic part |
| chrome-ya | a back-alley cyberware clinic, or the doctor who runs one |
| torite | a repo crew that reclaims unpaid chrome, by force if needed |
| giri | obligation; a debt of favor you owe someone |
| keiretsu | one of the five corporate houses that run the city |
| oyabun | the boss of a yakuza clan |
| Yomi | the deep net, where the data of the dead lingers |
| going to the lantern | dying |
| tsukumogami | an old machine that woke up as a rogue AI |

### Districts

**Tenjō Heights**: aliases `Tenjo`, `the Heights`
> Tenjō Heights is the keiretsu high city: towers linked by sky bridges above the smog line, filtered air sold by the breath, silent maglev pods, staff who smile on contract. Held by Hoshikawa Keiretsu and Ōgane Heavy security; outsiders need a sponsor badge. Hazard: every camera feeds Ōgane, and trespass is billed. Hook: a junior Hoshikawa auditor wants to sell the debt ledgers.

**Hanabira-chō**: aliases `Hanabira`
> Hanabira-chō is the pleasure district: idol streams on every wall, host clubs, the roar of pachinko halls, capsule love hotels, yakitori smoke. Held by the Kuze-gumi, who collect from every door. Hazard: debts run up here are sold to Hoshikawa by morning. Hook: a rising stream idol is hiding chrome she never paid for, and the torite are circling.

**Ikebe Low**: aliases `Ikebe`, `the Low`
> Ikebe Low is old wooden-era alleys under the expressway: lantern-lit izakaya, family chrome-ya clinics behind noren curtains, alley shrines strung with prayer-cable. Nobody holds it; the Kuze-gumi, Kaminari Run and Hoshikawa repo men all work its streets. Hazard: power cuts drop whole blocks into darkness. Hook: an old chrome-ya installs chrome off the books, with no payment plan and no repo.

**Kuroshio Docks**: aliases `the Docks`, `the port`
> Kuroshio Docks is container canyons and gantry cranes, black water slapping the piers, rusting ships turned into offshore data havens. Ōgane Heavy guards it on paper; smugglers pay the right shift. Hazard: automated cranes do not stop for people. Hook: a container arrived with no manifest, and something inside is still running.

**The Loop**: aliases `Loop`
> The Loop is the elevated ring expressway around the city, with arcade towers glowing at every off-ramp. Every night Kaminari Run bikes race it, light-trails bending through the rain. Kaminari Run holds it after dark; Ōgane traffic drones hold it by day. Hazard: speed duels settle disputes here, and the loser forfeits their ride. Hook: someone is racing the Loop on a bike with no rider.

**Yomi Line**: aliases `the sealed line`, `the dead line`
> The Yomi Line is a subway line sealed after an AI incident twenty years ago. Station signs still announce trains that never come, and the net is so thick that the dead speak through the platform speakers. Tsukumogami nest in the ticket machines and the dead trains. Hazard: stay too long and Yomi seeps into your chrome. Hook: the Lantern Guild wants something carried out of the deepest station.

### Factions

**Hoshikawa Keiretsu**: aliases `Hoshikawa`
> Hoshikawa Keiretsu financed the city's chrome and owns its debt. Wants: everyone on a payment plan, forever. Method: polite, patient and total, through contract law, credit scores and torite crews hired through the Kuze-gumi. Rival of Ōgane Heavy for control of Tenjō Heights. Narrate them with soft voices, perfect manners and the quiet threat of a balance due.

**Ōgane Heavy**: aliases `Ogane`
> Ōgane Heavy is an arms maker and the city's contracted police. Wants: order it can bill for. Method: drones, checkpoints, armored response teams and a fine for everything. Allied with Hoshikawa in public, competing with it in private. Narrate them as heavy boots, visor glare and an invoice after every arrest.

**Kuze-gumi**: aliases `Kuze`
> The Kuze-gumi is an old yakuza clan gone half-corporate; its oyabun sits on a Hoshikawa subsidiary board. Wants: to stay relevant as the city goes corporate. Method: protection rackets in Hanabira-chō and repo contracts for Hoshikawa. Its old members resent the suits. Narrate them through tradition worn thin: formal greetings, tattoos under business suits, very old grudges.

**Kaminari Run**: aliases `Kaminari`
> Kaminari Run is a bōsōzoku biker gang that rules the Loop at night. Wants: speed, and freedom from chrome debt; they ride on unpaid chrome and fight the torite. Method: races, swarm raids and loyalty to the crew above all. Enemies of the Kuze-gumi repo crews. Narrate them loud, young and flamboyant: painted jackets, engine roar, bravado hiding fear.

**Lantern Guild**: aliases `lantern-keepers`, `lantern-keeper`, `Yomi`
> The Lantern Guild is the licensed union that tends the dead in Yomi, the deep net. Wants: the dead left in peace, and the Guild left alone. Method: they hear what the dead remember and trade those secrets for favors, never money. Neutral, and every faction needs them sooner or later. Narrate them calm and soft-spoken, with paper lanterns and unhurried certainty.

**Tsukumogami**: aliases `rogue AI`, `rogue AIs`
> Tsukumogami are old machines that ran too long and woke: vending machines, ticket gates, train AIs, traffic systems. Each wants something strange and specific: to be thanked, to finish a last route, to be left running. They can be bargained with, tricked or fled. Narrate them as uncanny: chimes that sound wrong, screens that answer back, machines that move when no one is looking.

(The alias `Yomi` belongs to the Lantern Guild only. "Yomi Line" mentions also match it, which is intended: the two are related. The Yomi Line district does not alias plain "Yomi". Name and alias uniqueness is checked after normalization (lowercase, diacritics stripped), so an alias must never just be a re-spelling of a name: "Ōgane" already matches "Ogane" text.)

## Testing

**Unit tests** (pytest, alongside the existing suite):

`narrator/world.py`:
- The shipped `world/kuroshio.toml` loads.
- These each fail with a clear error:
  - a missing `card`;
  - an over-length card;
  - a duplicate alias across two entries;
  - an over-length primer plus glossary.
- `system_block()` contains the primer and every glossary term.

`select_cards`:
- A location match comes first, even when other entries are mentioned more recently.
- Diacritic-insensitive: "Tenjo" matches Tenjō Heights.
- Whole-word: "loophole" does not match The Loop.
- Aliases match.
- Caps: at most 4 cards, and the budget is respected (a tiny budget returns fewer cards).
- No match returns `[]`.
- Bracket lines are ignored.

`_build_messages`:
- The Scene and World notes blocks sit between the other context and `Player action:`.
- The Scene line drops empty parts, and is left out entirely when location, mood and objectives are all empty.
- World notes is left out when there are no cards.
- Existing exact-format assertions are updated.

`build_app`:
- The system prompt contains the primer.

**Live verification** against the real `qwen3:8b` narrator (Ollama, `num_ctx=8192`), following the precedent of Phases 11 and 13. A mocked suite passing is necessary but not sufficient.

Run a probe session of 6 to 8 turns that moves between districts:
1. Start in Ikebe Low.
2. Hire on with a chrome-ya.
3. Ride The Loop.
4. Go to Hanabira-chō to deal with the Kuze-gumi.

Record:
- whether `update_world.location` gets set using district names;
- which cards fired on each turn;
- whether glossary terms are used naturally, versus explained or overused;
- any lore recitation (card text copied word for word, or near-word-for-word spans of more than about 12 words);
- the real prompt character count before and after;
- the tool-call and schema-error rate compared with recent phases.

Report the sample size honestly, and treat small-sample results as indicative only. If recitation shows up, shorten the cards or the primer rather than adding prompt rules.

## Docs

- A `ROADMAP.md` Phase 14 entry, written once it is built and verified.
- A short "World" section in the README explaining how to edit `world/kuroshio.toml`: add districts or factions, keep cards standalone and under 400 characters, and note that aliases must be unique.
