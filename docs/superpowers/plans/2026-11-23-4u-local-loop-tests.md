# 4U Box Local Loop Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make looping background clips from approved stills on the 4U box's 4070 with Wan 2.2, AniSora V3 and LTX-2.3, file them as ordinary shorts takes, and judge them against a few Seedance 2.5 clips.

**Architecture:** A new shorts backend `tools/shorts/backends/comfy_video.py` sits beside `fal.py`. It loads one ComfyUI workflow JSON per model, patches the start and end frames, prompt, length and seed by node title, runs it through the existing `tools.image_studio.Comfy` client, and files the result with `takes.file_take` at no cost. The page, verdicts and assembly all reuse the existing take flow. A seam score (first frame against last frame) shows how cleanly each clip loops.

**Tech Stack:** Python 3, ComfyUI (ComfyUI-GGUF, Kijai's WanVideoWrapper, the native Wan/LTX nodes), ffmpeg, pytest.

**Spec:** `docs/superpowers/research/2026-11-23-local-video-and-stills.md` (owner goal and review cards `vid-local` and `vid-paid`, both kept 2026-11-23). Shorts spec: `docs/superpowers/specs/2026-11-08-shorts-studio-design.md`.

## Global Constraints

- Owner goal: local stills plus minimal looping background motion; Seedance only for final polish.
- No daytime scenes or images.
- GPU gentle: only requested batches, kept small; cool down from 74 °C to 62 °C with 45 s rests between jobs.
- Every paid run (fal Seedance) needs the owner's go-ahead in chat, with the cost stated.
- Downloads have a standing OK: check the licence first, and tell the owner afterwards.
- NoobAI-XL stills stay the source of truth; a loop's first and last frames are an approved still.
- Test size: 832×480, 5 s. Wan runs at 16 fps and needs 4n+1 frames (81 for 5 s). LTX needs 8n+1 frames.
- Reviews go through the Nightwire Reviews inbox, plus the existing shorts take page for the clips.
- Commits carry no AI-attribution trailer.

## Review Focus

1. ComfyUI runs out of memory, or a node errors: the take isn't filed, and the error names the model and node.
2. The ComfyUI host is unreachable, or the still is missing: a clear message, nothing is queued.
3. Different output nodes (VHS `gifs` against native `videos`): both are found, and a run with no video output is an error.
4. Seconds that don't fit the frame rule: rounded up to the next valid count, never sent invalid.
5. The workflow JSON is missing a titled node the patcher needs: a clear error at load, not a silent unpatched run.

---

### Task 1: Set up the box (manual, owner hardware)

**Files:**
- Modify: `docs/superpowers/research/2026-11-23-local-video-and-stills.md` (licence and fit notes)

- [ ] **Step 1:** On the 4070, install or update ComfyUI. Add the ComfyUI-GGUF node pack, Kijai's ComfyUI-WanVideoWrapper (for AniSora) and the SeedVR2 node pack.
- [ ] **Step 2:** Read these licences before downloading anything:
  - the Wan 2.2 A14B I2V card;
  - the AniSora V3 repo;
  - the LTX-2 community licence text.

  Note each one's terms on promotional use in the research doc. Skip a model whose terms rule out promotion, and tell the owner.
- [ ] **Step 3:** Download the weights:
  - Wan 2.2 I2V A14B Q5 GGUF (high and low noise) plus the lightx2v 4-step LoRAs;
  - AniSora V3 fp8;
  - LTX-2.3 distilled GGUF.
- [ ] **Step 4:** In the ComfyUI UI, build or load each model's first+last-frame image-to-video template and run it once at 832×480, 5 s. Export each graph in API format to `tools/shorts/backends/workflows/{wan22-flf,anisora-v3,ltx23}.json`.
  - Give the nodes these titles: `start`, `end`, `prompt`, `length` and `seed`.
  - Wan 2.2 has two samplers. Title the high-noise one `seed` (it adds the noise); titling both is fine, as every `seed` node is patched.
  - A first+last-frame workflow always gets an end frame, so `--no-loop` is refused for it.
  - AniSora and LTX may lack an end-frame input. If so, leave `end` out of that file and note it.
- [ ] **Step 5:** Record seconds per clip and peak VRAM for each model in the research doc (`nvidia-smi --query-gpu=memory.used --format=csv -l 1` during the run).
- [ ] **Step 6:** Commit.

```bash
git add tools/shorts/backends/workflows docs/superpowers/research/2026-11-23-local-video-and-stills.md
git commit -m "4U box: local video workflows and measured fit"
```

### Task 2: Workflow patching

**Files:**
- Create: `tools/shorts/backends/comfy_video.py`
- Test: `tests/test_shorts_comfy_video.py` (with small fixture workflows in `tests/fixtures/comfy_video/`)

**Interfaces:**
- Produces:
  - `MODELS: dict[str, dict]`, keyed `wan22-flf`, `anisora-v3`, `ltx23`, each with `fps: int`, `frame_step: int` (4 or 8) and `workflow: str` (file name).
  - `frames(model: str, seconds: float) -> int`.
  - `graph(model: str, start: str, end: str | None, prompt: str, seconds: float, seed: int) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
def test_frames_follow_each_models_rule():
    assert frames("wan22-flf", 5) == 81
    assert frames("wan22-flf", 4.9) == 81  # rounded up to the next 4n+1
    assert (frames("ltx23", 5) - 1) % 8 == 0

def test_a_loop_uses_the_same_still_at_both_ends():
    g = graph("wan22-flf", "izakaya.png", "izakaya.png", "rain on the window, neon flicker", 5, 7)
    assert titled(g, "start")["inputs"]["image"] == titled(g, "end")["inputs"]["image"] == "izakaya.png"
    assert titled(g, "seed")["inputs"]["seed"] == 7 and titled(g, "length")["inputs"]["length"] == 81

def test_a_workflow_without_a_needed_title_fails_at_load():
    with pytest.raises(ValueError, match="prompt"):
        graph_from(FIXTURES / "no_prompt.json", ...)

def test_an_end_frame_on_a_model_without_one_is_refused():
    with pytest.raises(ValueError, match="end frame"):
        graph("ltx23-no-end-fixture", "a.png", "a.png", "x", 5, 1)
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest tests/test_shorts_comfy_video.py -v`
Expected: FAIL with an ImportError.

- [ ] **Step 3: Implement `frames`, `graph`, and the `titled(g, title)` helper in `comfy_video.py`**

Find each node by `_meta.title` and set its widget input. Seed and length inputs are named after the node type's own input, so read the name from the loaded JSON's existing keys and don't hard-code it.

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python -m pytest tests/test_shorts_comfy_video.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/shorts/backends/comfy_video.py tests/test_shorts_comfy_video.py tests/fixtures/comfy_video
git commit -m "Shorts: ComfyUI video workflows patched by node title"
```

### Task 3: Run a take, and score the seam

**Files:**
- Modify: `tools/shorts/backends/comfy_video.py`
- Test: `tests/test_shorts_comfy_video.py`

**Interfaces:**
- Consumes: `graph` (Task 2); `tools.image_studio.Comfy` (`upload`, `submit`, `history`, `image`); `tools.shorts.takes.file_take(shot_dir, video, meta) -> str`.
- Produces:
  - `run_take(short_dir: Path, shot_id: str, model: str, prompt: str, still: Path, seconds: float, *, comfy, seed: int = 0, loop: bool = True, poll_s: float = 5.0, timeout_s: float = 1800) -> str`, which returns the take id.
  - `seam(video: Path) -> float`.

- [ ] **Step 1: Write the failing tests** (use a fake Comfy object with canned `history`)

```python
def test_a_run_files_a_free_comfy_take_with_its_seam(tmp_path):
    tid = run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(video=TWO_SECOND_STATIC_MP4))
    meta = take_meta(tmp_path / "shots" / "s1", tid)
    assert (meta["backend"], meta["cost"], meta["model"]) == ("comfy", 0, "wan22-flf")
    assert meta["seam"] < 1.0  # a static clip loops perfectly

