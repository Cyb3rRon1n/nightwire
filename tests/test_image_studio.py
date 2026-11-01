import json
import threading
import urllib.error
import urllib.request

import pytest

from narrator.designs import Design
from tools import image_studio as st


def designs():
    return {
        "mei-lan": Design("Mei Lan", "character", "new:x", "black hair, sharp eyes, mature female, thigh boots, long legs",
                          presentation="feminine", negative="plump", status="approved", seed=111,
                          notes=["2026-11-01 draft: club singer"]),
        "hachi": Design("Hachi", "character", "x", "android, blue hair", presentation="feminine", status="approved", seed=222),
        "the-loop": Design("The Loop", "location", "x", "elevated highway, rain", status="approved", seed=333),
        "draft": Design("Draft", "character", "x", "red hair", status="candidates", seed=444),
    }


class FakeComfy:
    def __init__(self):
        self.submitted, self.running, self.waiting, self.done, self.cancelled = [], [], [], {}, []
        self.freed = 0
        self.ollama_freed = 0

    def free_ollama(self):
        self.ollama_freed += 1

    def submit(self, wf):
        self.submitted.append(wf)
        cid = f"c{len(self.submitted)}"
        self.waiting.append(cid)
        return cid

    def queue(self):
        return {"queue_running": [[0, c] for c in self.running],
                "queue_pending": [[i + 1, c] for i, c in enumerate(self.waiting)]}

    def history(self, cid):
        return self.done.get(cid)

    def cancel(self, cid):
        self.cancelled.append(cid)
        self.waiting.remove(cid)

    def image(self, image):
        return b"PNG:" + image["filename"].encode()

    def free_comfy(self):
        self.freed += 1

    def finish(self, cid, name="a.png"):
        self.running = [c for c in self.running if c != cid]
        self.waiting = [c for c in self.waiting if c != cid]
        self.done[cid] = {"status": {"completed": True, "status_str": "success"},
                          "outputs": {"9": {"images": [{"filename": name, "subfolder": "image_studio", "type": "output"}]}}}


@pytest.fixture
def studio(tmp_path):
    return st.Studio(tmp_path / "state" / "jobs.json", FakeComfy(), designs=designs)


def nodes(wf):
    text = " ".join(str(n["inputs"].get("text", "")) for n in wf.values() if n["class_type"] == "CLIPTextEncode")
    return text


@pytest.mark.parametrize("shot", list(st.SHOTS))
def test_every_shot_keeps_the_no_nudity_and_adult_negatives(studio, shot):
    studio.create({"character": "mei-lan", "shot": shot, "seed": 5})
    text = nodes(studio.comfy.submitted[0])
    for word in ("nude", "explicit", "loli", "child"):
        assert word in text


def test_location_only_scene_keeps_the_negatives_too(studio):
    studio.create({"location": "the-loop"})
    assert "nude" in nodes(studio.comfy.submitted[0]) and "elevated highway" in nodes(studio.comfy.submitted[0])


@pytest.mark.parametrize("action", ["nude on a rooftop", "NAKED", "(nude:1.4)", "nude_body", "topless, rain",
                                    "having sex", "as a teenager", "schoolgirl uniform", "loli"])
def test_action_cant_ask_for_nudity_sex_or_minors(studio, action):
    with pytest.raises(st.BadRequest, match="adult and clothed"):
        studio.create({"character": "mei-lan", "action": action})
    assert studio.comfy.submitted == []


@pytest.mark.parametrize("action", ["singing on stage, sharp suit", "essex street market", "cumulus clouds", "minority report poster",
                                    "kidney bowl, sextant on the desk"])
def test_ordinary_words_arent_refused(studio, action):
    assert st.refused_terms(action) == []


