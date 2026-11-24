from pathlib import Path

import pytest

from tools.shorts.backends import comfy_video
from tools.shorts.backends.comfy_video import frames, graph, graph_from, titled

FIXTURES = Path(__file__).parent / "fixtures" / "comfy_video"


@pytest.fixture(autouse=True)
def _fixture_workflows(monkeypatch):
    monkeypatch.setattr(comfy_video, "WORKFLOWS", FIXTURES)


def test_frames_follow_each_models_rule():
    assert frames("wan22-flf", 5) == 81
    assert frames("wan22-flf", 4.9) == 81  # rounded up to the next 4n+1
    assert (frames("ltx23", 5) - 1) % 8 == 0 and frames("ltx23", 5) >= 5 * comfy_video.MODELS["ltx23"]["fps"]


def test_a_loop_uses_the_same_still_at_both_ends():
    g = graph("wan22-flf", "izakaya.png", "izakaya.png", "rain on the window, neon flicker", 5, 7)
    assert titled(g, "start")["inputs"]["image"] == titled(g, "end")["inputs"]["image"] == "izakaya.png"
    assert titled(g, "seed")["inputs"]["noise_seed"] == 7 and titled(g, "length")["inputs"]["length"] == 81
    assert titled(g, "prompt")["inputs"]["text"] == "rain on the window, neon flicker"


def test_a_workflow_without_a_needed_title_fails_at_load():
    with pytest.raises(ValueError, match="prompt"):
        graph_from(FIXTURES / "no_prompt.json", "wan22-flf", "a.png", "a.png", "x", 5, 1)


def test_an_end_frame_on_a_model_without_one_is_refused():
    with pytest.raises(ValueError, match="end frame"):
        graph("ltx23", "a.png", "a.png", "x", 5, 1)
    assert "end" not in {n["_meta"]["title"] for n in graph("ltx23", "a.png", None, "x", 5, 1).values()}


import json
import subprocess
import urllib.error

from tools.shorts.backends.comfy_video import run_take, seam


def make_mp4(tmp_path: Path, colours: list[str], name: str = "") -> Path:
    """One 0.5 s segment per colour, joined: a clip whose first and last frames we know."""
    out = tmp_path / (name or f"{'-'.join(colours)}.mp4")
    src = [x for c in colours for x in ("-f", "lavfi", "-i", f"color=c={c}:s=64x36:r=8:d=0.5")]
    joined = "".join(f"[{i}:v]" for i in range(len(colours))) + f"concat=n={len(colours)}:v=1:a=0"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *src, "-filter_complex", joined, "-pix_fmt", "yuv420p", str(out)], check=True)
    return out


class FakeComfy:
    comfy = "http://fake:8188"

    def __init__(self, video: Path | None = None, kind: str = "gifs", error_node: str = "", down: bool = False,
                 drops: int = 0, interrupted: bool = False, running: bool = False, filename: str = "clip_00001.mp4"):
        self.video, self.kind, self.error_node, self.down = video, kind, error_node, down
        self.drops, self.interrupted, self.running, self.filename = drops, interrupted, running, filename
        self.submitted, self.uploads, self.cancelled, self.interrupts = [], [], [], []

    def cancel(self, pid):
        self.cancelled.append(pid)

    def queue(self):
        return {"queue_running": [[0, "p1", {}, {}, []]] if self.running else [], "queue_pending": []}

    def interrupt(self, pid):
        self.interrupts.append(pid)

    def upload(self, name, data):
        if self.down:
            raise urllib.error.URLError("refused")
        self.uploads.append(name)
        return f"nightwire/{name}"

    def submit(self, wf):
        self.submitted.append(wf)
        return "p1"

    def history(self, pid):
        if self.drops:
            self.drops -= 1
            raise TimeoutError("timed out")
        if self.running:
            return None
        if self.interrupted:
            return {"status": {"status_str": "error", "messages": [["execution_interrupted", {
                "node_id": "5", "node_type": "KSamplerAdvanced"}]]}, "outputs": {}}
        if self.error_node:
            return {"status": {"status_str": "error", "messages": [["execution_error", {
                "node_id": "4", "node_type": self.error_node, "exception_message": "CUDA out of memory"}]]}, "outputs": {}}
        out = {"6": {self.kind: [{"filename": self.filename, "subfolder": "", "type": "output"}]}} if self.video else {}
        return {"status": {"status_str": "success", "completed": True}, "outputs": out}

    def image(self, item):
        return self.video.read_bytes()


@pytest.fixture
def still(tmp_path):
    p = tmp_path / "izakaya.png"
    p.write_bytes(b"png")
    return p


def take_meta(shot_dir: Path, tid: str) -> dict:
    return json.loads((shot_dir / "takes" / f"{tid}.json").read_text())


