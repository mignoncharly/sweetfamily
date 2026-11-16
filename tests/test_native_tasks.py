"""Guard shared-host isolation, including inherited operator credentials."""

import socket
import sys
from pathlib import Path

import pytest
import tasks


def test_occupied_port_is_refused_without_replacing_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        with pytest.raises(tasks.Blocked, match="occupied"):
            tasks.require_free_port(listener.getsockname()[1])
        assert listener.getsockname()[1] > 0


def test_application_environment_excludes_inherited_foreign_and_operator_secrets(monkeypatch):
    names = [
        "VAULT_OPERATIONS_KEY",
        "CONTROL_BACKUP_KEY",
        "OPERATIONS_KEY",
        "BACKUP_DB_PASSWORD",
        "PGPASSWORD",
        "PG_BIN",
    ]
    for name in names:
        monkeypatch.setenv(name, "synthetic-inherited-credential")
    control, vault = tasks.environment("control"), tasks.environment("vault")
    for env in (control, vault):
        assert all(name not in env for name in names)
        assert "DB_ADMIN_PASSWORD" not in env
    assert control["DB_PORT"] != vault["DB_PORT"]
    assert control["AUTH_DATA_KEY"] != vault["AUTH_DATA_KEY"]
    assert control["DRAW_MASTER_KEYS"] == "{}"


def test_environment_detection_distinguishes_system_interpreter_from_venv(monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(tasks.ROOT / ".venv"))
    assert tasks.in_project_environment()
    monkeypatch.setattr(sys, "prefix", str(Path("/synthetic/system/python")))
    assert not tasks.in_project_environment()


@pytest.mark.skipif(sys.platform != "linux", reason="Native process lifecycle uses Linux /proc")
@pytest.mark.parametrize("shutdown", ["parent", "child_failure"])
def test_two_web_processes_stop_together_without_leaving_listeners(shutdown):
    import os
    import signal
    import subprocess
    import time
    import urllib.request

    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    env = tasks.environment("control") | {"NOEL_WEB_PROCESSES": "2", "NOEL_WEB_THREADS": "2"}
    process = subprocess.Popen(
        [str(tasks.PYTHON), str(tasks.ROOT / "scripts/serve.py"), "control", str(port)],
        env=env,
        cwd=tasks.ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    children = []
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/live", timeout=1) as r:
                    assert r.status == 200
                children = [
                    int(pid)
                    for pid in Path(f"/proc/{process.pid}/task/{process.pid}/children")
                    .read_text()
                    .split()
                ]
                if len(children) == 2:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        assert len(children) == 2, "Two native web children did not start"
        if shutdown == "parent":
            process.terminate()
        else:
            os.kill(children[0], signal.SIGKILL)
        process.wait(timeout=15)
        assert process.returncode == (0 if shutdown == "parent" else 1)
        for pid in children:
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
        tasks.require_free_port(port)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=15)
