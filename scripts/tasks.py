"""Manual local task runner. No containers, hosted repository or CI/CD required."""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
ROLES = ("control", "vault")
DB_PORTS = {"control": 55431, "vault": 55432}
WEB_PORTS = {"control": 8001, "vault": 8002}
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


class Blocked(RuntimeError):
    pass


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def executable(name):
    suffix = ".exe" if os.name == "nt" else ""
    portable = LOCAL / "tools/postgresql/pgsql/bin" / (name + suffix)
    if portable.exists():
        return str(portable)
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        for version in ("18", "17"):
            path = Path(f"C:/Program Files/PostgreSQL/{version}/bin/{name}.exe")
            if path.exists():
                return str(path)
    raise Blocked(f"{name} missing; install PostgreSQL 17/18 or set PATH")


def config():
    path = ROOT / ".env"
    if not path.exists():
        raise Blocked("Run bootstrap first")
    values = dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line and not line.startswith("#") and "=" in line
    )
    if values.get("APP_ENV") != "local":
        raise Blocked("Local tasks require APP_ENV=local in .env")
    return values


def ensure_auth_secrets():
    import base64

    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    values = config()
    values.setdefault("VAULT_WISHLIST_KEY", Fernet.generate_key().decode())
    values.setdefault("VAULT_DRAW_MASTER_KEY", Fernet.generate_key().decode())
    values.setdefault("VAULT_BACKUP_KEY", Fernet.generate_key().decode())
    values.setdefault("VAULT_MASTER_KEYS", json.dumps({"v1": values["VAULT_DRAW_MASTER_KEY"]}))
    values.setdefault("VAULT_ACTIVE_MASTER_KEY", "v1")
    for role in ROLES:
        values.setdefault(f"{role.upper()}_AUTH_DATA_KEY", Fernet.generate_key().decode())
        values.setdefault(f"{role.upper()}_OPERATIONS_KEY", Fernet.generate_key().decode())
        values.setdefault(f"{role.upper()}_BACKUP_KEY", Fernet.generate_key().decode())
    for private_name, public_name in (
        ("CONTROL_COMMAND_PRIVATE_KEY", "VAULT_COMMAND_PUBLIC_KEY"),
        ("VAULT_PROJECTION_PRIVATE_KEY", "CONTROL_PROJECTION_PUBLIC_KEY"),
    ):
        if private_name not in values:
            private = Ed25519PrivateKey.generate()
            values[private_name] = base64.urlsafe_b64encode(
                private.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
            ).decode()
            values[public_name] = base64.urlsafe_b64encode(
                private.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
            ).decode()
    (ROOT / ".env").write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")


