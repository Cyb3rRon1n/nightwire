from __future__ import annotations

import platform
import subprocess
from typing import Callable, Literal

import psutil
from pydantic import BaseModel

CommandRunner = Callable[[list[str]], str]

_OS_MAP = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}


class HardwareProfile(BaseModel):
    os: Literal["linux", "macos", "windows"]
    gpu_vendor: Literal["nvidia", "apple", "none"]
    vram_gb: float | None
    system_ram_gb: float
    cpu_cores: int


def _default_run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
    return result.stdout


def _detect_gpu(run: CommandRunner, os_name: str) -> tuple[Literal["nvidia", "apple", "none"], float | None]:
    try:
        output = run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
        mib = float(output.strip().splitlines()[0])
        return "nvidia", round(mib / 1024, 1)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    if os_name == "macos" and platform.machine() == "arm64":
        return "apple", None
    return "none", None


def probe(run: CommandRunner = _default_run) -> HardwareProfile:
    os_name = _OS_MAP[platform.system()]
    gpu_vendor, vram_gb = _detect_gpu(run, os_name)
    return HardwareProfile(
        os=os_name,
        gpu_vendor=gpu_vendor,
        vram_gb=vram_gb,
        system_ram_gb=round(psutil.virtual_memory().total / (1024**3), 1),
        cpu_cores=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
    )
