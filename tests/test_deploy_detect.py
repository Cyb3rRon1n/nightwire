import subprocess

import pytest

from deploy.detect import probe


def test_probe_detects_nvidia_gpu(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Linux")

    def fake_run(cmd):
        assert cmd[0] == "nvidia-smi"
        return "8192\n"

    profile = probe(run=fake_run)

    assert profile.os == "linux"
    assert profile.gpu_vendor == "nvidia"
    assert profile.vram_gb == 8.0


def test_probe_falls_back_to_apple_when_nvidia_smi_missing_on_mac(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Darwin")
    monkeypatch.setattr("deploy.detect.platform.machine", lambda: "arm64")

    def fake_run(cmd):
        raise FileNotFoundError("no nvidia-smi")

    profile = probe(run=fake_run)

    assert profile.os == "macos"
    assert profile.gpu_vendor == "apple"
    assert profile.vram_gb is None


def test_probe_falls_back_to_none_when_no_gpu_found(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Windows")

    def fake_run(cmd):
        raise FileNotFoundError("no nvidia-smi")

    profile = probe(run=fake_run)

    assert profile.os == "windows"
    assert profile.gpu_vendor == "none"
    assert profile.vram_gb is None


def test_probe_treats_nvidia_smi_command_error_as_no_gpu(monkeypatch):
    monkeypatch.setattr("deploy.detect.platform.system", lambda: "Linux")

    def fake_run(cmd):
        raise subprocess.CalledProcessError(1, cmd)

    profile = probe(run=fake_run)

    assert profile.gpu_vendor == "none"


def test_probe_reports_real_ram_and_cpu_cores():
    profile = probe()

    assert profile.system_ram_gb > 0
    assert profile.cpu_cores >= 1
