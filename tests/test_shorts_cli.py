import pytest
import json

from test_shorts_model import PLANNED, SHORT, SHOT
from tools.shorts.__main__ import main


SCENE = '''
[scene]
time = "late night"
weather = "rain on the windows, wet street"
set = "a narrow izakaya"

[wardrobe]
C1 = "navy jacket zipped"
C2 = "red coat"
'''
# The reference-mode planned shot with a plate: passes the package checks once the plate and scene are approved.
PACKAGED = PLANNED.replace("lens = 35.0", 'lens = 35.0\nmode = "reference"\nplate = "door"')


def approvals(work, per_shot):
    """Write approvals.json with the scene bible approved, plus the given per-shot fingerprints."""
    from tools.shorts.approve import scene_fp
    from tools.shorts.model import load_short
    work.mkdir(parents=True, exist_ok=True)
    fp = scene_fp(load_short(work.parent.parent.parent / "script" / "pilot"))
    (work / "approvals.json").write_text(json.dumps({**per_shot, "SCENE": {fp: {"verdict": "keep"}}}))


def setup(tmp_path, monkeypatch, shot=PACKAGED, approved=True):
    script = tmp_path / "script" / "pilot"
    (script / "shots").mkdir(parents=True)
    (script / "short.toml").write_text(SHORT + SCENE)
    plates = tmp_path / "plates"
    plates.mkdir()
    (plates / "mama-satos-izakaya.toml").write_text('[[plate]]\nname = "door"\nview = "toward the door"\n')
    monkeypatch.setattr("tools.shorts.plates.PLATES_ROOT", plates)
    monkeypatch.setattr("tools.shorts.__main__._images_api", lambda: _api_with_scene(tmp_path))  # never touch the network
    (script / "shots" / "S01.toml").write_text(shot)
    monkeypatch.setattr("tools.shorts.__main__.SHORTS_DIR", tmp_path / "script")
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(tmp_path / "design-data"))
    from test_shorts_model import designs
    monkeypatch.setattr("tools.shorts.__main__.load_designs", lambda: designs())
    if approved:
        monkeypatch.setattr("tools.shorts.approve.approval", lambda *a: {"verdict": "keep"})
    # Placeholder references so planned shots pass pre-flight's "every expected ref exists" check.
    from PIL import Image
    from tools.shorts.prompt import CHARACTER_SHEETS
    dd = tmp_path / "design-data"
    for slug in ("saeko-kirigaya", "rin-kageyama"):
        (dd / slug).mkdir(parents=True, exist_ok=True)
        for f in CHARACTER_SHEETS:
            Image.new("RGB", (8, 8)).save(dd / slug / f)
    (dd / "mama-satos-izakaya").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(dd / "mama-satos-izakaya" / "play.png")
    sd = dd / "shorts" / "pilot" / "shots" / "S01"
    sd.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(sd / "board-start.png")
    (dd / "mama-satos-izakaya" / "plates").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8)).save(dd / "mama-satos-izakaya" / "plates" / "door.png")
    approvals(dd / "shorts" / "pilot", {})


def test_check_ok_and_prompt_prints_layers(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, shot=PACKAGED)
    assert main(["check", "pilot"]) == 0
    assert main(["prompt", "pilot", "S01"]) == 0
    assert "C1 = Saeko Kirigaya" in capsys.readouterr().out


def test_check_fails_on_problems(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, shot=SHOT.replace("end = 5.0", "end = 40.0"))
    assert main(["check", "pilot"]) == 1


def test_bundle_writes_prompt(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    assert main(["bundle", "pilot", "S01"]) == 0
    assert (tmp_path / "design-data" / "shorts" / "pilot" / "shots" / "S01" / "bundle" / "prompt.txt").exists()


def test_submit_without_yes_and_no_answer_spends_nothing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(1))
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    from tools.shorts.backends import fal
    model = next(iter(fal.MODELS))
    assert main(["submit", "pilot", "S01", "--model", model]) == 1
    assert called == []


def test_unknown_shot_is_clear_error(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["prompt", "pilot", "S99"]) == 1
    assert "S99" in capsys.readouterr().err


def test_submit_unknown_model_rejected(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["submit", "pilot", "S01", "--model", "veo", "--yes"]) == 1
    assert "veo" in capsys.readouterr().err


