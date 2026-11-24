import json
import shutil
import subprocess

import pytest
from PIL import Image

from engine.persistence import JSONFileSessionStore
from tests.test_referee import _session
from tools import recap as render


def _saved(tmp_path):
    s = _session()
    s.session_id = "night"
    Image.new("RGB", (64, 40), (200, 40, 40)).save(tmp_path / "scene1.png")
    s.log += ["p1: I look around.", "Rain on the lanterns. More rain.", "[image: scene1.png]",
              "p1: I sit at the bar.", "Mama Sato: Sit down, child, before you fall down.",
              "p1: I go to the docks.", "Cranes groan.", "[image: missing.png]"]
    s.trail = [[1, "Ikebe Low"], [2, "Mama Sato's izakaya"], [3, "Kuroshio Docks"]]
    s.promises = [{"who": "Old Hara", "what": "bring tea"}]
    JSONFileSessionStore(tmp_path).save(s)
    return tmp_path / "night.json"


def test_html_has_every_panel_facts_and_copied_images(tmp_path):
    out = tmp_path / "out"
    (page,) = render.build(_saved(tmp_path), out, video=False)
    text = page.read_text()
    for bit in ("Rain on the lanterns.", "Sit down, child, before you fall down.", "Cranes groan.",
                "Rook: I sit at the bar.", "Old Hara: bring tea", "Ikebe Low"):
        assert bit in text
    assert (out / "img" / f"{tmp_path.name}-scene1.png").exists()
    assert (out / "img" / "character_art-mama-sato.jpg").exists()
    assert "missing.png" not in text
    assert (out / "img" / "place_art-kuroshio-docks.jpg").exists()  # its scene image is gone: the place art stands in


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="needs ffmpeg")
def test_video_lasts_hold_times_panels(tmp_path):
    out = tmp_path / "out"
    _, video = render.build(_saved(tmp_path), out)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
                           capture_output=True, text=True, check=True)
    assert abs(float(json.loads(probe.stdout)["format"]["duration"]) - 3 * render.HOLD_S) < 0.3


def test_art_paths_from_the_log_stay_inside_their_roots(tmp_path):
    secret = tmp_path.parent / "secret.png"
    Image.new("RGB", (4, 4)).save(secret)
    (tmp_path / "notes.txt").write_text("x")
    assert render.source(f"../{secret.name}", tmp_path) is None
    assert render.source(str(secret), tmp_path) is None
    assert render.source("notes.txt", tmp_path) is None
    assert render.source("place-art/../../../pyproject.toml", tmp_path) is None
    assert render.source("place-art/ikebe-low.jpg", tmp_path) is not None


def test_no_turns_is_a_value_error_not_an_exit(tmp_path):
    s = _session()
    s.session_id = "empty"
    JSONFileSessionStore(tmp_path).save(s)
    with pytest.raises(ValueError):
        render.build(tmp_path / "empty.json", tmp_path / "out", video=False)
