import json
import threading
import urllib.error
import urllib.request

import pytest

from tools import design_picks as dp


@pytest.fixture
def api(tmp_path):
    (tmp_path / "rounds.json").write_text(json.dumps({"mei-lan": 2}))
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

