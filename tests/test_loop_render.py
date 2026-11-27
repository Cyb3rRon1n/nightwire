import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.loop_still.render import Options, render

W, H = 160, 112


def _still(tmp_path, character=True):
    rng = np.random.default_rng(0)
    img = (rng.random((H, W, 3)) * 40 + 20).astype(np.uint8)
    img[10:30, 10:50] = (255, 80, 250)    # a neon sign
    img[60:70, 120:150] = (60, 220, 255)  # a lit window
    p = tmp_path / "scene.png"
    matte = np.zeros((H, W), np.uint8)
    if character:
        img[30:105, 70:100] = (90, 110, 150)
        img[30:60, 66:104] = (20, 20, 30)     # hair
        img[38:50, 78:92] = (170, 190, 230)   # face
        matte[30:105, 66:104] = 255
        hair = np.zeros_like(matte); hair[30:60, 66:104] = 255; hair[38:50, 78:92] = 0
        face = np.zeros_like(matte); face[38:50, 78:92] = 255
        coat = np.zeros_like(matte); coat[60:105, 70:100] = 255
        for name, m in (("hair", hair), ("coat", coat), ("face", face)):
            cv2.imwrite(str(tmp_path / f"scene.{name}.png"), m)
    cv2.imwrite(str(p), img)
    cv2.imwrite(str(tmp_path / "scene.matte.png"), matte)
    return p


def _opts(tmp_path, still, **kw):
    base = dict(still=still, seconds=2, fps=12, size=f"{W}x{H}", rain="steady", lights=True, fog=True,
                plate="telea", out=tmp_path / "out")
    base.update(kw)
    return Options(**base)


def test_render_writes_all_outputs_and_ffprobe_reads_them(tmp_path):
    out = render(_opts(tmp_path, _still(tmp_path)))
    for name in ("master.mkv", "loop.mp4", "preview3x.mp4", "poster.jpg", "meta.json"):
        assert (out / name).exists(), name
    for name in ("master.mkv", "loop.mp4"):
        n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(out / name)], capture_output=True, text=True)
        assert n.stdout.strip() == "24"


def test_meta_has_check_results_and_cycles(tmp_path):
    meta = json.loads((render(_opts(tmp_path, _still(tmp_path))) / "meta.json").read_text())
    assert meta["checks"]["face_max_diff"] == 0
    assert {"seam_ratio", "repeat_score", "halo_ratio", "stretch_min", "passed"} <= meta["checks"].keys()
    assert "hair" in meta["cycles"] and meta["options"]["seed"] == 1


def test_still_character_holds_the_whole_matte_core(tmp_path):
    meta = json.loads((render(_opts(tmp_path, _still(tmp_path), still_character=True)) / "meta.json").read_text())
    assert meta["checks"]["face_max_diff"] == 0 and meta["cycles"].get("hair") is None
    assert meta["held"] == "matte core"


def test_no_character_still_renders(tmp_path):
    meta = json.loads((render(_opts(tmp_path, _still(tmp_path, character=False))) / "meta.json").read_text())
    assert meta["checks"]["face_max_diff"] is None and meta["checks"]["halo_ratio"] is None


def test_same_args_same_frames(tmp_path):
    still = _still(tmp_path)
    a = json.loads((render(_opts(tmp_path, still, out=tmp_path / "a")) / "meta.json").read_text())["frames_sha1"]
    b = json.loads((render(_opts(tmp_path, still, out=tmp_path / "b")) / "meta.json").read_text())["frames_sha1"]
    assert a == b


def test_blink_flag_without_patches_warns_and_continues(tmp_path, capsys):
    out = render(_opts(tmp_path, _still(tmp_path), blink=True))
    assert (out / "loop.mp4").exists() and "blink" in capsys.readouterr().out.lower()


def test_frames_only_writes_pngs(tmp_path):
    out = render(_opts(tmp_path, _still(tmp_path), frames_only=3))
    assert sorted(p.name for p in out.glob("*.png")) == ["0000.png", "0001.png", "0002.png"]


def test_cli_defaults_match_the_spec():
    from tools.loop_still.__main__ import parse
    o = parse(["x.png"])
    assert (o.seconds, o.fps, o.size, o.rain, o.near_rain, o.edge_tint, o.blink) == (20, 24, "1920x1338", "heavy",
                                                                                    True, True, None)
    assert o.motion == "hair,coat,breath" and not o.still_character
    assert parse(["x.png", "--no-blink", "--still-character"]).blink is False


def test_face_on_her_outline_stays_exact_with_edge_tint(tmp_path):
    # Final review: the edge tint and the edge clean-up both touched a face that sits on her outline.
    p = _still(tmp_path)
    img = cv2.imread(str(p))
    img[26:30, 60:110] = (255, 80, 250)  # neon right above her head
    img[30:42, 78:92] = (170, 190, 230)  # the face now touches the top of the matte
    cv2.imwrite(str(p), img)
    face = np.zeros((H, W), np.uint8); face[30:42, 78:92] = 255
    cv2.imwrite(str(tmp_path / "scene.face.png"), face)
    out = render(_opts(tmp_path, p, rain="none", fog=False, edge_tint=True, frames_only=4))
    for k in range(4):
        f = cv2.imread(str(out / f"{k:04d}.png"))
        assert np.array_equal(f[30:42, 78:92], img[30:42, 78:92]), k


def test_defaults_are_preset_b_the_owners_pick():
    """Owner 2026-11-26 picked preset B: heavy rain, breathing neon, edge glow, no fog."""
    from tools.loop_still.__main__ import parse
    o = parse(["x.png"])
    assert (o.rain, o.lights, o.edge_tint, o.fog) == ("heavy", True, True, False)
    assert Options(still=Path("x.png")).rain == "heavy"
    o = parse(["x.png", "--no-lights", "--no-edge-tint", "--rain", "steady"])
    assert (o.rain, o.lights, o.edge_tint) == ("steady", False, False)


def test_realism_defaults_on():
    from tools.loop_still.__main__ import parse
    o = parse(["x.png"])
    assert (o.ripples, o.bloom, o.lit_rain, o.car, o.grain, o.mirror) == (True, True, True, True, True, False)
    o = parse(["x.png", "--no-ripples", "--no-grain", "--mirror"])
    assert (o.ripples, o.grain, o.mirror) == (False, False, True)


def test_render_with_realism_passes_checks(tmp_path):
    still = _still(tmp_path)
    out = render(_opts(tmp_path, still, seconds=8, rain="heavy", ground=0.7, mirror=True))
    meta = json.loads((out / "meta.json").read_text())
    c = meta["checks"]
    assert c["face_max_diff"] == 0 and c["ripples_on_her"] == 0, c
    assert c["passed"], c
    assert "car" not in " ".join(meta["notes"])  # 8 s fits the car
    off = render(_opts(tmp_path, still, seconds=8, rain="heavy", ground=0.7, ripples=False, bloom=False,
                       lit_rain=False, car=False, grain=False, out=tmp_path / "off"))
    assert json.loads((off / "meta.json").read_text())["frames_sha1"] != meta["frames_sha1"]


def test_car_skipped_on_short_loop(tmp_path):
    meta = json.loads((render(_opts(tmp_path, _still(tmp_path), seconds=2)) / "meta.json").read_text())
    assert any("car" in n for n in meta["notes"])


def test_car_needs_lights(tmp_path):
    meta = json.loads((render(_opts(tmp_path, _still(tmp_path), seconds=8, lights=False)) / "meta.json").read_text())
    assert any("car" in n and "lights" in n for n in meta["notes"])
