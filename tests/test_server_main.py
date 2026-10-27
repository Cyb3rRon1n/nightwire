from fastapi import FastAPI


def test_build_app_returns_a_fastapi_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)


def test_system_prompt_ends_with_the_world_primer_and_glossary():
    from narrator.world import kuroshio
    from server.__main__ import build_system_prompt

    prompt = build_system_prompt()

    assert prompt.startswith("You are a cyberpunk tabletop game master.")
    assert prompt.endswith(kuroshio().system_block())


def test_build_app_gives_the_narrator_the_world_system_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import server.__main__ as main

    class Recorder:
        system_prompt = ""

    recorder = Recorder()
    monkeypatch.setattr(main, "create_narrator_backend", lambda: recorder)

    main.build_app()

    assert recorder.system_prompt == main.build_system_prompt()


def test_system_prompt_tells_the_narrator_to_stop_before_the_roll_result():
    from server.__main__ import build_system_prompt

    prompt = build_system_prompt()

    assert "narrate only the lead-up" in prompt
    assert "never contradict it" in prompt
