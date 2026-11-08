from tools.shorts.backends.manual import import_inbox, write_bundle
from tools.shorts.takes import Ledger


def test_bundle_has_prompt_and_named_refs(tmp_path):
    ref = tmp_path / "turnaround.png"
    ref.write_bytes(b"png")
    shot = tmp_path / "S01"
    (shot / "bundle").mkdir(parents=True)
    (shot / "bundle" / "stale.png").write_bytes(b"old")
    out = write_bundle(shot, "the prompt", [("C1_turnaround.png", ref)])
    assert (out / "prompt.txt").read_text() == "the prompt"
    assert (out / "C1_turnaround.png").read_bytes() == b"png"
    assert not (out / "stale.png").exists()


def test_inbox_files_takes_and_records_cost(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "dreamina_123.mp4").write_bytes(b"v")
    led = Ledger(tmp_path / "costs.json")
    assert import_inbox(tmp_path, "S01", 0.35, "seedance-2.5", led) == ["t001"]
    assert (tmp_path / "shots" / "S01" / "takes" / "t001.mp4").exists()
    assert (tmp_path / "inbox" / "done" / "dreamina_123.mp4").exists()
    assert led.total() == 0.35


def test_second_import_files_nothing(tmp_path):
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "a.mp4").write_bytes(b"v")
    led = Ledger(tmp_path / "costs.json")
    assert import_inbox(tmp_path, "S01", 0.35, "seedance-2.5", led) == ["t001"]
    assert import_inbox(tmp_path, "S01", 0.35, "seedance-2.5", led) == []
    assert led.total() == 0.35


def test_failed_move_does_not_double_charge(tmp_path, monkeypatch):
    import shutil

    import pytest

    real_move = shutil.move
    calls = []

    def flaky_move(src, dst):
        calls.append(src)
        if len(calls) == 1:
            raise OSError("disk hiccup")
        return real_move(src, dst)

    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "a.mp4").write_bytes(b"v")
    led = Ledger(tmp_path / "costs.json")
    monkeypatch.setattr(shutil, "move", flaky_move)
    with pytest.raises(OSError):
        import_inbox(tmp_path, "S01", 0.35, "seedance-2.5", led)
    assert import_inbox(tmp_path, "S01", 0.35, "seedance-2.5", led) == ["t001"]
    assert led.total() == 0.35
