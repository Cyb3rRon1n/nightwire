import base64
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import httpx

from narrator.comfyui_backend import ComfyUIBackend


class ImageBackend(Protocol):
    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes: ...
    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes: ...


# ultra-fast-image-gen's own worker (frontend/image_server/optimized_image_server.py)
# only ever reads references[:2] (prepare_reference_paths) regardless of what's sent.
_MAX_REFERENCES = 2


class FluxWorkerBackend:
    """Talks to open-dungeon's image_server worker (POST /generate on port
    7869 by default) - the real API, read directly from
    frontend/image_server/optimized_image_server.py, not assumed from docs.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:7869",
        backend: str = "sdnq-hs",
        output_dir: Path | str = Path("frontend/public/generated"),
        http_fn: Callable[[dict], Awaitable[dict]] | None = None,
        # The worker's own defaults (its "fast" mode) target 1024px, which
        # needs ~16GB - real, live-verified OOM on an 8GB card (Phase 5 Task
        # 7). 512px is the documented fit for 8GB. Config, not a protocol
        # constant, per the spec's forward-compat requirement - bump this on
        # better hardware, no code change needed elsewhere.
        long_side: int = 512,
    ) -> None:
        self.base_url = base_url
        self.backend = backend
        self.output_dir = Path(output_dir)
        self.long_side = long_side
        self._http_fn = http_fn or self._default_http

    async def _default_http(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.base_url}/generate", json=payload)
            response.raise_for_status()
            return response.json()

    def _to_data_url(self, path: str) -> dict:
        data = Path(path).read_bytes()
        encoded = base64.b64encode(data).decode()
        return {"dataUrl": f"data:image/png;base64,{encoded}"}

    def _dimensions_for(self, aspect: str) -> tuple[int, int]:
        if aspect == "portrait":
            return round(self.long_side * 0.75), self.long_side
        if aspect == "landscape":
            return self.long_side, round(self.long_side * 0.75)
        return self.long_side, self.long_side

    async def _generate(
        self,
        prompt: str,
        aspect: str,
        reference_paths: list[str] | None = None,
        reference_photos: list[str] | None = None,
    ) -> bytes:
        from_paths = [self._to_data_url(p) for p in (reference_paths or [])]
        from_photos = [{"dataUrl": url} for url in (reference_photos or [])]
        references = (from_paths + from_photos)[:_MAX_REFERENCES]
        width, height = self._dimensions_for(aspect)
        payload = {
            "backend": self.backend,
            "prompt": prompt,
            "aspect": aspect,
            "width": width,
            "height": height,
            "references": references,
        }
        result = await self._http_fn(payload)
        return (self.output_dir / f"{result['id']}.png").read_bytes()

    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None) -> bytes:
        return await self._generate(description, aspect="portrait", reference_photos=reference_photos)

    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes:
        return await self._generate(prompt, aspect="square", reference_paths=reference_paths)


def create_image_backend() -> ImageBackend:
    """IMAGE_BACKEND selects the image backend at startup - config, not a
    runtime toggle, same shape TTSBackend selection already uses. Defaults
    to flux_worker (current behavior, unchanged for existing deployments)."""
    backend = os.environ.get("IMAGE_BACKEND", "flux_worker").strip().lower()
    if backend == "flux_worker":
        return FluxWorkerBackend(
            base_url=os.environ.get("FLUX_WORKER_URL", "http://127.0.0.1:7869"),
            output_dir=os.environ.get("IMAGE_OUTPUT_DIR", "frontend/public/generated"),
        )
    if backend == "comfyui":
        return ComfyUIBackend(
            base_url=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"),
            checkpoint=os.environ.get("COMFYUI_CHECKPOINT", "v1-5-pruned-emaonly-fp16.safetensors"),
        )
    raise ValueError(f"Unknown IMAGE_BACKEND {backend!r}. Valid backends: 'flux_worker', 'comfyui'.")
