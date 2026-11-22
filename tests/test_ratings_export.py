from tools.ratings_export import export, trim, weights


def test_long_prompts_lose_their_oldest_recent_lines_only():
    user = "Party: Rin\nRecent events:\nold line one\nold line two\nnewest line\n\nPresent: Mama Sato\nPlayer action: I eat."
    short = trim(user, len(user) - 20)
    assert "old line one" not in short and "newest line" in short and short.endswith("Player action: I eat.")
    assert trim(user, 10).count("\n") >= 4  # never drops the last recent line or anything outside the block


def test_rows_match_trl_kto_and_skip_empty_ones():
    rows = export([{"prompt": "Player action: I eat.", "narration": "The eel is good.", "like": True},
                   {"prompt": "", "narration": "x", "like": False}], "SYSTEM", 6000)
    assert rows == [{"prompt": [{"role": "system", "content": "SYSTEM"},
                                {"role": "user", "content": "Player action: I eat."}],
                     "completion": [{"role": "assistant", "content": "The eel is good."}], "label": True}]


def test_weights_land_the_ratio_in_one_to_four_thirds():
    for likes, dislikes in ((100, 10), (10, 100), (50, 50), (40, 30)):
        dw, uw = weights(likes, dislikes)
        assert 1 <= round(likes * dw / (dislikes * uw), 2) <= 4 / 3 + 0.01