def environment(role):
    values = config()
    env = os.environ.copy()
    env.update(
        {
            "APP_ENV": "local",
            "SERVICE_ROLE": role,
            "DEBUG": "false",
            "ENABLE_SYNTHETIC_DIAGNOSTICS": "false",
            "DJANGO_SECRET_KEY": values[f"{role.upper()}_DJANGO_SECRET_KEY"],
            "DB_NAME": f"noel_{role}",
            "DB_USER": f"noel_{role}",
            "DB_PASSWORD": values[f"{role.upper()}_DB_PASSWORD"],
            "DB_HOST": "127.0.0.1",
            "DB_PORT": str(DB_PORTS[role]),
            "DB_SSLMODE": "disable",
            "DB_CONN_MAX_AGE": values.get(
                role.upper() + "_DB_CONN_MAX_AGE", os.environ.get("DB_CONN_MAX_AGE", "60")
            ),
            "ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
            "MAILPIT_SMTP_PORT": "11025",
            "SMTP_HOST": values.get(role.upper() + "_SMTP_HOST", "smtp.zoho.eu"),
            "SMTP_PORT": values.get(role.upper() + "_SMTP_PORT", "465"),
            "SMTP_USE_SSL": values.get(role.upper() + "_SMTP_USE_SSL", "true"),
            "SMTP_USE_TLS": values.get(role.upper() + "_SMTP_USE_TLS", "false"),
            "SMTP_USERNAME": values.get(role.upper() + "_SMTP_USERNAME", ""),
            "SMTP_PASSWORD": values.get(role.upper() + "_SMTP_PASSWORD", ""),
            **{
                name: values.get(role.upper() + "_" + name, "")
                for name in (
                    "RESEND_API_KEY",
                    "RESEND_WEBHOOK_SECRET",
                    "RESEND_DOMAIN_ID",
                    "MAIL_LIVE_ENABLED",
                    "MAIL_DNS_VERIFIED",
                    "MAIL_TRACKING_DISABLED",
                    "MAIL_TEST_RECIPIENTS",
                )
            },
            "MAIL_PROVIDER": values.get(role.upper() + "_MAIL_PROVIDER", "mailpit"),
            "NOTIFICATION_FROM_EMAIL": values.get(
                role.upper() + "_NOTIFICATION_FROM_EMAIL", "simulation@noel.invalid"
            ),
            "DJANGO_SETTINGS_MODULE": f"{role}_project.settings",
            "PYTHONPATH": os.pathsep.join(
                [str(ROOT / "services" / role), str(ROOT / "packages/contracts")]
            ),
            "AUTH_DATA_KEY": values.get(f"{role.upper()}_AUTH_DATA_KEY", ""),
            "COMMAND_KEY": values.get(
                "CONTROL_COMMAND_PRIVATE_KEY" if role == "control" else "VAULT_COMMAND_PUBLIC_KEY",
                "",
            ),
            "PUBLIC_ORIGIN": f"http://127.0.0.1:{WEB_PORTS[role]}",
            "WISHLIST_KEYS": json.dumps({"v1": values.get("VAULT_WISHLIST_KEY", "")})
            if role == "vault"
            else "{}",
            "WISHLIST_ACTIVE_KEY": "v1",
            "DRAW_MASTER_KEYS": values.get(
                "VAULT_MASTER_KEYS", json.dumps({"v1": values.get("VAULT_DRAW_MASTER_KEY", "")})
            )
            if role == "vault"
            else "{}",
            "DRAW_ACTIVE_KEY": values.get("VAULT_ACTIVE_MASTER_KEY", "v1")
            if role == "vault"
            else "v1",
            "VAULT_ORIGIN": "http://127.0.0.1:8002",
            "CONTROL_ORIGIN": "http://127.0.0.1:8001",
            "PROJECTION_KEY": values.get(
                "CONTROL_PROJECTION_PUBLIC_KEY"
                if role == "control"
                else "VAULT_PROJECTION_PRIVATE_KEY",
                "",
            ),
        }
    )
    if os.environ.get("NOEL_TEST_MAILPIT") == "true":
        env.update(
            MAIL_PROVIDER="mailpit",
            MAIL_LIVE_ENABLED="false",
            RESEND_API_KEY="",
            RESEND_WEBHOOK_SECRET="",
            SMTP_USERNAME="",
            SMTP_PASSWORD="",
            NOTIFICATION_FROM_EMAIL=f"simulation-{role}@noel.invalid",
        )
    return env


def manage(role, *args, **kwargs):
    return run(
        [PYTHON, ROOT / "services" / role / "manage.py", *args], env=environment(role), **kwargs
    )


def bootstrap():
    LOCAL.mkdir(exist_ok=True)
    if not (ROOT / ".env").exists():
        values = {"APP_ENV": "local"}
        for role in ROLES:
            for key in ("DJANGO_SECRET_KEY", "DB_PASSWORD", "DB_ADMIN_PASSWORD"):
                values[f"{role.upper()}_{key}"] = secrets.token_urlsafe(48)
        fd = os.open(ROOT / ".env", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in values.items()))
    run(["uv", "sync", "--locked", "--group", "control", "--group", "vault"])
    if Path(sys.executable).resolve() != PYTHON.resolve():
        run([PYTHON, Path(__file__).resolve(), "bootstrap"])
        return
    run([executable("npm"), "--prefix", "frontend", "ci"])
    ensure_auth_secrets()
    install_tools()
    assets()
    print("Local-only secrets generated/reused without displaying them")


def assets():
    run([executable("npm"), "--prefix", "frontend", "run", "check"])
    run([executable("npm"), "--prefix", "frontend", "run", "build"])
    for role in ROLES:
        target = ROOT / "services" / role / "staticfiles"
        shutil.copytree(ROOT / "frontend/dist", target, dirs_exist_ok=True)
        manage(role, "collectstatic", "--noinput")


def install_tools():
    tools = json.loads((ROOT / "infra/tool-versions.json").read_text())
    pg = tools["postgresql"]
    if os.name == "nt":
        directory = LOCAL / "tools/postgresql"
        binary = directory / "pgsql/bin/postgres.exe"
        if not binary.exists():
            archive = LOCAL / "tools/postgresql-download.zip"
            archive.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(pg["url"], archive)
            if hashlib.sha256(archive.read_bytes()).hexdigest() != pg["archive_sha256"]:
                archive.unlink()
                raise Blocked("PostgreSQL archive integrity mismatch")
            with zipfile.ZipFile(archive) as z:
                for entry in z.infolist():
                    target = (directory / entry.filename).resolve()
                    if not target.is_relative_to(directory.resolve()):
                        raise Blocked("Unsafe PostgreSQL archive path")
                    if entry.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
                        z.extract(entry, directory)
            archive.unlink()
        if hashlib.sha256(binary.read_bytes()).hexdigest() != pg["binary_sha256"]:
            raise Blocked("PostgreSQL binary integrity mismatch")
    mailpit()


