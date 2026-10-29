# Image Look (Phase 19a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the owner-approved NoobAI-XL v-pred + Smooth Booster image look through ComfyUI, with an engine-decided subject, a cleaned tag-writer pass with a sentence fallback, and an optional player presentation field.

**Architecture:** A new pure-ish module `narrator/image_prompt.py` turns a narrator sentence (or portrait description) into a positive/negative prompt pair using `client.judge()` for tags and engine rules for the subject. `narrator/comfyui_backend.py` gains a `noobai` profile (the locked graph) beside the unchanged `sd15` graph, and advertises `wants_tags`. The scene image block and portrait handler call `resolve()` before unloading the narrator.

**Tech Stack:** Python 3, httpx, pydantic, pytest (`asyncio_mode = "auto"`); Next.js/TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-10-28-image-look-19a-design.md`

## Global Constraints

- Locked noobai graph: CheckpointLoaderSimple → LoraLoader (strength 0.6 model + clip) → ModelSamplingDiscrete(sampling="v_prediction", zsnr=True) → RescaleCFG(multiplier=0.6); CLIPSetLastLayer(stop_at_clip_layer=-2); KSampler euler / normal / 28 steps / CFG 4.5 / denoise 1.0; VAEDecodeTiled(tile_size=512, overlap=64, temporal_size=64, temporal_overlap=8); portrait 832×1216, scene 1216×832.
- Defaults: `COMFYUI_PROFILE=noobai`; checkpoint `NoobAI-XL-Vpred-v1.0.safetensors` (noobai) / `v1-5-pruned-emaonly-fp16.safetensors` (sd15); `COMFYUI_LORA=Smooth_Booster_v3.safetensors` (empty disables); `COMFYUI_LORA_STRENGTH=0.6`; `COMFYUI_SAMPLER=euler`, `COMFYUI_SCHEDULER=normal`, `COMFYUI_CFG=4.5`.
- Constants `QUALITY`, `STYLE`, `NEGATIVE` and the tag-writer system prompt are copied verbatim from the spec.
- No forced `light skin` tag.
- Subject is decided by the engine; tag-writer subject tags are stripped.
- `resolve()` falls back to the sentence when tagging raises or yields fewer than 5 cleaned tags.
- Tagging happens before `narrator_client.unload()`.
- `presentation`: `feminine | masculine | androgynous | None`; old saves load.
- Never add Co-Authored-By or AI-attribution trailers. Tests: `.venv/bin/python -m pytest tests/ -q` from the repo root.

---

### Task 1: `narrator/image_prompt.py`

**Files:**
- Create: `narrator/image_prompt.py`, `tests/test_image_prompt.py`

**Interfaces:**
- Consumes: `client.judge(messages: list[dict], schema: dict) -> dict` (exists on all narrator backends); `is_tsukumogami(character)` (engine/character.py).
- Produces: `QUALITY`, `STYLE`, `NEGATIVE`, `TAGGER_PROMPT` (str); `subject_tags(kind: str, character=None) -> list[str]`; `clean_tags(raw: list[str]) -> list[str]`; `build_prompt(subject: list[str], content: list[str] | str) -> str`; `async tagify(client, text: str) -> list[str]`; `async resolve(client, kind: str, text: str, character=None) -> tuple[str, str, str]` returning `(positive, negative, source)` with source `"tags"` or `"sentence"`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_image_prompt.py`:

