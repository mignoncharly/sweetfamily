"""Loopback load, synthetic authenticated sessions; no response bodies retained."""

import json
import math
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import tasks
from django.test import Client


def measure(role, port, actors, paths):
    cookies = []
    for index in range(40):
        actor = actors[index // 20]
        client = Client()
        if role == "control":
            # Reuse the genuine recent MFA session content in independent encrypted sessions.
            saved = client.session
            saved.update(actor.session.items())
            saved.save()
            cookies.append("noel_control_session=" + saved.session_key)
        else:
            client.force_login(actor)
            cookies.append("; ".join(k + "=" + v.value for k, v in client.cookies.items()))

    def request(index):
        path = paths[(index % 40) // 20]
        started = time.perf_counter()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}" + path, headers={"Cookie": cookies[index % 40]}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
            assert response.status == 200
        return (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=40) as pool:
        list(pool.map(request, range(40)))
        start = time.perf_counter()
        samples = list(pool.map(request, range(400)))
    samples.sort()
    data = {
        "role": role,
        "events": 2,
        "sessions_per_event": 20,
        "concurrency": 40,
        "requests": 400,
        "warmup_requests": 40,
        "p50_http_ms": round(samples[199], 3),
        "p95_http_ms": round(samples[math.ceil(0.95 * len(samples)) - 1], 3),
        "max_http_ms": round(samples[-1], 3),
        "wall_seconds": round(time.perf_counter() - start, 3),
        "target_p95_ms": 500,
        "transport": "HTTP loopback, new connection per request, no TLS",
        "server_threads": 4,
        "resource_limits": "none; local host, not reference production sizes",
    }
    data["target_met"] = data["p95_http_ms"] < 500
    import psycopg
    from django.conf import settings
    from django.db import connections

    database = settings.DATABASES["default"]["NAME"]
    assert settings.APP_ENV == "local" and database.startswith("noel_phase3_test_")
    # End actual native server backends after load, leaving durable sessions/data intact.
    connections.close_all()
    values = tasks.config()
    with psycopg.connect(
        host="127.0.0.1",
        port=tasks.DB_PORTS[role],
        dbname="postgres",
        user="noel_admin",
        password=values[role.upper() + "_DB_ADMIN_PASSWORD"],
        autocommit=True,
    ) as admin:
        rows = admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid<>pg_backend_pid()",
            [database],
        ).fetchall()
    data["terminated_backends"] = len(rows)
    assert rows and all(row[0] for row in rows)
    request(0)
    data["reconnect_after_backend_termination"] = "PASS"
    data["db_conn_max_age"] = settings.DATABASES["default"]["CONN_MAX_AGE"]
    data["db_health_checks"] = settings.DATABASES["default"]["CONN_HEALTH_CHECKS"]
    if os.environ.get("NOEL_QUALIFICATION_DIR"):
        folder = Path(os.environ["NOEL_QUALIFICATION_DIR"]).resolve()
        assert folder.is_relative_to(tasks.LOCAL.resolve())
        (folder / f"http-{role}.json").write_text(json.dumps(data, indent=2), encoding="utf8")
    return data
