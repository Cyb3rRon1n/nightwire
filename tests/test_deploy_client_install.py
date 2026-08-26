from deploy.client_install import node_version_ok, run


def test_node_version_ok_true_for_22_plus():
    ok, version = node_version_ok(lambda cmd: "v22.4.0\n")
    assert ok is True
    assert version == "v22.4.0"


def test_node_version_ok_false_for_below_22():
    ok, version = node_version_ok(lambda cmd: "v20.11.0\n")
    assert ok is False
    assert version == "v20.11.0"


def test_node_version_ok_false_when_node_missing():
    def fake_run(cmd):
        raise FileNotFoundError("no node")

    ok, version = node_version_ok(fake_run)
    assert ok is False
    assert version == "not found"


def test_run_writes_env_local_and_runs_npm_ci(tmp_path):
    calls = []
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    run("ws://192.168.1.10:8000", frontend_dir, run_cmd=calls.append)

    env_file = frontend_dir / ".env.local"
    assert env_file.read_text().strip() == "NEXT_PUBLIC_NIGHTWIRE_WS_URL=ws://192.168.1.10:8000"
    assert calls == [["npm", "ci"]]


def test_run_default_run_cmd_calls_real_subprocess(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "deploy.client_install.subprocess.run",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)),
    )
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    run("ws://localhost:8000", frontend_dir)

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == ["npm", "ci"]
    assert kwargs["check"] is True
    assert kwargs["cwd"] == frontend_dir