```python
import pytest

from engine.character import CharacterSheet
from narrator.image_prompt import (
    NEGATIVE, QUALITY, STYLE, build_prompt, clean_tags, resolve, subject_tags,
)


def _pc(**kw):
    return CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", **kw)


def test_scene_subject():
    assert subject_tags("scene") == ["scenery", "no humans"]


@pytest.mark.parametrize("presentation,first", [("feminine", "1girl"), ("masculine", "1boy"),
                                                ("androgynous", "1other"), (None, "1other")])
def test_portrait_subject_follows_presentation(presentation, first):
    assert subject_tags("portrait", _pc(presentation=presentation)) == [first, "solo", "upper body", "looking at viewer"]


def test_tsukumogami_portrait_overrides_presentation():
    c = _pc(lifepath="tsukumogami", presentation="feminine")
    assert subject_tags("portrait", c) == ["1other", "solo", "upper body", "android", "robot joints"]


def test_clean_tags_drops_round_four_junk_and_owned_tags():
    raw = ["1structure", "1Bridge", "1girl", "Neon_Signs", "neon signs", "masterpiece", "highly detailed",
           "anime", "rain", "  wet street ", "", "2girls", "best quality"]
    assert clean_tags(raw) == ["neon signs", "rain", "wet street"]


def test_clean_tags_caps_at_25():
    assert len(clean_tags([f"tag {i}" for i in range(40)])) == 25


def test_build_prompt_order():
    assert build_prompt(["scenery", "no humans"], ["rain", "alley"]) == ", ".join(
        [QUALITY, "scenery", "no humans", STYLE, "rain", "alley"])
    assert build_prompt(["scenery", "no humans"], "a rainy alley").endswith(", a rainy alley")


class _Client:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    async def judge(self, messages, schema):
        self.calls.append((messages, schema))
        if self.error:
            raise self.error
        return self.answer


async def test_resolve_uses_cleaned_tags():
    client = _Client({"tags": ["1girl", "izakaya", "paper lanterns", "steam", "ramen", "counter", "rain"]})
    pos, neg, source = await resolve(client, "scene", "a lantern-lit izakaya")
    assert source == "tags" and neg == NEGATIVE
    assert pos == build_prompt(["scenery", "no humans"], ["izakaya", "paper lanterns", "steam", "ramen", "counter", "rain"])
    assert client.calls[0][1]["required"] == ["tags"]


@pytest.mark.parametrize("client", [_Client(error=ValueError("bad json")), _Client({"tags": ["rain", "alley"]})])
async def test_resolve_falls_back_to_the_sentence(client):
    pos, neg, source = await resolve(client, "scene", "a rainy alley")
    assert source == "sentence"
    assert pos == build_prompt(["scenery", "no humans"], "a rainy alley")


async def test_resolve_portrait_uses_character_subject():
    client = _Client({"tags": ["bomber jacket", "short hair", "cyberarm", "neon", "rain"]})
    pos, _, _ = await resolve(client, "portrait", "Rook, a streetkid solo", _pc(presentation="masculine"))
    assert pos.startswith(QUALITY + ", 1boy, solo")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_image_prompt.py -q`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `narrator/image_prompt.py`**

