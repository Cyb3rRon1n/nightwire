from pathlib import Path

from deploy.detect import HardwareProfile
from deploy.server_install import install_ollama, ollama_installed, pull_model, run
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
