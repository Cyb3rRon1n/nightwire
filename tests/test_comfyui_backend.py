import pytest

from narrator.comfyui_backend import ComfyUIBackend


class _FakeResponse:
    def __init__(self, json_data=None, content=b""):
        self._json_data = json_data
        self.content = content

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass


class _FakeComfyClient:
    """Stands in for httpx.AsyncClient - only the methods ComfyUIBackend
    actually calls (post, get), duck-typed to httpx's own response shape."""

    def __init__(self, prompt_id="abc123", history=None, history_sequence=None, image_bytes=b"fake-comfyui-png"):
        self.prompt_id = prompt_id
        self.history = history if history is not None else {
            "abc123": {
                "outputs": {
                    "9": {"images": [{"filename": "nightwire_00001_.png", "subfolder": "", "type": "output"}]}
                }
            }
        }
        # When set, each /history poll pops the next entry off this list
        # instead of returning the fixed self.history - lets a test simulate
        # history changing shape across successive polls (e.g. present-but-
        # empty, then populated).
        self.history_sequence = list(history_sequence) if history_sequence is not None else None
        self.image_bytes = image_bytes
        self.calls = []

    async def post(self, url, json=None):
        self.calls.append(("post", url, json))
        return _FakeResponse(json_data={"prompt_id": self.prompt_id})

    async def get(self, url, params=None):
        self.calls.append(("get", url, params))
        if url.startswith("/history/"):
            if self.history_sequence is not None:
                next_history = self.history_sequence.pop(0) if self.history_sequence else self.history
                return _FakeResponse(json_data=next_history)
            return _FakeResponse(json_data=self.history)
        if url == "/view":
            return _FakeResponse(content=self.image_bytes)
        raise AssertionError(f"unexpected GET {url}")


async def _no_sleep(seconds):
    pass


@pytest.mark.asyncio
async def test_generate_portrait_returns_fetched_image_bytes():
    client = _FakeComfyClient(image_bytes=b"portrait-bytes")
    backend = ComfyUIBackend(checkpoint="v1-5-pruned-emaonly-fp16.safetensors", client=client, sleep_fn=_no_sleep)

    result = await backend.generate_portrait("a lean netrunner in a rain-slicked jacket")

    assert result == b"portrait-bytes"


@pytest.mark.asyncio
async def test_generate_portrait_builds_correct_workflow_graph():
    client = _FakeComfyClient()
    backend = ComfyUIBackend(checkpoint="v1-5-pruned-emaonly-fp16.safetensors", client=client, sleep_fn=_no_sleep)

    await backend.generate_portrait("a lean netrunner")

    submit_calls = [c for c in client.calls if c[0] == "post"]
    assert len(submit_calls) == 1
    _, url, payload = submit_calls[0]
    assert url == "/prompt"
    nodes = payload["prompt"]
    assert nodes["4"]["class_type"] == "CheckpointLoaderSimple"
    assert nodes["4"]["inputs"]["ckpt_name"] == "v1-5-pruned-emaonly-fp16.safetensors"
    assert nodes["6"]["inputs"]["text"] == "a lean netrunner"
    assert nodes["5"]["inputs"]["width"] == 512
    assert nodes["5"]["inputs"]["height"] == 768
    assert nodes["9"]["class_type"] == "SaveImage"


@pytest.mark.asyncio
async def test_generate_scene_uses_square_dimensions():
    client = _FakeComfyClient()
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep)

    await backend.generate_scene("a rain-slicked alley, neon signs", reference_paths=[])

    submit_calls = [c for c in client.calls if c[0] == "post"]
    nodes = submit_calls[0][2]["prompt"]
    assert nodes["5"]["inputs"]["width"] == 512
    assert nodes["5"]["inputs"]["height"] == 512
    assert nodes["6"]["inputs"]["text"] == "a rain-slicked alley, neon signs"


@pytest.mark.asyncio
async def test_generate_portrait_fetches_the_view_with_history_image_info():
    client = _FakeComfyClient(
        prompt_id="xyz",
        history={
            "xyz": {"outputs": {"9": {"images": [{"filename": "shot.png", "subfolder": "sub", "type": "output"}]}}}
        },
    )
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep)

    await backend.generate_portrait("a fixer")

    view_calls = [c for c in client.calls if c[0] == "get" and c[1] == "/view"]
    assert len(view_calls) == 1
    assert view_calls[0][2] == {"filename": "shot.png", "subfolder": "sub", "type": "output"}


