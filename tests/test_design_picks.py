import json
import threading
import urllib.error
import urllib.request

import pytest

from tools import design_picks as dp


@pytest.fixture
def api(tmp_path):
    (tmp_path / "rounds.json").write_text(json.dumps({"mei-lan": 2}))
    (tmp_path / "status.json").write_text(json.dumps({"needs_pick": {}, "review": {"mei-lan": "1", "akira-sendo": "7"}}))
    (tmp_path / "img" / "mei-lan").mkdir(parents=True)
    (tmp_path / "img" / "mei-lan" / "r2-c3.jpg").write_bytes(b"x")
    data = tmp_path / "state" / "picks.json"
    server = dp.make_server("127.0.0.1", 0, data, tmp_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/designs/api/picks", data
    server.shutdown()


def call(url, method="GET", body=None, ctype="application/json"):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=raw, method=method, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None


def test_pick_saves_to_disk_and_can_be_undone(api):
    url, data = api
    assert call(url) == (200, {})
    status, picks = call(f"{url}/mei-lan", "PUT", {"action": "pick", "n": 3, "round": 2})
    assert status == 200 and picks["mei-lan"]["n"] == 3
    assert json.loads(data.read_text())["mei-lan"]["action"] == "pick"
    assert call(f"{url}/mei-lan", "DELETE") == (200, {})
    assert json.loads(data.read_text()) == {}


def test_reroll_needs_a_note_and_skip_does_not(api):
    url, _ = api
    assert call(f"{url}/mei-lan", "PUT", {"action": "reroll", "note": "  "})[0] == 400
    assert call(f"{url}/mei-lan", "PUT", {"action": "reroll", "note": "x" * 501})[0] == 400
    assert call(f"{url}/mei-lan", "PUT", {"action": "reroll", "note": "older"})[1]["mei-lan"]["note"] == "older"
    assert call(f"{url}/mei-lan", "PUT", {"action": "skip"})[1]["mei-lan"]["action"] == "skip"


@pytest.mark.parametrize("slug,body", [
    ("not-a-design", {"action": "skip"}),
    ("..%2Fetc", {"action": "skip"}),
    ("mei-lan", {"action": "delete-everything"}),
    ("mei-lan", {"action": "pick", "n": 4, "round": 2}),   # no such image
    ("mei-lan", {"action": "pick", "n": 3, "round": 1}),   # stale round
    ("mei-lan", {"action": "pick", "n": "3", "round": 2}),
    ("mei-lan", ["not", "an", "object"]),
])
def test_bad_input_is_refused_and_nothing_is_saved(api, slug, body):
    url, data = api
    assert call(f"{url}/{slug}", "PUT", body)[0] == 400
    assert not data.exists()


def test_cross_site_and_oversized_writes_are_refused(api):
    url, data = api
    assert call(f"{url}/mei-lan", "PUT", {"action": "skip"}, ctype="text/plain")[0] == 415
    assert call(f"{url}/mei-lan", "PUT", b"x" * (dp.MAX_BODY + 1))[0] == 413
    assert not data.exists()


def test_corrupt_store_fails_loudly_instead_of_wiping_picks(api):
    url, data = api
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text("{broken")
    assert call(url)[0] == 500
    assert call(f"{url}/mei-lan", "PUT", {"action": "skip"})[0] == 500
    assert data.read_text() == "{broken"


def test_reviews_are_separate_from_picks_and_validated(api):
    url, data = api
    reviews = url.replace("/picks", "/reviews")
    assert call(reviews) == (200, {})
    assert call(f"{reviews}/nobody", "PUT", {"verdict": "ok", "v": "1"})[0] == 400
    assert call(f"{reviews}/mei-lan", "PUT", {"verdict": "ok"})[0] == 400
    assert call(f"{reviews}/mei-lan", "PUT", {"verdict": "fix", "note": " ", "v": "1"})[0] == 400
    assert call(f"{reviews}/mei-lan", "PUT", {"verdict": "ok", "v": "1"}, ctype="text/plain")[0] == 415
    status, saved = call(f"{reviews}/mei-lan", "PUT", {"verdict": "fix", "note": "wrong eyes", "v": "1"})
    assert status == 200 and saved["mei-lan"]["note"] == "wrong eyes"
    assert call(url) == (200, {}) and json.loads(data.with_name("reviews.json").read_text())["mei-lan"]["v"] == "1"
    assert call(f"{reviews}/mei-lan", "DELETE") == (200, {})



def test_a_sheet_can_be_reviewed_after_its_design_left_the_picker(api):
    url, _ = api
    reviews = url.replace("/picks", "/reviews")
    status, saved = call(f"{reviews}/akira-sendo", "PUT", {"verdict": "ok", "v": "7"})
    assert status == 200 and saved["akira-sendo"]["verdict"] == "ok"


def _entry(filename, positive="", subfolder="", kind="output"):
    graph = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
             "20": {"class_type": "LoraLoader", "inputs": {"lora_name": "l.safetensors"}},
             "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive}},
             "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad"}},
             "3": {"class_type": "KSampler", "inputs": {"seed": 5, "steps": 28, "cfg": 4.5, "sampler_name": "euler",
                                                         "positive": ["6", 0], "negative": ["7", 0]}}}
    return {"prompt": [1, "id", graph, {}, ["9"]],
            "outputs": {"9": {"images": [{"filename": filename, "subfolder": subfolder, "type": kind}]}}}


