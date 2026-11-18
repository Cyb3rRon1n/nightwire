import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from test_character_creator import GOOD, FakeComfy, render

from tools import character_creator as cc
from tools.image_studio import Comfy

REPO = Path(__file__).parent.parent
OWNER = "o" * 32
NOT_FOUND = (404, {"error": "not found"})


@pytest.fixture(autouse=True)
def no_quiet_wait(monkeypatch):
    monkeypatch.setattr(cc, "QUIET_CHECKS", 1)
    monkeypatch.setattr(cc, "QUIET_SECONDS", 0)


@pytest.fixture
def api(tmp_path):
    comfy = FakeComfy()
    creator = cc.Creator(tmp_path, comfy)
    server = cc.make_server("127.0.0.1", 0, creator, OWNER)
    threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/create/api", creator, comfy
    server.shutdown()


def call(url, method="GET", body=None, ctype="application/json", headers=None):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=raw, method=method, headers={"Content-Type": ctype, **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read()
            return r.status, json.loads(data) if r.headers["Content-Type"] == "application/json" else data
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def new(url, kind="player", answers=GOOD):
    status, record = call(f"{url}/characters", "POST", {"kind": kind, "answers": answers})
    assert status == 201
    return record["id"]


def test_create_generate_and_read_a_player_character(api):
    url, creator, comfy = api
    cid = new(url)
    assert call(f"{url}/characters/{cid}/generate", "POST", {})[0] == 200
    status, record = call(f"{url}/characters/{cid}")
    assert status == 200 and record["queue"]["position"] == 1 and record["answers"]["name"] == "Vex"
    render(creator, comfy)
    record = call(f"{url}/characters/{cid}")[1]
    assert len(record["rounds"][0]["images"]) == 4 and record["queue"] is None


def test_the_whole_review_flow_over_http(api):
    url, creator, comfy = api
    cid = new(url)
    base = f"{url}/characters/{cid}"
    call(f"{base}/generate", "POST", {"note": "red scarf"})
    render(creator, comfy)
    assert "red scarf" in comfy.submitted[0]["6"]["inputs"]["text"]
    assert call(f"{base}/vary", "POST", {"round": 1, "n": 1, "strength": "strong", "note": "older coat"})[0] == 200
    render(creator, comfy)
    assert comfy.submitted[-1]["3"]["inputs"]["denoise"] == 0.6
    assert call(f"{base}/favourite", "POST", {"round": 1, "n": 2})[1]["favourites"]
    assert call(f"{base}/lock", "POST", {})[0] == 400   # nothing picked
    assert call(f"{base}/pick", "POST", {"round": 1, "n": 2})[1]["picked"]
    status, record = call(f"{base}/answers", "PUT", {**GOOD, "outfit": "trench coat"})
    assert status == 200 and record["answers"]["outfit"] == "trench coat"
    assert call(f"{base}/lock", "POST", {})[1]["status"] == "locked"
    render(creator, comfy)
    assert call(f"{base}/sheet", "POST", {"sheet": "turnaround"})[0] == 200
    render(creator, comfy)
    assert call(f"{base}", "DELETE", {})[0] == 200
    assert call(base) == NOT_FOUND


def test_retry_runs_a_failed_batch_again(api):
    url, creator, comfy = api
    cid = new(url)
    call(f"{url}/characters/{cid}/generate", "POST", {})
    creator.tick()
    comfy.fail()
    creator.tick()
    assert call(f"{url}/characters/{cid}")[1]["queue"]["error"]
    assert call(f"{url}/characters/{cid}/retry", "POST", {})[0] == 200
    render(creator, comfy)
    assert len(call(f"{url}/characters/{cid}")[1]["rounds"]) == 1


def test_options_offer_the_questions(api):
    url, _, _ = api
    status, options = call(f"{url}/options")
    assert status == 200 and options["questions"][0]["id"] == "name"
    assert options["strengths"] == ["subtle", "strong"] and options["expressions"][0] == "Neutral"


@pytest.mark.parametrize("method, path", [("POST", "/characters"), ("POST", "/characters/ID/generate"),
                                          ("PUT", "/characters/ID/answers"), ("DELETE", "/characters/ID")])
def test_writes_need_json_and_a_matching_origin(api, method, path):
    url, _, _ = api
    cid = new(url)
    target = url + path.replace("ID", cid)
    host = url.split("/")[2]
    body = {"kind": "player", "answers": GOOD, **GOOD}   # fits every one of these routes
    assert call(target, method, body, ctype="text/plain")[0] == 415
    assert call(target, method, body, ctype="application/x-www-form-urlencoded")[0] == 415
    assert call(target, method, body, headers={"Origin": "https://evil.example"})[0] == 403
    assert call(target, method, body, headers={"Origin": "null"})[0] == 403
    assert call(target, method, body, headers={"Origin": f"http://{host}"})[0] < 400


def test_body_limit_and_bad_bodies(api):
    url, _, _ = api
    assert call(f"{url}/characters", "POST", b"x" * (16 * 1024 + 1))[0] == 413
    assert call(f"{url}/characters", "POST", b"{bad")[0] == 400
    assert call(f"{url}/characters", "POST", ["not an object"])[0] == 400
    assert call(f"{url}/characters", "POST", {"kind": "player"})[0] == 400


def test_a_refused_word_says_which_and_why(api):
    url, _, _ = api
    status, body = call(f"{url}/characters", "POST", {"kind": "player", "answers": {**GOOD, "outfit": "nude"}})
    assert status == 400 and "nude" in body["error"] and "outfit" in body["error"]


def test_a_full_queue_is_429_with_a_clear_message(api):
    url, _, _ = api
    ids = [new(url) for _ in range(13)]
    for cid in ids[:12]:
        assert call(f"{url}/characters/{cid}/generate", "POST", {})[0] == 200
    status, body = call(f"{url}/characters/{ids[12]}/generate", "POST", {})
    assert status == 429 and "12" in body["error"]


def test_unknown_link_is_404_with_no_record_leaked(api):
    url, _, _ = api
    new(url)
    missing = "x" * 32
    for attempt in (call(f"{url}/characters/{missing}"), call(f"{url}/characters/{missing}/image/turnaround.png"),
                    call(f"{url}/characters/{missing}/generate", "POST", {}), call(f"{url}/characters/{missing}", "DELETE", {}),
                    call(f"{url}/characters/{missing}/answers", "PUT", GOOD), call(f"{url}/characters/..%2f..%2fqueue.json")):
        assert attempt == NOT_FOUND


def test_one_characters_token_cant_read_anothers_image(api):
    url, creator, comfy = api
    mine = new(url)
    call(f"{url}/characters/{mine}/generate", "POST", {})
    render(creator, comfy)
    name = call(f"{url}/characters/{mine}")[1]["rounds"][0]["images"][0]
    other = new(url)
    assert call(f"{url}/characters/{mine}/image/{name}")[0] == 200
    assert call(f"{url}/characters/{other}/image/{name}") == NOT_FOUND


def test_image_responses_are_private_pngs(api):
    url, creator, comfy = api
    cid = new(url)
    call(f"{url}/characters/{cid}/generate", "POST", {})
    render(creator, comfy)
    name = call(f"{url}/characters/{cid}")[1]["rounds"][0]["images"][0]
    with urllib.request.urlopen(f"{url}/characters/{cid}/image/{name}") as r:
        assert r.headers["Content-Type"] == "image/png" and r.headers["Cache-Control"].startswith("private")
        assert r.read().startswith(b"PNG:")
    assert call(f"{url}/characters/{cid}/image/..%2fcharacter.json") == NOT_FOUND


def test_suggester_cant_generate_after_acceptance_owner_can(api):
    url, creator, comfy = api
    cid = new(url, "npc")
    status, record = call(f"{url}/characters/{cid}")
    assert status == 200 and record["status"] == "suggested"
    assert call(f"{url}/characters/{cid}/generate", "POST", {})[0] == 403
    owner = f"{url}/owner/{OWNER}/characters/{cid}"
    assert call(f"{owner}/generate", "POST", {})[0] == 400   # not accepted yet: nothing renders
    assert call(f"{owner}/accept", "POST", {})[1]["status"] == "accepted"
    assert call(f"{url}/characters/{cid}/generate", "POST", {})[0] == 403
    assert call(f"{owner}/generate", "POST", {})[0] == 200
    render(creator, comfy)
    assert len(call(f"{url}/characters/{cid}")[1]["rounds"]) == 1


@pytest.mark.parametrize("method, path, body", [
    ("POST", "generate", {}), ("POST", "vary", {"round": 1, "n": 1, "strength": "subtle"}), ("POST", "pick", {"round": 1, "n": 1}),
    ("POST", "favourite", {"round": 1, "n": 1}), ("POST", "lock", {}), ("POST", "sheet", {"sheet": "turnaround"}), ("POST", "retry", {}),
    ("PUT", "answers", GOOD), ("DELETE", "", {})])
@pytest.mark.parametrize("kind", ["npc", "ai"])
def test_only_player_characters_can_be_changed_on_the_public_route(api, method, path, body, kind):
    url, creator, _ = api
    cid = new(url, kind)
    assert call(f"{url}/characters/{cid}/{path}".rstrip("/"), method, body)[0] == 403
    assert creator.get(cid)["answers"]["name"] == "Vex"


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_review_actions_only_exist_on_the_owner_route(api, action):
    url, creator, _ = api
    cid = new(url, "npc")
    assert call(f"{url}/characters/{cid}/{action}", "POST", {"note": "no"}) == NOT_FOUND
    assert creator.get(cid)["status"] == "suggested"


def test_decline_shows_the_owners_note_on_the_players_link(api):
    url, _, _ = api
    cid = new(url, "ai")
    owner = f"{url}/owner/{OWNER}/characters/{cid}"
    assert call(f"{owner}/decline", "POST", {"note": "too close to Mei Lan"})[1]["status"] == "declined"
    record = call(f"{url}/characters/{cid}")[1]
    assert record["status"] == "declined" and record["note"] == "too close to Mei Lan"


def test_owner_can_create_edit_and_delete_any_character(api):
    url, creator, comfy = api
    owner = f"{url}/owner/{OWNER}/characters"
    status, npc = call(owner, "POST", {"kind": "npc", "answers": {**GOOD, "world_role": "ramen cook", "home": "Dock Nine"}})
    assert status == 201 and npc["status"] == "draft"
    assert call(f"{owner}/{npc['id']}/generate", "POST", {})[0] == 200
    render(creator, comfy)
    assert call(f"{owner}/{npc['id']}/pick", "POST", {"round": 1, "n": 1})[0] == 200
    assert call(f"{owner}/{npc['id']}/vary", "POST", {"round": 1, "n": 1, "strength": "subtle"})[0] == 200
    render(creator, comfy)
    assert call(f"{owner}/{npc['id']}/favourite", "POST", {"round": 1, "n": 1})[0] == 200
    assert call(f"{owner}/{npc['id']}/lock", "POST", {})[0] == 200
    render(creator, comfy)
    assert call(f"{owner}/{npc['id']}/sheet", "POST", {"sheet": "turnaround"})[0] == 200
    suggestion = new(url, "npc")
    edited = call(f"{owner}/{suggestion}/answers", "PUT", {**GOOD, "hair": "green hair"})
    assert edited[0] == 200 and edited[1]["answers"]["hair"] == "green hair"   # the spec: accept, edit or decline
    player = new(url)
    assert call(f"{owner}/{player}", "DELETE", {})[0] == 200
    assert call(f"{url}/characters/{player}") == NOT_FOUND


def test_owner_routes_404_with_a_wrong_token_just_like_a_missing_route(api):
    url, _, _ = api
    cid = new(url, "npc")
    wrong = f"{url}/owner/{'x' * 32}"
    missing = call(f"{url}/no/such/route")
    assert missing == NOT_FOUND
    assert call(f"{wrong}/characters") == missing
    assert call(f"{wrong}/characters", "POST", {"kind": "npc", "answers": GOOD}) == missing
    assert call(f"{wrong}/characters/{cid}/accept", "POST", {}) == missing
    assert call(f"{wrong}/characters/{cid}", "DELETE", {}) == missing
    assert call(f"{wrong}/characters", "POST", b"x", ctype="text/plain") == missing   # no 415 to give it away
    assert call(f"{url}/no/such/route", "POST", b"x", ctype="text/plain") == missing
    assert call(f"{url}/owner/caf%C3%A9/characters") == missing
    assert call(f"{url}/owner/{OWNER}/nope") == missing


def test_non_ascii_owner_token_is_a_plain_404_not_a_crash(api):
    url, _, _ = api
    host, port = url.split("/")[2].split(":")
    with socket.create_connection((host, int(port))) as s:
        s.sendall(b"GET /create/api/owner/caf\xc3\xa9/characters HTTP/1.0\r\n\r\n")
        assert b"404" in s.recv(200).split(b"\r\n")[0]


def test_only_the_owner_route_lists_characters(api):
    url, _, _ = api
    mine, suggestion = new(url), new(url, "npc", {**GOOD, "name": "Aki"})
    assert call(f"{url}/characters") == NOT_FOUND
    assert call(f"{url}/characters/") == NOT_FOUND
    status, listing = call(f"{url}/owner/{OWNER}/characters")
    assert status == 200 and [c["id"] for c in listing["characters"]] == [suggestion, mine]
    assert listing["characters"][0]["answers"]["name"] == "Aki"


def test_a_damaged_character_doesnt_take_down_the_owner_list(api):
    url, creator, _ = api
    good, bad = new(url), new(url)
    (creator.root / "characters" / bad / "character.json").write_text("{broken")
    status, listing = call(f"{url}/owner/{OWNER}/characters")
    assert status == 200 and {c["id"]: c.get("damaged", False) for c in listing["characters"]} == {good: False, bad: True}
    assert call(f"{url}/owner/{OWNER}/characters/{bad}", "DELETE", {})[0] == 200
    assert [c["id"] for c in call(f"{url}/owner/{OWNER}/characters")[1]["characters"]] == [good]


def test_full_store_is_429_with_a_clear_message(api, monkeypatch):
    url, _, _ = api
    monkeypatch.setattr(cc, "MAX_SUGGESTIONS", 1)
    new(url, "npc")
    status, body = call(f"{url}/characters", "POST", {"kind": "ai", "answers": GOOD})
    assert status == 429 and "suggestions" in body["error"]


def test_comfy_being_down_doesnt_stop_anyone_getting_in_line(tmp_path):
    creator = cc.Creator(tmp_path, Comfy("http://127.0.0.1:9", "http://127.0.0.1:9"))
    server = cc.make_server("127.0.0.1", 0, creator, OWNER)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/create/api"
    cid = new(url)
    assert call(f"{url}/characters/{cid}/generate", "POST", {})[0] == 200
    assert call(f"{url}/characters/{cid}")[1]["queue"]["position"] == 1
    server.shutdown()


def test_owner_token_is_private_and_stable(tmp_path):
    token = cc.owner_token(tmp_path / "state")
    path = tmp_path / "state" / "owner.token"
    assert len(token) == 32 and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert cc.owner_token(tmp_path / "state") == token


def test_empty_owner_token_file_fails_at_startup_instead_of_failing_open(tmp_path):
    for content in ("", "  \n"):
        (tmp_path / "owner.token").write_text(content)
        with pytest.raises(ValueError, match="owner.token"):
            cc.owner_token(tmp_path)


def test_owner_token_creation_leaves_no_temp_file_and_never_a_partial_token(tmp_path):
    token = cc.owner_token(tmp_path)
    assert (tmp_path / "owner.token").read_text().strip() == token
    assert [p.name for p in tmp_path.iterdir()] == ["owner.token"]


def test_server_refuses_to_start_with_an_empty_token(tmp_path):
    with pytest.raises(ValueError):
        cc.make_server("127.0.0.1", 0, cc.Creator(tmp_path, FakeComfy()), "")


def test_an_empty_token_in_the_path_is_a_plain_404(api):
    url, _, _ = api
    assert call(f"{url}/owner//characters") == NOT_FOUND
    assert call(f"{url}/owner//characters", "POST", {"kind": "npc", "answers": GOOD}) == NOT_FOUND


def test_service_starts_on_the_standard_library_alone_with_the_worker_running(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # -S skips site-packages. Nothing listens on ComfyUI's port, so the worker can only log that.
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    proc = subprocess.Popen([sys.executable, "-S", "-m", "tools.character_creator", "--root", str(tmp_path), "--port", str(port),
                             "--comfy", "http://127.0.0.1:9", "--ollama", "http://127.0.0.1:9"],
                            cwd=REPO, env=env, stderr=subprocess.PIPE, text=True)
    try:
        url = f"http://127.0.0.1:{port}/create/api"
        for _ in range(100):
            try:
                assert call(f"{url}/options")[0] == 200
                break
            except urllib.error.URLError:
                time.sleep(0.1)
        else:
            raise AssertionError("the service never answered")
        cid = new(url)
        assert call(f"{url}/characters/{cid}/generate", "POST", {})[0] == 200
        assert (tmp_path / "owner.token").exists()
        time.sleep(2.5)   # at least one tick against the dead ComfyUI
        assert proc.poll() is None
    finally:
        proc.terminate()
        logged = proc.communicate(timeout=5)[1]
    assert "character creator worker" in logged and "Traceback" not in logged and cid not in logged