@pytest.mark.asyncio
async def test_generate_portrait_raises_timeout_error_when_never_ready():
    client = _FakeComfyClient(history={})  # prompt_id never appears
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep, timeout=0.05, poll_interval=0.01)

    with pytest.raises(TimeoutError):
        await backend.generate_portrait("a fixer")


@pytest.mark.asyncio
async def test_generate_portrait_does_not_break_on_history_entry_with_no_outputs_yet():
    # Some ComfyUI versions insert the history[prompt_id] key at execution
    # start, before "outputs" is populated - the poll loop must not treat a
    # present-but-outputs-less entry as "done".
    client = _FakeComfyClient(
        prompt_id="abc123",
        history_sequence=[
            {"abc123": {}},  # key present, no outputs yet - must not break
            {"abc123": {"outputs": {}}},  # outputs present but empty - must not break
            {
                "abc123": {
                    "outputs": {
                        "9": {"images": [{"filename": "done.png", "subfolder": "", "type": "output"}]}
                    }
                }
            },
        ],
    )
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep, timeout=5.0, poll_interval=0.0)

    result = await backend.generate_portrait("a fixer")

    assert result == b"fake-comfyui-png"
    history_polls = [c for c in client.calls if c[0] == "get" and c[1].startswith("/history/")]
    assert len(history_polls) == 3


@pytest.mark.asyncio
async def test_generate_portrait_raises_runtime_error_when_outputs_have_no_images():
    client = _FakeComfyClient(
        prompt_id="abc123",
        history={"abc123": {"outputs": {"9": {"images": []}}}},
    )
    backend = ComfyUIBackend(client=client, sleep_fn=_no_sleep)

    with pytest.raises(RuntimeError, match="abc123"):
        await backend.generate_portrait("a fixer")


def _noob(**kw):
    return ComfyUIBackend(base_url="http://x", profile="noobai", lora="Smooth_Booster_v3.safetensors", **kw)


def _by_type(wf):
    return {n["class_type"]: n for n in wf.values()}


def test_noobai_profile_builds_the_locked_graph():
    b = _noob()
    assert b.wants_tags is True and b.checkpoint == "NoobAI-XL-Vpred-v1.0.safetensors"
    wf = b._build_workflow("POS", 7, 832, 1216, "nightwire_portrait", negative="NEG")
    t = _by_type(wf)
    assert t["ModelSamplingDiscrete"]["inputs"]["sampling"] == "v_prediction"
    assert t["ModelSamplingDiscrete"]["inputs"]["zsnr"] is True
    assert t["RescaleCFG"]["inputs"]["multiplier"] == 0.6
    assert t["LoraLoader"]["inputs"]["lora_name"] == "Smooth_Booster_v3.safetensors"
    assert t["LoraLoader"]["inputs"]["strength_model"] == 0.6 == t["LoraLoader"]["inputs"]["strength_clip"]
    assert t["CLIPSetLastLayer"]["inputs"]["stop_at_clip_layer"] == -2
    k = t["KSampler"]["inputs"]
    assert (k["sampler_name"], k["scheduler"], k["steps"], k["cfg"]) == ("euler", "normal", 28, 4.5)
    assert t["VAEDecodeTiled"]["inputs"]["tile_size"] == 512
    assert (t["EmptyLatentImage"]["inputs"]["width"], t["EmptyLatentImage"]["inputs"]["height"]) == (832, 1216)
    texts = sorted(n["inputs"]["text"] for n in wf.values() if n["class_type"] == "CLIPTextEncode")
    assert texts == ["NEG", "POS"]


def test_noobai_without_lora_skips_the_loader():
    b = ComfyUIBackend(base_url="http://x", profile="noobai", lora="")
    assert "LoraLoader" not in _by_type(b._build_workflow("P", 1, 832, 1216, "x"))


def test_sd15_profile_is_unchanged_and_does_not_want_tags():
    b = ComfyUIBackend(base_url="http://x")
    assert b.wants_tags is False and b.checkpoint == "v1-5-pruned-emaonly-fp16.safetensors"
    t = _by_type(b._build_workflow("P", 1, 512, 768, "x"))
    assert "ModelSamplingDiscrete" not in t and "VAEDecode" in t


def test_noobai_sizes():
    from narrator import comfyui_backend as cb
    assert cb._NOOBAI_PORTRAIT_SIZE == (832, 1216) and cb._NOOBAI_SCENE_SIZE == (1216, 832)


def test_noobai_default_negative_is_the_tag_negative():
    from narrator.image_prompt import NEGATIVE
    texts = {n["inputs"]["text"] for n in _noob()._build_workflow("P", 1, 832, 1216, "x").values() if n["class_type"] == "CLIPTextEncode"}
    assert texts == {"P", NEGATIVE}
