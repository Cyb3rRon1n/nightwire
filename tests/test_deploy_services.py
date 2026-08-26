from pathlib import Path

from deploy.services import _ps_single_quote, write_launchd_plist, write_systemd_unit, write_windows_start_script


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
    assert "<key>NIGHTWIRE_MODEL</key>" in content
    assert "<string>qwen3:8b</string>" in content


def test_write_launchd_plist_env_uses_key_not_string(tmp_path):
    """Verify that environment variable keys use <key> tags (not <string>) for valid plist dict format."""
    path = write_launchd_plist(
        "test-svc", Path("/tmp"), ["python", "run.py"], {"MY_VAR": "value1", "ANOTHER": "value2"}, tmp_path
    )

    content = path.read_text()
    # Must use <key> for dict keys, not <string>
    assert "<key>MY_VAR</key>" in content
    assert "<key>ANOTHER</key>" in content
    # Ensure we're not using the buggy <string> form for keys
    assert "<string>MY_VAR</string>\n        <string>value1</string>" not in content
    assert "<string>ANOTHER</string>\n        <string>value2</string>" not in content


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


def test_write_windows_start_script_command_payload_escaping(tmp_path):
    """Verify that env var values are properly single-quoted so PowerShell -Command payload doesn't break."""
    script_path = tmp_path / "start-all.ps1"
    entries = [
        ("nightwire-server", ["python", "-m", "server"], Path("C:/nightwire"), {"NIGHTWIRE_MODEL": "qwen3:8b"}),
    ]

    result_path = write_windows_start_script(entries, script_path)

    content = result_path.read_text()
    # Build expected -Command payload the same way the implementation does
    expected_env_assign = f"$env:NIGHTWIRE_MODEL={_ps_single_quote('qwen3:8b')}"
    expected_cd = f"cd {_ps_single_quote(str(Path('C:/nightwire')))}"
    expected_cmd = "python -m server"
    expected_inner = f"{expected_env_assign}; {expected_cd}; {expected_cmd}"
    expected_command_arg = _ps_single_quote(expected_inner)

    # The full -Command argument must appear in the script
    assert f"-Command', {expected_command_arg}" in content
