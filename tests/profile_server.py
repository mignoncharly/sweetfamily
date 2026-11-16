"""Opt-in synthetic HTTP profiler. Never included in production distributions.

Only aggregate timings/counts cross HTTP; SQL text, parameters and bodies are not recorded.
Template timing is inclusive (nested templates overlap). HTTP minus app includes queue/network.
"""

import importlib
import os
import sys
import threading
import time
from pathlib import Path

import django
from django.conf import settings
from django.db import connection
from django.template.base import Template
from noel_server import serve_application

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import tasks

role = settings.SERVICE_ROLE
assert role in tasks.ROLES
assert os.environ.get("NOEL_HTTP_PROFILE") == "true"
django.setup()
assert settings.APP_ENV == "local"
assert settings.DATABASES["default"]["NAME"].startswith("noel_phase3_test_")
application = importlib.import_module(f"{role}_project.wsgi").application
state = threading.local()
original_render = Template.render


def render(self, context):
    started = time.perf_counter()
    try:
        return original_render(self, context)
    finally:
        if hasattr(state, "template"):
            state.template += time.perf_counter() - started


Template.render = render


def profile(environ, start_response):
    state.template = 0
    sql_seconds = 0
    query_count = 0

    def execute(call, sql, params, many, context):
        nonlocal sql_seconds, query_count
        query_count += 1
        started = time.perf_counter()
        try:
            return call(sql, params, many, context)
        finally:
            sql_seconds += time.perf_counter() - started

    started = time.perf_counter()

    def response(status, headers, exc_info=None):
        headers.append(
            (
                "Server-Timing",
                ", ".join(
                    [
                        f"app;dur={(time.perf_counter() - started) * 1000:.3f}",
                        f"sql;dur={sql_seconds * 1000:.3f}",
                        f"template;dur={state.template * 1000:.3f}",
                        f"queries;dur={query_count}",
                    ]
                ),
            )
        )
        return start_response(status, headers, exc_info)

    with connection.execute_wrapper(execute):
        return application(environ, response)


if __name__ == "__main__":
    os.environ["PYTHONPATH"] = os.pathsep.join(
        [str(tasks.ROOT / "tests"), os.environ.get("PYTHONPATH", "")]
    )
    serve_application(
        "profile_server:profile",
        port=int(sys.argv[2]),
        processes=tasks.WEB_PROCESSES,
        threads=tasks.WEB_THREADS,
    )
