"""Synthetic native-browser qualification, isolated from production distributions."""

import json
import os
import subprocess
import time
import urllib.request

import pytest
import tasks
from django.conf import settings
from django.core import mail
from django.test import Client
from helpers import login_with_code, user


@pytest.mark.concurrent_db
def test_native_browser_forms_and_accessibility():
    role = settings.SERVICE_ROLE
    mail.outbox = []
    if role == "control":
        actor = user("ui-control@example.invalid")
        client = login_with_code(Client(), actor, mfa=True)
        from control_cases import create
        from control_core.models import EventDraft, RosterProposal

        events = [EventDraft.objects.get(pk=create(client)["id"]) for _ in range(2)]
        for i, event in enumerate(events):
            for index in range(20 if i == 0 else 8):
                RosterProposal.objects.create(
                    event=event,
                    display_name=f"Personne {index}",
                    country="FR" if index % 2 else "DE",
                    email=f"{index}@example.invalid",
                )
        paths = [f"/events/{e.id}" for e in events]
        fixture = {"role": role, "event_id": None}
    else:
        from private_cases import fixture as seed

        event, member, client = seed()
        from qualification_cases import eight_person_group
        from vault_core.durability import release

        second, draw = eight_person_group()
        release(draw.id, {"sealed_id": str(draw.id), "fixture": True})
        paths = [f"/wishlist?event_id={e.id}" for e in (event, second)]
        fixture = {"role": role, "event_id": str(event.id)}
    fixture["email"] = actor.email if role == "control" else member.identity.email
    port = tasks.BROWSER_PORTS[role]
    fixture["origin"] = f"http://127.0.0.1:{port}"
    tasks.require_free_port(port)
    fixture["cookies"] = [
        {
            "name": cookie.key,
            "value": cookie.value,
            "url": f"http://127.0.0.1:{port}",
            "httpOnly": bool(cookie["httponly"]),
            "sameSite": "Lax",
        }
        for cookie in client.cookies.values()
    ]
    process = subprocess.Popen(
        [
            str(tasks.PYTHON),
            str(
                tasks.ROOT
                / (
                    "tests/profile_server.py"
                    if os.environ.get("NOEL_HTTP_PROFILE") == "true"
                    else "scripts/serve.py"
                )
            ),
            role,
            str(port),
        ],
        env=os.environ.copy(),
        cwd=tasks.ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        port = tasks.BROWSER_PORTS[role]
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError("UI server exited")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        if os.environ.get("NOEL_QUALIFICATION_DIR"):
            import sys

            sys.path.insert(0, str(tasks.ROOT / "tests"))
            from http_measurements import measure

            measure(
                role,
                port,
                [client, client]
                if role == "control"
                else [member.identity.user, second.members.first().identity.user],
                paths,
            )
        if os.environ.get("NOEL_HTTP_ONLY") == "true":
            return
        env = os.environ.copy() | {
            "NOEL_UI_FIXTURE": json.dumps(fixture),
            "NOEL_TEST_PYTHON": str(tasks.PYTHON),
            "PLAYWRIGHT_BROWSERS_PATH": str(tasks.LOCAL / "pw-browsers"),
        }
        result = subprocess.run(
            ["node", str(tasks.ROOT / "frontend/tests/journeys.mjs")],
            env=env,
            cwd=tasks.ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
    finally:
        process.terminate()
        process.wait(timeout=15)
        if role == "control":
            from control_core.models import EventDraft

            EventDraft.objects.filter(owner__user=actor).delete()
        else:
            # Remove both event graphs before shared identities/users.
            from django.contrib.auth import get_user_model
            from vault_core.models import PrivateEvent, SealedDraw

            users = set(event.members.values_list("identity__user_id", flat=True)) | set(
                second.members.values_list("identity__user_id", flat=True)
            )
            SealedDraw.objects.filter(event__in=[event, second]).delete()
            PrivateEvent.objects.filter(pk__in=[event.id, second.id]).delete()
            get_user_model().objects.filter(pk__in=users).delete()