@pytest.mark.parametrize("body", [
    {},
    {"character": "draft"},                # not approved
    {"character": "the-loop"},             # wrong kind
    {"location": "mei-lan"},
    {"character": ["mei-lan"]},
    {"character": "mei-lan", "shot": "raw"},
    {"character": "mei-lan", "size": "8k"},
    {"character": "mei-lan", "count": 5},
    {"character": "mei-lan", "count": True},
    {"character": "mei-lan", "seed": -1},
    {"character": "mei-lan", "seed": "1; DROP"},
    {"character": "mei-lan", "action": "x" * (st.MAX_ACTION + 1)},
    {"character": "mei-lan", "day": "yes"},
    ["not an object"],
])
def test_bad_requests_are_refused(studio, body):
    with pytest.raises(st.BadRequest):
        studio.create(body)
    assert studio.comfy.submitted == []


def test_raw_prompt_fields_are_ignored(studio):
    studio.create({"character": "mei-lan", "prompt": "SMUGGLED", "negative": "SMUGGLED", "raw": True})
    assert "SMUGGLED" not in nodes(studio.comfy.submitted[0])


def test_scene_mixes_character_location_and_action_with_the_design_seed(studio):
    studio.create({"character": "mei-lan", "location": "the-loop", "action": "singing in the rain", "seed": "design", "count": 2})
    text = nodes(studio.comfy.submitted[0])
    assert all(t in text for t in ("black hair", "elevated highway", "singing in the rain", "1girl"))
    jobs = studio.refresh()["jobs"]
    assert sorted(j["seed"] for j in jobs) == [111, 112]
    assert jobs[0]["label"] == "Mei Lan at The Loop"


def test_portrait_drops_lower_body_tags_and_location(studio):
    studio.create({"character": "mei-lan", "location": "the-loop", "shot": "portrait"})
    prompt = nodes(studio.comfy.submitted[0]).split("full body")[0]
    assert "black hair" in prompt and "thigh boots" not in prompt and "elevated highway" not in prompt


def test_android_gets_the_android_subject(studio):
    studio.create({"character": "hachi"})
    assert "1other" in nodes(studio.comfy.submitted[0])


def test_job_lifecycle_frees_the_gpu_only_when_everything_is_finished(studio):
    comfy = studio.comfy
    studio.create({"character": "mei-lan", "count": 2})
    assert comfy.ollama_freed == 1
    jobs = {j["seed"]: j for j in studio.refresh()["jobs"]}
    assert [j["position"] for j in sorted(jobs.values(), key=lambda j: j["seed"])] == [0, 1]
    comfy.waiting.remove("c1")
    comfy.running.append("c1")
    jobs = sorted(studio.refresh()["jobs"], key=lambda j: j["seed"])
    assert [j["status"] for j in jobs] == ["rendering", "queued"] and jobs[1]["position"] == 1
    comfy.finish("c1")
    jobs = sorted(studio.refresh()["jobs"], key=lambda j: j["seed"])
    assert jobs[0]["status"] == "done" and jobs[0]["hasImage"] and "comfy_id" not in jobs[0]
    assert comfy.freed == 0
    assert studio.image(jobs[0]["id"]) == b"PNG:a.png"
    comfy.finish("c2", "b.png")
    studio.refresh()
    assert comfy.freed == 1
    studio.refresh()
    assert comfy.freed == 1


def test_gpu_isnt_freed_while_someone_elses_job_runs(studio):
    studio.create({"character": "mei-lan"})
    studio.comfy.finish("c1")
    studio.comfy.running.append("design-sheets-batch")
    studio.refresh()
    assert studio.comfy.freed == 0


def test_failed_and_lost_jobs_say_so(studio):
    studio.create({"character": "mei-lan", "count": 2})
    studio.comfy.waiting.clear()
    studio.comfy.done["c1"] = {"status": {"completed": False, "status_str": "error"}, "outputs": {}}
    jobs = sorted(studio.refresh()["jobs"], key=lambda j: j["seed"])
    assert jobs[0]["status"] == "failed" and "error" in jobs[0]["error"]
    assert jobs[1]["status"] == "failed" and "lost" in jobs[1]["error"]


def test_pending_cap(studio):
    for _ in range(3):
        studio.create({"character": "mei-lan", "count": 4})
    with pytest.raises(st.Busy):
        studio.create({"character": "mei-lan"})
    assert len(studio.comfy.submitted) == 12


