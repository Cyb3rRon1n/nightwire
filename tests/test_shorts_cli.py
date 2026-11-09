import json

from test_shorts_model import PLANNED, SHORT, SHOT
from tools.shorts.__main__ import main


def setup(tmp_path, monkeypatch, shot=PLANNED, approved=True):
    script = tmp_path / "script" / "pilot"
    (script / "shots").mkdir(parents=True)
    (script / "short.toml").write_text(SHORT)
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
    (sd / "greybox.mp4").write_bytes(b"g")


def test_check_ok_and_prompt_prints_layers(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
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


def test_submit_kling_drops_video_refs_and_says_so(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    got = {}
    monkeypatch.setattr("tools.shorts.backends.fal.load_key", lambda *a: "k")
    monkeypatch.setattr("tools.shorts.backends.fal.run_take", lambda *a, **k: got.update(refs=a[4], seconds=a[5]) or "t001")
    assert main(["submit", "pilot", "S01", "--model", "kling-3", "--yes"]) == 0
    assert not [l for l, _ in got["refs"] if l.endswith(".mp4")]
    assert "greybox.mp4" in capsys.readouterr().out
    got.clear()
    assert main(["submit", "pilot", "S01", "--model", "seedance-2.5", "--yes"]) == 0
    assert "greybox.mp4" in [l for l, _ in got["refs"]]


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
    work.mkdir(parents=True, exist_ok=True)
    (work / "approvals.json").write_text('{"S01": {"0000000000": {"verdict": "keep"}}}')  # an old fingerprint
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
    data = json.loads((tmp_path / "design-data" / "shorts" / "_site" / "pilot" / "sheet" / "sheet.json").read_text())
    fp = data["shots"][0]["fp"]
    work = tmp_path / "design-data" / "shorts" / "pilot"
    work.mkdir(parents=True, exist_ok=True)
    (work / "approvals.json").write_text(json.dumps({"S01": {fp: {"verdict": "keep"}}}))
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
    fp = json.loads((tmp_path / "design-data" / "shorts" / "_site" / "pilot" / "sheet" / "sheet.json").read_text())["shots"][0]["fp"]
    (tmp_path / "design-data" / "shorts" / "pilot" / "approvals.json").write_text(json.dumps({"S01": {fp: {"verdict": "keep"}}}))
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
