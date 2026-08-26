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

    env = {
        "NIGHTWIRE_MODEL": recommendation.ollama_model,
        "NIGHTWIRE_IMAGE_BACKEND": "none",
    }

    device = "cpu" if profile.gpu_vendor == "none" else _DEVICE_BY_OS[profile.os]

    if recommendation.tts_backend == "kokoro":
        kokoro_dir = siblings_dir / "Kokoro-FastAPI"
        clone_repo(KOKORO_REPO_URL, kokoro_dir, run_cmd)
        setup_kokoro(kokoro_dir, device, run_cmd, which)
        kokoro_env = {"ALLOW_DEV_UNLOAD": "true"}
        kokoro_argv = kokoro_start_command(kokoro_dir, device, profile.os == "windows")
        if profile.os == "linux":
            write_systemd_unit("kokoro-server", kokoro_dir, " ".join(kokoro_argv), kokoro_env, units_dir)
        elif profile.os == "macos":
            write_launchd_plist("kokoro-server", kokoro_dir, kokoro_argv, kokoro_env, units_dir)
        # Windows: kokoro-server entry added to start-all.ps1 below, not here
        env["NIGHTWIRE_TTS_BACKEND"] = "kokoro"
    elif recommendation.tts_backend == "hosted":
        env["NIGHTWIRE_TTS_BACKEND"] = "openai"
        if tts_api_key:
            env["NIGHTWIRE_TTS_API_KEY"] = tts_api_key
    else:
        env["NIGHTWIRE_TTS_BACKEND"] = "none"

    server_argv = ["python", "-m", "server"]
    if profile.os == "linux":
        write_systemd_unit("nightwire-server", Path.cwd(), " ".join(server_argv), env, units_dir)
    elif profile.os == "macos":
        write_launchd_plist("nightwire-server", Path.cwd(), server_argv, env, units_dir)
    else:
        write_windows_start_script([("nightwire-server", server_argv, Path.cwd(), env)], units_dir / "start-all.ps1")

    return env
