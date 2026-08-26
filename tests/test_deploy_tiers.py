from deploy.detect import HardwareProfile
from deploy.tiers import recommend


def test_confirmed_8gb_nvidia_tier_matches_real_deployment():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:8b"
    assert rec.enable_image_gen is True
    assert rec.tts_backend == "kokoro"


def test_higher_vram_gets_the_same_recommendation():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=24.0, system_ram_gb=64, cpu_cores=16)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:8b"
    assert rec.enable_image_gen is True


def test_mid_vram_disables_image_gen_but_keeps_local_tts():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=6.0, system_ram_gb=16, cpu_cores=8)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:4b"
    assert rec.enable_image_gen is False
    assert rec.tts_backend == "kokoro"


def test_low_vram_falls_back_to_hosted_tts():
    profile = HardwareProfile(os="windows", gpu_vendor="nvidia", vram_gb=2.5, system_ram_gb=16, cpu_cores=8)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:1.7b"
    assert rec.enable_image_gen is False
    assert rec.tts_backend == "hosted"


def test_apple_silicon_never_recommends_image_gen():
    profile = HardwareProfile(os="macos", gpu_vendor="apple", vram_gb=None, system_ram_gb=16, cpu_cores=8)

    rec = recommend(profile)

    assert rec.enable_image_gen is False
    assert rec.tier == "apple-unified"


def test_cpu_only_caps_model_size_even_with_huge_ram():
    profile = HardwareProfile(os="linux", gpu_vendor="none", vram_gb=None, system_ram_gb=256, cpu_cores=32)

    rec = recommend(profile)

    assert rec.ollama_model == "qwen3:4b"
    assert rec.enable_image_gen is False
    assert rec.tier == "cpu-only"


def test_reasoning_is_a_nonempty_explanation():
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)

    rec = recommend(profile)

    assert len(rec.reasoning) > 20
