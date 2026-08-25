import base64
from pathlib import Path

import pytest

from narrator.image_backend import FluxWorkerBackend


def _fake_http_fn(response: dict, seen: dict):
    async def http_fn(payload: dict) -> dict:
        seen["payload"] = payload
        return response

    return http_fn


@pytest.mark.asyncio
async def test_generate_portrait_calls_http_fn_with_no_references(tmp_path):
    (tmp_path / "img1.png").write_bytes(b"fake-png-bytes")
    seen = {}
    backend = FluxWorkerBackend(
        output_dir=tmp_path,
        http_fn=_fake_http_fn({"id": "img1"}, seen),
    )

    result = await backend.generate_portrait("a lean netrunner in a rain-slicked jacket")

    assert result == b"fake-png-bytes"
    assert seen["payload"]["prompt"] == "a lean netrunner in a rain-slicked jacket"
    assert seen["payload"]["aspect"] == "portrait"
    assert seen["payload"]["width"] == 384
    assert seen["payload"]["height"] == 512
    assert seen["payload"]["references"] == []
    assert seen["payload"]["backend"] == "sdnq-hs"


@pytest.mark.asyncio
async def test_generate_scene_encodes_reference_files_as_data_urls(tmp_path):
    ref_path = tmp_path / "portrait.png"
    ref_path.write_bytes(b"\x89PNG-ref-bytes")
    (tmp_path / "img2.png").write_bytes(b"fake-scene-bytes")
    seen = {}
    backend = FluxWorkerBackend(
        output_dir=tmp_path,
        http_fn=_fake_http_fn({"id": "img2"}, seen),
    )

    result = await backend.generate_scene("a rain-slicked alley, neon signs", [str(ref_path)])

    assert result == b"fake-scene-bytes"
    assert seen["payload"]["aspect"] == "square"
    assert seen["payload"]["width"] == 512
    assert seen["payload"]["height"] == 512
    references = seen["payload"]["references"]
    assert len(references) == 1
    expected_b64 = base64.b64encode(b"\x89PNG-ref-bytes").decode()
    assert references[0] == {"dataUrl": f"data:image/png;base64,{expected_b64}"}


@pytest.mark.asyncio
async def test_generate_portrait_encodes_reference_photos_as_provided_data_urls(tmp_path):
    (tmp_path / "img4.png").write_bytes(b"fake-portrait-bytes")
    seen = {}
    backend = FluxWorkerBackend(
        output_dir=tmp_path,
        http_fn=_fake_http_fn({"id": "img4"}, seen),
    )

    result = await backend.generate_portrait(
        "a lean netrunner",
        reference_photos=["data:image/png;base64,QUJD"],
    )

    assert result == b"fake-portrait-bytes"
    assert seen["payload"]["references"] == [{"dataUrl": "data:image/png;base64,QUJD"}]


@pytest.mark.asyncio
async def test_generate_portrait_only_sends_the_first_two_reference_photos(tmp_path):
    (tmp_path / "img5.png").write_bytes(b"x")
    seen = {}
    backend = FluxWorkerBackend(output_dir=tmp_path, http_fn=_fake_http_fn({"id": "img5"}, seen))
    photos = [f"data:image/png;base64,PHOTO{i}" for i in range(3)]

    await backend.generate_portrait("a fixer", reference_photos=photos)

    assert seen["payload"]["references"] == [{"dataUrl": photos[0]}, {"dataUrl": photos[1]}]


@pytest.mark.asyncio
async def test_generate_scene_only_sends_the_first_two_references(tmp_path):
    paths = []
    for i in range(4):
        p = tmp_path / f"ref{i}.png"
        p.write_bytes(f"ref-{i}".encode())
        paths.append(str(p))
    (tmp_path / "img3.png").write_bytes(b"x")
    seen = {}
    backend = FluxWorkerBackend(output_dir=tmp_path, http_fn=_fake_http_fn({"id": "img3"}, seen))

    await backend.generate_scene("a scene", paths)

    # The real worker (frontend/image_server/optimized_image_server.py's
    # prepare_reference_paths) only ever reads references[:2] - sending more
    # is silently wasted bandwidth, not an error, but there's no reason to.
    assert len(seen["payload"]["references"]) == 2
