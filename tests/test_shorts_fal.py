import json

import httpx
import pytest

from tools.shorts.backends import fal
from tools.shorts.takes import RATES, BudgetError, Ledger, estimate


def transport(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url), request.headers.get("authorization")))
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "r1", "status_url": "https://queue.fal.run/x/requests/r1/status",
                                             "response_url": "https://queue.fal.run/x/requests/r1"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=b"mp4bytes")
        return httpx.Response(200, json={"video": {"url": "https://cdn.example/v.mp4"}})
    return httpx.MockTransport(handler)


def test_load_key_reads_env_file_and_hides_contents(tmp_path):
    f = tmp_path / "secrets.env"
    f.write_text("OTHER=1\nFAL_KEY=abc:def\n")
    assert fal.load_key(f) == "abc:def"
    f.write_text("OTHER=secretvalue\n")
    with pytest.raises(RuntimeError) as e:
        fal.load_key(f)
    assert "secretvalue" not in str(e.value)


def test_build_input_uses_model_field_names(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG")
    model = next(iter(fal.MODELS))
    body = fal.build_input(model, "hello", [("C1_turnaround.png", img)], 5)
    spec = fal.MODELS[model]
    assert body[spec["prompt"]] == "hello"
    assert body[spec["images"]][0].startswith("data:image/png;base64,")


def test_fal_enum_durations_are_strings():
    for model, spec in fal.MODELS.items():
        assert spec.get("duration_str") is True, model
        assert fal.build_input(model, "p", [], 5.4)[spec["duration"]] == "5"


def test_int_duration_option():
    fal.MODELS["_t"] = {"endpoint": "e", "prompt": "prompt", "images": "i", "video": None, "duration": "d", "extra": {}}
    try:
        assert fal.build_input("_t", "p", [], 5.4)["d"] == 5
    finally:
        del fal.MODELS["_t"]


def test_models_all_have_rates():
    assert set(fal.MODELS) <= set(RATES)


def test_run_take_submits_files_and_records(tmp_path):
    calls = []
    client = httpx.Client(transport=transport(calls))
    model = next(iter(fal.MODELS))
    tid = fal.run_take(tmp_path, "S01", model, "p", [], 5, 25, key="k", client=client)
    assert tid == "t001"
    assert (tmp_path / "shots" / "S01" / "takes" / "t001.mp4").read_bytes() == b"mp4bytes"
    assert calls[0][2] == "Key k"
    assert Ledger(tmp_path / "costs.json").total() > 0


def test_run_take_refuses_over_budget_before_any_request(tmp_path):
    calls = []
    client = httpx.Client(transport=transport(calls))
    with pytest.raises(BudgetError):
        fal.run_take(tmp_path, "S01", next(iter(fal.MODELS)), "p", [], 30, 1, key="k", client=client)
    assert calls == []


def test_failed_download_after_post_still_records_spend(tmp_path):
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "r1", "status_url": "https://q/s/status", "response_url": "https://q/r"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.url.host == "cdn.example":
            return httpx.Response(500)
        return httpx.Response(200, json={"video": {"url": "https://cdn.example/v.mp4"}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    model = next(iter(fal.MODELS))
    with pytest.raises(httpx.HTTPStatusError):
        fal.run_take(tmp_path, "S01", model, "p", [], 5, 25, key="k", client=client)
    assert Ledger(tmp_path / "costs.json").total() == estimate(model, 5)


def test_success_writes_exactly_one_ledger_row(tmp_path):
    client = httpx.Client(transport=transport([]))
    fal.run_take(tmp_path, "S01", next(iter(fal.MODELS)), "p", [], 5, 25, key="k", client=client)
    assert len(Ledger(tmp_path / "costs.json")._rows()) == 1


def test_unsendable_refs_raise(tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    with pytest.raises(ValueError, match="notes.txt"):
        fal.build_input("seedance-2.0-fast", "p", [("notes.txt", f)], 5)
    with pytest.raises(ValueError, match="clip.mp4"):
        fal.build_input("kling-3", "p", [("clip.mp4", f)], 5)


def test_short_duration_refused_before_request(tmp_path):
    calls = []
    client = httpx.Client(transport=transport(calls))
    with pytest.raises(ValueError):
        fal.run_take(tmp_path, "S01", "kling-3", "p", [], 2, 25, key="k", client=client)
    assert calls == []


def test_run_take_bills_the_rounded_seconds(tmp_path):
    model = "seedance-2.5"
    fal.run_take(tmp_path, "S02", model, "p", [], 7.5, 25, key="k", client=httpx.Client(transport=transport([])))
    assert Ledger(tmp_path / "costs.json").total() == estimate(model, 8)
    assert json.loads((tmp_path / "shots/S02/takes/t001.json").read_text())["seconds"] == 8
