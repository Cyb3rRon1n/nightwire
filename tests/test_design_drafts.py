from narrator.designs import kuroshio_designs
from narrator.world import kuroshio


def test_all_22_drafts_load():
    designs = kuroshio_designs()
    assert len(designs) == 22
    assert sum(d.kind == "character" for d in designs.values()) == 11


def test_character_sources_match_world_npcs():
    npc_names = {n.name for n in kuroshio().npcs}
    sources = {d.source.removeprefix("npc:") for d in kuroshio_designs().values() if d.kind == "character"}
    assert sources == npc_names


def test_district_sources_match_world_districts():
    districts = {d.name for d in kuroshio().districts}
    sources = {d.source.removeprefix("district:") for d in kuroshio_designs().values() if d.source.startswith("district:")}
    assert sources == districts


def test_drafts_follow_the_writing_rules():
    for d in kuroshio_designs().values():
        tags = [t.strip() for t in d.tags.split(",")]
        assert 12 <= len(tags) <= 25, d.name
        assert d.status == "draft" and d.notes == ["2026-10-28 draft from world card"], d.name
        if d.kind == "location":
            assert d.alt_tags and 3 <= len(d.props) <= 5, d.name
            assert "scenery" not in d.tags, d.name
        if "mechanical left arm" in d.tags or "mechanical right arm" in d.tags:
            assert "two mechanical arms" in d.negative, d.name