```python
"""Phase 19a: turn narrator image text into the owner-approved NoobAI-XL prompt.
The engine decides the subject; a small tag-writer call supplies content tags,
cleaned, with the original sentence as the fallback.
See docs/superpowers/specs/2026-10-28-image-look-19a-design.md."""

import re

from engine.character import is_tsukumogami

QUALITY = "masterpiece, best quality, very awa, newest, year 2024, absurdres, highres, safe"
STYLE = ("anime screenshot, anime coloring, cel shading, thick outlines, detailed background, neon lights, "
         "pink neon rim light, cyan backlight, yellow accents, high contrast, bloom, depth of field, "
         "chromatic aberration, cyberpunk, night")
NEGATIVE = ("nsfw, worst quality, old, early, low quality, lowres, signature, username, logo, bad hands, "
            "mutated hands, mammal, anthro, furry, ambiguous form, feral, semi-anthro, text, watermark, "
            "jpeg artifacts, blurry, worst aesthetic, flat color, simple background, blue skin, colored skin, "
            "monochrome, limited palette")
TAGGER_PROMPT = ("Convert the image description into Danbooru-style tags for an anime image model. "
                 "Output 10-25 lowercase tags: setting, objects, people's clothing and features, lighting, "
                 "weather, mood. Concrete nouns only; no subject-count tags, no style or quality tags, "
                 "no artist names, no sentences.")
_SCHEMA = {"type": "object", "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
           "required": ["tags"], "additionalProperties": False}
_PRESENTATION = {"feminine": "1girl", "masculine": "1boy", "androgynous": "1other"}
_COUNT_TAG = re.compile(r"^\d+\w*$|^\d+\s*\w+$")
_BANNED_WORDS = {"masterpiece", "quality", "best", "absurdres", "highres", "aesthetic", "style", "artist",
                 "anime", "detailed"}
_MAX_TAGS = 25
_MIN_TAGS = 5


def subject_tags(kind: str, character=None) -> list[str]:
    if kind == "scene":
        return ["scenery", "no humans"]
    if character is not None and is_tsukumogami(character):
        return ["1other", "solo", "upper body", "android", "robot joints"]
    presentation = getattr(character, "presentation", None)
    return [_PRESENTATION.get(presentation, "1other"), "solo", "upper body", "looking at viewer"]


def clean_tags(raw: list[str]) -> list[str]:
    out: list[str] = []
    for tag in raw:
        t = str(tag).strip().lower().replace("_", " ")
        t = " ".join(t.split())
        if not t or _COUNT_TAG.match(t.replace(" ", "")) or any(w in _BANNED_WORDS for w in t.split()):
            continue
        if t not in out:
            out.append(t)
    return out[:_MAX_TAGS]


def build_prompt(subject: list[str], content: list[str] | str) -> str:
    body = content if isinstance(content, str) else ", ".join(content)
    return ", ".join([QUALITY, *subject, STYLE, body])


async def tagify(client, text: str) -> list[str]:
    messages = [{"role": "system", "content": TAGGER_PROMPT}, {"role": "user", "content": text}]
    answer = await client.judge(messages, _SCHEMA)
    return clean_tags(answer.get("tags", []) if isinstance(answer, dict) else [])


async def resolve(client, kind: str, text: str, character=None) -> tuple[str, str, str]:
    subject = subject_tags(kind, character)
    try:
        tags = await tagify(client, text)
    except Exception:  # any tag-writer failure falls back to the narrator's own words
        tags = []
    if len(tags) >= _MIN_TAGS:
        return build_prompt(subject, tags), NEGATIVE, "tags"
    return build_prompt(subject, text), NEGATIVE, "sentence"
```

Note: `_COUNT_TAG` matches both `1structure`/`1girl`/`2girls` (digits then letters) after removing spaces. `"best quality"` and `"highly detailed"` are dropped by `_BANNED_WORDS`.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/image_prompt.py tests/test_image_prompt.py
git commit -m "feat(19a): image prompt builder - engine subject, cleaned tag-writer, sentence fallback"
```

---

### Task 2: ComfyUI `noobai` profile

**Files:**
- Modify: `narrator/comfyui_backend.py`, `narrator/image_backend.py`
- Test: `tests/test_comfyui_backend.py`, `tests/test_image_backend.py`

**Interfaces:**
- Produces: `ComfyUIBackend(base_url, checkpoint=None, timeout=..., poll_interval=..., client=None, sleep_fn=None, profile="sd15", lora=None, lora_strength=0.6, sampler=None, scheduler=None, cfg=None)`; attribute `wants_tags: bool` (True only for profile `"noobai"`); `generate_portrait(description, reference_photos=None, negative=None)`; `generate_scene(prompt, reference_paths, negative=None)`. `FluxWorkerBackend.wants_tags = False`. `create_image_backend()` reads the env vars in Global Constraints. The `ImageBackend` protocol gains `wants_tags: bool` and the optional `negative` parameter.

Note: the constructor default stays `profile="sd15"` so existing direct constructions in tests keep their behaviour; `create_image_backend()` defaults the env to `noobai`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_comfyui_backend.py` (read its top first to reuse its fake client helpers; if none suit, call `_build_workflow` directly as below):

```python
from narrator.comfyui_backend import ComfyUIBackend


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
```

Append to `tests/test_image_backend.py`:

