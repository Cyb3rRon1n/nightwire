import pytest

from test_shorts_model import PLANNED, SHORT, write
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


def _designs():
    from narrator.designs import Design
    return {"saeko-kirigaya": Design(name="Saeko", kind="character", source="t", tags="black hair", status="approved"),
            "rin-kageyama": Design(name="Rin", kind="character", source="t", tags="pink hair tips", status="approved"),
            "mama-satos-izakaya": Design(name="Izakaya", kind="location", source="t", tags="izakaya counter", status="approved")}


LOCKED = SHORT + '\n[locks]\nC1 = "chrome prosthetic hand"\nC2 = "torn denim jacket"\n'


def test_still_locks_go_into_each_characters_area_prompt(tmp_path):
    s = load_short(write(tmp_path, short=LOCKED, shot=PLANNED))  # C2 screen-left (node 50), C1 screen-right (node 53)
    wf = stills.still_workflow(s, s.shots[0], _designs(), 703)
    assert "torn denim jacket" in wf["50"]["inputs"]["text"] and "chrome prosthetic hand" not in wf["50"]["inputs"]["text"]
    assert "chrome prosthetic hand" in wf["53"]["inputs"]["text"]


def test_still_one_character_gets_its_lock(tmp_path):
    one = PLANNED.replace('C1 = "foreground screen-right, back of head"\n', "")
    s = load_short(write(tmp_path, short=LOCKED, shot=one))
    wf = stills.still_workflow(s, s.shots[0], _designs(), 703)
    assert "torn denim jacket" in wf["6"]["inputs"]["text"] and "pink hair tips" in wf["6"]["inputs"]["text"]


def test_still_without_frame_is_a_clear_error(tmp_path):
    s = load_short(write(tmp_path))  # old shot: no [frame]
    with pytest.raises(ValueError, match=r"shot S01 has no \[frame\]; fill it before rendering a still"):
        stills.still_workflow(s, s.shots[0], _designs(), 703)


def test_still_more_than_two_in_frame_uses_first_two(tmp_path):
    from narrator.designs import Design
    three = SHORT.replace('C2 = "rin-kageyama"', 'C2 = "rin-kageyama"\nC3 = "mama-sato"')
    shot = PLANNED.replace('C1 = "foreground screen-right, back of head"\n',
                           'C1 = "foreground screen-right, back of head"\nC3 = "screen-right, far back"\n')
    s = load_short(write(tmp_path, short=three, shot=shot))
    assert stills.in_frame_order(s.shots[0]) == ["C2", "C1", "C3"]
    d = _designs() | {"mama-sato": Design(name="Mama", kind="character", source="t", tags="apron", status="approved")}
    wf = stills.still_workflow(s, s.shots[0], d, 703)
    assert "apron" not in " ".join(str(n["inputs"].get("text", "")) for n in wf.values() if isinstance(n, dict) and "inputs" in n)


def test_run_without_jobs_skips_gpu_etiquette(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not touch the GPU")
    monkeypatch.setattr("tools.design_studio._gpu_etiquette", boom)
    assert stills.run([], "http://nowhere") == []
