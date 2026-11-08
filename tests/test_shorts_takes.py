import json

import pytest

from tools.shorts.takes import (BudgetError, Ledger, apply_verdicts, estimate, file_take, next_take_id,
                                take_image_id)


def test_estimate_uses_rate_per_second():
    assert estimate("seedance-2.5", 5) == pytest.approx(5 * 0.473)
    with pytest.raises(KeyError):
        estimate("nope", 5)


def test_ledger_totals_and_refuses_over_budget(tmp_path):
    led = Ledger(tmp_path / "costs.json")
    led.add("S01", "t001", "seedance-2.0-fast", 1.21)
    led.add("S01", "t002", "kling-3", 0.70)
    assert led.total() == pytest.approx(1.91)
    led.check(budget=25, cost=20)
    with pytest.raises(BudgetError, match="25"):
        led.check(budget=25, cost=24)
    assert json.loads((tmp_path / "costs.json").read_text())[0]["take"] == "t001"


def test_take_ids_count_up_and_files_are_written(tmp_path):
    shot = tmp_path / "S01"
    src = tmp_path / "x.mp4"
    src.write_bytes(b"video")
    assert next_take_id(shot) == "t001"
    assert file_take(shot, src, {"model": "kling-3", "cost": 0.7}) == "t001"
    assert file_take(shot, src, {"model": "kling-3", "cost": 0.7}) == "t002"
    assert (shot / "takes" / "t002.mp4").read_bytes() == b"video"
    meta = json.loads((shot / "takes" / "t001.json").read_text())
    assert meta["model"] == "kling-3" and meta["id"] == "t001" and "at" in meta


def test_take_image_id_matches_picks_api_rule():
    import re
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", take_image_id("saeko-rin-izakaya", "S01", "t001"))


def test_apply_verdicts_writes_per_shot_files(tmp_path):
    (tmp_path / "shots" / "S01").mkdir(parents=True)
    api = {take_image_id("pilot", "S01", "t001"): {"verdict": "keep"},
           take_image_id("pilot", "S01", "t002"): {"verdict": "fix", "note": "C2 flips side at 3s"},
           "other--image": {"verdict": "keep"}}
    mine = apply_verdicts(tmp_path, "pilot", api)
    assert len(mine) == 2
    v = json.loads((tmp_path / "shots" / "S01" / "verdicts.json").read_text())
    assert v == {"t001": {"verdict": "keep"}, "t002": {"verdict": "fix", "note": "C2 flips side at 3s"}}


def test_take_ids_follow_highest_existing_number(tmp_path):
    shot = tmp_path / "S01"
    (shot / "takes").mkdir(parents=True)
    for n in (1, 2):
        (shot / "takes" / f"t{n:03d}.mp4").write_bytes(b"v")
    (shot / "takes" / "t001.mp4").unlink()
    assert next_take_id(shot) == "t003"


def test_take_image_id_rejects_bad_slugs():
    for bad in ("bad--slug", "Bad", "-lead", "under_score", ""):
        with pytest.raises(ValueError):
            take_image_id(bad, "S01", "t001")


def test_apply_verdicts_skips_malformed_keys(tmp_path):
    (tmp_path / "shots" / "S01").mkdir(parents=True)
    api = {take_image_id("pilot", "S01", "t001"): {"verdict": "keep"},
           "short--pilot--s01--t002--extra": {"verdict": "fix"}}
    mine = apply_verdicts(tmp_path, "pilot", api)
    assert list(mine) == [take_image_id("pilot", "S01", "t001")]
    assert json.loads((tmp_path / "shots" / "S01" / "verdicts.json").read_text()) == {"t001": {"verdict": "keep"}}
