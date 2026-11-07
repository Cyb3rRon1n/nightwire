from tools.taste import summary


def test_summary_splits_likes_and_carries_notes():
    taste = {"a": {"like": True, "at": "1"}, "b": {"like": False, "at": "2"}, "c": {"like": True, "at": "3"}}
    text = summary(taste, {"b": {"note": "too flat"}})
    assert text == "Liked (2):\n  c\n  a\nDisliked (1):\n  b: too flat"


def test_keep_counts_as_like_and_reject_as_dislike_unless_a_thumb_says_otherwise():
    images = {"k": {"verdict": "keep", "at": "1"}, "r": {"verdict": "reject", "at": "2"},
              "f": {"verdict": "fix", "at": "3", "note": "legs"}, "t": {"verdict": "keep", "at": "4"}}
    text = summary({"t": {"like": False, "at": "5"}}, images)
    assert text == "Liked (1):\n  k\nDisliked (2):\n  t\n  r"
