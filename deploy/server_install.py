from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable, Literal

from deploy.detect import HardwareProfile
from deploy.services import write_launchd_plist, write_systemd_unit, write_windows_start_script
from deploy.tiers import Recommendation

CommandRunner = Callable[[list[str]], None]


def _default_run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ollama_installed(which: Callable[[str], str | None] = shutil.which) -> bool:
    return which("ollama") is not None


_OLLAMA_INSTALL_CMD = {
    "linux": ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
    "macos": ["brew", "install", "ollama"],
    "windows": ["winget", "install", "-e", "--id", "Ollama.Ollama"],
}


def install_ollama(os_name: str, run: CommandRunner = _default_run) -> None:
    run(_OLLAMA_INSTALL_CMD[os_name])


def pull_model(model: str, run: CommandRunner = _default_run) -> None:
    run(["ollama", "pull", model])


KOKORO_REPO_URL = "https://github.com/remsky/Kokoro-FastAPI.git"


def _is_windows() -> bool:
    import platform

    return platform.system() == "Windows"


def clone_repo(repo_url: str, dest: Path, run_cmd: CommandRunner = _default_run) -> None:
    if not dest.exists():
        run_cmd(["git", "clone", repo_url, str(dest)])


def setup_kokoro(repo_dir: Path, device: Literal["cuda", "cpu", "mps"], run_cmd: CommandRunner = _default_run, which: Callable[[str], str | None] = shutil.which) -> None:
    # Kokoro-FastAPI's own start-gpu/start-cpu scripts manage their own
    # uv-installed deps on first run (verified against its README,
    # 2026-08-26) - the only prerequisite this installer owns is uv itself.
    if which("uv") is None:
        if _is_windows():
            run_cmd(["powershell", "-c", "irm https://astral.sh/uv/install.ps1 | iex"])
        else:
            run_cmd(["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])


def kokoro_start_command(repo_dir: Path, device: Literal["cuda", "cpu", "mps"], is_windows: bool) -> list[str]:
    script = "start-cpu" if device == "cpu" else "start-gpu"
    if is_windows:
        return ["powershell", "-File", f"{repo_dir}/{script}.ps1"]
    return ["bash", f"{repo_dir}/{script}.sh"]


_DEVICE_BY_OS = {"macos": "mps", "linux": "cuda", "windows": "cuda"}


def setup_image_gen(repo_dir: Path, device: Literal["cuda", "cpu", "mps"], run_cmd: CommandRunner = _default_run, which: Callable[[str], str | None] = shutil.which) -> None:
    venv_dir = repo_dir / ".venv"
    if not venv_dir.exists():
        run_cmd(["python", "-m", "venv", str(venv_dir)])
    venv_python = str(venv_dir / ("Scripts/python.exe" if _is_windows() else "bin/python"))
    if device == "cpu":
        # The CPU wheel index is stable and safe to hardcode. The CUDA case
        # deliberately does NOT pin a specific index here: PyTorch's CUDA
        # wheel tag (cuXXX) changes release to release, and a version pinned
        # today would silently go stale. Plain `pip install torch` resolves
        # a working GPU-enabled wheel for the common case; a user on an
        # unusual CUDA version should install their own torch build into
        # this venv first.
        run_cmd([venv_python, "-m", "pip", "install", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu"])
    else:
        run_cmd([venv_python, "-m", "pip", "install", "torch", "torchvision"])
    run_cmd([venv_python, "-m", "pip", "install", "-r", str(repo_dir / "requirements.txt")])


def run(
    profile: HardwareProfile,
    recommendation: Recommendation,
    siblings_dir: Path,
    units_dir: Path,
    run_cmd: CommandRunner = _default_run,
    which: Callable[[str], str | None] = shutil.which,
    image_gen_repo_url: str | None = None,
    tts_api_key: str | None = None,
) -> dict[str, str]:
    if not ollama_installed(which):
        install_ollama(profile.os, run_cmd)
    pull_model(recommendation.ollama_model, run_cmd)

    device: Literal["cuda", "cpu", "mps"] = "cpu" if profile.gpu_vendor == "none" else _DEVICE_BY_OS[profile.os]
    env = {"NIGHTWIRE_MODEL": recommendation.ollama_model}
    services: list[tuple[str, list[str], Path, dict[str, str]]] = []

    if recommendation.tts_backend == "kokoro":
        kokoro_dir = siblings_dir / "Kokoro-FastAPI"
        clone_repo(KOKORO_REPO_URL, kokoro_dir, run_cmd)
        setup_kokoro(kokoro_dir, device, run_cmd, which)
        kokoro_argv = kokoro_start_command(kokoro_dir, device, profile.os == "windows")
        services.append(("kokoro-server", kokoro_argv, kokoro_dir, {"ALLOW_DEV_UNLOAD": "true"}))
        env["NIGHTWIRE_TTS_BACKEND"] = "kokoro"
    elif recommendation.tts_backend == "hosted":
        env["NIGHTWIRE_TTS_BACKEND"] = "openai"
        if tts_api_key:
            env["NIGHTWIRE_TTS_API_KEY"] = tts_api_key
    else:
        env["NIGHTWIRE_TTS_BACKEND"] = "none"

    if recommendation.enable_image_gen and image_gen_repo_url:
        image_gen_dir = siblings_dir / "ultra-fast-image-gen"
        clone_repo(image_gen_repo_url, image_gen_dir, run_cmd)
        setup_image_gen(image_gen_dir, device, run_cmd, which)
        image_env = {"ULTRA_FAST_IMAGE_GEN_DIR": str(image_gen_dir)}
        services.append(("image-server", ["npm", "run", "image:server"], Path.cwd() / "frontend", image_env))
        env["NIGHTWIRE_IMAGE_BACKEND"] = "flux"
    else:
        env["NIGHTWIRE_IMAGE_BACKEND"] = "none"

    services.append(("nightwire-server", ["python", "-m", "server"], Path.cwd(), env))

    if profile.os == "linux":
        for name, argv, working_dir, service_env in services:
            write_systemd_unit(name, working_dir, " ".join(argv), service_env, units_dir)
    elif profile.os == "macos":
        for name, argv, working_dir, service_env in services:
            write_launchd_plist(name, working_dir, argv, service_env, units_dir)
    else:
        write_windows_start_script(services, units_dir / "start-all.ps1")

    return env
