from tools.export_npc_palettes import OUT, render


def test_generated_palettes_match_the_approved_designs():
    assert OUT.read_text() == render(), "stale: run python -m tools.export_npc_palettes"


def test_palettes_include_an_approved_npc():
    assert '"Mama Sato"' in render()