def test_renders_newest_first_and_only_nightwire_images():
    history = {"a": _entry("nightwire_design_00001_.png", "first"),
               "b": _entry("mature_00001_.png", "secret tags"),
               "c": _entry("mei-lan_00001_.png", "x", subfolder="image_studio"),
               "d": _entry("nightwire_x_00001_.png", "temp", kind="temp"),
               "e": _entry("nightwire_design_00002_.png", "second")}
    out = dp.summarize_history(history, {})
    assert [r["file"] for r in out] == ["nightwire_design_00002_.png", "mei-lan_00001_.png", "nightwire_design_00001_.png"]
    assert "secret tags" not in json.dumps(out)
    assert out[0]["seed"] == 5 and out[0]["negative"] == "bad" and out[0]["lora"] == "l.safetensors"
    assert out[1]["character"] == "Mei Lan" and out[1]["subfolder"] == "image_studio"


def test_renders_respect_the_limit_and_skip_entries_without_a_graph():
    history = {str(i): _entry(f"nightwire_a_{i:05}_.png") for i in range(5)}
    history["bad"] = {"outputs": {"9": {"images": [{"filename": "nightwire_b_.png", "subfolder": "", "type": "output"}]}}}
    assert [r["file"] for r in dp.summarize_history(history, {}, limit=2)] == ["nightwire_a_00004_.png", "nightwire_a_00003_.png"]


def test_renders_name_the_character_from_its_tags():
    chars = {"hachi": {"name": "Hachi", "tags": ["blue hair", "bob cut", "android", "uniform"]},
             "rin": {"name": "Rin", "tags": ["pink hair", "hoodie"]}}
    out = dp.summarize_history({"a": _entry("nightwire_design_1_.png", "1other, blue hair, bob cut, android, sad"),
                                "b": _entry("nightwire_sky_1_.png", "no humans, city, hoodie")}, chars)
    assert out[1]["character"] == "Hachi" and out[0]["character"] == ""


@pytest.mark.parametrize("positive,style", [
    ("anime screenshot, neon lights, night", "Neon screenshot"),
    ("cel shading, bright face, front lighting", "Glossy cel"),
    ("cel shading, pink neon rim light, turnaround", "Neon rim sheet"),
    ("no style words", "Other")])
def test_renders_label_the_style(positive, style):
    assert dp.summarize_history({"a": _entry("nightwire_a_.png", positive)}, {})[0]["style"] == style


def test_batch_estimates_time_left_and_restarts_on_a_new_batch():
    state = dp.next_batch({}, {"name": "Turnarounds", "done": 0, "total": 10}, now=1000)
    state = dp.next_batch(state, {"name": "Turnarounds", "done": 4, "total": 10, "item": "hachi"}, now=1400)
    view = dp.batch_view(state, now=1400)
    assert (view["done"], view["total"], view["item"], view["eta_seconds"], view["elapsed_seconds"]) == (4, 10, "hachi", 600, 400)
    state = dp.next_batch(state, {"name": "Expressions", "done": 0, "total": 3}, now=2000)
    assert state["started"] == 2000 and dp.batch_view(state, now=2000)["eta_seconds"] is None


@pytest.mark.parametrize("body", [[], {"name": "", "done": 0, "total": 1}, {"name": "x" * 81, "done": 0, "total": 1},
                                  {"name": "a", "done": 2, "total": 1}, {"name": "a", "done": True, "total": 1},
                                  {"name": "a", "done": 0, "total": 0}, {"name": "a", "done": 0, "total": 1, "failed": -1},
                                  {"name": "a", "done": 0, "total": 1, "item": "x" * 81}])
def test_batch_refuses_bad_updates(body):
    with pytest.raises(dp.BadPick):
        dp.next_batch({}, body, now=1)


def test_batch_api_round_trip(api):
    base = api[0].rsplit("/", 1)[0] + "/batch"
    assert call(base) == (200, {})
    assert call(base, "PUT", {"name": "Sheets", "done": 1, "total": 2})[0] == 200
    status, view = call(base)
    assert status == 200 and view["name"] == "Sheets" and view["done"] == 1
    assert call(base, "PUT", {"name": "Sheets", "done": 3, "total": 2})[0] == 400
    assert call(base, "PUT", b"{}", ctype="text/plain")[0] == 415
    assert call(base, "DELETE")[0] == 200
    assert call(base) == (200, {})


def test_renders_api_reports_comfyui_being_down(tmp_path):
    (tmp_path / "rounds.json").write_text("{}")
    server = dp.make_server("127.0.0.1", 0, tmp_path / "s" / "picks.json", tmp_path, comfyui="http://127.0.0.1:9")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert call(f"http://127.0.0.1:{server.server_port}/designs/api/renders")[0] == 502
    finally:
        server.shutdown()
