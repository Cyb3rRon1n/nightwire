import json

import pytest

from tools.shorts import approve


def refs(tmp_path, content=b"a"):
    (tmp_path / "x.png").write_bytes(content)
    return [("C1_turnaround.png", tmp_path / "x.png")]


def test_fingerprint_is_stable_and_sensitive(tmp_path):
    fp = approve.fingerprint("seedance-2.0-fast", "prompt", refs(tmp_path), 5)
    assert len(fp) == 10 and fp == approve.fingerprint("seedance-2.0-fast", "prompt", refs(tmp_path), 5)
    assert fp != approve.fingerprint("seedance-2.0-fast", "prompt!", refs(tmp_path), 5)
    assert fp != approve.fingerprint("seedance-2.0", "prompt", refs(tmp_path), 5)
    assert fp != approve.fingerprint("seedance-2.0-fast", "prompt", refs(tmp_path, b"b"), 5)
    assert fp != approve.fingerprint("seedance-2.0-fast", "prompt", refs(tmp_path), 6)  # a new length needs a new approval


def test_plan_image_id_and_bad_slug():
    assert approve.plan_image_id("pilot", "S01", "abc") == "plan--pilot--s01--abc"
    with pytest.raises(ValueError):
        approve.plan_image_id("bad--slug", "S01", "abc")


def test_apply_and_read_approvals(tmp_path):
    api = {"plan--pilot--s01--abc": {"verdict": "keep"}, "plan--pilot--s02--def": {"verdict": "fix", "note": "closer"},
           "plan--other--s01--abc": {"verdict": "keep"}, "short--pilot--s01--t001": {"verdict": "keep"}, "plan--pilot--bad": {}}
    mine = approve.apply_approvals(tmp_path, "pilot", api)
    assert set(mine) == {"plan--pilot--s01--abc", "plan--pilot--s02--def"}
    assert approve.approval(tmp_path, "S01", "abc") == {"verdict": "keep"}
    assert approve.approval(tmp_path, "S01", "zzz") is None
    assert json.loads((tmp_path / "approvals.json").read_text())["S02"]["def"]["note"] == "closer"


def test_attempts_counts_paid_ledger_rows(tmp_path):
    assert approve.attempts(tmp_path, "S01", "abc") == 0
    rows = [{"shot": "S01", "fp": "abc"}, {"shot": "S01", "fp": "abc"}, {"shot": "S01"}, {"shot": "S02", "fp": "abc"}]
    (tmp_path / "costs.json").write_text(json.dumps(rows))
    assert approve.attempts(tmp_path, "S01", "abc") == 2
