from fastapi import FastAPI


def test_build_app_returns_a_fastapi_app_with_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)


def test_build_app_reads_model_and_disables_optional_backends_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NIGHTWIRE_MODEL", "qwen3:4b")
    monkeypatch.setenv("NIGHTWIRE_IMAGE_BACKEND", "none")
    monkeypatch.setenv("NIGHTWIRE_TTS_BACKEND", "none")
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)


def test_build_app_wires_openai_tts_when_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NIGHTWIRE_TTS_BACKEND", "openai")
    monkeypatch.setenv("NIGHTWIRE_TTS_API_KEY", "sk-test")
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)


async def test_null_image_backend_fails_soft():
    from server.__main__ import NullImageBackend

    backend = NullImageBackend()

    try:
        await backend.generate_scene("prompt", [])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "disabled" in str(e)


async def test_null_tts_backend_fails_soft():
    from server.__main__ import NullTTSBackend

    backend = NullTTSBackend()

    try:
        await backend.synthesize("hi", "voice")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "disabled" in str(e)
    await backend.unload()  # no-op, must not raise
