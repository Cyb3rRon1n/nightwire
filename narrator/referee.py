"""Phase 18 referee: a small required-field yes/no pass after narration that
decides the state changes qwen3:8b never volunteered as optional tool fields.
See docs/superpowers/specs/2026-10-28-narrator-reliability-18-design.md."""

import re

from engine import phone
from engine.character import is_tsukumogami
from engine.chrome import change_humanity
from engine.debt import SHELL, new_shell, pay_installment, repo_target_name, repossess, unthrottle
from engine.session import Session
from narrator import clock, gossip, memory, people, places, promises
from narrator.movement import destination, known_place, places_in
from narrator.world import _mentions, _normalize, kuroshio
from ruleset.cyberware import CHROME

_LEVELS = ["none", "small", "big"]
_AMOUNT = {"none": 0, "small": 2, "big": 4}
_LEVEL_FIELDS = ("human_moment", "acted_as_machine")
_HARA_OBJECTIVE = "Owe Old Hara a favor"
_LOCATION_MAX = 60
_PROMISE_MAX = 120
_TEXT_FIELDS = ("moved_to", "new_lead", "objective_done", "promise_made", "told_npc", "new_person", "left_mark")
_TRUST_FIELDS = {"kept_promise_to": 1, "helped_at_a_cost": 1, "broke_promise_to": -1, "lie_discovered_by": 0}
_SPEECH = re.compile(r"^[^:\n]{1,30}: ")  # "Mama Sato: ..." lines in the narration text
_SYSTEM = (
    "You are a strict referee for a tabletop RPG. Read the player's action and the narration, "
    "then answer each question about what actually happened in the narration. "
    "When unsure, answer none or false. Before each none/small/big answer, its _quote field copies the exact words "
    "from the action or narration that show it (empty for none)."
)


def build_questions(session: Session, player_id: str) -> dict[str, str]:
    c = session.characters[player_id]
    name = c.name
    questions = {
        "human_moment": f"none/small/big: did {name} share a genuinely human moment (a kindness, a shared meal, "
                        "being thanked, keeping a promise, choosing restraint)? Sneaking, climbing, jumping, fighting, hacking "
                        "or any other skill use on its own is none.",
    }
    questions["moved_to"] = (f"text: if {name} arrived somewhere new this turn, the place's name exactly as the action or "
                             "narration writes it (for example: Mama Sato's izakaya); otherwise empty. Only asking about "
                             "or looking at a place is not arriving.")
    # GUMSHOE's core clue / "the players always get the lead" (spec 2026-11-07-story-thread-design.md).
    questions["new_lead"] = (f"text: a concrete next step this scene gave {name}: a named person to see, a place to "
                             "go or a thing to find, in under 8 words (for example: Ask Jun about the Yomi Line data); "
                             "otherwise empty. Warnings, threats and riddles are not leads.")
    if session.active_objectives:  # kaito3 replay: done objectives stayed listed
        listed = "; ".join(session.active_objectives)
        questions["objective_done"] = (f"text: which of these did {name} finish in this scene, copied exactly, or "
                                       f"empty: {listed}")
    questions["promise_made"] = (f"text: a new promise, debt or favour agreed this turn between {name} and one named "
                                 'person, written as "Who: what" in under 12 words (for example: Mama Sato: bring '
                                 "back her nephew Kenta); otherwise empty.")
    # Spec 2026-11-22 told-npc: soak 7 turn 11, "I already paid this week" was told to the collector and lost.
    questions["told_npc"] = (f"text: what {name} told a named person in the scene this turn that they would remember "
                             '(a claim, an offer, a threat, a lie), written as "Name: what was said, a few words" (for '
                             "example: Wataru Ono: already paid this week); otherwise empty.")
    # Emerging characters (spec 2026-11-22): promote on consequence, not mention (Nemesis; Starforged connections).
    # Soak 2026-11-22: the 8B referee left the "who: what happened" form empty on every turn of four soaks, a fistfight
    # included; a bare description it fills (live check: enforcer, Kaminari man, guard). The action is what happened.
    questions["new_person"] = (f"text: the unnamed person {name} talked to, fought, helped or traded with this turn, as "
                               "a 1-6 word description taken from the scene (for example: enforcer, dockworker with a "
                               "burned hand, noodle vendor); empty if there is none or they have a name.")
    # Places that grow (spec 2026-11-22 part 2): what the player leaves behind.
    questions["left_mark"] = (f"text: a lasting, visible change {name} caused to this place this turn (for example: "
                              "broken window, burned stall, blood on the counter), under 8 words; otherwise empty. "
                              "Moods, sounds and things that pass are not marks.")
    if ((p := session.phone.get(player_id)) and p["contacts"]) or session.promises:
        who = "the person's name exactly as written, or empty"
        questions["kept_promise_to"] = f"text: {name} kept a promise this turn to whom? {who}."
        questions["helped_at_a_cost"] = f"text: {name} helped someone at a real cost to themselves; whom? {who}."
        questions["broke_promise_to"] = f"text: {name} broke a promise this turn to whom? {who}."
        questions["lie_discovered_by"] = f"text: someone caught {name} in a lie this turn; who? {who}."
    if is_tsukumogami(c):
        questions["acted_as_machine"] = (f"none/small/big: did {name} act as a pure machine (cold calculation, "
                                         "following an owner's script, treating people as inputs)? Sneaking, climbing, "
                                         "jumping, fighting, hacking or any other skill use, and the dice result line, "
                                         "are none on their own.")
    if c.pending_repo:
        questions["gave_up_repo_item"] = (f"true/false: did {name} hand over or lose their "
                                          f"{repo_target_name(c.pending_repo)} to the repo crew?")
    if c.installments_owed > 0 and not c.bodiless:
        questions["gig_paid_out"] = f"true/false: did {name} get paid for finished work?"
    questions["went_to_sleep"] = f"true/false: did {name} lie down and go to sleep this turn?"  # the night clock
    if c.bodiless:
        questions["got_new_shell"] = f"true/false: did {name} get a new utsusemi shell?"
    if c.throttled:
        questions["hara_unlocked_chrome"] = (f"true/false: did Old Hara unlock {name}'s throttled "
                                             f"{CHROME[c.throttled].name}?")
    return questions


