"""Exercise the actual native proxy boundary over loopback HTTP."""

import json
import os
import socket
import subprocess
import time
import urllib.request

import pytest
import tasks


@pytest.mark.parametrize("trusted", [False, True])
def test_only_explicit_loopback_proxy_can_set_scheme_and_client_ip(tmp_path, trusted):
    (tmp_path / "proxy_probe.py").write_text("""import json

def application(environ, start_response):
    body = json.dumps({
        'scheme': environ['wsgi.url_scheme'],
        'remote': environ['REMOTE_ADDR'],
        'host': environ.get('HTTP_HOST'),
        'forwarded_host': environ.get('HTTP_X_FORWARDED_HOST'),
        'forwarded': environ.get('HTTP_FORWARDED'),
    }).encode()
    start_response('200 OK', [('Content-Type', 'application/json')])
    return [body]
""")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = os.environ.copy()
    env.pop("TRUSTED_PROXY", None)
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(tasks.ROOT / "packages/contracts")])
    if trusted:
        env["TRUSTED_PROXY"] = "127.0.0.1"
    code = (
        "from noel_server import serve_application; "
        f'serve_application("proxy_probe:application", port={port}, processes=2, threads=2)'
    )
    process = subprocess.Popen(
        [str(tasks.PYTHON), "-c", code],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/",
                    headers={
                        "Host": "portal.example.invalid",
                        "X-Forwarded-Proto": "https",
                        "X-Forwarded-For": "203.0.113.4",
                        "X-Forwarded-Host": "attacker.invalid",
                        "Forwarded": "for=198.51.100.10;host=attacker.invalid;proto=http",
                    },
                )
                with urllib.request.urlopen(request, timeout=1) as response:
                    data = json.load(response)
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("Native proxy server did not start")
        assert data["scheme"] == ("https" if trusted else "http")
        assert data["remote"] == ("203.0.113.4" if trusted else "127.0.0.1")
        assert data["host"] == "portal.example.invalid"
        assert data["forwarded_host"] is None and data["forwarded"] is None
    finally:
        process.terminate()
        process.wait(timeout=15)
    tasks.require_free_port(port)