```python
def test_create_image_backend_comfyui_defaults_to_noobai(monkeypatch):
    from narrator.image_backend import create_image_backend
    monkeypatch.setenv("IMAGE_BACKEND", "comfyui")
    for k in ("COMFYUI_PROFILE", "COMFYUI_CHECKPOINT", "COMFYUI_LORA", "COMFYUI_LORA_STRENGTH",
              "COMFYUI_SAMPLER", "COMFYUI_SCHEDULER", "COMFYUI_CFG"):
        monkeypatch.delenv(k, raising=False)
    b = create_image_backend()
    assert b.wants_tags and b.checkpoint == "NoobAI-XL-Vpred-v1.0.safetensors"
    assert b.lora == "Smooth_Booster_v3.safetensors" and b.lora_strength == 0.6
    monkeypatch.setenv("COMFYUI_PROFILE", "sd15")
    b = create_image_backend()
    assert not b.wants_tags and b.checkpoint == "v1-5-pruned-emaonly-fp16.safetensors"


def test_create_image_backend_reads_sampler_overrides(monkeypatch):
    from narrator.image_backend import create_image_backend
    monkeypatch.setenv("IMAGE_BACKEND", "comfyui")
    monkeypatch.setenv("COMFYUI_SAMPLER", "dpmpp_2m_sde")
    monkeypatch.setenv("COMFYUI_SCHEDULER", "beta")
    monkeypatch.setenv("COMFYUI_CFG", "5.0")
    b = create_image_backend()
    assert (b.sampler, b.scheduler, b.cfg) == ("dpmpp_2m_sde", "beta", 5.0)


def test_flux_worker_does_not_want_tags(monkeypatch):
    from narrator.image_backend import create_image_backend
    monkeypatch.setenv("IMAGE_BACKEND", "flux_worker")
    assert create_image_backend().wants_tags is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_comfyui_backend.py tests/test_image_backend.py -q`
Expected: FAIL (unknown `profile`, missing `wants_tags`).

- [ ] **Step 3: Implement**

In `narrator/comfyui_backend.py`, add constants next to the existing ones:

```python
_NOOBAI_CHECKPOINT = "NoobAI-XL-Vpred-v1.0.safetensors"
_SD15_CHECKPOINT = "v1-5-pruned-emaonly-fp16.safetensors"
_NOOBAI_PORTRAIT_SIZE = (832, 1216)
_NOOBAI_SCENE_SIZE = (1216, 832)
_NOOBAI_STEPS = 28
_NOOBAI_RESCALE = 0.6
```

Change `__init__`'s signature to add `profile: str = "sd15", lora: str | None = None, lora_strength: float = 0.6, sampler: str | None = None, scheduler: str | None = None, cfg: float | None = None`, make `checkpoint: str | None = None`, and set:

```python
        if profile not in ("noobai", "sd15"):
            raise ValueError(f"Unknown ComfyUI profile {profile!r}. Valid profiles: 'noobai', 'sd15'.")
        self.profile = profile
        self.wants_tags = profile == "noobai"
        self.checkpoint = checkpoint or (_NOOBAI_CHECKPOINT if self.wants_tags else _SD15_CHECKPOINT)
        self.lora = lora or None
        self.lora_strength = lora_strength
        self.sampler = sampler or _SAMPLER
        self.scheduler = scheduler or _SCHEDULER
        self.cfg = cfg if cfg is not None else (4.5 if self.wants_tags else _CFG)
```

Update the class docstring's last paragraph to say the `noobai` profile is the Phase 19a owner-approved look. Rename the current `_build_workflow` body to `_sd15_workflow(self, prompt, seed, width, height, filename_prefix, negative)` (using `negative or _NEGATIVE_PROMPT` for node "7" and `self.sampler`/`self.scheduler`/`self.cfg` in the KSampler — note sd15 defaults keep `euler`/`normal`/7.0), and add:

