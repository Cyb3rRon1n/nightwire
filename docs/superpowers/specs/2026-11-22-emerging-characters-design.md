# Emerging characters: walk-ons who matter come back

Status: draft for owner review (Nightwire Reviews, batch "Emerging characters"). Roadmap item 5, part 1 (2026-11-22).

## Why

Only the 12 hand-written NPCs are remembered. Across the last eight soaks the narrator named almost no one new. It uses
unnamed walk-ons instead: "the guy who bumps into me", "a vendor", "a Hoshikawa auditor". So the guy Rin punched in
Ikebe Low is gone for good the moment the scene moves on. He has no memory, no voice, and never comes back. A living
city needs the people you hurt, help or cheat to turn up again.

## Prior art (researcher pass, 2026-11-22)

- **Ironsworn: Starforged, "Make a Connection"** (Shawn Tomkin, 2022; Starforged SRD, verified). A relationship forms
  when the player gives focus to someone. The connection gets a role. It matters later because the connection helps
  on moves that fit that role.
- **Mythic Game Master Emulator 2e** (Tana Pigeon, Word Mill Games; partially verified, from fan references rather
  than the book):
  - When a scene ends, any NPC who was active in it is added to the Characters List.
  - An NPC already on the list gets one more entry, up to 3, which makes them likelier to come back.
  - When the list is full, NPCs with 3 entries drop to 2. Irrelevant or dead NPCs are removed.
- **Shadow of Mordor's Nemesis system** (Monolith, 2014; partially verified, from a player forum and not a designer
  source). The grunt who kills the player, or who escapes, gets promoted and named. Later he returns remembering what
  happened ("You burned me and left me for dead!").

All three share one rule: **promote on consequence, not on mention**. Every walk-on gets a name only in tools that
don't care about bloat.

## Goals

**Trigger: one more referee question, no extra model call.** The referee already runs every turn, so one more text
field costs nothing:

> `new_person`: someone without a name that the player dealt with directly this turn (talked to, fought, helped,
> traded with, or was helped or hurt by), written as `<who, 2-6 words>: <what happened, a few words>`. For example:
> `dockworker with a burned hand: Rin helped him lift a crate`. Otherwise leave it empty.

The answer is grounded like `new_lead`: a word of 4 or more letters from "who" must appear in the action or the
narration.

**Naming.** The engine gives the person a name from an owner-approved pool for the current district
(`narrator/worlds/names.toml`), skipping names already in use. The narrator does not invent names.

**The roster** (Mythic's list): `session.people`, capped at 12. Each entry is `{name, who, what, district, turn, weight}`.
- Weight starts at 1 and rises by 1 each later turn the player deals with that person, up to 3.
- **Same person or new?** A new answer is the same person when it is in the same district and shares a word of 4 or more
  letters from "who" with someone on the roster. Then their weight rises instead of a new entry being made.
- **When full,** the person with the lowest weight who was seen longest ago leaves the roster and is journaled as
  "lost touch".

**On promotion:**
- They join the scene's cast, so `Present:` lists them as `Goro (dockworker with a burned hand)`.
- Their "what happened" becomes their first memory, at weight 2 in NPC memory.
- They speak with the voice type their "who" matches (dockworker, vendor, enforcer and so on), if one matches.

**Coming back** (the Nemesis part). The director gets one state-tied event, `needs = ["people"]`:

> `{name}, the {who}, turns up again - they haven't forgotten: {what}.`

It comes with the lead `See what {name} wants`.
- The person is a weighted pick from the roster: this district first, then weight. A person you dealt with three times
  is three times as likely.
- The same person doesn't return within 20 turns.

**Player view.** The Status panel gets a "People" section under Promises: each name, who they are, where you met, and
what happened.

## Non-goals

- Promoting people who are only mentioned or seen.
- Model-written names.
- Gossip between people (item 5, part 3).
- A death or retirement flag for now: the roster cap does that job.

## How we'll know it worked

- Tests:
  - a grounded `new_person` makes one roster entry, with a name from the district pool;
  - an ungrounded one is ignored;
  - the same person seen twice raises their weight and does not duplicate them;
  - a full roster drops the weakest person;
  - the director's comeback event picks by weight;
  - old saves load.
- Soak: the punch at turn 25 ("I punch the guy who bumps into me") should promote one person.

## Left to the builder

Matching the voice type, and the exact Status panel styling.
