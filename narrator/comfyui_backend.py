import time
import uuid
from collections.abc import Awaitable, Callable

import httpx

_NEGATIVE_PROMPT = "blurry, deformed, extra limbs, bad anatomy, watermark, text, low quality"
_STEPS = 20
_CFG = 7.0
_SAMPLER = "euler"
_SCHEDULER = "normal"
_PORTRAIT_SIZE = (512, 768)
_SCENE_SIZE = (512, 512)


class ComfyUIBackend:
    """Talks to a real ComfyUI instance's HTTP API - workflow-graph shape
    (CheckpointLoaderSimple -> two CLIPTextEncode -> EmptyLatentImage ->
    KSampler -> VAEDecode -> SaveImage) and the submit/fetch sequence are a
    technical reference from oracle's own working ComfyUIBackend (the same
    external tool's API, not a design decision being copied).

    Polls GET /history instead of the websocket progress stream oracle's
    version uses - nightwire's ImageBackend protocol has no progress
    callback to feed, so there's nothing to stream to; polling avoids a
    new dependency (websockets) for a capability nothing would use.

    No reference-photo/img2img support - the real ComfyUI instance this
    targets (sentinel, verified live) has no IPAdapter/InstantID custom
    node installed. reference_photos/reference_paths are accepted (protocol
    compliance) and silently ignored - a known, documented limitation
    (see the Phase 10 design spec), not an oversight.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        checkpoint: str = "v1-5-pruned-emaonly-fp16.safetensors",
        timeout: float = 120.0,
        poll_interval: float = 1.0,
        client: httpx.AsyncClient | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.checkpoint = checkpoint
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._client = client or httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=30.0)
        if sleep_fn is not None:
            self._sleep = sleep_fn
        else:
            import asyncio

            self._sleep = asyncio.sleep

    def _build_workflow(self, prompt: str, seed: int, width: int, height: int, filename_prefix: str) -> dict:
        return {
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self.checkpoint}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": _NEGATIVE_PROMPT, "clip": ["4", 1]}},
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": seed,
                    "steps": _STEPS,
                    "cfg": _CFG,
                    "sampler_name": _SAMPLER,
                    "scheduler": _SCHEDULER,
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}},
        }

    async def _generate(self, prompt: str, width: int, height: int, filename_prefix: str) -> bytes:
        seed = uuid.uuid4().int & 0xFFFFFFFF
        workflow = self._build_workflow(prompt, seed, width, height, filename_prefix)

        submit = await self._client.post("/prompt", json={"prompt": workflow})
        submit.raise_for_status()
        prompt_id = submit.json()["prompt_id"]

        deadline = time.monotonic() + self.timeout
        history: dict = {}
        while time.monotonic() < deadline:
            response = await self._client.get(f"/history/{prompt_id}")
            response.raise_for_status()
            history = response.json()
            if history.get(prompt_id, {}).get("outputs"):
                break
            await self._sleep(self.poll_interval)
        else:
            raise TimeoutError(f"ComfyUI didn't finish generating within {self.timeout}s")

        outputs = history[prompt_id]["outputs"]
        image_info = next(
            (image for node_output in outputs.values() for image in node_output.get("images", [])),
            None,
        )
        if image_info is None:
            raise RuntimeError(f"ComfyUI returned no images for prompt {prompt_id}")

        view = await self._client.get(
            "/view",
            params={
                "filename": image_info["filename"],
                "subfolder": image_info.get("subfolder", ""),
                "type": image_info.get("type", "output"),
            },
        )
        view.raise_for_status()
        return view.content

    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes:
        width, height = _PORTRAIT_SIZE
        return await self._generate(description, width, height, "nightwire_portrait")

    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes:
        width, height = _SCENE_SIZE
        return await self._generate(prompt, width, height, "nightwire_scene")
