from tools.taste import summary


def test_summary_splits_likes_and_carries_notes():
    taste = {"a": {"like": True, "at": "1"}, "b": {"like": False, "at": "2"}, "c": {"like": True, "at": "3"}}
    text = summary(taste, {"b": {"note": "too flat"}})
    assert text == "Liked (2):\n  c\n  a\nDisliked (1):\n  b: too flat"
