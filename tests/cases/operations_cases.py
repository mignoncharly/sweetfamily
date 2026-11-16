"""Phase 10: real PostgreSQL restoration; never uses family data or live mail."""

import os
import subprocess
import uuid
from datetime import timedelta

import psycopg
import pytest
import tasks
from django.conf import settings
from django.db import transaction
from django.test import Client
from django.utils import timezone
from noel_operations import (
    MaintenanceRequired,
    append_record,
    enter_maintenance,
    event_model,
    model,
    purge_due,
    recover,
    resume,
)
from psycopg import sql


def new_event():
    if settings.SERVICE_ROLE == "vault":
        from vault_cases import open_message
        from vault_core.domain import apply_command

        message = open_message()
        apply_command(message)
        return event_model().objects.get(pk=message["payload"]["event_id"])
    from helpers import user

    owner = model("Organizer").objects.create(user=user(str(uuid.uuid4()) + "@example.invalid"))
    return event_model().objects.create(
        owner=owner,
        title="Synthétique",
        celebration_at=timezone.now() + timedelta(days=30),
        wishlist_deadline=timezone.now() + timedelta(days=10),
        handover="À apporter.",
    )


def test_maintenance_blocks_http_readiness_and_requires_verified_recovery():
    enter_maintenance()
    assert Client().get("/health/live").status_code == 200
    assert Client().get("/health/ready").status_code == 503
    assert Client().get("/").status_code == 503
    assert Client().post("/api/events").status_code == 503
    with pytest.raises(MaintenanceRequired):
        resume()
    recover()
    resume()
    assert Client().get("/health/ready").status_code == 200