def build_schema(questions: dict[str, str]) -> dict:
    # The quote comes first so the model commits to evidence before its answer.
    properties = {}
    for k in questions:
        if k in _LEVEL_FIELDS:
            properties[f"{k}_quote"] = {"type": "string"}
            properties[k] = {"type": "string", "enum": _LEVELS}
        elif k in _TEXT_FIELDS or k in _TRUST_FIELDS:
            properties[k] = {"type": "string", "maxLength": _PROMISE_MAX if k in ("promise_made", "told_npc", "new_person") else _LOCATION_MAX}
        else:
            properties[k] = {"type": "boolean"}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def validate_verdict(verdict: dict, questions: dict[str, str]) -> None:
    expected = set(questions) | {f"{k}_quote" for k in questions if k in _LEVEL_FIELDS}
    if isinstance(verdict, dict):
        for k in (*_TEXT_FIELDS, *_TRUST_FIELDS):  # optional: older answers and test fakes leave them out
            if k in questions:
                verdict.setdefault(k, "")
        if "went_to_sleep" in questions:
            verdict.setdefault("went_to_sleep", False)
    if not isinstance(verdict, dict) or set(verdict) != expected:
        raise ValueError(f"referee answered {sorted(verdict) if isinstance(verdict, dict) else verdict!r}, "
                         f"expected {sorted(expected)}")
    for key, value in verdict.items():
        if key.endswith("_quote") or key in _TEXT_FIELDS or key in _TRUST_FIELDS:
            ok = isinstance(value, str)
        else:
            ok = value in _LEVELS if key in _LEVEL_FIELDS else isinstance(value, bool)
        if not ok:
            raise ValueError(f"bad referee value for {key}: {value!r}")


def _state_line(session: Session, player_id: str) -> str:
    c = session.characters[player_id]
    parts = [f"{c.name}: {'tsukumogami' if is_tsukumogami(c) else 'human'}"]
    if c.installments_owed > 0:
        parts.append(f"owes {c.installments_owed}")
    if c.pending_repo:
        parts.append(f"repo pending: {repo_target_name(c.pending_repo)}")
    if c.throttled:
        parts.append(f"throttled: {CHROME[c.throttled].name}")
    if c.bodiless:
        parts.append("bodiless")
    return ", ".join(parts)


