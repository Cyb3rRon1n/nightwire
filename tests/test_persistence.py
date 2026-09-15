import json
import os

import pytest

from engine.character import CharacterSheet
from engine.persistence import JSONFileSessionStore, SessionStoreUnwritable
from engine.session import Session


def test_store_creates_the_directory_if_missing(tmp_path):
    store_dir = tmp_path / "sessions"
    JSONFileSessionStore(store_dir)
    assert store_dir.is_dir()


def test_save_then_load_round_trips_a_session_with_a_character(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="test-session")
    session.characters["p1"] = CharacterSheet(
        player_id="p1",
        name="Rook",
        role="solo",
        lifepath="streetkid",
        attributes={"body": 14, "reflexes": 12},
        health=7,
        max_health=10,
        armor=2,
        conditions=["bleeding"],
        inventory=["stim pack"],
        portrait_path="sessions/portraits/test-session/p1.png",
        skills={"stealth": 3, "hacking": 2},
        unspent_skill_points=1,
        unspent_attribute_points=2,
    )
    session.turn_order = ["p1"]
    session.current_turn_index = 0
    session.in_combat = True
    session.pre_combat_turn_order = ["p1"]
    session.log = ["Rook draws a pistol."]
    session.location = "Night City - Watson district"
    session.scene_mood = "tense"
    session.active_objectives = ["find the fixer", "avoid corpo patrols"]
    session.speaker_voices["Jax"] = "am_adam"
    session.pending_initiative["p2"] = 8
    session.last_turn_had_image = True
    session.narrative_summary = "The party met a fixer and agreed to a job."
    session.narrative_summary_line_count = 14

    store.save(session)
    loaded = store.load("test-session")

    assert loaded is not None
    assert loaded.session_id == "test-session"
    assert loaded.turn_order == ["p1"]
    assert loaded.in_combat is True
    assert loaded.pre_combat_turn_order == ["p1"]
    assert loaded.log == ["Rook draws a pistol."]
    assert loaded.location == "Night City - Watson district"
    assert loaded.scene_mood == "tense"
    assert loaded.active_objectives == ["find the fixer", "avoid corpo patrols"]
    assert loaded.speaker_voices == {"Jax": "am_adam"}
    assert loaded.pending_initiative == {"p2": 8}
    assert loaded.last_turn_had_image is True
    assert loaded.narrative_summary == "The party met a fixer and agreed to a job."
    assert loaded.narrative_summary_line_count == 14
    loaded_character = loaded.characters["p1"]
    assert loaded_character.name == "Rook"
    assert loaded_character.role == "solo"
    assert loaded_character.lifepath == "streetkid"
    assert loaded_character.attributes == {"body": 14, "reflexes": 12}
    assert loaded_character.health == 7
    assert loaded_character.max_health == 10
    assert loaded_character.armor == 2
    assert loaded_character.conditions == ["bleeding"]
    assert loaded_character.portrait_path == "sessions/portraits/test-session/p1.png"
    assert loaded_character.inventory == ["stim pack"]
    assert loaded_character.skills == {"stealth": 3, "hacking": 2}
    assert loaded_character.unspent_skill_points == 1
    assert loaded_character.unspent_attribute_points == 2


def test_load_defaults_character_skills_when_missing_from_an_older_character_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    from dataclasses import asdict

    session_data = asdict(session)
    del session_data["characters"]["p1"]["skills"]
    del session_data["characters"]["p1"]["unspent_skill_points"]
    del session_data["characters"]["p1"]["unspent_attribute_points"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(session_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.characters["p1"].skills == {}
    assert loaded.characters["p1"].unspent_skill_points == 0
    assert loaded.characters["p1"].unspent_attribute_points == 0


def test_load_returns_none_for_a_session_id_with_no_saved_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    assert store.load("never-saved") is None


def test_load_defaults_speaker_voices_when_missing_from_a_pre_phase6_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    # Simulate a session file saved before speaker_voices existed: write the
    # same shape save() would produce, minus that key.
    from dataclasses import asdict

    legacy_data = asdict(session)
    del legacy_data["speaker_voices"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(legacy_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.speaker_voices == {}


def test_load_defaults_pending_initiative_when_missing_from_an_older_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    from dataclasses import asdict

    legacy_data = asdict(session)
    del legacy_data["pending_initiative"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(legacy_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.pending_initiative == {}


def test_load_defaults_last_turn_had_image_when_missing_from_an_older_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    from dataclasses import asdict

    legacy_data = asdict(session)
    del legacy_data["last_turn_had_image"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(legacy_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.last_turn_had_image is False


def test_construction_raises_on_an_unwritable_existing_directory(tmp_path):
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o500)
    try:
        if os.access(readonly_dir, os.W_OK):
            pytest.skip("running as a user that can write read-only directories (e.g. root)")
        with pytest.raises(SessionStoreUnwritable):
            JSONFileSessionStore(readonly_dir)
    finally:
        readonly_dir.chmod(0o700)


def test_construction_raises_when_parent_directory_blocks_creation(tmp_path):
    readonly_parent = tmp_path / "readonly_parent"
    readonly_parent.mkdir()
    readonly_parent.chmod(0o500)
    try:
        if os.access(readonly_parent, os.W_OK):
            pytest.skip("running as a user that can write read-only directories (e.g. root)")
        with pytest.raises(SessionStoreUnwritable):
            JSONFileSessionStore(readonly_parent / "sessions")
    finally:
        readonly_parent.chmod(0o700)


def test_save_rejects_a_path_traversal_session_id(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="../../escaped")
    with pytest.raises(ValueError):
        store.save(session)


def test_load_rejects_a_path_traversal_session_id(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    with pytest.raises(ValueError):
        store.load("../../escaped")


def test_save_rejects_an_empty_session_id(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="")
    with pytest.raises(ValueError):
        store.save(session)


def test_load_defaults_narrative_summary_when_missing_from_an_older_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="legacy-session")
    from dataclasses import asdict

    legacy_data = asdict(session)
    del legacy_data["narrative_summary"]
    del legacy_data["narrative_summary_line_count"]
    store.directory.joinpath("legacy-session.json").write_text(json.dumps(legacy_data))

    loaded = store.load("legacy-session")

    assert loaded is not None
    assert loaded.narrative_summary == ""
    assert loaded.narrative_summary_line_count == 0
