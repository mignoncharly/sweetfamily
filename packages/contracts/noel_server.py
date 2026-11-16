"""Bounded native WSGI processes sharing a single private listener on POSIX."""

import importlib
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from waitress import serve


def application(spec):
    module, name = spec.split(":", 1)
    return getattr(importlib.import_module(module), name)


def proxy_options():
    proxy = os.environ.get("TRUSTED_PROXY", "")
    if not proxy:
        return {"clear_untrusted_proxy_headers": True}
    if proxy != "127.0.0.1":
        raise ValueError("Only the private loopback reverse proxy may be trusted")
    return {
        "trusted_proxy": proxy,
        "trusted_proxy_count": 1,
        "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto"},
        "clear_untrusted_proxy_headers": True,
    }


def stop_children(children):
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + 10
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def serve_application(spec, *, port, processes=1, threads=4):
    if not (1 <= processes <= 4 and 1 <= threads <= 16 and processes * threads <= 16):
        raise ValueError("Native web limits: 1..4 processes, 1..16 total threads")
    if processes == 1:
        serve(
            application(spec),
            host="127.0.0.1",
            port=port,
            threads=threads,
            **proxy_options(),
        )
        return
    if os.name != "posix":
        raise ValueError("Multiple native web processes are qualified only on POSIX")

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    children = []
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))
            listener.listen(1024)
            # Each child execs a fresh interpreter: no inherited Django SQL connection,
            # cached session, decrypted value or Python thread state crosses a fork.
            for _ in range(processes):
                children.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--child",
                            spec,
                            str(listener.fileno()),
                            str(threads),
                        ],
                        pass_fds=(listener.fileno(),),
                    )
                )
            while all(child.poll() is None for child in children):
                time.sleep(0.1)
            print("Native web worker exited; stopping siblings", file=sys.stderr)
            raise SystemExit(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_children(children)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "--child":
        raise SystemExit("Use the service web entry point")
    with socket.socket(fileno=int(sys.argv[3])) as inherited:
        serve(
            application(sys.argv[2]),
            sockets=[inherited],
            threads=int(sys.argv[4]),
            **proxy_options(),
        )
