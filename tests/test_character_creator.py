import email
import http.server
import threading
import urllib.error

import pytest

from narrator.design_sheets import EXPRESSION_SIZE
from tools import character_creator as cc
from tools.image_studio import BadRequest, Busy, Comfy

GOOD = {"name": "Vex", "presentation": "feminine", "hair": "silver hair", "signature": "katana"}


class FakeComfy:
    def __init__(self):
        self.submitted, self.others_running, self.current, self.done, self.uploads = [], False, None, {}, {}
        self.freed = self.ollama_freed = 0
        self.down = self.refuse = False

    def queue(self):
        if self.down:
            raise urllib.error.URLError("down")
        running = (["someone-else"] if self.others_running else []) + ([self.current] if self.current else [])
        return {"queue_running": [[0, c] for c in running], "queue_pending": []}

    def submit(self, wf):
        if self.refuse:
            raise urllib.error.HTTPError("http://comfy/prompt", 400, "bad workflow", None, None)
        self.submitted.append(wf)
        self.current = f"c{len(self.submitted)}"
        return self.current

    def history(self, cid):
        return self.done.get(cid)

    def image(self, ref):
        return b"PNG:" + ref["filename"].encode()

    def upload(self, name, data):
        self.uploads[name] = data
        return f"character_creator/{name}"

    def free_ollama(self):
        self.ollama_freed += 1

    def free_comfy(self):
        self.freed += 1

    def finish(self):
        self.done[self.current] = {"status": {"completed": True, "status_str": "success"},
                                   "outputs": {"9": {"images": [{"filename": f"{self.current}.png", "subfolder": "x", "type": "output"}]}}}
        self.current = None

    def fail(self):
        self.done[self.current] = {"status": {"completed": False, "status_str": "error"}, "outputs": {}}
        self.current = None

    def lose(self):
        self.current = None


@pytest.fixture
def comfy():
    return FakeComfy()


@pytest.fixture
def creator(tmp_path, comfy):
    return cc.Creator(tmp_path, comfy)


def render(creator, comfy):
    for _ in range(50):
        creator.tick()
        if not comfy.current:
            return
        comfy.finish()
    raise AssertionError("the queue never emptied")


def with_round(creator, comfy, **answers):
    cid = creator.create("player", {**GOOD, **answers}, by_owner=False)["id"]
    creator.generate(cid)
    render(creator, comfy)
    return cid


def classes(wf):
    return {n["class_type"] for n in wf.values()}


def text(wf, node="6"):
    return wf[node]["inputs"]["text"]