def db_up():
    import psycopg
    from psycopg import sql

    values = config()
    for role in ROLES:
        data = LOCAL / f"pg-{role}"
        admin_password = values[f"{role.upper()}_DB_ADMIN_PASSWORD"]
        admin_env = os.environ | {"PGPASSWORD": admin_password}
        if not (data / "PG_VERSION").exists():
            pw = LOCAL / f"{role}-init-password"
            try:
                pw.write_text(admin_password, encoding="utf-8")
                run(
                    [
                        executable("initdb"),
                        "-D",
                        data,
                        "-U",
                        "noel_admin",
                        "--pwfile",
                        pw,
                        "--auth-host=scram-sha-256",
                        "--auth-local=scram-sha-256",
                        "--encoding=UTF8",
                        "--locale=C",
                    ],
                    stdout=subprocess.DEVNULL,
                )
            finally:
                pw.unlink(missing_ok=True)
        status = subprocess.run(
            [executable("pg_ctl"), "-D", str(data), "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if status.returncode:
            run(
                [
                    executable("pg_ctl"),
                    "-D",
                    data,
                    "-l",
                    LOCAL / f"pg-{role}.log",
                    "-o",
                    f"-h 127.0.0.1 -p {DB_PORTS[role]}",
                    "-w",
                    "start",
                ],
                env=admin_env,
            )
        with psycopg.connect(
            host="127.0.0.1",
            port=DB_PORTS[role],
            dbname="postgres",
            user="noel_admin",
            password=admin_password,
            autocommit=True,
        ) as conn:
            username = f"noel_{role}"
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (username,)).fetchone():
                conn.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                    ).format(
                        sql.Identifier(username), sql.Literal(values[f"{role.upper()}_DB_PASSWORD"])
                    )
                )
            if not conn.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (username,)
            ).fetchone():
                conn.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(username), sql.Identifier(username)
                    )
                )
                conn.execute(
                    sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                        sql.Identifier(username)
                    )
                )
            conn.execute("REVOKE CONNECT ON DATABASE postgres FROM PUBLIC")
            conn.execute("REVOKE CONNECT ON DATABASE template1 FROM PUBLIC")


def migrate():
    ensure_auth_secrets()
    for role in ROLES:
        manage(role, "migrate", "--noinput")
        manage(role, "bind_environment")
        manage(role, "check_runtime")
        if role == "vault":
            manage(role, "migrate_private_envelopes")


