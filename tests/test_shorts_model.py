from pathlib import Path

import pytest

from narrator.designs import Design
from tools.shorts.model import load_short, validate_short

SHORT = '''
title = "Last orders"
logline = "Saeko pays Rin's tab and asks one question too many."
place = "mama-satos-izakaya"
style = "anime cinematic, neon night, rain on the windows"
budget_usd = 25.0
beats = ["anomaly: Rin's tab is already paid"]

[cast]
C1 = "saeko-kirigaya"
C2 = "rin-kageyama"

[[room.blocks]]
name = "counter"
size = [4.0, 0.6, 1.0]
at = [0.0, 1.2, 0.0]

[figures.C1]
tier = "mannequin"
pose = "sit"
keys = [[0.0, -0.6, 0.5, 90.0]]

[figures.C2]
tier = "capsule"
pose = "stand"
keys = [[0.0, 0.8, 0.5, 270.0], [4.0, 0.4, 0.5, 270.0]]
'''

SHOT = '''
id = "S01"
start = 0.0
end = 5.0
summary = "slow push in over C1's right shoulder to C2 medium close-up"
lens = 35.0
camera = [
  { t = 0.0, at = [-1.8, -1.5, 1.4], look = [0.6, 0.5, 1.2] },
  { t = 5.0, at = [-1.1, -0.6, 1.35], look = [0.5, 0.5, 1.3] },
]

[state]
C1 = "tired, amused, decided"
C2 = "guarded, pretending not to care"

[[beats]]
t = [0.0, 2.5]
text = "C1 MCU from behind, C2 enters frame right in background, looks at C1"

[[acting]]
who = "C2"
t = [1.0, 3.5]
goal = "find out why her tab is paid"
emotion = "suspicion cracking into embarrassment"
trigger = "paid"

[[lines]]
who = "C2"
t = 1.2
text = "Who paid it?"
disfluency = "block"
on_word = "Who"
'''


def write(tmp_path: Path, short=SHORT, shot=SHOT) -> Path:
    (tmp_path / "shots").mkdir(parents=True)
    (tmp_path / "short.toml").write_text(short)
    (tmp_path / "shots" / "S01.toml").write_text(shot)
    return tmp_path


def designs():
    return {s: Design(name=n, kind="character", source="t", tags="x", status="approved")
            for s, n in (("saeko-kirigaya", "Saeko Kirigaya"), ("rin-kageyama", "Rin Kageyama"))} | {
        "mama-satos-izakaya": Design(name="Mama Sato's Izakaya", kind="location", source="t", tags="x", status="approved")}


def test_load_short_reads_cast_figures_and_shots(tmp_path):
    s = load_short(write(tmp_path))
    assert s.slug == tmp_path.name
    assert s.cast == {"C1": "saeko-kirigaya", "C2": "rin-kageyama"}
    assert s.figures["C2"].keys[1] == (4.0, 0.4, 0.5, 270.0)
    shot = s.shots[0]
    assert shot.id == "S01" and shot.duration == 5.0
    assert shot.camera[1].at == (-1.1, -0.6, 1.35)
    assert shot.lines[0].disfluency == "block"
    assert shot.acting[0].t == (1.0, 3.5)


def test_valid_short_has_no_problems(tmp_path):
    assert validate_short(load_short(write(tmp_path)), designs()) == []


@pytest.mark.parametrize("bad, expected", [
    (SHOT.replace('who = "C2"\nt = 1.2', 'who = "C9"\nt = 1.2'), "unknown cast id C9"),
    (SHOT.replace("end = 5.0", "end = 31.0"), "longer than 30"),
    (SHOT.replace('disfluency = "block"', 'disfluency = "stutter"'), "disfluency"),
    (SHOT.replace("t = 1.2", "t = 9.0"), "outside the shot"),
    (SHOT.replace("{ t = 5.0, at", "{ t = 9.0, at"), "shot S01: camera key at 9.0s is outside 0..5.0s (camera times are relative to the shot start)"),
])
def test_validate_short_reports_problems(tmp_path, bad, expected):
    problems = validate_short(load_short(write(tmp_path, shot=bad)), designs())
    assert any(expected in p for p in problems), problems


def test_unapproved_or_missing_design_is_a_problem(tmp_path):
    d = designs()
    d["rin-kageyama"].status = "draft"
    del d["mama-satos-izakaya"]
    problems = validate_short(load_short(write(tmp_path)), d)
    assert any("rin-kageyama is not approved" in p for p in problems)
    assert any("place mama-satos-izakaya" in p for p in problems)