def test_generate_queues_four_and_tick_renders_one_at_a_time(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    assert comfy.submitted == [] and creator.get(cid)["rounds"] == []
    creator.tick()
    assert len(comfy.submitted) == 1 and comfy.ollama_freed == 1
    creator.tick()   # still rendering: nothing new
    assert len(comfy.submitted) == 1
    for done in range(1, 4):
        comfy.finish()
        creator.tick()
        assert len(comfy.submitted) == done + 1
    assert creator.get(cid)["rounds"] == []   # a round appears once it's complete
    comfy.finish()
    creator.tick()
    got = creator.get(cid)
    assert got["queue"] is None and len(got["rounds"]) == 1 and got["rounds"][0]["type"] == "reroll"
    images = got["rounds"][0]["images"]
    assert len(images) == 4 and all(cc.NAME.fullmatch(i) for i in images)
    assert creator.image_path(cid, images[0]).read_bytes() == b"PNG:c1.png"
    assert len({wf["3"]["inputs"]["seed"] for wf in comfy.submitted}) == 4
    assert all("katana" in text(wf) and "silver hair" in text(wf) and "nude" in text(wf, "7") for wf in comfy.submitted)


def test_tick_waits_while_someone_elses_job_is_in_comfyui(creator, comfy):
    comfy.others_running = True
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.tick()
    assert comfy.submitted == [] and creator.get(cid)["queue"]["position"] == 1
    comfy.others_running = False
    creator.tick()
    assert len(comfy.submitted) == 1


def test_tick_waits_between_items_if_someone_else_got_in(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.tick()
    comfy.finish()
    comfy.others_running = True
    creator.tick()
    assert len(comfy.submitted) == 1
    assert (creator.root / "characters" / cid / "candidates").is_dir()


def test_one_batch_per_character_and_twelve_overall(creator, comfy):
    ids = [creator.create("player", GOOD, by_owner=False)["id"] for _ in range(13)]
    creator.generate(ids[0])
    with pytest.raises(Busy):
        creator.generate(ids[0])
    for cid in ids[1:12]:
        creator.generate(cid)
    assert [creator.get(c)["queue"]["position"] for c in ids[:3]] == [1, 2, 3]
    with pytest.raises(Busy, match="12"):
        creator.generate(ids[12])
    creator.tick()
    comfy.fail()
    creator.tick()   # a failed batch isn't waiting, so it frees a place
    creator.generate(ids[12])


def test_failed_render_marks_batch_failed_keeps_old_rounds_and_retry_works(creator, comfy):
    cid = with_round(creator, comfy)
    first = creator.get(cid)["rounds"]
    other = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.generate(other)
    creator.tick()
    comfy.finish()
    creator.tick()
    comfy.fail()
    creator.tick()
    got = creator.get(cid)
    assert got["rounds"] == first and "error" in got["queue"]["error"] and got["queue"]["position"] is None
    assert len(comfy.submitted) == 4 + 2 + 1   # the failed batch doesn't hold up the next one
    render(creator, comfy)
    assert len(creator.get(other)["rounds"]) == 1
    before = len(comfy.submitted)
    creator.retry(cid)
    assert creator.get(cid)["queue"]["error"] == ""
    render(creator, comfy)
    got = creator.get(cid)
    assert len(got["rounds"]) == 2 and got["queue"] is None
    assert len(comfy.submitted) == before + 3   # the finished candidate isn't rendered again
    assert all(creator.image_path(cid, i).exists() for i in got["rounds"][1]["images"])
    with pytest.raises(BadRequest):
        creator.retry(cid)


def test_new_batch_replaces_a_failed_one(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.tick()
    comfy.fail()
    creator.tick()
    creator.generate(cid)
    assert creator.get(cid)["queue"]["error"] == ""
    render(creator, comfy)
    assert len(creator.get(cid)["rounds"]) == 1 and creator.get(cid)["queue"] is None


def test_finished_without_an_image_fails_the_batch(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.tick()
    comfy.done["c1"] = {"status": {"completed": True}, "outputs": {}}
    comfy.current = None
    creator.tick()
    assert "without an image" in creator.get(cid)["queue"]["error"]


def test_a_workflow_comfyui_refuses_fails_instead_of_blocking_everyone(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    other = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.generate(other)
    comfy.refuse = True
    creator.tick()
    assert creator.get(cid)["queue"]["error"] and creator.get(other)["queue"]["position"] == 1
    comfy.refuse = False
    creator.tick()
    assert len(comfy.submitted) == 1


def test_comfyui_down_leaves_jobs_waiting(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    comfy.down = True
    with pytest.raises(OSError):
        creator.tick()
    assert creator.get(cid)["queue"] == {"position": 1, "label": "candidates", "error": ""}
    comfy.down = False
    render(creator, comfy)
    assert len(creator.get(cid)["rounds"]) == 1


def test_restart_requeues_a_render_that_comfyui_lost(tmp_path, comfy):
    first = cc.Creator(tmp_path, comfy)
    cid = first.create("player", GOOD, by_owner=False)["id"]
    first.generate(cid)
    first.tick()
    comfy.lose()
    again = cc.Creator(tmp_path, comfy)
    assert again.get(cid)["queue"]["error"] == ""
    again.tick()
    assert len(comfy.submitted) == 2 and comfy.submitted[0] == comfy.submitted[1]
    assert again.get(cid)["queue"]["error"] == ""
    render(again, comfy)
    assert len(again.get(cid)["rounds"]) == 1 and len(comfy.submitted) == 5


def test_restart_picks_up_a_render_still_running_and_waiting_jobs(tmp_path, comfy):
    first = cc.Creator(tmp_path, comfy)
    cid = first.create("player", GOOD, by_owner=False)["id"]
    first.generate(cid)
    first.tick()
    again = cc.Creator(tmp_path, comfy)
    again.tick()
    assert len(comfy.submitted) == 1
    comfy.finish()
    render(again, comfy)
    assert len(again.get(cid)["rounds"]) == 1 and len(comfy.submitted) == 4


def test_vary_uploads_source_and_uses_image_to_image(creator, comfy):
    cid = with_round(creator, comfy)
    source = creator.get(cid)["rounds"][0]["images"][1]
    for strength, denoise, round_no in (("subtle", 0.35, 2), ("strong", 0.6, 3)):
        creator.vary(cid, 1, 2, strength, note="longer coat")
        creator.tick()
        wf = comfy.submitted[-1]
        loaded = wf["40"]["inputs"]["image"].removeprefix("character_creator/")
        assert comfy.uploads[loaded] == creator.image_path(cid, source).read_bytes()
        assert wf["41"] == {"class_type": "VAEEncode", "inputs": {"pixels": ["40", 0], "vae": ["4", 2]}}
        assert wf["3"]["inputs"]["latent_image"] == ["41", 0] and wf["3"]["inputs"]["denoise"] == denoise
        assert "EmptyLatentImage" not in classes(wf) and "longer coat" in text(wf)
        render(creator, comfy)
        got = creator.get(cid)["rounds"][-1]
        assert got["n"] == round_no and got["type"] == "vary" and got["from"] == source and got["note"] == "longer coat"
        assert len(got["images"]) == 4
    with pytest.raises(BadRequest):
        creator.vary(cid, 1, 2, "wild")
    with pytest.raises(BadRequest):
        creator.vary(cid, 9, 1, "subtle")


def test_uploads_cant_collide_or_name_the_character(creator, comfy):
    cid, other = with_round(creator, comfy), with_round(creator, comfy)
    for c in (cid, other):
        creator.vary(c, 1, 1, "subtle")
    render(creator, comfy)
    assert len(comfy.uploads) == 8 and not any(c in n for n in comfy.uploads for c in (cid, other))


@pytest.mark.parametrize("note", ["nude", "(nude:1.4)", 5])
def test_notes_are_screened_like_answers(creator, comfy, note):
    cid = with_round(creator, comfy)
    with pytest.raises(BadRequest):
        creator.generate(cid, note=note)
    with pytest.raises(BadRequest):
        creator.vary(cid, 1, 1, "subtle", note=note)


def test_reroll_note_reaches_the_prompt_cleaned(creator, comfy):
    cid = with_round(creator, comfy)
    creator.generate(cid, note="(red scarf:1.5)")
    creator.tick()
    assert "red scarf" in text(comfy.submitted[-1]) and "1.5" not in text(comfy.submitted[-1])


def test_nothing_private_reaches_comfyui_filenames(creator, comfy):
    cid = with_round(creator, comfy)
    assert all(cid not in wf["9"]["inputs"]["filename_prefix"] for wf in comfy.submitted)


def test_earlier_round_can_be_picked_and_unknown_image_refused(creator, comfy):
    cid = with_round(creator, comfy)
    creator.generate(cid)
    render(creator, comfy)
    first = creator.get(cid)["rounds"][0]["images"]
    assert creator.pick(cid, 1, 3)["picked"] == first[2]
    assert creator.get(cid)["seed"] == int(first[2].rsplit("-", 1)[1].removesuffix(".png"))
    for round_no, n in ((1, 5), (3, 1), (1, 0), ("1", 1), (1, True)):
        with pytest.raises(BadRequest):
            creator.pick(cid, round_no, n)
    assert creator.get(cid)["picked"] == first[2]


def test_favourite_toggles_and_survives_later_rounds(creator, comfy):
    cid = with_round(creator, comfy)
    name = creator.get(cid)["rounds"][0]["images"][0]
    assert creator.favourite(cid, 1, 1)["favourites"] == [name]
    creator.generate(cid)
    render(creator, comfy)
    assert creator.get(cid)["favourites"] == [name]
    assert creator.favourite(cid, 1, 1)["favourites"] == []


def test_lock_needs_a_pick_then_queues_all_sheets(creator, comfy):
    cid = with_round(creator, comfy)
    with pytest.raises(BadRequest):
        creator.lock(cid)
    creator.pick(cid, 1, 2)
    seed = creator.get(cid)["seed"]
    before = len(comfy.submitted)
    assert creator.lock(cid)["status"] == "locked"
    assert creator.get(cid)["queue"]["label"] == "sheets"
    render(creator, comfy)
    sheets = comfy.submitted[before:]
    assert len(sheets) == 8
    assert "turnaround" in text(sheets[0]) and "UpscaleModelLoader" in classes(sheets[0])
    assert "color guide" in text(sheets[1])
    assert "1girl" in text(sheets[2]) and "close-up" in text(sheets[2])
    for wf in sheets[2:]:
        assert (wf["5"]["inputs"]["width"], wf["5"]["inputs"]["height"]) == EXPRESSION_SIZE
        assert "katana" in text(wf, "7") and "katana" not in text(wf)
    assert {wf["3"]["inputs"]["seed"] for wf in sheets} == {seed}   # the picked look, as in approve then sheets
    got = creator.get(cid)
    assert got["sheets"] == {"turnaround": "turnaround.png", "colorguide": "colorguide.png",
                             "expressions": [f"expression-{i}.png" for i in range(1, 7)]}
    for name in ("turnaround.png", "colorguide.png", "expression-6.png"):
        assert creator.image_path(cid, name).exists()


def test_locked_character_can_redo_a_sheet_but_nothing_else(creator, comfy):
    cid = with_round(creator, comfy)
    creator.pick(cid, 1, 1)
    with pytest.raises(BadRequest):
        creator.redo_sheet(cid, "turnaround")   # not locked yet
    creator.lock(cid)
    with pytest.raises(Busy):
        creator.redo_sheet(cid, "turnaround")   # its sheets are still in line
    render(creator, comfy)
    old = creator.image_path(cid, "turnaround.png").read_bytes()
    before = len(comfy.submitted)
    creator.redo_sheet(cid, "turnaround")
    creator.tick()
    comfy.fail()
    creator.tick()
    assert creator.image_path(cid, "turnaround.png").read_bytes() == old
    assert creator.get(cid)["sheets"]["turnaround"] == "turnaround.png"
    creator.retry(cid)
    render(creator, comfy)
    assert creator.image_path(cid, "turnaround.png").read_bytes() != old
    assert comfy.submitted[-1]["3"]["inputs"]["seed"] != creator.get(cid)["seed"]   # a redo must look different
    creator.redo_sheet(cid, "expressions")
    render(creator, comfy)
    assert len(comfy.submitted) == before + 2 + 6
    with pytest.raises(BadRequest):
        creator.redo_sheet(cid, "nope")
    for change in (lambda: creator.generate(cid), lambda: creator.vary(cid, 1, 1, "subtle"), lambda: creator.pick(cid, 1, 2),
                   lambda: creator.lock(cid), lambda: creator.update_answers(cid, GOOD)):
        with pytest.raises(BadRequest):
            change()


def test_lock_waits_for_a_running_batch(creator, comfy):
    cid = with_round(creator, comfy)
    creator.pick(cid, 1, 1)
    creator.generate(cid)
    with pytest.raises(Busy):
        creator.lock(cid)
    assert creator.get(cid)["status"] == "draft"


def test_update_answers_screens_and_keeps_the_old_ones_when_refused(creator):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    with pytest.raises(BadRequest, match="nude"):
        creator.update_answers(cid, {**GOOD, "outfit": "nude"})
    assert "outfit" not in creator.get(cid)["answers"]
    assert creator.update_answers(cid, {**GOOD, "outfit": "trench coat"})["answers"]["outfit"] == "trench coat"


def test_suggestion_renders_nothing_until_accepted(creator, comfy):
    s = creator.create("npc", GOOD, by_owner=False)
    assert s["status"] == "suggested"
    with pytest.raises(BadRequest):
        creator.generate(s["id"])
    creator.tick()
    assert comfy.submitted == []
    assert creator.accept(s["id"])["status"] == "accepted"
    creator.generate(s["id"])
    creator.tick()
    assert len(comfy.submitted) == 1
    with pytest.raises(BadRequest):
        creator.accept(s["id"])


def test_declined_suggestion_keeps_the_note_and_never_renders(creator):
    s = creator.create("ai", GOOD, by_owner=False)
    got = creator.decline(s["id"], "too close to Mei Lan")
    assert got["status"] == "declined" and got["note"] == "too close to Mei Lan"
    with pytest.raises(BadRequest):
        creator.generate(s["id"])
    with pytest.raises(BadRequest):
        creator.accept(s["id"])
    with pytest.raises(BadRequest):
        creator.decline(creator.create("player", GOOD, by_owner=False)["id"], "no")


def test_player_cannot_create_npc_directly_as_owner(creator):
    assert creator.create("npc", GOOD, by_owner=False)["status"] == "suggested"
    assert creator.create("npc", GOOD, by_owner=True)["status"] == "draft"
    assert creator.create("player", GOOD, by_owner=False)["status"] == "draft"
    for kind in ("owner", "character", None, ["npc"]):
        with pytest.raises(BadRequest):
            creator.create(kind, GOOD, by_owner=True)


def test_image_path_refuses_traversal(creator, comfy):
    cid = with_round(creator, comfy)
    for name in ("../character.json", "character.json", "../../queue.json", "r1-c1-1.png\n", "r1-c1-1.png/../x", "turnaround.png"):
        with pytest.raises(KeyError):
            creator.image_path(cid, name)


def test_ids_are_private_length_and_unknown_id_is_keyerror(creator):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    assert len(cid) == 32 and cc.TOKEN.fullmatch(cid)
    for bad in ("x" * 32, "../" + cid, cid + "\n", ""):
        for call in (creator.get, creator.generate, creator.delete):
            with pytest.raises(KeyError):
                call(bad)


def test_delete_removes_the_character_and_its_queued_work(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.tick()
    creator.delete(cid)
    with pytest.raises(KeyError):
        creator.get(cid)
    assert not (creator.root / "characters" / cid).exists()
    comfy.finish()
    creator.tick()
    assert len(comfy.submitted) == 1 and not (creator.root / "characters" / cid).exists()


def test_list_all_is_everyone_without_leaking_workflows(creator):
    one = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(one)
    two = creator.create("npc", {**GOOD, "name": "Aki"}, by_owner=False)["id"]
    got = creator.list_all()
    assert [c["id"] for c in got] == [two, one] and got[1]["queue"]["position"] == 1
    assert "workflow" not in repr(got) and "workflow" not in repr(creator.get(one))


def test_corrupt_state_is_never_overwritten(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    path = creator.root / "characters" / cid / "character.json"
    path.write_text("{broken")
    with pytest.raises(ValueError):
        creator.generate(cid)
    assert path.read_text() == "{broken" and comfy.submitted == []


def test_gpu_is_handed_back_when_queue_empties(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.tick()
    assert comfy.freed == 0   # idle: nothing to hand back
    creator.generate(cid)
    creator.tick()
    comfy.finish()
    creator.tick()
    assert comfy.freed == 0   # three more to go
    render(creator, comfy)
    assert comfy.freed == 1
    creator.tick()
    assert comfy.freed == 1


def test_gpu_isnt_freed_while_someone_elses_job_runs(creator, comfy):
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    for _ in range(4):
        creator.tick()
        comfy.finish()
    comfy.others_running = True
    creator.tick()
    assert len(creator.get(cid)["rounds"]) == 1 and comfy.freed == 0


def test_best_effort_gpu_calls_cant_stop_a_render(creator, comfy):
    def broken():
        raise OSError("no")
    comfy.free_ollama = comfy.free_comfy = broken
    cid = with_round(creator, comfy)
    assert len(creator.get(cid)["rounds"]) == 1


def test_worker_logs_errors_and_keeps_going(creator, comfy, capsys):
    stop = threading.Event()
    calls = []

    def tick():
        calls.append(1)
        if len(calls) == 2:
            stop.set()
        raise OSError("ComfyUI is down")

    creator.tick = tick
    cc.run_worker(creator, stop, interval=0)
    assert len(calls) == 2 and "ComfyUI is down" in capsys.readouterr().err


def test_comfy_upload_posts_multipart_to_comfyui():
    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.update(path=self.path, msg=email.message_from_bytes(f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        got = Comfy(f"http://127.0.0.1:{server.server_port}", "http://127.0.0.1:9").upload("a.png", b"\x89PNG\r\n\x00")
    finally:
        server.shutdown()
    assert got == "character_creator/a.png" and seen["path"] == "/upload/image"
    parts = {p.get_param("name", header="content-disposition"): p for p in seen["msg"].get_payload()}
    assert parts["subfolder"].get_payload() == "character_creator" and parts["overwrite"].get_payload() == "true"
    assert parts["image"].get_filename() == "a.png" and parts["image"].get_payload(decode=True) == b"\x89PNG\r\n\x00"
