from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

CommandRunner = Callable[[list[str]], str]


def _default_run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return result.stdout


def node_version_ok(run: CommandRunner = _default_run) -> tuple[bool, str]:
    try:
        output = run(["node", "--version"]).strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False, "not found"
    major = int(output.lstrip("v").split(".")[0])
    return major >= 22, output


def run(server_url: str, frontend_dir: Path, run_cmd: Callable[[list[str]], None] | None = None) -> None:
    (frontend_dir / ".env.local").write_text(f"NEXT_PUBLIC_NIGHTWIRE_WS_URL={server_url}\n")
    actual_run_cmd = run_cmd or (lambda cmd: subprocess.run(cmd, check=True, cwd=frontend_dir))
    actual_run_cmd(["npm", "ci"])
