from tools.review.migrate import plan_migration


def test_plan_migration_maps_and_skips_existing():
    reviews = {"saeko": {"verdict": "ok", "v": "123", "note": ""},
               "rin": {"verdict": "fix", "v": "456", "note": "hair colour"},
               "old": {"verdict": "ok"}}  # no version: cannot be matched to a sheet set, skipped
    images = {"sheet--rin--456": {"verdict": "fix"}}
    assert plan_migration(reviews, images) == {"sheet--saeko--123": {"verdict": "keep"}}


def test_fix_without_note_is_skipped():
    reviews = {"rin": {"verdict": "fix", "v": "7", "note": ""}, "mio": {"verdict": "fix", "v": "8"}}
    assert plan_migration(reviews, {}) == {}
