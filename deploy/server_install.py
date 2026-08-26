from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

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
        "NIGHTWIRE_TTS_BACKEND": "none",
    }

    server_argv = ["python", "-m", "server"]
    if profile.os == "linux":
        write_systemd_unit("nightwire-server", Path.cwd(), " ".join(server_argv), env, units_dir)
    elif profile.os == "macos":
        write_launchd_plist("nightwire-server", Path.cwd(), server_argv, env, units_dir)
    else:
        write_windows_start_script([("nightwire-server", server_argv, Path.cwd(), env)], units_dir / "start-all.ps1")

    return env
