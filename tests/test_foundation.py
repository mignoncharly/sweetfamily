import ast
import json
import subprocess

import pytest
import tasks

ROOT = tasks.ROOT


def execute(role, code, **overrides):
    env = tasks.environment(role)
    env.update(overrides)
    if env["APP_ENV"] != "local":
        env["PUBLIC_ORIGIN"] = f"https://{role}.example.invalid"
        env["CONTROL_ORIGIN"] = "https://control.example.invalid"
        env["VAULT_ORIGIN"] = "https://vault.example.invalid"
    return subprocess.run(
        [str(tasks.PYTHON), "-c", code], env=env, cwd=ROOT, capture_output=True, text=True
    )


@pytest.mark.parametrize("role", tasks.ROLES)
def test_liveness_is_database_independent(role):
    result = execute(
        role,
        """
import django
django.setup()
from django.test import Client
response = Client().get('/health/live')
assert response.status_code == 200
assert response.json() == {'status':'ok'}
assert response['Cache-Control'] == 'no-store'
assert "frame-ancestors 'none'" in response['Content-Security-Policy']
assert Client().post('/health/live').status_code == 405
""",
        DB_PORT="1",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("role", tasks.ROLES)
def test_unavailable_readiness_is_neutral(role):
    result = execute(
        role,
        """
import django
django.setup()
from django.test import Client
response = Client().get('/health/ready')
assert response.status_code == 503
assert response.json() == {'status':'unavailable'}
""",
        DB_PORT="1",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.privacy
@pytest.mark.parametrize("role", tasks.ROLES)
@pytest.mark.parametrize(
    "overrides",
    [
        {"SERVICE_ROLE": "foreign"},
        {"APP_ENV": "unknown"},
        {"APP_ENV": "production", "DEBUG": "true"},
        {"APP_ENV": "production", "DB_SSLMODE": "disable"},
        {"ENABLE_SYNTHETIC_DIAGNOSTICS": "true"},
        {"DJANGO_SECRET_KEY": ""},
        {"ALLOWED_HOSTS": "*"},
        {"DB_CONN_MAX_AGE": "-1"},
        {"DB_CONN_MAX_AGE": "301"},
        {"DB_CONN_MAX_AGE": "invalid"},
    ],
)
def test_invalid_configuration_refused(role, overrides):
    result = execute(role, "import django; django.setup()", **overrides)
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr


@pytest.mark.privacy
@pytest.mark.parametrize("role", tasks.ROLES)
def test_nested_diagnostic_route_refused(role):
    result = execute(
        role,
        f"""
import django
django.setup()
from django.urls import include, path
from django.core.exceptions import ImproperlyConfigured
from {role}_core.health import live
from {role}_core.runtime import assert_routes
try:
    assert_routes([path('hidden/', include([path('diagnostics/', live)]))])
except ImproperlyConfigured:
    pass
else:
    raise AssertionError("Diagnostic route accepted")
""",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.privacy
def test_service_import_boundaries():
    for role in tasks.ROLES:
        foreign = "vault" if role == "control" else "control"
        for path in (ROOT / "services" / role).rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [n.name for n in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                assert not any(
                    m.startswith((f"{foreign}_core", f"{foreign}_project")) for m in modules
                )


@pytest.mark.privacy
@pytest.mark.parametrize("role", tasks.ROLES)
def test_logs_omit_payloads_and_exceptions(role):
    result = execute(
        role,
        f"""
import django, logging
django.setup()
from {role}_core.logging import SafeFormatter
record = logging.LogRecord('test', 40, '', 0, 'PRIVATE_CANARY %s', ('SECRET',), None)
assert 'PRIVATE_CANARY' not in SafeFormatter().format(record)
assert 'SECRET' not in SafeFormatter().format(record)
""",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("role", tasks.ROLES)
def test_nonlocal_mail_fails_closed(role):
    result = execute(
        role,
        """
import django
django.setup()
from django.core.mail import send_mail
try:
    send_mail('hello','body','sender@example.invalid',['receiver@example.invalid'])
except RuntimeError:
    pass
else:
    raise AssertionError('Email silently sent or discarded')
""",
        APP_ENV="staging",
        DB_SSLMODE="verify-full",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
@pytest.mark.parametrize("role", tasks.ROLES)
def test_runtime_and_environment_binding(role):
    result = execute(
        role,
        f"""
import django
django.setup()
from django.test import Client, override_settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from {role}_core.runtime import assert_runtime
assert_runtime()
assert Client().get('/health/ready').json() == {{'status':'ok'}}
with override_settings(APP_ENV='staging'):
    try:
        assert_runtime()
    except ImproperlyConfigured:
        pass
    else:
        raise AssertionError('Foreign environment accepted')
    try:
        call_command('bind_environment')
    except CommandError:
        pass
    else:
        raise AssertionError('Database rebound')
    assert Client().get('/health/ready').status_code == 503
assert_runtime()
""",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
@pytest.mark.privacy
def test_databases_and_credentials_are_isolated():
    import psycopg

    for role in tasks.ROLES:
        foreign = "vault" if role == "control" else "control"
        env = tasks.environment(role)
        with pytest.raises(psycopg.OperationalError) as refused:
            psycopg.connect(
                host="127.0.0.1",
                port=tasks.DB_PORTS[foreign],
                dbname=f"noel_{foreign}",
                user=env["DB_USER"],
                password=env["DB_PASSWORD"],
                connect_timeout=3,
            )
        assert "password authentication failed" in str(refused.value).lower()
        with psycopg.connect(
            host=env["DB_HOST"],
            port=env["DB_PORT"],
            dbname=env["DB_NAME"],
            user=env["DB_USER"],
            password=env["DB_PASSWORD"],
        ) as conn:
            row = conn.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole "
                "FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            assert row == (False, False, False)


@pytest.mark.integration
@pytest.mark.parametrize("role", tasks.ROLES)
def test_fresh_database_and_reversible_migration(role):
    import secrets

    import psycopg
    from psycopg import sql

    name = "noel_phase2_test_" + secrets.token_hex(6)
    values = tasks.config()
    admin = psycopg.connect(
        host="127.0.0.1",
        port=tasks.DB_PORTS[role],
        dbname="postgres",
        user="noel_admin",
        password=values[f"{role.upper()}_DB_ADMIN_PASSWORD"],
        autocommit=True,
    )
    try:
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(name), sql.Identifier(f"noel_{role}")
            )
        )
        env = tasks.environment(role) | {"DB_NAME": name}
        command = [str(tasks.PYTHON), str(ROOT / "services" / role / "manage.py")]
        for args in (
            ["migrate", "--noinput"],
            ["bind_environment"],
            ["check_runtime"],
            ["migrate", f"{role}_core", "zero", "--noinput"],
            ["migrate", "--noinput"],
            ["bind_environment"],
            ["check_runtime"],
        ):
            result = subprocess.run(
                command + args, env=env, cwd=ROOT, capture_output=True, text=True
            )
            assert result.returncode == 0, result.stderr
    finally:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        admin.close()


@pytest.mark.integration
def test_real_local_web_worker_and_mailpit_processes():
    import time
    import urllib.request

    processes = []
    try:
        processes.append(
            subprocess.Popen(
                [
                    str(tasks.mailpit()),
                    "--listen",
                    "127.0.0.1:18025",
                    "--smtp",
                    "127.0.0.1:11025",
                    "--label",
                    "Simulation",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        for role in tasks.ROLES:
            processes.append(
                subprocess.Popen(
                    [str(tasks.PYTHON), str(ROOT / "scripts/serve.py"), role],
                    env=tasks.environment(role),
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
            processes.append(
                subprocess.Popen(
                    [str(tasks.PYTHON), str(ROOT / "services" / role / "manage.py"), "worker"],
                    env=tasks.environment(role),
                    cwd=ROOT,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        for url in (
            "http://127.0.0.1:18025/api/v1/messages",
            "http://127.0.0.1:8001/health/ready",
            "http://127.0.0.1:8002/health/ready",
        ):
            deadline = time.monotonic() + 180
            while True:
                assert all(p.poll() is None for p in processes), "Local process exited"
                try:
                    with urllib.request.urlopen(url, timeout=3) as response:
                        assert response.status == 200
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise AssertionError("Local service readiness timeout") from None
                    time.sleep(1)
        result = execute(
            "vault",
            """
import django
django.setup()
from django.core.mail import send_mail
assert send_mail('Simulation phase 2', 'Message synthetique sans attribution.',
                 'simulation@noel.invalid', ['recette@example.invalid']) == 1
""",
        )
        assert result.returncode == 0, result.stderr
        with urllib.request.urlopen("http://127.0.0.1:18025/api/v1/messages") as response:
            payload = json.load(response)
        assert payload["total"] >= 1
        from phase3_smoke import run_smoke

        run_smoke()
        assert all(p.poll() is None for p in processes)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


@pytest.mark.privacy
@pytest.mark.parametrize("case", ["missing", "shared", "bad_id"])
def test_draw_master_key_is_required_and_independent(case):
    env = tasks.environment("vault")
    keys = {
        "missing": "{}",
        "shared": json.dumps({"v1": env["AUTH_DATA_KEY"]}),
        "bad_id": json.dumps({"x" * 41: tasks.config()["VAULT_DRAW_MASTER_KEY"]}),
    }
    result = execute("vault", "import django; django.setup()", DRAW_MASTER_KEYS=keys[case])
    assert result.returncode != 0
    assert "Independent draw keys required" in result.stderr


@pytest.mark.privacy
def test_sealed_models_have_no_plaintext_assignment_and_no_service_read_route():
    result = execute(
        "vault",
        """
import django
django.setup()
from django.test import Client
from vault_core.models import DrawJob, SealedDraw, DrawNotification
for model in (DrawJob,SealedDraw,DrawNotification):
    forbidden = {"recipient_id","permutation","seed","result_hash"}
    assert not forbidden & {f.name for f in model._meta.fields}
assert Client().get('/api/me/recipient').status_code==401
assert Client().get('/internal/result').status_code==404
""",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.privacy
def test_private_process_refuses_debugger_in_nonlocal_mode():
    result = execute(
        "vault",
        """
import django
django.setup()
from django.test import override_settings
from django.core.exceptions import ImproperlyConfigured
from unittest.mock import patch
from vault_core.hardening import harden_process
harden_process.cache_clear()
with override_settings(APP_ENV='production'), patch('sys.gettrace',return_value=object()):
    try:
        harden_process()
    except ImproperlyConfigured:
        pass
    else:
        raise AssertionError('Debugger accepted')
""",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.privacy
def test_local_master_staging_never_replaces_old_version(tmp_path, monkeypatch, capsys):
    import sys

    import noel_operator

    monkeypatch.setattr(tasks, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("APP_ENV=local\n")
    monkeypatch.setattr(sys, "argv", ["noel_operator.py", "stage-master-key", "--to-key", "v2"])
    noel_operator.main()
    first = json.loads(tasks.config()["VAULT_MASTER_KEYS"])
    noel_operator.main()
    assert json.loads(tasks.config()["VAULT_MASTER_KEYS"]) == first
    monkeypatch.setattr(sys, "argv", ["noel_operator.py", "activate-master-key", "--to-key", "v2"])
    noel_operator.main()
    values = tasks.config()
    assert values["VAULT_ACTIVE_MASTER_KEY"] == "v2" and len(first) == 2
    output = capsys.readouterr().out
    assert not any(value in output for value in first.values())


@pytest.mark.privacy
def test_mail_provider_credentials_remain_separate(monkeypatch):
    monkeypatch.delenv("NOEL_TEST_MAILPIT", raising=False)
    values = tasks.config() | {
        "CONTROL_RESEND_API_KEY": "control-only-provider",
        "VAULT_RESEND_API_KEY": "vault-only-provider",
    }
    monkeypatch.setattr(tasks, "config", lambda: values)
    control = tasks.environment("control")
    vault = tasks.environment("vault")
    assert control["RESEND_API_KEY"] == "control-only-provider"
    assert vault["RESEND_API_KEY"] == "vault-only-provider"
    assert "vault-only-provider" not in control.values()
    assert "control-only-provider" not in vault.values()


@pytest.mark.privacy
def test_resend_transport_requires_explicit_live_configuration():
    result = execute(
        "vault",
        """
import django
django.setup()
from django.test import override_settings
from noel_delivery import send,DeliveryError
from unittest.mock import patch
import uuid
with override_settings(MAIL_PROVIDER='resend',MAIL_LIVE_ENABLED=False):
    with patch('noel_delivery.provider_request') as request:
        try:
            send({'from':'notify@example.invalid','email':'inbox@example.invalid',
                  'subject':'neutre','body':'message'},uuid.uuid4(),'resend')
        except DeliveryError:
            pass
        else:
            raise AssertionError('Unconfigured real mail accepted')
        request.assert_not_called()
""",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.privacy
def test_automated_tests_force_simulation_and_remove_live_credentials(monkeypatch):
    values = tasks.config() | {
        "VAULT_MAIL_PROVIDER": "zoho",
        "VAULT_MAIL_LIVE_ENABLED": "true",
        "VAULT_SMTP_PASSWORD": "live-synthetic-only",
    }
    monkeypatch.setattr(tasks, "config", lambda: values)
    monkeypatch.setenv("NOEL_TEST_MAILPIT", "true")
    env = tasks.environment("vault")
    assert env["MAIL_PROVIDER"] == "mailpit" and env["MAIL_LIVE_ENABLED"] == "false"
    assert env["SMTP_PASSWORD"] == env["RESEND_API_KEY"] == ""
