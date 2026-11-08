from test_shorts_model import SHORT, SHOT
from tools.shorts.__main__ import main


def setup(tmp_path, monkeypatch, shot=SHOT):
    script = tmp_path / "script" / "pilot"
    (script / "shots").mkdir(parents=True)
    (script / "short.toml").write_text(SHORT)
    (script / "shots" / "S01.toml").write_text(shot)
    monkeypatch.setattr("tools.shorts.__main__.SHORTS_DIR", tmp_path / "script")
    monkeypatch.setenv("NIGHTWIRE_DESIGN_DIR", str(tmp_path / "design-data"))
    from test_shorts_model import designs
    monkeypatch.setattr("tools.shorts.__main__.load_designs", lambda: designs())


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
