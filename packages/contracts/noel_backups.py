"""Native encrypted full snapshots and isolated recovery targets, per service."""

import os
import subprocess
import uuid
from datetime import timedelta
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet
from django.conf import settings
from django.utils import timezone
from noel_operations import journal, model, records, remember_draw, require_maintenance
from psycopg import sql


def program(name):
    return str(Path(os.environ["PG_BIN"]) / (name + (".exe" if os.name == "nt" else "")))


def admin_config():
    db = settings.DATABASES["default"]
    return {
        "host": db["HOST"],
        "port": db["PORT"],
        "dbname": "postgres",
        "user": os.environ["BACKUP_DB_USER"],
        "password": os.environ["BACKUP_DB_PASSWORD"],
        "sslmode": db["OPTIONS"]["sslmode"],
    }


def pg_environment():
    config = admin_config()
    return os.environ | {
        "PGHOST": str(config["host"]),
        "PGPORT": str(config["port"]),
        "PGUSER": config["user"],
        "PGPASSWORD": config["password"],
        "PGSSLMODE": config["sslmode"],
    }


def backup(directory):
    from django.db import transaction

    with transaction.atomic():
        require_maintenance()
        records()
        if settings.SERVICE_ROLE == "vault":
            for draw in model("SealedDraw").objects.all():
                remember_draw(draw)
    dump = subprocess.run(
        [
            program("pg_dump"),
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--dbname",
            settings.DATABASES["default"]["NAME"],
        ],
        env=pg_environment(),
        capture_output=True,
        check=True,
        timeout=120,
    ).stdout
    directory = Path(directory).resolve()
    journal_root, _ = journal()
    if directory == journal_root or directory in journal_root.parents:
        raise ValueError("Keep backups separate from the recovery journal.")
    directory.mkdir(parents=True, exist_ok=True)
    cipher = Fernet(os.environ["BACKUP_ENCRYPTION_KEY"].encode())
    path = directory / (settings.SERVICE_ROLE + "-" + uuid.uuid4().hex + ".pgdump.fernet")
    with path.open("xb") as stream:
        stream.write(cipher.encrypt(dump))
        stream.flush()
        os.fsync(stream.fileno())
    if cipher.decrypt(path.read_bytes()) != dump:
        raise ValueError("Archive verification failed.")
    return path


def restore_isolated(path):
    """Always creates a fresh target; never replaces an existing database."""
    dump = Fernet(os.environ["BACKUP_ENCRYPTION_KEY"].encode()).decrypt(Path(path).read_bytes())
    target = "noel_recovery_" + uuid.uuid4().hex
    with psycopg.connect(**admin_config(), autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(target), sql.Identifier(settings.DATABASES["default"]["USER"])
            )
        )
        try:
            subprocess.run(
                [
                    program("pg_restore"),
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--role",
                    settings.DATABASES["default"]["USER"],
                    "--dbname",
                    target,
                ],
                input=dump,
                env=pg_environment(),
                capture_output=True,
                check=True,
                timeout=120,
            )
        except Exception:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(target)))
            raise
    return target


def expire_backups(directory):
    """Only this role's regular snapshots; never remove journal/key files."""
    root = Path(directory).resolve()
    threshold = (timezone.now() - timedelta(days=30)).timestamp()
    count = 0
    for path in root.glob(settings.SERVICE_ROLE + "-*.pgdump.fernet"):
        if (
            not path.is_symlink()
            and path.resolve().parent == root
            and path.stat().st_mtime <= threshold
        ):
            path.unlink()
            count += 1
    return count
