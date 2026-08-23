from fastapi import FastAPI


def test_build_app_returns_a_fastapi_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)
