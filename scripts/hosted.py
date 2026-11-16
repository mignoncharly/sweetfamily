"""Isolated HTTPS staging deployment. Never imports another application's configuration."""

import argparse
import base64
import json
import os
import secrets
import subprocess
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local/hosted"
PYTHON = ROOT / ".venv/bin/python"
PG = Path("/usr/lib/postgresql/17/bin")
ROLES = ("control", "vault")
PORTS = {"control": (55441, 8101), "vault": (55443, 8102)}
DOMAINS = {"control": "sweetfamily.gestionatech.de", "vault": "vault.sweetfamily.gestionatech.de"}


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")


def environment(role, operator=False):
    # An allowlist prevents inherited deployment/admin/other-service secrets leaking.
    env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "TZ") if k in os.environ}
    env.update(json.loads((BASE / role / "app.json").read_text()))
    if operator:
        env.update(json.loads((BASE / role / "operator.json").read_text()))
    return env


def python(role):
    return BASE / role / "venv/bin/python"


def manage(role, *args, operator=False):
    return run(
        [python(role), BASE / role / "release/manage.py", *args], env=environment(role, operator)
    )


def certificates(folder):
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    folder.mkdir(mode=0o700)
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Sweetfamily staging SQL CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(ca_key, hashes.SHA256())
    )
    for file, content in {
        "ca.pem": ca.public_bytes(serialization.Encoding.PEM),
        "server.crt": cert.public_bytes(serialization.Encoding.PEM),
        "server.key": key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    }.items():
        path = folder / file
        path.write_bytes(content)
        path.chmod(0o600)
    # The disposable SQL CA signing key is not retained; renew via a reviewed new CA.


def prepare():
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    BASE.mkdir(mode=0o700, exist_ok=True)
    public, private = {}, {}
    for role in ROLES:
        key = Ed25519PrivateKey.generate()
        private[role] = base64.urlsafe_b64encode(
            key.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
        ).decode()
        public[role] = base64.urlsafe_b64encode(
            key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode()
    if any((BASE / role).exists() for role in ROLES):
        raise SystemExit("Hosted configuration already exists; refusing to regenerate keys")
    for role in ROLES:
        folder = BASE / role
        folder.mkdir(mode=0o700)
        certificates(folder / "tls")
        release = folder / "release"
        release.mkdir(mode=0o700)
        archive = ROOT / f"artifacts/noel-{role}-production.zip"
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                if not (release / entry.filename).resolve().is_relative_to(release.resolve()):
                    raise SystemExit("Unsafe artifact path")
            z.extractall(release)
        env = {
            "APP_ENV": "staging",
            "SERVICE_ROLE": role,
            "DEBUG": "false",
            "ENABLE_SYNTHETIC_DIAGNOSTICS": "false",
            "DJANGO_SETTINGS_MODULE": f"{role}_project.settings",
            "PYTHONPATH": str(release),
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DB_NAME": f"sweetfamily_stage_{role}",
            "DB_USER": f"sweetfamily_stage_{role}",
            "DB_PASSWORD": secrets.token_urlsafe(48),
            "DB_HOST": "127.0.0.1",
            "DB_PORT": str(PORTS[role][0]),
            "DB_SSLMODE": "verify-full",
            "PGSSLROOTCERT": str(folder / "tls/ca.pem"),
            "DB_CONN_MAX_AGE": "60",
            "ALLOWED_HOSTS": DOMAINS[role] + ",127.0.0.1",
            "PUBLIC_ORIGIN": "https://" + DOMAINS[role],
            "CONTROL_ORIGIN": "https://" + DOMAINS["control"],
            "VAULT_ORIGIN": "https://" + DOMAINS["vault"],
            "AUTH_DATA_KEY": Fernet.generate_key().decode(),
            "COMMAND_KEY": private["control"] if role == "control" else public["control"],
            "PROJECTION_KEY": public["vault"] if role == "control" else private["vault"],
            "TRUSTED_PROXY": "127.0.0.1",
            "MAIL_PROVIDER": "blocked",
            "MAIL_LIVE_ENABLED": "false",
            "NOTIFICATION_FROM_EMAIL": f"disabled-{role}@noel.invalid",
            "WEB_PROCESSES": "2",
            "WEB_THREADS": "2",
            "PORT": str(PORTS[role][1]),
            "PYTHONUNBUFFERED": "1",
            "PYTHONBREAKPOINT": "0",
        }
        if role == "vault":
            env.update(
                WISHLIST_KEYS=json.dumps({"v1": Fernet.generate_key().decode()}),
                WISHLIST_ACTIVE_KEY="v1",
                DRAW_MASTER_KEYS=json.dumps({"v1": Fernet.generate_key().decode()}),
                DRAW_ACTIVE_KEY="v1",
            )
        admin = {
            "BACKUP_DB_USER": "sweetfamily_admin",
            "BACKUP_DB_PASSWORD": secrets.token_urlsafe(48),
            "BACKUP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "OPERATIONS_KEY": Fernet.generate_key().decode(),
            "OPERATIONS_DIRECTORY": str(BASE / "operations"),
            "PG_BIN": str(PG),
        }
        save(folder / "app.json", env)
        save(folder / "operator.json", admin)
        run(
            [
                ROOT / ".local/tools/uv",
                "venv",
                "--python",
                ROOT / ".local/python/cpython-3.13.11-linux-x86_64-gnu/bin/python3.13",
                folder / "venv",
            ]
        )
        run(
            [
                ROOT / ".local/tools/uv",
                "pip",
                "install",
                "--python",
                python(role),
                "--require-hashes",
                "-r",
                release / "requirements.txt",
            ]
        )
        data = folder / "postgres"
        pw = folder / "init-password"
        try:
            pw.write_text(admin["BACKUP_DB_PASSWORD"])
            pw.chmod(0o600)
            run(
                [
                    PG / "initdb",
                    "-D",
                    data,
                    "-U",
                    "sweetfamily_admin",
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
        sockets = folder / "socket"
        sockets.mkdir(mode=0o700)
        with (data / "postgresql.conf").open("a") as f:
            f.write(
                f"\nlisten_addresses='127.0.0.1'\nport={PORTS[role][0]}\n"
                f"unix_socket_directories='{sockets}'\nssl=on\n"
                f"ssl_cert_file='{folder / 'tls/server.crt'}'\n"
                f"ssl_key_file='{folder / 'tls/server.key'}'\n"
                "ssl_min_protocol_version='TLSv1.2'\nshared_buffers='32MB'\n"
                "max_connections=32\nlog_statement='none'\nlog_min_error_statement='panic'\n"
            )
        (data / "pg_hba.conf").write_text(
            "local all sweetfamily_admin scram-sha-256\n"
            "hostssl all sweetfamily_admin 127.0.0.1/32 scram-sha-256\n"
            f"hostssl {env['DB_NAME']} {env['DB_USER']} 127.0.0.1/32 scram-sha-256\n"
            "host all all 127.0.0.1/32 reject\nhost all all ::1/128 reject\n"
        )
    print("Separate staging credentials, TLS and clusters prepared; no secrets shown")


def provision(role):
    import psycopg
    from psycopg import sql

    env = environment(role, True)
    with psycopg.connect(
        host=env["DB_HOST"],
        port=env["DB_PORT"],
        dbname="postgres",
        user=env["BACKUP_DB_USER"],
        password=env["BACKUP_DB_PASSWORD"],
        sslmode="verify-full",
        sslrootcert=env["PGSSLROOTCERT"],
        autocommit=True,
    ) as db:
        assert (
            Path(db.execute("SHOW data_directory").fetchone()[0]).resolve()
            == (BASE / role / "postgres").resolve()
        )
        if not db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", [env["DB_USER"]]).fetchone():
            db.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(env["DB_USER"]), sql.Literal(env["DB_PASSWORD"]))
            )
        if not db.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", [env["DB_NAME"]]
        ).fetchone():
            db.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(env["DB_NAME"]), sql.Identifier(env["DB_USER"])
                )
            )
        for name in (env["DB_NAME"], "postgres", "template1"):
            db.execute(
                sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name))
            )
        assert db.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[0]
    for command in ("migrate", "bind_environment", "check_runtime"):
        manage(role, command, *(["--noinput"] if command == "migrate" else []))
    manage(role, "check", "--deploy", "--fail-level", "WARNING")
    if not (BASE / "operations" / role).exists():
        manage(role, "operations", "init", operator=True)
    print(f"{role}: fresh staging database bound; verify-full SQL TLS verified")


