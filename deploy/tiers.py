from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from deploy.detect import HardwareProfile

# ollama.com/library/qwen3 tags, default quantization, fetched 2026-08-26.
MODEL_SIZES_GB = {
    "qwen3:8b": 5.2,
    "qwen3:4b": 2.5,
    "qwen3:1.7b": 1.4,
    "qwen3:0.6b": 0.6,
}

# Kokoro-82M: "~300MB/<2GB VRAM" - see
# docs/superpowers/specs/2026-08-23-tts-narration-design.md.
KOKORO_VRAM_GB = 2.0

# The confirmed real deployment (RTX 2080). nvidia-smi sometimes reports a
# few hundred MB under the nominal 8192MiB due to reserved memory, so 7.5
# catches the real card without excluding it. This same threshold gates
# BOTH qwen3:8b selection and image-gen (FLUX.2-klein-4B at 4-bit SDNQ:
# "8GB VRAM at 512px" per docs/superpowers/specs/2026-08-23-image-generation-design.md,
# NVIDIA/CUDA-only) - they're the same real card fitting both, so using two
# different threshold values for them would let a card qualify for one but
# not the other with no real basis for the split.
STANDARD_TIER_VRAM_GB = 7.5

# Apple unified memory and CPU-only RAM are shared with the OS and every
# other running app. No cited real-world number exists yet for a safe
# reserve on either (open item, see spec) - this flat reserve is a
# documented, disclosed estimate, not a verified measurement.
_UNIFIED_MEMORY_RESERVE_GB = 4.0

# Each _pick_model() bucket gets its own tier name - previously qwen3:4b and
# qwen3:1.7b were both named "lite", which collapsed two distinct hardware
# bands into one undifferentiated tier name (see task-10-tiers-fix-report.md).
_TIER_BY_MODEL = {
    "qwen3:8b": "standard",
    "qwen3:4b": "lite",
    "qwen3:1.7b": "minimal",
    "qwen3:0.6b": "floor",
}


class Recommendation(BaseModel):
    tier: str
    ollama_model: str
    enable_image_gen: bool
    tts_backend: Literal["kokoro", "hosted", "none"]
    reasoning: str


def _pick_model(budget_gb: float) -> str:
    if budget_gb >= STANDARD_TIER_VRAM_GB:
        return "qwen3:8b"
    if budget_gb >= 3.0:
        return "qwen3:4b"
    if budget_gb >= 2.0:
        return "qwen3:1.7b"
    return "qwen3:0.6b"


def _tts_for(budget_gb: float, model: str) -> Literal["kokoro", "hosted"]:
    headroom = budget_gb - MODEL_SIZES_GB[model]
    return "kokoro" if headroom >= KOKORO_VRAM_GB else "hosted"


def recommend(profile: HardwareProfile) -> Recommendation:
    if profile.gpu_vendor == "nvidia" and profile.vram_gb is not None:
        budget = profile.vram_gb
        model = _pick_model(budget)
        enable_image_gen = model == "qwen3:8b"
        tts_backend = _tts_for(budget, model)
        tier = _TIER_BY_MODEL[model]
        reasoning = (
            f"{budget:.1f}GB NVIDIA VRAM detected. Recommending {model} "
            f"({MODEL_SIZES_GB[model]}GB, leaves {budget - MODEL_SIZES_GB[model]:.1f}GB headroom). "
            + (
                "Image-gen fits (needs >= 8GB for FLUX.2-klein-4B at 512px)."
                if enable_image_gen
                else "Image-gen disabled - needs >= 8GB VRAM for FLUX.2-klein-4B at 512px."
            )
            + (
                " Kokoro (local TTS) fits alongside."
                if tts_backend == "kokoro"
                else " Recommending hosted TTS - not enough headroom left for Kokoro's <2GB alongside the model."
            )
        )
        return Recommendation(tier=tier, ollama_model=model, enable_image_gen=enable_image_gen, tts_backend=tts_backend, reasoning=reasoning)

    if profile.gpu_vendor == "apple":
        budget = max(profile.system_ram_gb - _UNIFIED_MEMORY_RESERVE_GB, 0.6)
        model = _pick_model(budget)
        tts_backend = _tts_for(budget, model)
        reasoning = (
            f"Apple Silicon detected, {profile.system_ram_gb:.1f}GB unified memory "
            f"(~{budget:.1f}GB assumed available after OS/app overhead - a documented estimate, "
            "not a verified number, since unified memory is shared with everything else running). "
            f"Recommending {model}. Image-gen disabled - FLUX.2-klein-4B's SDNQ quantization is "
            "NVIDIA/CUDA-specific and unverified on Metal."
            + (" Kokoro fits alongside." if tts_backend == "kokoro" else " Recommending hosted TTS.")
        )
        return Recommendation(tier="apple-unified", ollama_model=model, enable_image_gen=False, tts_backend=tts_backend, reasoning=reasoning)

    budget = max(profile.system_ram_gb - _UNIFIED_MEMORY_RESERVE_GB, 0.6)
    # Capped at qwen3:4b even with huge RAM headroom - CPU inference of
    # anything bigger is impractically slow without a GPU regardless of RAM.
    model = _pick_model(min(budget, 4.0))
    tts_backend = _tts_for(budget, model)
    reasoning = (
        f"No GPU detected. {profile.system_ram_gb:.1f}GB system RAM (~{budget:.1f}GB assumed "
        f"available). Recommending {model} for CPU inference - capped at qwen3:4b even with "
        "more RAM, since larger models are impractically slow without a GPU. Image-gen disabled "
        "- no CPU inference path for FLUX.2-klein-4B in this project."
        + (" Kokoro fits alongside." if tts_backend == "kokoro" else " Recommending hosted TTS.")
    )
    return Recommendation(tier="cpu-only", ollama_model=model, enable_image_gen=False, tts_backend=tts_backend, reasoning=reasoning)