def test_deletion_journal_survives_database_rollback_and_prevents_recreation():
    event = new_event()
    event.celebration_at = timezone.now() - timedelta(days=91)
    event.save()
    enter_maintenance()
    with pytest.raises(RuntimeError), transaction.atomic():
        assert purge_due() == 1
        raise RuntimeError("crash after external record, before SQL commit")
    assert event_model().objects.filter(pk=event.id).exists()
    assert purge_due() == 1  # retry directly after the interrupted transaction
    recover()
    assert not event_model().objects.filter(pk=event.id).exists()
    assert model("DeletionTombstone").objects.filter(event_id=event.id).exists()
    assert purge_due() == 0
    recover()
    resume()
    if settings.SERVICE_ROLE == "vault":
        from noel_contracts import sign
        from vault_cases import open_message
        from vault_core.domain import apply_command

        payload = open_message()["payload"]
        payload["event_id"] = str(event.id)
        with pytest.raises(ValueError, match="supprimé"):
            apply_command(sign("open", payload, tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"]))


def test_missing_or_corrupt_journal_cannot_resume(monkeypatch):
    enter_maintenance()
    monkeypatch.setenv("OPERATIONS_KEY", "invalid")
    with pytest.raises(ValueError):
        recover()
    assert not model("OperationsState").objects.get(pk=1).recovery_verified


def test_routine_verification_preserves_current_outbox_but_restore_holds_it():
    event = new_event()
    mail = model("PendingMail" if settings.SERVICE_ROLE == "vault" else "AuthMail")
    if settings.SERVICE_ROLE == "control":
        mail.objects.create(payload="synthetic", expires_at=timezone.now() + timedelta(days=1))
    enter_maintenance()
    recover(restored=False)
    assert mail.objects.filter(state="QUEUED").exists()
    recover()
    assert not mail.objects.filter(state="QUEUED").exists()
    assert mail.objects.filter(state="DELIVERY_UNKNOWN").exists()
    assert event_model().objects.filter(pk=event.pk).exists()


def test_unavailable_draw_master_key_prevents_reopening():
    if settings.SERVICE_ROLE != "vault":
        return
    from django.test import override_settings
    from draw_cases import start
    from vault_core.draw_service import run_one_draw

    start()
    run_one_draw()
    enter_maintenance()
    with override_settings(DRAW_MASTER_KEYS={}), pytest.raises(KeyError):
        recover()
    with pytest.raises(MaintenanceRequired):
        resume()


def test_unavailable_authentication_key_prevents_reopening():
    from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret
    from cryptography.fernet import Fernet, InvalidToken
    from django.test import override_settings
    from helpers import user

    TOTP.activate(user("key-check@example.invalid"), generate_totp_secret())
    enter_maintenance()
    with (
        override_settings(AUTH_DATA_KEY=Fernet.generate_key().decode()),
        pytest.raises(InvalidToken),
    ):
        recover()
    with pytest.raises(MaintenanceRequired):
        resume()


def test_missing_previously_sealed_draw_blocks_reopening():
    if settings.SERVICE_ROLE != "vault":
        return
    append_record(
        "sealed-missing",
        {
            "kind": "sealed",
            "event_id": str(uuid.uuid4()),
            "sealed_id": str(uuid.uuid4()),
            "fingerprint": "0" * 64,
        },
    )
    enter_maintenance()
    with pytest.raises(MaintenanceRequired, match="missing"):
        recover()
    with pytest.raises(MaintenanceRequired):
        resume()


def test_backup_expiration_is_role_scoped_and_preserves_recent_and_journal_files(tmp_path):
    from noel_backups import expire_backups

    old = tmp_path / (settings.SERVICE_ROLE + "-old.pgdump.fernet")
    recent = tmp_path / (settings.SERVICE_ROLE + "-recent.pgdump.fernet")
    other = tmp_path / ("vault" if settings.SERVICE_ROLE == "control" else "control")
    other = other.with_name(other.name + "-old.pgdump.fernet")
    anchor = tmp_path / "anchor.fernet"
    for path in (old, recent, other, anchor):
        path.write_bytes(b"synthetic")
    past = (timezone.now() - timedelta(days=31)).timestamp()
    for path in (old, other, anchor):
        os.utime(path, (past, past))
    assert expire_backups(tmp_path) == 1
    assert not old.exists() and recent.exists() and other.exists() and anchor.exists()


def test_requested_account_deletion_is_replayed_and_active_membership_is_protected():
    from django.contrib.auth import get_user_model
    from helpers import user
    from noel_operations import delete_account

    actor = user("erase-request@example.invalid")
    enter_maintenance()
    delete_account(actor.pk)
    assert not get_user_model().objects.filter(pk=actor.pk).exists()
    recover()
    assert not get_user_model().objects.filter(pk=actor.pk).exists()
    resume()
    event = new_event()
    if settings.SERVICE_ROLE == "vault":
        actor = event.members.first().identity.user
    else:
        actor = event.owner.user
    enter_maintenance()
    with pytest.raises(MaintenanceRequired):
        delete_account(actor.pk)


def test_retained_verified_account_can_join_next_year_without_duplicate_identity():
    if settings.SERVICE_ROLE != "vault":
        return
    from allauth.account.models import EmailAddress
    from django.contrib.auth import get_user_model
    from noel_contracts import sign
    from vault_cases import claim, open_message
    from vault_core.domain import apply_command

    event = new_event()
    member = event.members.first()
    claim(member)
    actor_id, email = member.identity.user_id, member.identity.email
    event.celebration_at = timezone.now() - timedelta(days=91)
    event.save()
    enter_maintenance()
    purge_due()
    recover(restored=False)
    resume()
    assert get_user_model().objects.filter(pk=actor_id).exists()
    assert not model("VerifiedIdentity").objects.filter(user_id=actor_id).exists()
    payload = open_message()["payload"]
    payload["members"][0]["email"] = email
    # All other proposals use new emails: only this verified returning account is reused.
    for index, proposal in enumerate(payload["members"][1:], 1):
        proposal["email"] = f"annual-{index}@example.invalid"
    apply_command(sign("open", payload, tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"]))
    member = model("Membership").objects.get(event_id=payload["event_id"], identity__email=email)
    assert member.identity.user_id == actor_id
    assert EmailAddress.objects.filter(email=email, verified=True).count() == 1
    claim(member)
    member.refresh_from_db()
    assert member.claimed_at is not None


@pytest.mark.concurrent_db
def test_native_restore_repurges_deleted_event_preserves_sealed_draw_and_holds_mail(
    tmp_path, monkeypatch
):
    from helpers import user
    from noel_backups import admin_config, backup, restore_isolated
    from noel_operations import delete_account, draw_fingerprint

    values = tasks.config()
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", values["VAULT_BACKUP_KEY"])
    monkeypatch.setenv("BACKUP_DB_USER", "noel_admin")
    monkeypatch.setenv(
        "BACKUP_DB_PASSWORD", values[settings.SERVICE_ROLE.upper() + "_DB_ADMIN_PASSWORD"]
    )
    monkeypatch.setenv("PG_BIN", str(tasks.postgres_bin()))
    doomed = new_event()
    orphan = user("native-erasure@example.invalid")
    live = None
    target = None
    try:
        if settings.SERVICE_ROLE == "vault":
            from draw_cases import start
            from vault_core.draw_service import run_one_draw

            live = start()
            assert run_one_draw()
            fingerprint = draw_fingerprint(model("SealedDraw").objects.get(event=live))
        else:
            live = new_event()
            fingerprint = ""
            model("AuthMail").objects.create(
                payload="synthetic", expires_at=timezone.now() + timedelta(days=1)
            )
        enter_maintenance()
        from allauth.mfa.totp.internal.auth import TOTP, generate_totp_secret

        actor = (
            live.members.first().identity.user
            if settings.SERVICE_ROLE == "vault"
            else live.owner.user
        )
        TOTP.activate(actor, generate_totp_secret())
        archive = backup(tmp_path / "snapshots")
        delete_account(orphan.pk)
        # Backup still contains a future event. Delete it LATER in the source database.
        doomed.celebration_at = timezone.now() - timedelta(days=91)
        doomed.save()
        assert purge_due() == 1
        target = restore_isolated(archive)
        env = dict(
            os.environ,
            DB_NAME=target,
            FORCE_MAINTENANCE="true",
            DOOMED_ID=str(doomed.id),
            LIVE_ID=str(live.id),
            EXPECTED_DRAW=fingerprint,
            ERASED_USER_ID=str(orphan.pk),
        )
        code = """
import os, django
django.setup()
from django.test import Client, override_settings
from noel_operations import enter_maintenance, recover, resume, event_model, model, draw_fingerprint
from django.conf import settings
from django.contrib.auth import get_user_model
assert Client().get('/').status_code == 503
assert event_model().objects.filter(pk=os.environ['DOOMED_ID']).exists()
enter_maintenance()
recover()
assert not event_model().objects.filter(pk=os.environ['DOOMED_ID']).exists()
assert not get_user_model().objects.filter(pk=os.environ['ERASED_USER_ID']).exists()
assert event_model().objects.filter(pk=os.environ['LIVE_ID']).exists()
mail = model('PendingMail' if settings.SERVICE_ROLE == 'vault' else 'AuthMail')
assert not mail.objects.filter(state__in=['QUEUED','RUNNING','HELD']).exists()
assert mail.objects.filter(state='DELIVERY_UNKNOWN').exists()
if settings.SERVICE_ROLE == 'vault':
    from vault_core.domain import deliver_one
else:
    from control_core.mail import deliver_one
assert not deliver_one()  # no automatic submission of the restored queue
if settings.SERVICE_ROLE == 'vault':
    draw = model('SealedDraw').objects.get(event_id=os.environ['LIVE_ID'])
    assert draw_fingerprint(draw) == os.environ['EXPECTED_DRAW']
    assert model('DrawJob').objects.get(event_id=os.environ['LIVE_ID']).state == 'SEALED'
recover()  # repeat is safe
resume()
with override_settings(FORCE_MAINTENANCE=False):
    assert Client().get('/health/ready').status_code == 200
print('RESTORE_REPURGE_AND_REPLAY_PASS')
"""
        result = subprocess.run(
            [str(tasks.PYTHON), "-c", code],
            env=env,
            cwd=tasks.ROOT,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "RESTORE_REPURGE_AND_REPLAY_PASS" in result.stdout
    finally:
        if target:
            with psycopg.connect(**admin_config(), autocommit=True) as admin:
                assert target.startswith("noel_recovery_")
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(target))
                )
        if settings.SERVICE_ROLE == "vault":
            model("SealedDraw").objects.all().delete()
        event_model().objects.all().delete()
        model("OperationsState").objects.all().delete()
        model("DeletionTombstone").objects.all().delete()