def units():
    target = Path.home() / ".config/systemd/user"
    target.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        for component in ("db", "web", "worker"):
            name = f"sweetfamily-staging-{role}-{component}.service"
            if component == "db":
                command = f"{PG}/postgres -D {BASE / role / 'postgres'}"
                dependency = ""
                cap = "192M"
            else:
                command = (
                    f"{PYTHON} {ROOT}/scripts/hosted.py run --role {role} --component {component}"
                )
                dependency = (
                    f"Requires=sweetfamily-staging-{role}-db.service\n"
                    f"After=sweetfamily-staging-{role}-db.service\n"
                )
                cap = "384M" if component == "web" else "192M"
            content = (
                f"[Unit]\nDescription=Sweetfamily synthetic staging {role} {component}\n"
                f"{dependency}\n[Service]\nType=simple\nWorkingDirectory={ROOT}\n"
                f"ExecStart={command}\nRestart=on-failure\nRestartSec=3\n"
                "UMask=0077\nNoNewPrivileges=true\nLimitCORE=0\n"
                f"MemoryMax={cap}\nTasksMax=64\nTimeoutStopSec=20\nKillMode=control-group\n"
                "[Install]\nWantedBy=default.target\n"
            )
            path = target / name
            if path.exists() and not path.read_text().startswith("[Unit]\nDescription=Sweetfamily"):
                raise SystemExit("Refusing to replace an unmanaged user unit")
            path.write_text(content)
    run(["systemctl", "--user", "daemon-reload"])
    print("Six project user units installed; no system service modified")


def execute(role, component):
    env = environment(role)
    release = BASE / role / "release"
    args = [str(python(role)), str(release / ("serve.py" if component == "web" else "manage.py"))]
    if component == "worker":
        args.append("worker")
    os.execve(python(role), args, env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["prepare", "units", "provision", "run", "manage", "operator"]
    )
    parser.add_argument("--role", choices=ROLES)
    parser.add_argument("--component", choices=["web", "worker"])
    args, extra = parser.parse_known_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "units":
        units()
    elif not args.role:
        parser.error("--role required")
    elif args.action == "provision":
        provision(args.role)
    elif args.action == "run":
        if not args.component:
            parser.error("--component required")
        execute(args.role, args.component)
    else:
        manage(args.role, *extra, operator=args.action == "operator")


if __name__ == "__main__":
    if Path(sys.prefix).resolve() != PYTHON.parent.parent.resolve():
        raise SystemExit(subprocess.call([str(PYTHON), __file__, *sys.argv[1:]]))
    main()
