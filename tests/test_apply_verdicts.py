from tools.apply_verdicts import apply


def _entries():
    return [{"path": "a/debt5/train-90233.png", "status": "candidate", "note": "old"}, {"path": "a/life3/mama.png", "status": "candidate"}]


def test_verdicts_set_status_and_notes():
    entries = _entries()
    changed, unmatched = apply(entries, {"debt-train-90233": {"verdict": "keep", "note": ""}, "life-mama": {"verdict": "fix", "note": "hand"}})
    assert (changed, unmatched) == (2, [])
    assert entries[0]["status"] == "approved" and entries[0]["note"] == "old"
    assert entries[1]["status"] == "needs-fix" and entries[1]["note"] == "owner: hand"


def test_unmatched_ids_are_reported_and_nothing_else_changes():
    entries = _entries()
    assert apply(entries, {"wall-nope": {"verdict": "reject", "note": ""}}) == (0, ["wall-nope"])
    assert entries == _entries()


def test_a_note_without_a_choice_keeps_the_status():
    entries = _entries()
    assert apply(entries, {"life-mama": {"verdict": None, "note": "more cyberpunk"}}) == (1, [])
    assert entries[1]["status"] == "candidate" and entries[1]["note"] == "owner: more cyberpunk"


def test_an_original_counts_as_approved():
    entries = _entries()
    apply(entries, {"life-mama": {"verdict": "original", "note": ""}})
    assert entries[1]["status"] == "approved"
