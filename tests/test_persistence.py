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
    )
    session.turn_order = ["p1"]
    session.current_turn_index = 0
    session.in_combat = True
    session.pre_combat_turn_order = ["p1"]
    session.log = ["Rook draws a pistol."]

    store.save(session)
    loaded = store.load("test-session")

    assert loaded is not None
    assert loaded.session_id == "test-session"
    assert loaded.turn_order == ["p1"]
    assert loaded.in_combat is True
    assert loaded.pre_combat_turn_order == ["p1"]
    assert loaded.log == ["Rook draws a pistol."]
    loaded_character = loaded.characters["p1"]
    assert loaded_character.name == "Rook"
    assert loaded_character.role == "solo"
    assert loaded_character.lifepath == "streetkid"
    assert loaded_character.attributes == {"body": 14, "reflexes": 12}
    assert loaded_character.health == 7
    assert loaded_character.max_health == 10
    assert loaded_character.armor == 2
    assert loaded_character.conditions == ["bleeding"]
    assert loaded_character.inventory == ["stim pack"]


def test_load_returns_none_for_a_session_id_with_no_saved_file(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    assert store.load("never-saved") is None


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
