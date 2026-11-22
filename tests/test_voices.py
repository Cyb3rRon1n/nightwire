import json
import random

import pytest

from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.voices import HEADER, Line, load_voices, voice_block, voices
from narrator.world import kuroshio


def test_the_shipped_voices_load():
    v = voices()
    assert len(v.characters) == 12 and len(v.types) == 8
    assert v.characters["Mama Sato"].lines[2] == Line("warn", "Kuze boys drink at that table. Kaminari boys drink at "
                                                              "this one. You drink at the counter.")


@pytest.mark.parametrize("toml", [
    '[[character]]\nname = "Nobody Real"\nlines = [{move="a",text="x"},{move="b",text="y"},{move="c",text="z"}]',
    '[[character]]\nname = "Mama Sato"\nlines = [{move="a",text="x"},{move="b",text="y"}]',
    '[[character]]\nname = "Mama Sato"\nlines = [{move="a",text="x"},{move="a",text="y"},{move="c",text="z"}]',
    '[[type]]\nname = "Vendor"\nmatch = []\nvoice = "busy"\nlines = ["a", "b", "c"]',
])
def test_bad_voice_data_is_refused(tmp_path, toml):
    path = tmp_path / "voices.toml"
    path.write_text(toml)
    with pytest.raises(ValueError):
        load_voices(path, kuroshio())


def test_a_present_character_gets_one_line_and_never_the_same_move_twice():
    random.seed(7)
    s = Session(session_id="s", present=["Mama Sato"])
    hers = {line.text: line.move for line in voices().characters["Mama Sato"].lines}
    moves = []
    for _ in range(6):
        block = voice_block(s, "I wait.")
        assert block.startswith(HEADER)
        entries = [line for line in block.splitlines()[1:] if line.startswith("- Mama Sato will ")]
        assert len(entries) == 1 and s.voice_lines[0] in hers and f'"{s.voice_lines[0]}"' in entries[0]
        moves.append(hers[s.voice_lines[0]])
    assert all(a != b for a, b in zip(moves, moves[1:]))


def test_a_mentioned_type_gets_its_voice_and_lines_rotate():
    s = Session(session_id="s", log=["A noodle vendor waves you over."])
    vendor = next(t for t in voices().types if t.name == "Street vendor")
    shown = []
    for _ in range(3):
        block = voice_block(s, "I walk up.")
        assert "- A street vendor (busy, practical, gossipy; wants a sale and a quiet night) sounds like: " in block
        shown += s.voice_lines
    assert shown == list(vendor.lines)


def test_nobody_with_a_sheet_means_no_block():
    s = Session(session_id="s", voice_lines=["stale"])
    assert voice_block(s, "I look around.") == "" and s.voice_lines == []


def test_caps_and_unknowns():
    s = Session(session_id="s", present=["Mama Sato", "Old Hara", "Kenta", "Hachi", "Mitsu"],
                last_moves={"Gone": "warn"}, log=["The install hums. A cop and a racer argue. An auditor waits."])
    block = voice_block(s, "I wait.")
    entries = block.splitlines()[1:]
    assert sum(" will " in e for e in entries) == 3 and not any("Kenta" in e for e in entries)
    assert sum(e.startswith("- A ") for e in entries) == 2  # at most 2 types
    assert "street vendor" not in block  # "install" is not "stall"


def test_the_new_session_fields_load_from_an_old_save(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    store.save(Session(session_id="s"))
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    for key in ("last_moves", "type_turns", "voice_lines"):
        data.pop(key)
    path.write_text(json.dumps(data))
    loaded = store.load("s")
    assert loaded.last_moves == {} and loaded.type_turns == {} and loaded.voice_lines == []


def test_a_named_character_replaces_their_type_and_a_bare_faction_word_is_not_a_person():
    # Review 2026-11-22: "officer" beside Captain Ide gave two officer voices; "torite" is said in most narration.
    s = Session(session_id="s", present=["Captain Ide"], log=["An officer stamps a form."])
    assert "ōgane heavy officer" not in voice_block(s, "I wait.")
    s = Session(session_id="s", log=["The torite took his arm last week."])
    assert voice_block(s, "I wait.") == ""
    s = Session(session_id="s", log=["A torite crew member blocks the door."])
    assert "torite crew member" in voice_block(s, "I wait.")


def test_a_redo_reuses_the_turns_voices():
    # Review 2026-11-22: a redo rebuilt the prompt and rerolled the lines the kept reply was checked against.
    from server.narration import _build_messages
    s = Session(session_id="s", present=["Mama Sato"])
    block = voice_block(s, "I sit.")
    lines, moves = list(s.voice_lines), dict(s.last_moves)
    for _ in range(3):
        assert block in _build_messages(s, "I sit.", 8192, block)[0]["content"]
    assert s.voice_lines == lines and s.last_moves == moves
