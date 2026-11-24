from pathlib import Path

import pytest

from tools.shorts.backends import comfy_video
from tools.shorts.backends.comfy_video import frames, graph, graph_from, titled

FIXTURES = Path(__file__).parent / "fixtures" / "comfy_video"


@pytest.fixture(autouse=True)
def _fixture_workflows(monkeypatch):
    monkeypatch.setattr(comfy_video, "WORKFLOWS", FIXTURES)


def test_frames_follow_each_models_rule():
    assert frames("wan22-flf", 5) == 81
    assert frames("wan22-flf", 4.9) == 81  # rounded up to the next 4n+1
    assert (frames("ltx23", 5) - 1) % 8 == 0 and frames("ltx23", 5) >= 5 * comfy_video.MODELS["ltx23"]["fps"]


def test_a_loop_uses_the_same_still_at_both_ends():
    g = graph("wan22-flf", "izakaya.png", "izakaya.png", "rain on the window, neon flicker", 5, 7)
    assert titled(g, "start")["inputs"]["image"] == titled(g, "end")["inputs"]["image"] == "izakaya.png"
    assert titled(g, "seed")["inputs"]["noise_seed"] == 7 and titled(g, "length")["inputs"]["length"] == 81
    assert titled(g, "prompt")["inputs"]["text"] == "rain on the window, neon flicker"


def test_a_workflow_without_a_needed_title_fails_at_load():
    with pytest.raises(ValueError, match="prompt"):
        graph_from(FIXTURES / "no_prompt.json", "wan22-flf", "a.png", "a.png", "x", 5, 1)


def test_an_end_frame_on_a_model_without_one_is_refused():
    with pytest.raises(ValueError, match="end frame"):
        graph("ltx23", "a.png", "a.png", "x", 5, 1)
    assert "end" not in {n["_meta"]["title"] for n in graph("ltx23", "a.png", None, "x", 5, 1).values()}
