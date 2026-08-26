from deploy.cli import confirm, main
from deploy.tiers import Recommendation


def _rec(**overrides):
    defaults = dict(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="kokoro", reasoning="test reasoning")
    defaults.update(overrides)
    return Recommendation(**defaults)


def test_confirm_accepts_default_on_enter():
    result = confirm(_rec(), input_fn=lambda prompt: "")
    assert result.ollama_model == "qwen3:8b"


def test_confirm_raises_systemexit_on_no():
    try:
        confirm(_rec(), input_fn=lambda prompt: "n")
        assert False, "expected SystemExit"
    except SystemExit:
        pass


def test_confirm_customize_overrides_model():
    inputs = iter(["customize", "qwen3:4b", "n", "hosted"])
    result = confirm(_rec(), input_fn=lambda prompt: next(inputs))
    assert result.ollama_model == "qwen3:4b"
    assert result.enable_image_gen is False
    assert result.tts_backend == "hosted"


def test_main_detect_prints_and_returns_zero(capsys):
    code = main(["detect"])
    captured = capsys.readouterr()
    assert code == 0
    assert "gpu_vendor" in captured.out


def test_main_install_client_calls_client_install(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("deploy.cli.run_client_install", lambda server_url, frontend_dir=None: calls.append(server_url))
    inputs = iter(["ws://localhost:8000"])

    code = main(["install", "--role", "client"], input_fn=lambda prompt: next(inputs))

    assert code == 0
    assert calls == ["ws://localhost:8000"]


def test_main_install_server_skips_image_gen_when_no_url_and_calls_server_install(monkeypatch):
    captured = {}

    def fake_server_install(profile, recommendation, siblings_dir, units_dir, **kwargs):
        captured["recommendation"] = recommendation
        captured["kwargs"] = kwargs
        return {"NIGHTWIRE_MODEL": recommendation.ollama_model}

    monkeypatch.setattr("deploy.cli.run_server_install", fake_server_install)
    inputs = iter(["", "", ""])  # confirm default, blank image-gen url, (no tts prompt since kokoro)

    code = main(["install", "--role", "server"], input_fn=lambda prompt: next(inputs))

    assert code == 0
    assert captured["kwargs"]["image_gen_repo_url"] is None