def test_submit_reports_value_and_budget_errors(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    from tools.shorts.backends import fal
    from tools.shorts.takes import BudgetError
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    for exc in (ValueError("too short"), BudgetError("over budget")):
        def boom(*a, **k):
            raise exc
        monkeypatch.setattr("tools.shorts.backends.fal.run_take", boom)
        assert main(["submit", "pilot", "S01", "--model", next(iter(fal.MODELS)), "--yes"]) == 1
        assert str(exc) in capsys.readouterr().err


def test_unknown_slug_is_clear_error(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["check", "nonexistent"]) == 1
    assert "nonexistent" in capsys.readouterr().err


def test_submit_missing_key_and_closed_stdin_are_clean_errors(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    from tools.shorts.backends import fal

    def no_key(*a):
        raise RuntimeError("FAL_KEY missing")
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", no_key)
    model = next(iter(fal.MODELS))
    assert main(["submit", "pilot", "S01", "--model", model, "--yes"]) == 1
    assert "FAL_KEY" in capsys.readouterr().err

    def eof(_):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    assert main(["submit", "pilot", "S01", "--model", model]) == 1
    assert "--yes" in capsys.readouterr().err


def test_submit_kling_sends_board_and_plate_and_drops_its_skip_list(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    got = {}
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: got.update(refs=a[4], seconds=a[5]) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "kling-3", "--yes"]) == 0
    labels = [l for l, _ in got["refs"]]
    assert "start_frame.png" in labels and "place.png" in labels and "C1_portrait.png" not in labels
    assert "C1_portrait.png" in capsys.readouterr().out
    got.clear()
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.5", "--yes"]) == 0
    assert "C1_portrait.png" in [l for l, _ in got["refs"]]


def test_submit_estimate_uses_rounded_seconds(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.5", "--seconds", "7.5", "--yes"]) == 0
    assert "8s" in capsys.readouterr().out


def test_greybox_clears_stale_frames_but_not_takes(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    sd = tmp_path / "design-data" / "shorts" / "pilot" / "shots" / "S01"
    (sd / "frames").mkdir(parents=True)
    (sd / "frames" / "0099.png").write_bytes(b"old")
    (sd / "takes").mkdir()
    (sd / "takes" / "t001.mp4").write_bytes(b"t")
    seen = []
    def fake_run(work, slug):
        seen.append((sd / "frames").exists())
    monkeypatch.setattr("tools.shorts.remote.run", fake_run)
    monkeypatch.setattr("tools.shorts.__main__.subprocess.run", lambda *a, **k: seen.append("run"))
    monkeypatch.setattr("tools.shorts.remote.encode", lambda *a: ["x"])
    assert main(["greybox", "pilot"]) == 0
    assert seen[0] is False and not (sd / "frames").exists()
    assert (sd / "takes" / "t001.mp4").read_bytes() == b"t"


def test_preflight_reports_missing_fields(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, shot=SHOT)
    assert main(["preflight", "pilot", "--model", "seedance-2.0-fast"]) == 1
    assert "missing size" in capsys.readouterr().out


def test_submit_refuses_unapproved_and_stale(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(k) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert "not approved" in capsys.readouterr().err and called == []
    work = tmp_path / "design-data" / "shorts" / "pilot"
    approvals(work, {"S01": {"0000000000": {"verdict": "keep"}}})  # an old fingerprint
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1 and called == []


def test_submit_override_is_logged(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    got = {}
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: got.update(k) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes", "--override", "owner said go"]) == 0
    assert got["note"] == "override: owner said go" and len(got["meta"]["fp"]) == 10


def test_submit_blocked_by_preflight_spends_nothing(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, shot=SHOT)  # the unplanned shot fails pre-flight
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(1))
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert "pre-flight failed" in capsys.readouterr().err and called == []


def test_submit_retry_cap(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    monkeypatch.setattr("tools.shorts.approve.attempts", lambda *a: 3)
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: "t004")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert "cap 3" in capsys.readouterr().err


def test_preflight_unknown_model_rejected(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["preflight", "pilot", "--model", "veo"]) == 1
    assert "unknown model 'veo'" in capsys.readouterr().err


def test_sheet_fingerprint_matches_submit(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    assert main(["sheet", "pilot", "--model", "seedance-2.0-fast"]) == 0
    data = json.loads((tmp_path / "design-data" / "shorts" / "_site" / "pilot" / "sheet.json").read_text())
    fp = data["shots"][0]["fp"]
    work = tmp_path / "design-data" / "shorts" / "pilot"
    monkeypatch.setattr("tools.shorts.__main__._images_api", lambda: _api_with_scene(tmp_path, {f"plan--pilot--s01--{fp}": {"verdict": "keep"}}))
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 0


def test_sheet_unknown_model_rejected(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["sheet", "pilot", "--model", "veo"]) == 1
    assert "unknown model 'veo'" in capsys.readouterr().err


def test_preflight_reports_missing_cast_sheet(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["preflight", "pilot", "--model", "seedance-2.0-fast"]) == 0
    (tmp_path / "design-data" / "rin-kageyama" / "portrait.png").unlink()
    assert main(["preflight", "pilot", "--model", "seedance-2.0-fast"]) == 1
    out = capsys.readouterr().out
    assert "C2_portrait.png: file missing" in out and "floorplan" not in out  # floor plan is optional


def test_submit_with_other_seconds_than_approved_is_refused(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    assert main(["sheet", "pilot", "--model", "seedance-2.0-fast"]) == 0
    fp = json.loads((tmp_path / "design-data" / "shorts" / "_site" / "pilot" / "sheet.json").read_text())["shots"][0]["fp"]
    monkeypatch.setattr("tools.shorts.__main__._images_api", lambda: _api_with_scene(tmp_path, {f"plan--pilot--s01--{fp}": {"verdict": "keep"}}))
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(a[5]) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--seconds", "8", "--yes"]) == 1
    assert "not approved" in capsys.readouterr().err and called == []
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--seconds", "5", "--yes"]) == 0 and called == [5]


def test_stills_skips_shot_without_frame_with_clear_message(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, shot=SHOT)  # old shot: no [frame]
    monkeypatch.setattr("tools.design_scenes.gpu_busy", lambda url: False)
    seen = []
    monkeypatch.setattr("tools.shorts.stills.run", lambda jobs, url: seen.append(jobs) or [])
    assert main(["stills", "pilot"]) == 1
    assert "shot S01 has no [frame]; fill it before rendering a still" in capsys.readouterr().err and seen == [[]]


def test_submit_blank_override_is_refused(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, approved=False)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(k) or "t001")
    for blank in ("", "   "):
        assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes", "--override", blank]) == 1
        assert "--override needs a reason" in capsys.readouterr().err and called == []
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes", "--override", "  owner said go  "]) == 0
    assert called[0]["note"] == "override: owner said go"


def test_submit_network_error_is_clean_and_says_money_may_be_spent(tmp_path, monkeypatch, capsys):
    import httpx
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "secret-key-value")
    for exc in (TimeoutError("fal took too long"), httpx.ConnectError("refused")):
        def boom(*a, **k):
            raise exc
        monkeypatch.setattr("tools.shorts.backends.fal.run_take", boom)
        assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
        out = capsys.readouterr()
        assert "may already be spent" in out.err and "costs.json" in out.err and "secret-key-value" not in out.err + out.out


def test_i2v_sends_and_fingerprints_only_keyframes(tmp_path, monkeypatch):
    from test_shorts_model import designs
    from tools.shorts.__main__ import _preflight, _short
    setup(tmp_path, monkeypatch, shot=PACKAGED.replace('mode = "reference"', 'mode = "i2v"\nmotion = "C2 turns."'))
    sd = tmp_path / "design-data" / "shorts" / "pilot" / "shots" / "S01"
    (sd / "keyframe-start.png").write_bytes(b"k")
    s = _short("pilot")
    _, _, refs = _preflight(s, s.shots[0], "seedance-2.0-fast", designs())
    assert [label for label, _ in refs] == ["keyframe-start.png"]


def test_i2v_sheet_fp_equals_submit_fp_and_plate_rerender_changes_it(tmp_path, monkeypatch):
    from test_shorts_model import designs
    from tools.shorts import approve
    from tools.shorts.__main__ import _preflight, _short
    setup(tmp_path, monkeypatch, shot=PACKAGED.replace('mode = "reference"', 'mode = "i2v"\nmotion = "C2 turns."'))
    dd = tmp_path / "design-data"
    (dd / "shorts" / "pilot" / "shots" / "S01" / "keyframe-start.png").write_bytes(b"k")
    assert main(["sheet", "pilot", "--model", "seedance-2.0-fast"]) == 0
    sheet_fp = json.loads((dd / "shorts" / "_site" / "pilot" / "sheet.json").read_text())["shots"][0]["fp"]
    s = _short("pilot")
    _, prompt, refs = _preflight(s, s.shots[0], "seedance-2.0-fast-i2v", designs())
    extra = approve.fp_extra(s, s.shots[0], dd)
    assert approve.fingerprint("seedance-2.0-fast-i2v", prompt, refs, 5, extra) == sheet_fp
    (dd / "mama-satos-izakaya" / "plates" / "door.png").write_bytes(b"new render")
    assert approve.fp_extra(s, s.shots[0], dd) != extra


def test_mode_and_model_kind_must_match(tmp_path, monkeypatch):
    from test_shorts_model import designs
    from tools.shorts.__main__ import _preflight, _short
    setup(tmp_path, monkeypatch, shot=PACKAGED.replace('mode = "reference"', 'mode = "i2v"\nmotion = "C2 turns."'))
    s = _short("pilot")
    assert any("mode i2v needs an -i2v model" in p for p in _preflight(s, s.shots[0], "seedance-2.0-fast", designs())[0].problems)
    assert not any("-i2v model" in p for p in _preflight(s, s.shots[0], "seedance-2.0-fast-i2v", designs())[0].problems)


def test_reference_shot_refuses_i2v_model(tmp_path, monkeypatch):
    from test_shorts_model import designs
    from tools.shorts.__main__ import _preflight, _short
    setup(tmp_path, monkeypatch, shot=PACKAGED)
    s = _short("pilot")
    assert any("mode reference can't use an -i2v model" in p for p in _preflight(s, s.shots[0], "seedance-2.0-fast-i2v", designs())[0].problems)


def test_ledger_sync_cli(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(["ledger-sync", "pilot", "--balance", "3.29"]) == 0
    from tools.shorts.__main__ import _short, _work
    from tools.shorts.takes import Ledger
    assert round(_short("pilot").budget_usd - Ledger(_work("pilot") / "costs.json").total(), 2) == 3.29
    assert "$3.29 left" in capsys.readouterr().out


def test_sheet_uses_per_shot_model_and_matches_submit_fp(tmp_path, monkeypatch, capsys):
    from test_shorts_model import designs
    from tools.shorts import approve
    from tools.shorts.__main__ import _preflight, _short
    from tools.shorts.backends import fal
    setup(tmp_path, monkeypatch, shot=PACKAGED.replace('mode = "reference"', 'mode = "i2v"\nmotion = "C2 turns."'))
    dd = tmp_path / "design-data"
    (dd / "shorts" / "pilot" / "shots" / "S01" / "keyframe-start.png").write_bytes(b"k")
    assert main(["sheet", "pilot", "--model", "seedance-2.0-fast"]) == 0
    shot_json = json.loads((dd / "shorts" / "_site" / "pilot" / "sheet.json").read_text())["shots"][0]
    assert shot_json["model"] == "seedance-2.0-fast-i2v" and not any("-i2v model" in p for p in shot_json["problems"])
    s = _short("pilot")
    _, prompt, refs = _preflight(s, s.shots[0], "seedance-2.0-fast-i2v", designs())
    refs, _ = fal.usable_refs("seedance-2.0-fast-i2v", refs)
    assert approve.fingerprint("seedance-2.0-fast-i2v", prompt, refs, 5, approve.fp_extra(s, s.shots[0], dd)) == shot_json["fp"]
    capsys.readouterr()
    main(["preflight", "pilot", "--model", "seedance-2.0-fast"])  # explicit mismatch is reported, with the fix
    assert "use seedance-2.0-fast-i2v" in capsys.readouterr().out


def test_mode_problem_names_right_model_and_preflight_default_has_none(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, shot=PACKAGED.replace('mode = "reference"', 'mode = "i2v"\nmotion = "C2 turns."'))
    s_toml = tmp_path / "script" / "pilot" / "short.toml"
    s_toml.write_text(s_toml.read_text().replace('budget_usd = 25.0', 'budget_usd = 25.0\nmodel = "seedance-2.0-fast"', 1))
    main(["preflight", "pilot"])
    assert "-i2v model" not in capsys.readouterr().out


def test_ledger_sync_refuses_out_of_range_and_is_idempotent(tmp_path, monkeypatch, capsys):
    from tools.shorts.__main__ import _work
    from tools.shorts.takes import Ledger
    setup(tmp_path, monkeypatch)
    for bad in ("-1", "99"):
        assert main(["ledger-sync", "pilot", "--balance", bad]) == 1
        assert "nothing written" in capsys.readouterr().err
    assert not (_work("pilot") / "costs.json").exists()
    main(["ledger-sync", "pilot", "--balance", "3.29"])
    assert "adjusting ledger by" in capsys.readouterr().out
    t1 = Ledger(_work("pilot") / "costs.json").total()
    main(["ledger-sync", "pilot", "--balance", "3.29"])
    assert Ledger(_work("pilot") / "costs.json").total() == t1


def test_plates_choose_and_busy_gpu_and_unreachable(tmp_path, monkeypatch, capsys):
    import urllib.error
    setup(tmp_path, monkeypatch)
    pdir = tmp_path / "design-data" / "mama-satos-izakaya" / "plates"
    assert main(["plates", "pilot", "--choose", "door", "2"]) == 1  # no candidate yet
    (pdir / "door-c02.png").write_bytes(b"two")
    assert main(["plates", "pilot", "--choose", "door", "2"]) == 0 and (pdir / "door.png").read_bytes() == b"two"
    (pdir / "door.png").unlink()
    monkeypatch.setattr("tools.design_scenes.gpu_busy", lambda url: True)
    assert main(["plates", "pilot"]) == 1
    err = capsys.readouterr().err
    assert "tools.taste" in err and "busy" in err
    def down(url): raise urllib.error.URLError("nope")
    monkeypatch.setattr("tools.design_scenes.gpu_busy", down)
    assert main(["plates", "pilot"]) == 1 and "not reachable" in capsys.readouterr().err


def _api_with_scene(tmp_path, extra=None):
    """The fake review store: the chosen plate and the scene bible approved (plus extra)."""
    from tools.shorts.approve import scene_fp
    from tools.shorts.model import load_short
    from tools.shorts.plates import plate_id
    fp = scene_fp(load_short(tmp_path / "script" / "pilot"))
    plate = tmp_path / "design-data" / "mama-satos-izakaya" / "plates" / "door.png"
    from tools.shorts.approve import board_id
    board = tmp_path / "design-data" / "shorts" / "pilot" / "shots" / "S01" / "board-start.png"
    boards = {board_id("pilot", "S01", board): {"verdict": "keep"}} if board.exists() else {}
    return {**boards, plate_id("mama-satos-izakaya", "door", plate): {"verdict": "keep"}, f"plan--pilot--scene--{fp}": {"verdict": "keep"}, **(extra or {})}


def test_prompt_with_model_in_short_toml(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    toml = tmp_path / "script" / "pilot" / "short.toml"
    toml.write_text('model = "seedance-2.0-fast"\n' + toml.read_text())
    assert main(["prompt", "pilot", "S01"]) == 0
    assert "C1 = Saeko Kirigaya" in capsys.readouterr().out


def test_submit_refreshes_approvals_and_blocks_a_new_reject(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(k) or "t001")
    scene_fp_ = next(k for k in _api_with_scene(tmp_path) if k.startswith("plan--"))
    monkeypatch.setattr("tools.shorts.__main__._images_api", lambda: _api_with_scene(tmp_path))
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 0  # fresh keep
    called.clear()
    # approvals.json still says keep for the scene, but the store now says reject
    monkeypatch.setattr("tools.shorts.__main__._images_api",
                        lambda: _api_with_scene(tmp_path, {scene_fp_: {"verdict": "reject"}}))
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert called == [] and "scene bible not approved" in capsys.readouterr().err


def test_submit_refuses_when_review_store_unreachable(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("tools.shorts.__main__._images_api", lambda: None)
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    called = []
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: called.append(k) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.0-fast", "--yes"]) == 1
    assert called == [] and "can't reach the review store; nothing was spent" in capsys.readouterr().err


def test_preflight_warns_once_when_store_unreachable(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr("tools.shorts.__main__._images_api", lambda: None)
    main(["preflight", "pilot", "--model", "seedance-2.0-fast"])
    assert capsys.readouterr().err.count("review store unreachable: approvals read as missing") == 1


def test_loop_runs_a_local_take_without_asking(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    still = tmp_path / "still.png"
    still.write_bytes(b"png")
    calls = []
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("a free local take must not ask"))
    monkeypatch.setattr("tools.shorts.backends.comfy_video.run_take", lambda *a, **k: calls.append((a, k)) or "t001")
    assert main(["loop", "pilot", "S01", "--still", str(still), "--model", "wan22-flf", "--seed", "3"]) == 0
    (short_dir, shot, model, prompt, got_still, seconds), kw = calls[0]
    assert (shot, model, got_still, seconds, kw["seed"], kw["loop"]) == ("S01", "wan22-flf", still, 5.0, 3, True)
    assert prompt  # the shot's motion, or the default "the city moves" line
    assert "t001" in capsys.readouterr().out


def test_loop_refuses_a_paid_model(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as e:
        main(["loop", "pilot", "S01", "--still", "x.png", "--model", "seedance-2.5"])
    assert e.value.code == 2  # argparse choices: only local models


def test_loop_reports_a_comfy_failure(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    def boom(*a, **k):
        raise RuntimeError("ComfyUI at http://127.0.0.1:8188 unreachable (refused)")
    monkeypatch.setattr("tools.shorts.backends.comfy_video.run_take", boom)
    assert main(["loop", "pilot", "S01", "--still", "x.png", "--model", "ltx23", "--no-loop"]) == 1
    assert "unreachable" in capsys.readouterr().err