```python
    def _build_workflow(self, prompt: str, seed: int, width: int, height: int, filename_prefix: str,
                        negative: str | None = None) -> dict:
        if not self.wants_tags:
            return self._sd15_workflow(prompt, seed, width, height, filename_prefix, negative)
        wf = {"4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": self.checkpoint}}}
        model, clip = ["4", 0], ["4", 1]
        if self.lora:
            wf["20"] = {"class_type": "LoraLoader", "inputs": {"model": model, "clip": clip, "lora_name": self.lora,
                        "strength_model": self.lora_strength, "strength_clip": self.lora_strength}}
            model, clip = ["20", 0], ["20", 1]
        wf["21"] = {"class_type": "ModelSamplingDiscrete", "inputs": {"model": model, "sampling": "v_prediction", "zsnr": True}}
        wf["22"] = {"class_type": "RescaleCFG", "inputs": {"model": ["21", 0], "multiplier": _NOOBAI_RESCALE}}
        wf["10"] = {"class_type": "CLIPSetLastLayer", "inputs": {"clip": clip, "stop_at_clip_layer": -2}}
        wf["5"] = {"class_type": "EmptyLatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}}
        wf["6"] = {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["10", 0]}}
        wf["7"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative or _NEGATIVE_PROMPT, "clip": ["10", 0]}}
        wf["3"] = {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": _NOOBAI_STEPS, "cfg": self.cfg, "sampler_name": self.sampler,
            "scheduler": self.scheduler, "denoise": 1.0, "model": ["22", 0],
            "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}}
        wf["8"] = {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["3", 0], "vae": ["4", 2], "tile_size": 512,
                   "overlap": 64, "temporal_size": 64, "temporal_overlap": 8}}
        wf["9"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]}}
        return wf
```

Thread `negative` through `_generate(self, prompt, width, height, filename_prefix, negative=None)` into `_build_workflow`, and update the two public methods:

```python
    async def generate_portrait(self, description: str, reference_photos: list[str] | None = None,
                                negative: str | None = None) -> bytes:
        width, height = _NOOBAI_PORTRAIT_SIZE if self.wants_tags else _PORTRAIT_SIZE
        return await self._generate(description, width, height, "nightwire_portrait", negative)

    async def generate_scene(self, prompt: str, reference_paths: list[str], negative: str | None = None) -> bytes:
        width, height = _NOOBAI_SCENE_SIZE if self.wants_tags else _SCENE_SIZE
        return await self._generate(prompt, width, height, "nightwire_scene", negative)
```

Raise the default `timeout` from 120.0 to 300.0 (a cold 7 GB checkpoint load can exceed two minutes on the GPU box).

In `narrator/image_backend.py`: add `wants_tags: bool` and the optional `negative: str | None = None` parameter to both protocol methods; give `FluxWorkerBackend` a class attribute `wants_tags = False` and accept (and ignore) `negative` in both methods; replace the comfyui branch of `create_image_backend()` with:

```python
    if backend == "comfyui":
        profile = os.environ.get("COMFYUI_PROFILE", "noobai").strip().lower()
        default_lora = "Smooth_Booster_v3.safetensors" if profile == "noobai" else ""
        cfg = os.environ.get("COMFYUI_CFG")
        return ComfyUIBackend(
            base_url=os.environ.get("COMFYUI_URL", "http://192.168.10.19:8188"),
            checkpoint=os.environ.get("COMFYUI_CHECKPOINT") or None,
            profile=profile,
            lora=os.environ.get("COMFYUI_LORA", default_lora),
            lora_strength=float(os.environ.get("COMFYUI_LORA_STRENGTH", "0.6")),
            sampler=os.environ.get("COMFYUI_SAMPLER") or None,
            scheduler=os.environ.get("COMFYUI_SCHEDULER") or None,
            cfg=float(cfg) if cfg else None,
        )
```

Existing tests that construct `ComfyUIBackend` directly or assert the old `generate_*` signatures must keep passing unchanged (the sd15 default preserves them). If an existing test asserts `create_image_backend()` returns the SD1.5 checkpoint for `IMAGE_BACKEND=comfyui` with no profile set, update it to set `COMFYUI_PROFILE=sd15` and say so in your report.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add narrator/comfyui_backend.py narrator/image_backend.py tests/test_comfyui_backend.py tests/test_image_backend.py
git commit -m "feat(19a): ComfyUI noobai profile - v-pred, Smooth Booster, tags-aware backends"
```

---

### Task 3: Player presentation field

**Files:**
- Modify: `engine/character.py`, `server/dispatch.py`, `frontend/src/lib/nightwire/protocol.ts`, `frontend/src/app/nightwire/page.tsx`
- Test: `tests/test_dispatch.py`, `tests/test_persistence.py`, `tests/test_views.py` (if it enumerates CharacterSheet fields)

**Interfaces:**
- Produces: `CharacterSheet.presentation: str | None = None`; join accepts `presentation` in `{"feminine", "masculine", "androgynous"}` or absent/None; anything else raises `ValueError("presentation must be feminine, masculine or androgynous")`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_dispatch.py`:

