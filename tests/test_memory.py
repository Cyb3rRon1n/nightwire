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
