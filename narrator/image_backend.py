import base64
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import httpx


class ImageBackend(Protocol):
    async def generate_portrait(self, description: str) -> bytes: ...
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
    ) -> None:
        self.base_url = base_url
        self.backend = backend
        self.output_dir = Path(output_dir)
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

    async def _generate(self, prompt: str, aspect: str, reference_paths: list[str]) -> bytes:
        references = [self._to_data_url(p) for p in reference_paths[:_MAX_REFERENCES]]
        payload = {
            "backend": self.backend,
            "prompt": prompt,
            "aspect": aspect,
            "references": references,
        }
        result = await self._http_fn(payload)
        return (self.output_dir / f"{result['id']}.png").read_bytes()

    async def generate_portrait(self, description: str) -> bytes:
        return await self._generate(description, aspect="portrait", reference_paths=[])

    async def generate_scene(self, prompt: str, reference_paths: list[str]) -> bytes:
        return await self._generate(prompt, aspect="square", reference_paths=reference_paths)