def test_delete_cancels_queued_refuses_rendering_and_drops_finished(studio):
    comfy = studio.comfy
    studio.create({"character": "mei-lan", "count": 3})
    jobs = sorted(studio.refresh()["jobs"], key=lambda j: j["seed"])
    studio.delete(jobs[0]["id"])
    assert comfy.cancelled == ["c1"]
    comfy.waiting.remove("c2")
    comfy.running.append("c2")
    comfy.finish("c3")
    studio.refresh()
    with pytest.raises(st.BadRequest):
        studio.delete(jobs[1]["id"])
    studio.delete(jobs[2]["id"])
    assert [j["seed"] for j in studio.refresh()["jobs"]] == [jobs[1]["seed"]]
    with pytest.raises(KeyError):
        studio.delete("nope")


def test_corrupt_state_is_never_overwritten(studio):
    studio.state.parent.mkdir(parents=True)
    studio.state.write_text("{broken")
    with pytest.raises(ValueError):
        studio.create({"character": "mei-lan"})
    assert studio.state.read_text() == "{broken"
    assert studio.comfy.submitted == []


def test_options_only_lists_approved_designs(studio):
    opts = studio.options()
    assert [c["slug"] for c in opts["characters"]] == ["hachi", "mei-lan"]
    assert opts["characters"][1]["role"] == "club singer"
    assert [c["slug"] for c in opts["locations"]] == ["the-loop"]


def test_real_design_files_produce_a_valid_workflow():
    real = st.load_designs()
    character = next(s for s, d in real.items() if d.kind == "character" and d.status == "approved")
    location = next(s for s, d in real.items() if d.kind == "location" and d.status == "approved")
    for shot in st.SHOTS:
        for size in st.SIZES:
            wf = st.workflow(st.compose({"character": character, "location": location, "shot": shot, "size": size}, real)[0])
            assert wf["9"]["inputs"]["filename_prefix"] == f"image_studio/{character}"


@pytest.fixture
def api(studio):
    server = st.make_server("127.0.0.1", 0, studio)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/studio/api", studio
    server.shutdown()


def call(url, method="GET", body=None, ctype="application/json"):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=raw, method=method, headers={"Content-Type": ctype})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_http_round_trip(api):
    url, studio = api
    assert call(f"{url}/jobs", "POST", {"character": "mei-lan"})[0] == 201
    job = json.loads(call(f"{url}/jobs")[1])["jobs"][0]
    assert job["status"] == "queued"
    assert call(f"{url}/image/{job['id']}")[0] == 404
    studio.comfy.finish("c1")
    call(f"{url}/jobs")
    assert call(f"{url}/image/{job['id']}") == (200, b"PNG:a.png")
    assert call(f"{url}/jobs/{job['id']}", "DELETE")[0] == 200
    assert json.loads(call(f"{url}/options")[1])["maxCount"] == st.MAX_COUNT


def test_http_refusals(api):
    url, _ = api
    assert call(f"{url}/jobs", "POST", {"character": "mei-lan", "action": "nude"})[0] == 400
    assert call(f"{url}/jobs", "POST", {"character": "mei-lan"}, ctype="text/plain")[0] == 415
    assert call(f"{url}/jobs", "POST", b"x" * (st.MAX_BODY + 1))[0] == 413
    assert call(f"{url}/jobs", "POST", b"{bad")[0] == 400
    assert call(f"{url}/nope")[0] == 404


def test_comfy_down_reports_502_and_tracks_nothing(tmp_path):
    studio = st.Studio(tmp_path / "jobs.json", st.Comfy("http://127.0.0.1:9", "http://127.0.0.1:9"), designs=designs)
    server = st.make_server("127.0.0.1", 0, studio)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/studio/api"
    assert call(f"{url}/jobs", "POST", {"character": "mei-lan"})[0] == 502
    assert call(f"{url}/jobs")[0] == 502
    assert not (tmp_path / "jobs.json").exists()
    server.shutdown()
