"""Native operator-only encrypted backup and isolated restore before release."""

import hashlib
import os
import secrets
import subprocess
import uuid
from datetime import timedelta
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from psycopg import sql

from .draw_service import StateConflict, bump
from .models import DrawNotification, PrivateEvent, SealedDraw


def pg_program(name):
    root = Path(os.environ["PG_BIN"])
    return str(root / (name + (".exe" if os.name == "nt" else "")))


def operator_connection():
    db = settings.DATABASES["default"]
    return {
        "host": db["HOST"],
        "port": db["PORT"],
        "dbname": db["NAME"],
        "user": os.environ["BACKUP_DB_USER"],
        "password": os.environ["BACKUP_DB_PASSWORD"],
        "sslmode": db["OPTIONS"]["sslmode"],
    }


def backup_and_verify(event_id, directory):
    record = SealedDraw.objects.select_related("event", "job").get(event_id=event_id)
    if record.event.state != "DRAWN":
        raise StateConflict("Seul un tirage scellé actif peut être sauvegardé.")
    if record.release_state == "AVAILABLE":
        return record.backup_receipt
    key = Fernet(os.environ["BACKUP_ENCRYPTION_KEY"].encode())
    connection = operator_connection()
    env = os.environ.copy()
    env.update(
        PGHOST=str(connection["host"]),
        PGPORT=str(connection["port"]),
        PGDATABASE=connection["dbname"],
        PGUSER=connection["user"],
        PGPASSWORD=connection["password"],
        PGSSLMODE=connection["sslmode"],
    )
    dump = subprocess.run(
        [pg_program("pg_dump"), "--format=custom", "--no-owner", "--no-acl"],
        env=env,
        capture_output=True,
        check=True,
        timeout=120,
    ).stdout
    encrypted = key.encrypt(dump)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("vault-" + str(record.id) + "-" + secrets.token_hex(8) + ".pgdump.fernet")
    with path.open("xb") as stream:
        stream.write(encrypted)
        stream.flush()
        os.fsync(stream.fileno())
    reread = path.read_bytes()
    if reread != encrypted or key.decrypt(reread) != dump:
        raise StateConflict("Vérification de la sauvegarde impossible.")
    restored = "noel_restore_" + uuid.uuid4().hex
    with psycopg.connect(**(connection | {"dbname": "postgres"}), autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(restored))
        )
        try:
            subprocess.run(
                [
                    pg_program("pg_restore"),
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    restored,
                ],
                input=key.decrypt(reread),
                env=env,
                capture_output=True,
                check=True,
                timeout=120,
            )
            with psycopg.connect(**(connection | {"dbname": restored})) as restored_db:
                row = restored_db.execute(
                    "SELECT s.id,s.ciphertext,s.wrapped_key,s.nonce,s.wrap_nonce,s.key_id,"
                    "j.state,j.snapshot_digest,e.manifest_digest,"
                    "s.manifest_version,s.schema_version, "
                    "j.snapshot,e.frozen_manifest FROM vault_core_sealeddraw s "
                    "JOIN vault_core_drawjob j ON j.id=s.job_id "
                    "JOIN vault_core_privateevent e ON e.id=s.event_id WHERE s.event_id=%s",
                    [event_id],
                ).fetchone()
                expected = (
                    record.id,
                    bytes(record.ciphertext),
                    bytes(record.wrapped_key),
                    bytes(record.nonce),
                    bytes(record.wrap_nonce),
                    record.key_id,
                    "SEALED",
                    record.job.snapshot_digest,
                    record.event.manifest_digest,
                    record.manifest_version,
                    record.schema_version,
                    record.job.snapshot,
                    record.event.frozen_manifest,
                )
                if row != expected:
                    raise StateConflict("La restauration ne contient pas le tirage attendu.")
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(restored)))
    receipt = {
        "schema": 1,
        "sealed_id": str(record.id),
        "archive": str(path),
        "sha256": hashlib.sha256(reread).hexdigest(),
        "bytes": len(reread),
        "restored_at": timezone.now().isoformat(),
    }
    from noel_operations import remember_draw

    # Persist outside the database before a result can become available.
    remember_draw(record)
    release(record.id, receipt)
    return receipt


@transaction.atomic
def release(record_id, receipt):
    # Only called after the native backup/restore proof; no HTTP or worker bypass.

    initial = SealedDraw.objects.get(pk=record_id)
    event = PrivateEvent.objects.select_for_update().get(pk=initial.event_id)
    record = SealedDraw.objects.select_for_update().get(pk=record_id)
    if event.state != "DRAWN" or receipt.get("sealed_id") != str(record.id):
        raise StateConflict("Le tirage a été annulé ou remplacé.")
    if record.release_state == "AVAILABLE":
        return
    record.release_state = "AVAILABLE"
    record.backup_receipt = receipt
    record.save(update_fields=["release_state", "backup_receipt"])
    for notification in DrawNotification.objects.filter(draw=record, state="HELD").select_related(
        "member__identity"
    ):
        member = notification.member
        if notification.mail_id:
            mail = notification.mail
            mail.state = "QUEUED"
            mail.expires_at = timezone.now() + timedelta(days=7)
            mail.save(update_fields=["state", "expires_at"])
        else:
            from .notifications import enqueue

            mail = enqueue(member, "DRAW_READY", record.manifest_version)
        notification.mail = mail
        notification.state = "QUEUED" if mail else "IN_APP"
        notification.save(update_fields=["mail", "state"])
    bump(event)
