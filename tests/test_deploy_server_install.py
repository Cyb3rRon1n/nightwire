from pathlib import Path

from deploy.detect import HardwareProfile
from deploy.server_install import install_ollama, kokoro_start_command, ollama_installed, pull_model, run, setup_image_gen, setup_kokoro
from deploy.tiers import Recommendation


def test_ollama_installed_true_when_on_path():
    assert ollama_installed(which=lambda name: "/usr/bin/ollama") is True


def test_ollama_installed_false_when_missing():
    assert ollama_installed(which=lambda name: None) is False


def test_install_ollama_runs_the_official_installer_per_os():
    calls = []
    install_ollama("linux", run=calls.append)
    assert calls[0][0] in ("sh", "curl")

    calls.clear()
    install_ollama("windows", run=calls.append)
    assert calls[0][0] == "winget"


def test_pull_model_calls_ollama_pull():
    calls = []
    pull_model("qwen3:8b", run=calls.append)
    assert calls == [["ollama", "pull", "qwen3:8b"]]


def test_run_installs_ollama_when_missing_and_pulls_model(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=False, tts_backend="none", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: None,
    )

    assert ["ollama", "pull", "qwen3:8b"] in calls
    assert env["NIGHTWIRE_MODEL"] == "qwen3:8b"
    unit_path = tmp_path / "units" / "nightwire-nightwire-server.service"
    assert unit_path.exists()
    assert "NIGHTWIRE_MODEL=qwen3:8b" in unit_path.read_text()


def test_run_skips_ollama_install_when_already_present(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=False, tts_backend="none", reasoning="test")

    run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: "/usr/bin/ollama",
    )

    assert not any(cmd[0] in ("winget", "brew") or "install.sh" in " ".join(cmd) for cmd in calls)


def test_setup_kokoro_installs_uv_when_missing(tmp_path):
    calls = []
    setup_kokoro(tmp_path / "Kokoro-FastAPI", device="cuda", run_cmd=calls.append, which=lambda name: None)
    assert any("astral.sh/uv" in " ".join(cmd) if isinstance(cmd, list) else "astral.sh/uv" in cmd for cmd in calls)


def test_setup_kokoro_skips_uv_install_when_present(tmp_path):
    calls = []
    setup_kokoro(tmp_path / "Kokoro-FastAPI", device="cuda", run_cmd=calls.append, which=lambda name: "/usr/bin/uv")
    assert calls == []


def test_kokoro_start_command_picks_gpu_or_cpu_script():
    # Build expected values via f"{repo}/..." - the same construction the
    # implementation uses - rather than hardcoded forward-slash literals,
    # so this passes regardless of the host's native path separator.
    repo = Path("/x/Kokoro-FastAPI")
    assert kokoro_start_command(repo, device="cuda", is_windows=False) == ["bash", f"{repo}/start-gpu.sh"]
    assert kokoro_start_command(repo, device="cpu", is_windows=False) == ["bash", f"{repo}/start-cpu.sh"]
    win_repo = Path("C:/Kokoro-FastAPI")
    assert kokoro_start_command(win_repo, device="cuda", is_windows=True) == [
        "powershell", "-File", f"{win_repo}/start-gpu.ps1",
    ]


def test_run_with_kokoro_tts_clones_and_writes_its_own_unit(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=False, tts_backend="kokoro", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: "/usr/bin/ollama" if name == "ollama" else "/usr/bin/uv",
    )

    assert env["NIGHTWIRE_TTS_BACKEND"] == "kokoro"
    assert any(cmd[:2] == ["git", "clone"] for cmd in calls)
    kokoro_unit = tmp_path / "units" / "nightwire-kokoro-server.service"
    assert kokoro_unit.exists()
    assert "ALLOW_DEV_UNLOAD=true" in kokoro_unit.read_text()


def test_run_with_hosted_tts_sets_openai_env_and_api_key(tmp_path):
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=2.5, system_ram_gb=16, cpu_cores=8)
    recommendation = Recommendation(tier="lite", ollama_model="qwen3:1.7b", enable_image_gen=False, tts_backend="hosted", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: None, which=lambda name: "/usr/bin/ollama", tts_api_key="sk-test",
    )

    assert env["NIGHTWIRE_TTS_BACKEND"] == "openai"
    assert env["NIGHTWIRE_TTS_API_KEY"] == "sk-test"


def test_setup_image_gen_creates_venv_and_installs_requirements(tmp_path):
    calls = []
    repo_dir = tmp_path / "ultra-fast-image-gen"
    repo_dir.mkdir()

    setup_image_gen(repo_dir, device="cuda", run_cmd=calls.append, which=lambda name: "/usr/bin/python")

    assert any(cmd[:3] == ["python", "-m", "venv"] for cmd in calls)
    assert any("requirements.txt" in cmd[-1] for cmd in calls if cmd)


def test_setup_image_gen_cpu_uses_stable_cpu_wheel_index(tmp_path):
    calls = []
    repo_dir = tmp_path / "ultra-fast-image-gen"
    repo_dir.mkdir()

    setup_image_gen(repo_dir, device="cpu", run_cmd=calls.append, which=lambda name: "/usr/bin/python")

    assert any("download.pytorch.org/whl/cpu" in " ".join(cmd) for cmd in calls)


def test_run_with_image_gen_clones_when_url_given(tmp_path):
    calls = []
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="none", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: calls.append(cmd), which=lambda name: "something",
        image_gen_repo_url="git@example.com:private/ultra-fast-image-gen.git",
    )

    assert env["NIGHTWIRE_IMAGE_BACKEND"] == "flux"
    assert ["git", "clone", "git@example.com:private/ultra-fast-image-gen.git", str(tmp_path / "siblings" / "ultra-fast-image-gen")] in calls
    image_unit = tmp_path / "units" / "nightwire-image-server.service"
    assert image_unit.exists()
    assert "ULTRA_FAST_IMAGE_GEN_DIR" in image_unit.read_text()


def test_run_disables_image_gen_when_no_url_given_even_if_recommended(tmp_path):
    profile = HardwareProfile(os="linux", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="none", reasoning="test")

    env = run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: None, which=lambda name: "something", image_gen_repo_url=None,
    )

    assert env["NIGHTWIRE_IMAGE_BACKEND"] == "none"
    assert not (tmp_path / "units" / "nightwire-image-server.service").exists()


def test_run_on_windows_writes_one_start_script_for_every_enabled_service(tmp_path):
    profile = HardwareProfile(os="windows", gpu_vendor="nvidia", vram_gb=7.9, system_ram_gb=32, cpu_cores=8)
    recommendation = Recommendation(tier="standard", ollama_model="qwen3:8b", enable_image_gen=True, tts_backend="kokoro", reasoning="test")

    run(
        profile, recommendation, siblings_dir=tmp_path / "siblings", units_dir=tmp_path / "units",
        run_cmd=lambda cmd: None, which=lambda name: "something",
        image_gen_repo_url="https://example.com/private.git",
    )

    content = (tmp_path / "units" / "start-all.ps1").read_text()
    assert "nightwire-server" in content
    assert "kokoro-server" in content
    assert "image-server" in content