def test_both_output_node_kinds_are_found():  # VHS "gifs" and native "videos"
    ...

def test_a_node_error_files_nothing_and_names_the_node(tmp_path):
    with pytest.raises(RuntimeError, match="WanImageToVideo"):
        run_take(tmp_path, "s1", "wan22-flf", "rain", still, 5, comfy=FakeComfy(error_node="WanImageToVideo"))
    assert not (tmp_path / "shots" / "s1" / "takes").exists()

def test_a_missing_still_queues_nothing(tmp_path):
    fake = FakeComfy()
    with pytest.raises(FileNotFoundError):
        run_take(tmp_path, "s1", "wan22-flf", "rain", tmp_path / "nope.png", 5, comfy=fake)
    assert fake.submitted == []

def test_seam_is_near_zero_for_a_loop_and_large_for_a_cut(tmp_path):
    assert seam(make_mp4(tmp_path, ["red"] * 8)) < 1.0
    assert seam(make_mp4(tmp_path, ["red"] * 4 + ["blue"] * 4)) > 20.0
```

`make_mp4` builds the clips with ffmpeg's `color` source.

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest tests/test_shorts_comfy_video.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `run_take` and `seam`**
  - `seam` uses ffmpeg to grab the first and last frames as 64×36 grey raw bytes and returns the mean absolute difference on a 0-255 scale.
  - `run_take` waits by polling `history` until the job is done or errors, then downloads the first video output and calls `file_take` with `{"model", "backend": "comfy", "cost": 0, "seconds", "seed", "seam", "still": still.name}`.
  - Catch an unreachable host (`URLError`) and re-raise it as `RuntimeError(f"ComfyUI at {url} unreachable")`.

- [ ] **Step 4: Run the tests and see them pass**

Run: `.venv/bin/python -m pytest tests/test_shorts_comfy_video.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/shorts/backends/comfy_video.py tests/test_shorts_comfy_video.py
git commit -m "Shorts: local ComfyUI video takes with a loop seam score"
```

### Task 4: The `loop` command

**Files:**
- Modify: `tools/shorts/__main__.py`
- Test: `tests/test_shorts_cli.py`

**Interfaces:**
- Consumes: `comfy_video.run_take`, `comfy_video.MODELS`.
- Produces: `python -m tools.shorts loop <short> <shot> --still PATH --model {wan22-flf,anisora-v3,ltx23} [--seconds 5] [--seed N] [--prompt TEXT] [--comfy URL]`. It needs no `--yes` because nothing is paid. The default `--comfy` is `$NIGHTWIRE_COMFY_URL`, then `http://127.0.0.1:8188`.