def _messages(session, player_id, action_text, narration_text, questions) -> list[dict]:
    lines = "\n".join(f"- {k}: {q}" for k, q in questions.items())
    user = (f"State: {_state_line(session, player_id)}\nAction: {action_text}\n"
            f"Narration: {narration_text}\nQuestions:\n{lines}")
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def _squash(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s']", " ", text.lower()).split())


_SLEEP = re.compile(r"\b(sleep|sleeps|sleeping|slept|asleep|bed|nap|naps|doze|dozes|crash|turn in)\b", re.I)
_NON_ANSWERS = {"none", "n a", "empty", "nothing", "no one", "nobody"}
_SMALL_WORDS = {"about", "from", "into", "with", "that", "this", "there", "their", "your", "what", "where", "when"}


def _quotes_the_scene(lead: str, scene: str) -> bool:
    """Two lead words in a row, both real words (4+ letters, not filler), that the scene has in a row too:
    "Find the collector's ledger" quotes "The collector's ledger never leaves his table"."""
    words, said = _squash(lead).split(), f" {_squash(scene)} "
    return any(len(a) >= 4 and len(b) >= 4 and not {a, b} & _SMALL_WORDS and f" {a} {b} " in said
               for a, b in zip(words, words[1:]))


def _names_something_in(lead: str, scene: str, session: Session) -> bool:
    """The lead names a known place or a named person, and the scene names it too, or it quotes the scene
    (spec 2026-11-07 section 1; no invented leads)."""
    if places_in(lead) & places_in(scene) or _quotes_the_scene(lead, scene):
        return True
    # A proper name the scene says too, past the lead's first word (soak 2026-11-22: "Look for Kuroda in the ledger"
    # was dropped though the narration named Kuroda).
    names = [w for w in re.findall(r"[^\W\d_][\w'-]*", lead)[1:] if w[0].isupper() and len(w) >= 4]
    if any(re.search(rf"\b{re.escape(w)}\b", scene) for w in names):
        return True
    world = kuroshio()
    lead_n, scene_n = _normalize(lead), _normalize(scene)
    people = [n for n in world.npcs if _mentions(n, lead_n) and _mentions(n, scene_n)]
    contacts = [c for p in session.phone.values() for c in p["contacts"]
                if c.split()[0].lower() in lead_n.split() and c.split()[0].lower() in scene_n]
    return bool(people or contacts)


_SPEAKER = re.compile(r"^([^:\n]{3,40}): ")


def _unnamed_speaker(narration: str) -> str | None:
    """The first speaker line from an extra ("man in black duster: ..."), not a named person ("Mama Sato: ...")."""
    for line in narration.splitlines():
        if (m := _SPEAKER.match(line)) and m.group(1) != "narrator" and not m.group(1)[:1].isupper():
            return m.group(1)
    return None


def ground(session: Session, verdict: dict, action: str, narration: str, player: str = "the player") -> dict:
    """A level answer counts only if its quote really is in the text it may come from
    (Phase 18 live: plain stealth and jump turns earned +2 "human moments"). A human
    moment can be in the narration (being thanked); acting as a machine is the
    player's choice, so it must be in their own words (2026-11-06 live: the
    narrator's description of a roof climb was quoted as machine behaviour)."""
    sources = {"human_moment": (_squash(f"{action}\n{narration}"), "the scene"),
               "acted_as_machine": (_squash(action), "the player's action")}
    grounded = {k: v for k, v in verdict.items() if not k.endswith("_quote")}
    # The night clock (review 2026-11-23): sleep skips the night, so "I rest a moment" must not count.
    if grounded.get("went_to_sleep") and not _SLEEP.search(action):
        grounded["went_to_sleep"] = False
        session.log.append("[referee: went_to_sleep without sleep in the action, ignored]")
    for k in _TEXT_FIELDS:  # soak 2026-11-23: "none" for empty is a non-answer, not an invention to log
        if _squash(str(grounded.get(k, ""))) in _NON_ANSWERS:
            grounded[k] = ""
    for k in _LEVEL_FIELDS:
        text, where = sources[k]
        quote = _squash(verdict.get(f"{k}_quote", ""))
        if grounded.get(k, "none") != "none" and not (quote and quote in text):
            grounded[k] = "none"
            session.log.append(f"[referee: {k} had no quote from {where}, ignored]")
    # A new location counts only if the scene really names it (2026-11-06 live: the narrator never set the izakaya).
    moved = " ".join(str(grounded.get("moved_to", "")).split())[:_LOCATION_MAX]
    # Only the player or the narrator's own prose moves the player: an NPC naming a place isn't arriving there
    # (dry run 2026-11-06: "What brings you to Ikebe?" moved the player out of the izakaya).
    prose = "\n".join(line for line in narration.splitlines() if not _SPEECH.match(line))
    named_here = known_place(moved) in places_in(f"{action}\n{prose}")  # "the izakaya" names Mama Sato's izakaya
    if moved and _squash(moved) not in _squash(f"{action}\n{prose}") and not named_here:
        session.log.append("[referee: moved_to had no match in the scene, ignored]")
        moved = ""
    # Soak 2026-11-23 turn 22: "I head back toward Ikebe Low" and the narrator walked Rin into Old Hara's clinic, so
    # the next five turns (the punch) happened there. When the action says where it goes, the narrator can't pick
    # somewhere else.
    went = destination(action)
    if moved and went and known_place(moved) != went and known_place(moved) not in places_in(action):
        session.log.append(f'[referee: moved_to "{moved}" is not where the action went ({went}), ignored]')
        moved = ""
    # Only a known place moves the player, by its own name ("Ikebe Low - Old Hara's clinic" -> Old Hara's clinic).
    if moved and not known_place(moved):
        session.log.append("[referee: moved_to is not a known place, ignored]")
    grounded["moved_to"] = known_place(moved) or ""
    lead = " ".join(str(grounded.get("new_lead", "")).split())[:_LOCATION_MAX]
    if lead and not _names_something_in(lead, f"{action}\n{narration}", session):
        session.log.append(f'[referee: new_lead "{lead}" names nothing in the scene, ignored]')
        lead = ""
    if "new_lead" in grounded or lead:
        grounded["new_lead"] = lead
    # A promise counts only if its person is in the scene and its "what" names or quotes something there too.
    # Whole words only (review 2026-11-22: "Ken" matched "token"); split before capping, so "what" isn't cut mid-word.
    promise = " ".join(str(grounded.get("promise_made", "")).split())
    if promise:
        parts = promises.split(promise)
        said = f"{action}\n{narration}"
        if parts:
            promise = f"{parts[0]}: {parts[1]}"
        if not parts or not _has_words(parts[0], said) or not (_names_something_in(parts[1], said, session)
                                                                or _every_word_in(parts[1], said)):
            session.log.append(f'[referee: promise "{promise}" is not in the scene, ignored]')
            promise = ""
    if "promise_made" in grounded or promise:
        grounded["promise_made"] = promise
    told = " ".join(str(grounded.get("told_npc", "")).split())
    if told:
        parts = promises.split(told)
        # Whole words, one match only (review: "ama" matched Mama Sato; "Sato" with two Satos picked one).
        said = set(_squash(parts[0]).split()) if parts else set()
        hits = [p for p in session.present if said and said <= set(_squash(p).split())]
        who = hits[0] if len(hits) == 1 else parts and parts[0]
        # Soak 2026-11-23 turn 11: "I tell him I already paid" went to Wataru (named in speech), not Goro who answered.
        # The action names nobody, so "him" is whoever in the scene speaks back this turn, if exactly one does.
        speakers = {p for p in session.present for l in narration.splitlines() if l.startswith(f"{p}:")}
        if len(speakers) == 1 and who not in speakers and not (parts and _has_words(parts[0], action)):
            who = next(iter(speakers))
        players = {w for c in session.characters.values() for w in _squash(c.name).split()}
        if not parts or len(hits) > 1 or not people.has_a_name(session, who) or set(_squash(who).split()) & players \
                or not (who in session.present or _has_words(parts[0], f"{action}\n{narration}")) \
                or not _every_word_in(parts[1], action):
            session.log.append(f'[referee: told_npc "{told}" is not something said to someone here, ignored]')
            told = ""
        else:
            told = f"{who}: {parts[1]}"
    if "told_npc" in grounded or told:
        grounded["told_npc"] = told
    person = " ".join(str(grounded.get("new_person", "")).split())
    # Soak 2026-11-22: the bare action made Daisuke "remember" "I punch the guy who bumps into me."; quote it as Rin's.
    deed = f'{player} did this: "{" ".join(action.split()).rstrip(".")}"'
    if person and ":" not in person:
        person = f"{person}: {deed}"
    if person:
        parts = people.split(person)
        if parts and people.has_a_name(session, parts[0]):
            person = ""  # soak 2026-11-22: the referee often names Mama Sato here; not a walk-on, and not an error
        elif not parts or not people.grounded(session, parts[0], f"{action}\n{narration}"):
            session.log.append(f'[referee: new_person "{person}" is not in the scene, ignored]')
            person = ""
        elif not people.dealt_with(parts[0], action):
            session.log.append(f'[referee: new_person "{person}" is not someone the action dealt with, ignored]')
            person = ""
    if not person and (speaker := _unnamed_speaker(narration)) and not people.has_a_name(session, speaker) \
            and people.one_person(speaker):
        # The speaker is in the scene by construction, so only "not someone already named" is checked.
        # Soak 2026-11-22: "man in black duster" grabbed Rin and spoke three turns running, and the referee named no
        # one. An unnamed speaker in the scene is its own evidence; the player's action is what happened.
        person = f"{speaker}: {deed}"
    if "new_person" in grounded or person:
        grounded["new_person"] = person
    mark = " ".join(str(grounded.get("left_mark", "")).split())[:_LOCATION_MAX]
    if mark and not people.grounded(session, mark, f"{action}\n{narration}"):
        session.log.append(f'[referee: left_mark "{mark}" is not in the scene, ignored]')
        mark = ""
    if "left_mark" in grounded or mark:
        grounded["left_mark"] = mark
    # A contact confronting you in dialogue is the evidence, so these use the full narration, speech included.
    scene = _squash(f"{action}\n{narration}")
    for k in _TRUST_FIELDS:
        who = " ".join(str(grounded.get(k, "")).split())
        if who and not _has_words(who, scene):
            session.log.append(f"[referee: {k} had no match in the scene, ignored]")
            who = ""
        if k in grounded or who:
            grounded[k] = who
    return grounded


def _every_word_in(what: str, text: str) -> bool:
    """Every real word (3+ letters) of a promise, at least two, is in the scene (soak 2026-11-22: "Old Hara: bring tea
    tomorrow" was dropped; "tea" is too short for the two-words-in-a-row quote rule)."""
    words = [w for w in _squash(what).split() if len(w) >= 3 and w not in _SMALL_WORDS]
    said = set(_squash(text).split())
    return len(words) >= 2 and all(w in said for w in words)


def _has_words(phrase: str, text: str) -> bool:
    return bool(_squash(phrase)) and f" {_squash(phrase)} " in f" {_squash(text)} "


def _find_contact(session: Session, player_id: str, written: str) -> dict | None:
    """Full name (any case), or one word that belongs to exactly one contact's name."""
    return phone.find_contact(phone.phone_of(session, player_id)["contacts"], written)


def apply_verdict(session: Session, player_id: str, verdict: dict) -> None:
    c = session.characters[player_id]
    name = c.name
    for field, delta in _TRUST_FIELDS.items():
        contact = _find_contact(session, player_id, verdict[field]) if verdict.get(field) else None
        if not contact:
            continue
        if field != "lie_discovered_by":
            phone.change_trust(contact, delta)
            if field == "helped_at_a_cost":
                memory.remember(session, contact["name"], f"{name} came through for them", memory.ENGINE)
                gossip.record(session, f"{name} helped {contact['name']} at a cost", True)
                gossip.amends(session, contact["name"])
        elif contact["role"] not in ("rival", "enemy") and contact["trust"] >= 1:
            drop = 2 if contact["trust"] >= 4 or contact["role"] in ("family", "partner") else 1
            contact["trust"] = max(1.0, contact["trust"] - drop)
            contact["cold_until"] = phone.phone_of(session, player_id)["turn"] + 3
            session.pending_world_events.append(f"{contact['name']} knows {name} lied to them.")
            memory.remember(session, contact["name"], f"{name} lied to them", memory.ENGINE)
            gossip.record(session, f"{name} lied to {contact['name']}", False)
    for field, kept in (("kept_promise_to", True), ("broke_promise_to", False)):
        if verdict.get(field):
            promises.close(session, verdict[field], kept, name)
            gossip.record(session, f"{name} {'kept' if kept else 'broke'} their word to {verdict[field]}", kept)
            if kept:
                gossip.amends(session, verdict[field])
    if verdict.get("promise_made") and (parts := promises.split(verdict["promise_made"])):
        promises.record(session, *parts)
        memory.remember(session, parts[0], f"{name} promised: {parts[1]}", memory.ENGINE)
    if verdict.get("told_npc") and (parts := promises.split(verdict["told_npc"])):
        memory.remember(session, parts[0], f"{name} told them: {parts[1]}", memory.NOTABLE)
    done = verdict.get("objective_done")
    if done in session.active_objectives:
        session.active_objectives = [o for o in session.active_objectives if o != done]
        promises.note(session, done, "done")
    if verdict.get("new_person") and (parts := people.split(verdict["new_person"])):
        people.meet(session, *parts)
        if (good := gossip.classify(parts[1])) is not None:
            gossip.record(session, parts[1], good)
    places.mark(session, verdict.get("left_mark", ""))
    good = (verdict.get("human_moment", "none") != "none" or verdict.get("helped_at_a_cost")
            or verdict.get("kept_promise_to"))
    bad = verdict.get("broke_promise_to") or verdict.get("lie_discovered_by")
    places.warm(session, (1 if good else 0) - (1 if bad else 0))
    if verdict.get("new_lead"):
        promises.add_lead(session, verdict["new_lead"])
    if verdict.get("moved_to") and verdict["moved_to"] != session.location:
        session.location = verdict["moved_to"]
        session.log.append(f"[moved: {session.location} (referee)]")
    delta = _AMOUNT[verdict.get("human_moment", "none")] - _AMOUNT[verdict.get("acted_as_machine", "none")]
    if delta:
        before = c.humanity
        session.pending_world_events.extend(change_humanity(c, delta))
        if is_tsukumogami(c) and c.humanity != before:
            session.log.append(f"[selfhood: {c.humanity - before:+d}]")
    # Same order as 17b's tool path: repo and unthrottle before payment, which clears both.
    if verdict.get("gave_up_repo_item") and c.pending_repo:
        removed = repossess(c)
        if removed == SHELL:
            session.log.append(f"[torite: Saeko's crew took {name}'s shell - {name} drops into the nearest machine]")
        else:
            session.log.append(f"[torite: Saeko's crew took {name}'s {CHROME[removed].name}]")
    if verdict.get("hara_unlocked_chrome") and c.throttled:
        unthrottle(c)
        if _HARA_OBJECTIVE not in session.active_objectives:
            session.active_objectives.append(_HARA_OBJECTIVE)
    if verdict.get("went_to_sleep"):
        clock.sleep(session, player_id)
    elif player_id in session.sleepers:
        session.sleepers.remove(player_id)  # up and doing something: they're awake again
    if verdict.get("got_new_shell") and c.bodiless:
        new_shell(c)
        session.log.append(f"[utsusemi: {name} wakes in a new shell]")
    if verdict.get("gig_paid_out") and c.installments_owed > 0:
        pay_installment(c, 1)
        for creditor in [k for k in phone.phone_of(session, player_id)["contacts"].values() if k["role"] == "creditor"]:
            memory.remember(session, creditor["name"], f"{name} paid an installment on what they owe", memory.ENGINE)
        jun = phone.add_contact(session, player_id, "Jun Arakawa", "fixer")
        phone.post(session, player_id, "Jun Arakawa", "Jun Arakawa", "Money's in. Clean work.",
                   phone.phone_of(session, player_id)["turn"])
        phone.change_trust(jun, 0.5)


async def run_referee(session: Session, client, player_id: str, action_text: str, narration_text: str) -> None:
    if player_id not in session.characters:
        return
    questions = build_questions(session, player_id)
    try:
        verdict = await client.judge(_messages(session, player_id, action_text, narration_text, questions),
                                     build_schema(questions))
        validate_verdict(verdict, questions)
    except Exception as e:  # a failed referee must never break the turn
        session.log.append(f"[referee error: {e}]")
        return
    apply_verdict(session, player_id, ground(session, verdict, action_text, narration_text,
                                             session.characters[player_id].name))
