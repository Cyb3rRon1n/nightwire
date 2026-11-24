import json

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator import memory, promises
from narrator.referee import apply_verdict, ground
from server.narration import _build_messages
from tests.test_referee import _session

ACTION = "I promise Mama Sato I'll find her nephew Kenta."
SCENE = 'Mama Sato: "Bring Kenta home, child. His mother is sick with worry about her nephew."'


def _texts(s: Session, name: str) -> list[str]:
    return [memory.fact(f)["text"] for f in s.npc_memory[name]]


def test_the_engine_writes_promise_facts_with_top_weight():
    s = _session()
    apply_verdict(s, "p1", ground(s, {"promise_made": "Mama Sato: find her nephew Kenta"}, ACTION, SCENE))
    assert s.npc_memory["Mama Sato"][-1]["text"] == "Rook promised: find her nephew Kenta"
    assert s.npc_memory["Mama Sato"][-1]["weight"] == memory.ENGINE
    promises.close(s, "Mama Sato", False, "Rook")
    assert "Rook broke their word: find her nephew Kenta" in _texts(s, "Mama Sato")


def test_a_weighty_fact_outlives_twelve_turns_of_small_talk():
    s = _session()
    memory.remember(s, "Mama Sato", "Rook promised: find Kenta", memory.ENGINE)
    for i in range(12):
        s.log.append("p1: I chat.")
        memory.remember(s, "Mama Sato", f"small talk {i}")
    assert "Rook promised: find Kenta" in _texts(s, "Mama Sato")
    assert len(s.npc_memory["Mama Sato"]) == memory.MAX_FACTS


def test_narrator_facts_naming_the_player_or_a_big_word_weigh_more():
    s = _session()
    assert memory.remember(s, "Jax", "Rook bought him a drink")[-1]["weight"] == memory.NOTABLE
    assert memory.remember(s, "Jax", "he was saved by a stranger")[-1]["weight"] == memory.NOTABLE
    assert memory.remember(s, "Jax", "likes noodles")[-1]["weight"] == memory.PLAIN


def test_only_people_here_or_named_are_shown_three_by_three_late_in_the_prompt():
    s = _session()
    s.log = ["p1: I look around."]
    for name in ("Mama Sato", "Old Hara", "Jun Arakawa", "Saeko Kirigaya", "Nagi Sumida"):
        for i in range(5):
            memory.remember(s, name, f"{name} fact {i}")
    s.present = ["Mama Sato", "Old Hara"]
    block = memory.recall_block(s, "I wave at Nagi.")
    assert [line.split(":")[0] for line in block.splitlines()] == [
        "What Mama Sato remembers", "What Old Hara remembers", "What Nagi Sumida remembers"]
    assert all(line.count(";") == 2 for line in block.splitlines())
    assert "Jun Arakawa" not in block
    s.pending_world_events = ["A ship's horn sounds."]
    prompt = _build_messages(s, "I wave at Nagi.", 8192)[-1]["content"]
    assert prompt.index("What Mama Sato remembers") < prompt.index("World event:")
    assert "Known NPCs" not in json.dumps(_build_messages(s, "I wave at Nagi.", 8192))


def test_a_title_alone_does_not_match_someone_else():
    s = _session()
    memory.remember(s, "Mama Sato", "Rook promised: find Kenta", memory.ENGINE)
    s.present = ["Mama Kobayashi"]
    assert memory.recall_block(s, "I greet Mama.") == ""


def test_showing_a_fact_refreshes_it():
    s = _session()
    memory.remember(s, "Jax", "likes noodles")
    s.log += ["p1: I wait."] * 5
    memory.recall_block(s, "I talk to Jax.")
    assert s.npc_memory["Jax"][0]["last_used"] == 5