```python
def test_join_accepts_and_stores_presentation():
    session = Session(session_id="s1")
    handle_message(session, {"type": "join", "character": {
        "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid", "presentation": "feminine"}}, "p1")
    assert session.characters["p1"].presentation == "feminine"


def test_join_without_presentation_is_none():
    session = Session(session_id="s1")
    handle_message(session, {"type": "join", "character": {
        "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"}}, "p1")
    assert session.characters["p1"].presentation is None


@pytest.mark.parametrize("bad", ["robot", 5, ["feminine"]])
def test_join_rejects_unknown_presentation(bad):
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="presentation must be"):
        handle_message(session, {"type": "join", "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid", "presentation": bad}}, "p1")
```

(Use the file's existing imports for `Session`, `handle_message`, `pytest`; add any that are missing.)

Append to `tests/test_persistence.py`:

```python
def test_presentation_round_trips_and_defaults(tmp_path):
    import json
    from engine.character import CharacterSheet
    from engine.persistence import JSONFileSessionStore
    from engine.session import Session
    store = JSONFileSessionStore(tmp_path)
    s = Session(session_id="s1")
    s.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", presentation="masculine")
    store.save(s)
    assert store.load("s1").characters["p1"].presentation == "masculine"
    data = json.loads((tmp_path / "s1.json").read_text())
    del data["characters"]["p1"]["presentation"]
    (tmp_path / "s1.json").write_text(json.dumps(data))
    assert store.load("s1").characters["p1"].presentation is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_dispatch.py tests/test_persistence.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement**

`engine/character.py`, add after `awake_reached`:

```python
    # Phase 19a: optional, drives the portrait subject tag (1girl / 1boy / 1other).
    presentation: str | None = None
```

`server/dispatch.py`: add `"presentation"` to `_JOIN_CHARACTER_FIELDS`, add the module constant `_PRESENTATIONS = frozenset({"feminine", "masculine", "androgynous"})`, and in the `join` branch, right after the `starting_chrome` validation:

```python
        presentation = character_data.get("presentation")
        if presentation is not None and (not isinstance(presentation, str) or presentation not in _PRESENTATIONS):
            raise ValueError("presentation must be feminine, masculine or androgynous")
```

Existing tests that enumerate `CharacterSheet` fields or the join allowlist (e.g. a "client-settable field" test in tests/test_dispatch.py, the full-sheet dict in tests/test_views.py) must be updated to include `presentation` (client-settable) — report each.

`frontend/src/lib/nightwire/protocol.ts`: add `presentation: 'feminine' | 'masculine' | 'androgynous' | null` to the character view interface, and `presentation?: 'feminine' | 'masculine' | 'androgynous'` to the join payload's character type (the type at the line that already has `lifepath: string` inside the join message).

`frontend/src/app/nightwire/page.tsx`: add state `const [presentation, setPresentation] = useState("");` next to the `lifepath` state; include `...(presentation ? { presentation } : {})` in the join payload's `character` object (beside `starting_chrome`); and render, directly after the lifepath `<select>` block and its description paragraph:

```tsx
              <select className="nw-field" aria-label="Presentation" value={presentation} onChange={(e) => setPresentation(e.target.value)}>
                <option value="">Presentation (optional)</option>
                <option value="feminine">Feminine</option>
                <option value="masculine">Masculine</option>
                <option value="androgynous">Androgynous</option>
              </select>
```

Read `frontend/AGENTS.md` first. Do not run `next build` or a dev server.

- [ ] **Step 4: Verify**

Run: `.venv/bin/python -m pytest tests/ -q` — all pass.
Run: `cd frontend && npx tsc --noEmit && npm run lint` — no errors.

- [ ] **Step 5: Commit**

```bash
git add engine/character.py server/dispatch.py frontend/src/lib/nightwire/protocol.ts frontend/src/app/nightwire/page.tsx tests/
git commit -m "feat(19a): optional player presentation for portrait subject tags"
```

---

### Task 4: Wire the scene and portrait call sites

**Files:**
- Modify: `server/narration.py` (image block in `_run_turn`), `server/portrait.py`
- Test: `tests/test_narration.py`, `tests/test_portrait.py`

**Interfaces:**
- Consumes: `resolve(client, kind, text, character=None) -> (positive, negative, source)` (Task 1); `image_backend.wants_tags` and the `negative=` parameter (Task 2); `CharacterSheet.presentation` (Task 3).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_narration.py` (it already defines `_session_with_character`, `_scripted_client`, `_say`, `FakeTTSBackend`, `_call`):

```python
class _TagImageBackend:
    wants_tags = True

    def __init__(self, events):
        self.events, self.calls = events, []

    async def generate_portrait(self, description, reference_photos=None, negative=None):
        raise AssertionError("not used")

    async def generate_scene(self, prompt, reference_paths, negative=None):
        self.events.append("generate")
        self.calls.append((prompt, negative))
        return b"img"


async def test_scene_image_is_tagged_before_the_narrator_unloads(tmp_path):
    from narrator.image_prompt import NEGATIVE
    events = []
    session = _session_with_character()
    client = _scripted_client([{"narration": [{"speaker": "narrator", "text": "You step into the alley."}],
                                "tool_call": {"tool": None}, "image_request": {"prompt": "a rainy neon alley"}}])
    async def judge_fn(*, model, messages, format):
        events.append("judge:" + ("tags" if "tags" in format.get("properties", {}) else "referee"))
        if "tags" in format.get("properties", {}):
            return {"message": {"content": json.dumps({"tags": ["alley", "rain", "neon signs", "puddles", "steam", "wires"]})}}
        return {"message": {"content": json.dumps({k: ("none" if "enum" in v else False) for k, v in format["properties"].items()})}}
    client._judge_fn = judge_fn
    original_unload = client.unload
    async def unload():
        events.append("unload")
        await original_unload()
    client.unload = unload
    image = _TagImageBackend(events)
    await _call(session, client, "p1", {"text": "I walk in."}, tmp_path, image_backend=image, tts_backend=FakeTTSBackend())
    assert events.index("judge:tags") < events.index("unload") < events.index("generate")
    prompt, negative = image.calls[0]
    assert "scenery, no humans" in prompt and "puddles" in prompt and negative == NEGATIVE
    assert any(l.startswith("[image prompt (tags): ") for l in session.log)


async def test_non_tag_backend_keeps_the_old_scene_path(tmp_path):
    calls = []
    class _Plain:
        async def generate_portrait(self, description, reference_photos=None):
            raise AssertionError
        async def generate_scene(self, prompt, reference_paths):
            calls.append(prompt)
            return b"img"
    session = _session_with_character()
    client = _scripted_client([{"narration": [{"speaker": "narrator", "text": "x"}], "tool_call": {"tool": None},
                                "image_request": {"prompt": "a rainy neon alley"}}])
    await _call(session, client, "p1", {"text": "I walk in."}, tmp_path, image_backend=_Plain(), tts_backend=FakeTTSBackend())
    assert calls == ["a rainy neon alley"]
```

In `tests/test_portrait.py`, change the assertion at the line expecting `"... highly detailed digital painting"` to the new wording (the same string without `", highly detailed digital painting"`), and append:

```python
def test_portrait_prompt_has_no_digital_painting_phrase():
    from engine.character import CharacterSheet
    from server.portrait import _build_portrait_prompt
    assert "digital painting" not in _build_portrait_prompt(CharacterSheet(player_id="p", name="Rook", role="solo", lifepath="streetkid"))


async def test_tag_backend_portrait_uses_presentation_subject(tmp_path):
    from engine.character import CharacterSheet
    from engine.persistence import JSONFileSessionStore
    from engine.session import Session
    from server.portrait import handle_approve_character
    seen = {}
    class _Img:
        wants_tags = True
        async def generate_portrait(self, description, reference_photos=None, negative=None):
            seen["prompt"], seen["negative"] = description, negative
            return b"png"
        async def generate_scene(self, prompt, reference_paths, negative=None):
            raise AssertionError
    class _Client:
        async def judge(self, messages, schema):
            return {"tags": ["bomber jacket", "short hair", "cyberarm", "neon", "rain", "smirk"]}
        async def unload(self):
            seen["unloaded_after_prompt"] = "prompt" not in seen
    session = Session(session_id="s1")
    session.characters["p1"] = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", presentation="masculine")
    await handle_approve_character(session, JSONFileSessionStore(tmp_path), _Client(), _Img(), "p1", {})
    assert seen["prompt"].startswith("masterpiece") and ", 1boy, solo" in seen["prompt"] and "cyberarm" in seen["prompt"]
    assert seen["negative"] and seen["unloaded_after_prompt"] is True
```

(Read `handle_approve_character`'s full signature/return before finalising this test; adapt only the call arguments if they differ, not the assertions.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_narration.py tests/test_portrait.py -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

`server/narration.py`: import `resolve` from `narrator.image_prompt`. In `_run_turn`'s image block, immediately before the "Best-effort VRAM headroom" unload of `narrator_client`, add:

```python
        image_prompt, image_negative = response.image_request.prompt, None
        if getattr(image_backend, "wants_tags", False):
            # Phase 19a: tag while the narrator model is still loaded; unload comes next.
            image_prompt, image_negative, source = await resolve(
                narrator_client, "scene", response.image_request.prompt)
            session.log.append(f"[image prompt ({source}): {image_prompt}]")
```

and change the generate call to:

```python
            if image_negative is None:
                image_bytes = await image_backend.generate_scene(image_prompt, reference_paths)
            else:
                image_bytes = await image_backend.generate_scene(image_prompt, reference_paths, negative=image_negative)
```

(The two-branch call keeps backends/fakes that don't accept `negative` working.)

`server/portrait.py`: in `_build_portrait_prompt`, change `style` to `"moody neon lighting, rain-slicked cyberpunk city backdrop"`. In `handle_approve_character`, replace

```python
    description = _build_portrait_prompt(character)
    await narrator_client.unload()
    image_bytes = await image_backend.generate_portrait(description, reference_photos=reference_photos)
```

with

```python
    description = _build_portrait_prompt(character)
    negative = None
    if getattr(image_backend, "wants_tags", False):
        description, negative, _source = await resolve(narrator_client, "portrait", description, character)
    await narrator_client.unload()
    if negative is None:
        image_bytes = await image_backend.generate_portrait(description, reference_photos=reference_photos)
    else:
        image_bytes = await image_backend.generate_portrait(description, reference_photos=reference_photos, negative=negative)
```

(import `resolve` from `narrator.image_prompt`).

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/narration.py server/portrait.py tests/test_narration.py tests/test_portrait.py
git commit -m "feat(19a): tag scene and portrait prompts before unloading the narrator"
```

---

## Verification (controller, after the final review)

- **Live** on the GPU box with `IMAGE_BACKEND=comfyui` (profile default `noobai`) and `NIGHTWIRE_THINK=off`: unload Ollama/ComfyUI first; drive six first-time location arrivals through `handle_action` (real narrator, real ComfyUI) and two portraits through `handle_approve_character` (Rook feminine solo, Hachi tsukumogami). Record source (tags/sentence), tagging + image seconds, peak VRAM. Add the images to the owner's gallery (round 5) for sign-off, explicitly checking skin tone without `light skin`.
- **Browser:** the Presentation select on the join form; a generated scene image rendering in the feed.
- **Docs:** README image section (profiles, env vars, required model files + HF links, NoobAI non-commercial licence), ROADMAP "19a." entry.
