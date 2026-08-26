from pathlib import Path

from deploy.services import write_launchd_plist, write_systemd_unit, write_windows_start_script


def test_write_systemd_unit_contains_exec_and_env(tmp_path):
    # Path("/opt/nightwire") stringifies with the host's native separator
    # (backslash on Windows) - build the expected value the same way the
    # implementation does, via str(), rather than hardcoding a forward-slash
    # literal that would only match on POSIX.
    working_dir = Path("/opt/nightwire")
    path = write_systemd_unit(
        "nightwire-server", working_dir, "python -m server", {"NIGHTWIRE_MODEL": "qwen3:8b"}, tmp_path
    )

    content = path.read_text()
    assert path.name == "nightwire-nightwire-server.service"
    assert "ExecStart=python -m server" in content
    assert f"WorkingDirectory={working_dir}" in content
    assert "Environment=NIGHTWIRE_MODEL=qwen3:8b" in content
    assert "[Install]" in content


def test_write_launchd_plist_contains_program_args_and_env(tmp_path):
    path = write_launchd_plist(
        "nightwire-server", Path("/opt/nightwire"), ["python", "-m", "server"], {"NIGHTWIRE_MODEL": "qwen3:8b"}, tmp_path
    )

    content = path.read_text()
    assert path.name == "com.nightwire.nightwire-server.plist"
    assert "<string>python</string>" in content
    assert "<string>NIGHTWIRE_MODEL</string>" in content
    assert "<string>qwen3:8b</string>" in content


def test_write_windows_start_script_lists_every_entry(tmp_path):
    script_path = tmp_path / "start-all.ps1"
    entries = [
        ("nightwire-server", ["python", "-m", "server"], Path("C:/nightwire"), {"NIGHTWIRE_MODEL": "qwen3:8b"}),
        ("kokoro-server", ["bash", "start-gpu.sh"], Path("C:/Kokoro-FastAPI"), {"ALLOW_DEV_UNLOAD": "true"}),
    ]

    result_path = write_windows_start_script(entries, script_path)

    content = result_path.read_text()
    assert "nightwire-server" in content
    assert "kokoro-server" in content
    assert "NIGHTWIRE_MODEL" in content
    assert "ALLOW_DEV_UNLOAD" in content