def test_old_saves_with_plain_string_facts_still_work(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    s = Session(session_id="old")
    s.npc_memory = {"Jax": ["offered the party a job"]}
    store.save(s)
    loaded = store.load("old")
    assert "What Jax remembers: offered the party a job." == memory.recall_block(loaded, "I call Jax.")
    memory.remember(loaded, "Jax", "owes Rook money")
    assert [f["text"] for f in loaded.npc_memory["Jax"]] == ["offered the party a job", "owes Rook money"]


def test_one_person_is_one_entry_whatever_name_the_model_wrote():
    s = _session()
    memory.remember(s, "Mama Sato", "Rook lied to them", memory.ENGINE)
    memory.remember(s, "Sato", "Rook promised: find Kenta", memory.ENGINE)
    memory.remember(s, "mama sato", "likes the rain")
    assert list(s.npc_memory) == ["Mama Sato"]
    assert len(s.npc_memory["Mama Sato"]) == 3


def test_a_shared_first_name_or_common_word_does_not_pull_in_someone_else():
    s = _session()
    memory.remember(s, "Jun Arakawa", "owes Rook a favour")
    memory.remember(s, "Jun Mori", "sells noodles")
    memory.remember(s, "Old Man Hara", "fixed Rook's arm")
    s.present = ["Jun Mori"]
    block = memory.recall_block(s, "I nod at the man by the door.")
    assert block.splitlines() == ["What Jun Mori remembers: sells noodles."]
    assert "Jun Arakawa" in memory.recall_block(s, "I call Arakawa.")


def test_common_words_are_not_relevance():
    f = {"text": "Rook lied to them", "turn": 0, "last_used": 0, "weight": 3}
    assert memory._score(f, 0, memory._words("I tell them everything")) == memory._score(f, 0, set())


def test_a_promise_with_a_short_word_is_kept_when_every_word_is_in_the_scene():
    # Soak 2026-11-22 turn 15: "Old Hara: bring tea tomorrow" was dropped; "tea" is too short to quote.
    s = _session()
    action = "I thank him and promise to bring him tea tomorrow."
    apply_verdict(s, "p1", ground(s, {"promise_made": "Old Hara: bring tea tomorrow"}, action, "Old Hara nods."))
    assert [p["what"] for p in s.promises] == ["bring tea tomorrow"]


def test_a_promise_with_words_the_scene_never_said_is_still_ignored():
    s = _session()
    apply_verdict(s, "p1", ground(s, {"promise_made": "Old Hara: bring sake tonight"},
                                  "I promise to bring him tea tomorrow.", "Old Hara nods."))
    assert not s.promises


def _told(s: Session, answer: str, action: str = "I tell him I already paid this week.",
          scene: str = "Wataru Ono taps the ledger.") -> None:
    apply_verdict(s, "p1", ground(s, {"told_npc": answer}, action, scene))


def test_what_the_player_tells_a_named_person_is_remembered():
    # Soak 2026-11-22 turn 11: "I already paid this week" was told to the collector and nobody remembered it.
    s = _session()
    s.present = ["Wataru Ono"]
    _told(s, "Wataru: already paid this week")
    assert s.npc_memory["Wataru Ono"][-1]["text"] == "Rook told them: already paid this week"
    assert s.npc_memory["Wataru Ono"][-1]["weight"] == memory.NOTABLE


def test_told_to_an_unnamed_or_absent_person_is_ignored():
    s = _session()
    _told(s, "the guard: already paid this week")
    _told(s, "Old Hara: already paid this week")
    assert not s.npc_memory


def test_told_words_the_player_never_said_are_ignored():
    s = _session()
    s.present = ["Wataru Ono"]
    _told(s, "Wataru Ono: owes him a favour")
    assert not s.npc_memory and any("told_npc" in l for l in s.log)


def test_told_matches_whole_names_once_and_never_a_player():
    # Review 2026-11-23: "ama" matched Mama Sato; two Satos picked one; a player's own name made an NPC memory.
    s = _session()
    s.present = ["Mama Sato", "Kenta Sato"]
    _told(s, "ama: already paid this week", scene="Mama Sato pours.")
    _told(s, "Sato: already paid this week", scene="Mama Sato pours.")
    _told(s, "Rook: already paid this week", scene="Rook pays.")
    assert not s.npc_memory


def test_told_him_goes_to_the_one_person_who_answers():
    # Soak 2026-11-23 turn 11: "I tell him I already paid" was filed under Wataru (named in speech), not Goro.
    s = _session()
    s.present, s.people["Goro"] = ["Wataru Ono", "Goro"], {}
    _told(s, "Wataru Ono: already paid this week",
          scene="Goro: You already paid? Then you still owe Wataru Ono.\nThe man leans back.")
    assert s.npc_memory["Goro"][-1]["text"] == "Rook told them: already paid this week"
    assert "Wataru Ono" not in s.npc_memory


def test_told_by_name_stays_with_the_named_person_even_if_another_answers():
    s = _session()
    s.present, s.people["Goro"] = ["Wataru Ono", "Goro"], {}
    _told(s, "Wataru: already paid this week", action="I tell Wataru I already paid this week.",
          scene="Goro: He paid, Wataru.")
    assert "Goro" not in s.npc_memory and s.npc_memory["Wataru Ono"]
