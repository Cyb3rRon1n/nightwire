from test_shorts_model import PLANNED, write
from tools.shorts import stills
from tools.shorts.model import load_short


def test_in_frame_order_puts_screen_left_first(tmp_path):
    shot = load_short(write(tmp_path, shot=PLANNED)).shots[0]  # C2 screen-left, C1 screen-right
    assert stills.in_frame_order(shot) == ["C2", "C1"]


def test_still_workflow_has_shot_words_and_both_characters(tmp_path, monkeypatch):
    s = load_short(write(tmp_path, shot=PLANNED))
    from narrator.designs import Design
    d = {"saeko-kirigaya": Design(name="Saeko", kind="character", source="t", tags="black hair", status="approved", required=["blunt bangs"]),
         "rin-kageyama": Design(name="Rin", kind="character", source="t", tags="pink hair tips", status="approved"),
         "mama-satos-izakaya": Design(name="Izakaya", kind="location", source="t", tags="izakaya counter", status="approved")}
    wf = stills.still_workflow(s, s.shots[0], d, 703)
    text = " ".join(str(n["inputs"].get("text", "")) for n in wf.values() if isinstance(n, dict) and "inputs" in n)
    assert "upper body" in text and "blunt bangs" in text and "pink hair tips" in text and "izakaya counter" in text
    assert "night" in text.lower()