- [ ] **Step 1: Write the failing tests**

```python
def test_loop_runs_a_local_take_without_asking(monkeypatch, tmp_path): ...  # run_take called once, exit 0
def test_loop_refuses_a_paid_model(tmp_path):
    assert main(["loop", "pilot", "s1", "--still", str(still), "--model", "seedance-2.5"]) == 2  # argparse choices
```

- [ ] **Step 2: Run the tests and see them fail**

Run: `.venv/bin/python -m pytest tests/test_shorts_cli.py -k loop -v`
Expected: FAIL

- [ ] **Step 3: Add the subcommand next to the fal take command**

The default prompt is the shot's motion layer from `prompt.py` if it has one, otherwise "the city moves; the people stay still". Print the take id, the seconds taken and the seam.

- [ ] **Step 4: Run the full suite and see it pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tools/shorts/__main__.py tests/test_shorts_cli.py
git commit -m "Shorts: loop command for local background loops"
```

### Task 5: The test round (manual, with the owner)

**Files:**
- Modify: `docs/superpowers/research/2026-11-23-local-video-and-stills.md` (results)

- [ ] **Step 1:** Pick 3 approved night stills with a still character, for example Mama Sato's izakaya and a Ring Line platform. Then make 9 loops (3 models × 3 stills, seed 0) with `loop`, keeping the GPU rests.
- [ ] **Step 2:** Ask the owner for a go-ahead on 3 Seedance 2.5 clips: 480p, 5 s, the same still as first and last frame, about $1.10 each, about $3.30 in total. Run them with the existing fal take command only after a yes.
- [ ] **Step 3:** Put one inbox card per still on the Nightwire Reviews artifact, pointing to the shorts take page. The owner marks the best clip per still, and whether any local clip is good enough without Seedance.
- [ ] **Step 4:** Write up the results in the research doc: times, VRAM, seams, the owner's picks. Then make the 3090 call, and pick the default local model for loops.
- [ ] **Step 5:** Commit.

```bash
git add docs/superpowers/research/2026-11-23-local-video-and-stills.md
git commit -m "4U box: local loop test results"
```