def mailpit():
    versions = json.loads((ROOT / "infra/tool-versions.json").read_text())
    tool = versions["mailpit"]
    folder = LOCAL / "tools"
    binary = folder / ("mailpit.exe" if os.name == "nt" else "mailpit")
    if binary.exists():
        if hashlib.sha256(binary.read_bytes()).hexdigest() != tool["binary_sha256"]:
            raise Blocked("Mailpit binary hash mismatch")
        return binary
    if os.name != "nt":
        raise Blocked(
            "Install pinned Mailpit for your platform and update verified binary checksum"
        )
    folder.mkdir(exist_ok=True)
    archive = folder / "mailpit.zip"
    urllib.request.urlretrieve(tool["url"], archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != tool["archive_sha256"]:
        archive.unlink()
        raise Blocked("Mailpit archive hash mismatch")
    with zipfile.ZipFile(archive) as z:
        binary.write_bytes(z.read("mailpit.exe"))
    archive.unlink()
    return mailpit()


def dev_up():
    db_up()
    migrate()
    assets()
    binary = mailpit()
    commands = [
        (
            None,
            [
                binary,
                "--listen",
                "127.0.0.1:18025",
                "--smtp",
                "127.0.0.1:11025",
                "--label",
                "Simulation",
            ],
        )
    ]
    for role in ROLES:
        commands.extend(
            [
                (role, [PYTHON, ROOT / "scripts/serve.py", role]),
                (role, [PYTHON, ROOT / "services" / role / "manage.py", "worker"]),
            ]
        )
    processes = []
    try:
        for role, args in commands:
            processes.append(
                subprocess.Popen(
                    [str(x) for x in args],
                    cwd=ROOT,
                    env=environment(role) if role else os.environ.copy(),
                )
            )
        print(
            "Control http://127.0.0.1:8001/health/ready | Vault http://127.0.0.1:8002/health/ready"
        )
        print("Mailpit Simulation http://127.0.0.1:18025 | Ctrl+C stops apps/workers/Mailpit")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        raise RuntimeError("A supervised process exited")
    except KeyboardInterrupt:
        pass
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
        for p in processes:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def db_down():
    for role in ROLES:
        data = LOCAL / f"pg-{role}"
        if (data / "postmaster.pid").exists():
            run([executable("pg_ctl"), "-D", data, "-m", "fast", "-w", "stop"])


def checks():
    run([PYTHON, "-m", "ruff", "check", "services", "scripts", "tests", "packages"])
    run([PYTHON, "-m", "ruff", "format", "--check", "services", "scripts", "tests", "packages"])
    assets()
    for role in ROLES:
        manage(role, "check")
        manage(role, "makemigrations", "--check", "--dry-run")


def test(kind):
    if kind == "integration":
        db_up()
        migrate()
    run(
        [
            PYTHON,
            "-m",
            "pytest",
            "-q",
            "-m",
            {"unit": "not integration", "integration": "integration", "privacy": "privacy"}[kind],
        ]
    )


def test_draw():
    db_up()
    migrate()
    run([PYTHON, "-m", "pytest", "-q", "tests/test_draw_engine.py", "tests/test_phase3.py"])


def security():
    run([PYTHON, ROOT / "scripts/scan_secrets.py"])
    run([PYTHON, "-m", "pip_audit"])
    run([executable("npm"), "--prefix", "frontend", "audit", "--audit-level=low"])
    for role in ROLES:
        env = environment(role)
        env.update(
            APP_ENV="production",
            DB_SSLMODE="verify-full",
            ALLOWED_HOSTS=f"{role}.example.invalid",
            PUBLIC_ORIGIN=f"https://{role}.example.invalid",
            VAULT_ORIGIN="https://vault.example.invalid",
            CONTROL_ORIGIN="https://control.example.invalid",
        )
        run(
            [
                PYTHON,
                ROOT / "services" / role / "manage.py",
                "check",
                "--deploy",
                "--fail-level",
                "WARNING",
            ],
            env=env,
        )


def zip_entry(archive, name, content):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def build_test():
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    with zipfile.ZipFile(output / "noel-tests.zip", "w") as archive:
        for folder in ("services", "scripts", "tests", "packages", "docs"):
            for source in sorted((ROOT / folder).rglob("*")):
                if source.is_file() and (
                    source.suffix in {".py", ".md", ".json"} or "templates" in source.parts
                ):
                    zip_entry(archive, source.relative_to(ROOT).as_posix(), source.read_bytes())
        for name in (
            "pyproject.toml",
            "uv.lock",
            "infra/tool-versions.json",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/tsconfig.json",
            "frontend/build.mjs",
            "frontend/tests/journeys.mjs",
            "frontend/src/main.ts",
            "frontend/src/main.css",
            ".env.example",
            ".python-version",
            ".gitignore",
            "Makefile",
            "README.md",
        ):
            zip_entry(archive, name, (ROOT / name).read_bytes())
    print("Separate test distribution built")


def build_prod():
    assets()
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    for role in ROLES:
        # Import and inspect actual URL configuration; no DB access during artifact checks.
        code = (
            f"import django; django.setup(); "
            f"from {role}_core.runtime import assert_routes; assert_routes()"
        )
        env = environment(role)
        env.update(
            APP_ENV="production",
            DB_SSLMODE="verify-full",
            ALLOWED_HOSTS=f"{role}.example.invalid",
            PUBLIC_ORIGIN=f"https://{role}.example.invalid",
            VAULT_ORIGIN="https://vault.example.invalid",
            CONTROL_ORIGIN="https://control.example.invalid",
        )
        run([PYTHON, "-c", code], env=env)
        result = run(
            [
                "uv",
                "export",
                "--locked",
                "--no-default-groups",
                "--group",
                role,
                "--no-emit-project",
                "--no-header",
            ],
            capture_output=True,
            text=True,
        )
        with zipfile.ZipFile(
            output / f"noel-{role}-production.zip", "w", zipfile.ZIP_DEFLATED
        ) as z:
            for p in sorted((ROOT / "services" / role).rglob("*")):
                if p.is_file() and (
                    p.suffix in {".py", ".json"}
                    or "templates" in p.parts
                    or "staticfiles" in p.parts
                ):
                    zip_entry(z, p.relative_to(ROOT / "services" / role).as_posix(), p.read_bytes())
            zip_entry(
                z, "noel_contracts.py", (ROOT / "packages/contracts/noel_contracts.py").read_bytes()
            )
            zip_entry(
                z, "noel_delivery.py", (ROOT / "packages/contracts/noel_delivery.py").read_bytes()
            )
            zip_entry(z, "noel_ui.py", (ROOT / "packages/contracts/noel_ui.py").read_bytes())
            for module in ("noel_operations.py", "noel_backups.py"):
                zip_entry(z, module, (ROOT / "packages/contracts" / module).read_bytes())
            for p in sorted((ROOT / "frontend/dist").glob("*")):
                zip_entry(z, "assets/" + p.name, p.read_bytes())

            zip_entry(z, "requirements.txt", result.stdout)
            zip_entry(
                z,
                "serve.py",
                (ROOT / "scripts/artifact_serve.py").read_text().replace("ROLE", role),
            )
    artifact_check()


def artifact_check():
    for role in ROLES:
        path = ROOT / f"artifacts/noel-{role}-production.zip"
        if not path.exists():
            raise Blocked("Run build-prod first")
        other = "vault" if role == "control" else "control"
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if any(
                    w in name.lower()
                    for w in ("diagnostic", "synthetic", "test", ".env", "__pycache__")
                ):
                    raise RuntimeError("Forbidden production artifact entry")
                if name.startswith((f"{other}_core/", f"{other}_project/")):
                    raise RuntimeError("Foreign service packaged")
            for required in ("serve.py", "requirements.txt", "assets/main.js", "assets/main.css"):
                if required not in z.namelist():
                    raise RuntimeError("Incomplete production artifact")
            if "--hash=sha256:" not in z.read("requirements.txt").decode():
                raise RuntimeError("Dependency integrity missing")
    print("Production distributions checked; no diagnostics/tests/foreign service")


def browser_checks():
    db_up()
    assets()
    os.environ["NOEL_TEST_MAILPIT"] = "true"
    sys.path.insert(0, str(ROOT / "tests"))
    from test_phase3 import run_service_cases

    for role in ROLES:
        run_service_cases(role, ["tests/cases/browser_cases.py"])
    print(
        "Native browser journeys and Axe checks passed; manual "
        "assistive-technology review remains required"
    )


def verify_release():
    import tasks as shared_tasks
    from qualify import verify_release as verify

    try:
        verify()
    except shared_tasks.Blocked as exc:
        # tasks.py may be __main__; translate the imported module’s exception type.
        raise Blocked(str(exc)) from None
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise Blocked("Run qualify first; evidence missing or invalid") from exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    task = parser.parse_args().task
    if PYTHON.exists() and Path(sys.executable).resolve() != PYTHON.resolve():
        raise SystemExit(subprocess.call([str(PYTHON), str(Path(__file__).resolve()), task]))
    tasks = {
        "bootstrap": bootstrap,
        "db-up": db_up,
        "install-tools": install_tools,
        "db-down": db_down,
        "dev-up": dev_up,
        "migrate": migrate,
        "check": checks,
        "test-draw": test_draw,
        "test-e2e": browser_checks,
        "check-accessibility": browser_checks,
        "qualify": lambda: run([PYTHON, ROOT / "scripts/qualify.py"]),
        "verify-release": verify_release,
        "test-unit": lambda: test("unit"),
        "test-integration": lambda: test("integration"),
        "test-privacy": lambda: test("privacy"),
        "check-security": security,
        "build-prod": build_prod,
        "build-test": build_test,
        "check-prod-artifact": artifact_check,
        "backup-drill": backup_drill,
    }
    future = {}
    if task in future:
        raise Blocked(f"{task} requires phase {future[task]}; not implemented, not a passing check")
    if task not in tasks:
        parser.error("Unknown task")
    tasks[task]()


def backup_drill():
    db_up()
    sys.path.insert(0, str(ROOT / "tests"))
    from test_phase3 import run_service_cases

    for role in ROLES:
        run_service_cases(role, ["tests/cases/operations_cases.py"])
    print("Local isolated PostgreSQL recovery/purge drill passed for both services.")


if __name__ == "__main__":
    try:
        main()
    except Blocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as exc:
        print(f"FAILED: command exited with status {exc.returncode}", file=sys.stderr)
        sys.exit(exc.returncode)