def test_a_run_files_a_free_comfy_take_with_its_seam(tmp_path, still):
    tid = run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(video=make_mp4(tmp_path, ["red"] * 4)), poll_s=0)
    meta = take_meta(tmp_path / "shots" / "s1", tid)
    assert (meta["backend"], meta["cost"], meta["model"], meta["still"]) == ("comfy", 0, "wan22-flf", "izakaya.png")
    assert meta["seam"] < 1.0  # a static clip loops perfectly
    assert not (tmp_path / "shots" / "s1" / "incoming.mp4").exists()


def test_both_output_node_kinds_are_found(tmp_path, still):
    clip = make_mp4(tmp_path, ["red"] * 4)
    for kind in ("gifs", "videos"):
        assert run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(video=clip, kind=kind), poll_s=0)
    with pytest.raises(RuntimeError, match="no video"):
        run_take(tmp_path, "s2", "wan22-flf", "rain", still, 5, comfy=FakeComfy(), poll_s=0)


def test_a_node_error_files_nothing_and_names_the_node(tmp_path, still):
    with pytest.raises(RuntimeError, match="WanImageToVideo"):
        run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(error_node="WanImageToVideo"), poll_s=0)
    assert not (tmp_path / "shots" / "s1" / "takes").exists()


def test_a_missing_still_or_a_down_host_queues_nothing(tmp_path, still):
    fake = FakeComfy()
    with pytest.raises(FileNotFoundError):
        run_take(tmp_path, "s1", "wan22-flf", "rain", tmp_path / "nope.png", 5, comfy=fake)
    down = FakeComfy(down=True)
    with pytest.raises(RuntimeError, match="unreachable"):
        run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=down)
    assert fake.submitted == down.submitted == []


def test_seam_is_near_zero_for_a_loop_and_large_for_a_cut(tmp_path):
    assert seam(make_mp4(tmp_path, ["red"] * 8)) < 1.0
    assert seam(make_mp4(tmp_path, ["red"] * 4 + ["blue"] * 4)) > 20.0


def test_a_failed_seam_still_files_the_render(tmp_path, still, monkeypatch):
    def broken(_):
        raise subprocess.CalledProcessError(1, "ffmpeg")
    monkeypatch.setattr(comfy_video, "seam", broken)
    tid = run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(video=make_mp4(tmp_path, ["red"])), poll_s=0)
    assert take_meta(tmp_path / "shots" / "s1", tid)["seam"] is None


def test_a_refused_workflow_shows_comfys_reason(tmp_path, still):
    import io
    fake = FakeComfy()
    def refuse(wf):
        raise urllib.error.HTTPError("http://fake/prompt", 400, "Bad Request", {},
                                     io.BytesIO(b'{"node_errors": {"7": "ckpt not found"}}'))
    fake.submit = refuse
    with pytest.raises(RuntimeError, match="refused the workflow.*ckpt not found"):
        run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=fake, poll_s=0)


def test_a_dropped_poll_is_retried_and_a_timeout_cancels_only_our_prompt(tmp_path, still):
    clip = make_mp4(tmp_path, ["red"])
    assert run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(video=clip, drops=2), poll_s=0)
    with pytest.raises(RuntimeError, match="unreachable"):
        run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(video=clip, drops=3), poll_s=0)
    slow = FakeComfy(video=clip, running=True)
    with pytest.raises(RuntimeError, match="cancelled"):
        run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=slow, poll_s=0, timeout_s=0.01)
    assert slow.cancelled == slow.interrupts == ["p1"]


def test_an_interrupted_run_says_so(tmp_path, still):
    with pytest.raises(RuntimeError, match="KSamplerAdvanced.*interrupted"):
        run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(interrupted=True), poll_s=0)


def test_no_loop_on_a_first_last_frame_workflow_is_refused():
    with pytest.raises(ValueError, match="always takes an end frame"):
        graph("wan22-flf", "a.png", None, "x", 5, 1)


def test_a_webm_or_mkv_output_is_filed_as_h264_mp4(tmp_path, still):
    webm = tmp_path / "clip.mkv"  # this ffmpeg has no VP9 encoder; any non-mp4 container takes the same path
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(make_mp4(tmp_path, ["red"])), "-c:v", "mpeg4", str(webm)], check=True)
    tid = run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(video=webm, filename="c.mkv"), poll_s=0)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                            str(tmp_path / "shots" / "s1" / "takes" / f"{tid}.mp4")], capture_output=True, text=True).stdout
    assert probe.strip() == "h264" and not list((tmp_path / "shots" / "s1").glob("incoming*"))


def test_every_seed_node_gets_the_seed_and_seconds_must_be_positive(tmp_path):
    wf = json.loads((FIXTURES / "wan22-flf.json").read_text())
    wf["8"] = {"class_type": "KSamplerAdvanced", "inputs": {"noise_seed": 0}, "_meta": {"title": "seed"}}
    (tmp_path / "two.json").write_text(json.dumps(wf))
    g = graph_from(tmp_path / "two.json", "wan22-flf", "a.png", "a.png", "x", 5, 9)
    assert g["5"]["inputs"]["noise_seed"] == g["8"]["inputs"]["noise_seed"] == 9
    with pytest.raises(ValueError, match="more than 0"):
        frames("wan22-flf", 0)
