"""Synthetic PostgreSQL qualification of independently verified email-free access."""

import json
import os
import re
import subprocess
import uuid
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
import tasks
from allauth.account.models import EmailAddress
from allauth.usersessions.models import UserSession
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings
from django.utils import timezone
from noel_contracts import sign
from noel_enrollment_approval import sign_approval
from noel_operations import MaintenanceRequired, enter_maintenance, purge_due, recover, resume
from vault_cases import open_message
from vault_core import access_codes as codes
from vault_core.domain import apply_command
from vault_core.models import (
    AccessCredential,
    EnrollmentClaim,
    EnrollmentVerifier,
    Invitation,
    Membership,
    PendingMail,
    PrivateEvent,
)


@pytest.fixture(autouse=True)
def enabled(tmp_path, monkeypatch):
    with override_settings(WHATSAPP_ENROLLMENT_ENABLED=True):
        directory = tmp_path / "synthetic-verifier"
        subprocess.run(
            [
                str(tasks.PYTHON),
                "scripts/enrollment_verifier.py",
                "init",
                "--directory",
                str(directory),
            ],
            check=True,
            capture_output=True,
        )
        monkeypatch.setenv("NOEL_SYNTHETIC_VERIFIER_KEY", str(directory / "private.json"))
        call_command(
            "enrollment_verifier",
            "grant",
            public_key_file=str(directory / "public.json"),
            stdout=StringIO(),
        )
        yield


def group():
    payload = open_message()["payload"]
    for member in payload["members"]:
        member["email"] = None
    message = sign("open", payload, tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"])
    apply_command(message)
    return PrivateEvent.objects.get(pk=payload["event_id"])


def begin(client, member):
    response = client.post(f"/accounts/enroll/{member.id}/", {"confirm": "on"})
    assert response.status_code == 302, response.content
    return EnrollmentClaim.objects.get(pk=client.session["code_enrollment"]["claim_id"])


def signed_approval(claim, comparison=None):
    identity = json.loads(Path(os.environ["NOEL_SYNTHETIC_VERIFIER_KEY"]).read_text())
    return sign_approval(identity, claim.id, comparison or claim.comparison, settings.PUBLIC_ORIGIN)


def approve(claim):
    path = Path(os.environ["NOEL_SYNTHETIC_VERIFIER_KEY"]).parent / (uuid.uuid4().hex + ".json")
    path.write_text(json.dumps(signed_approval(claim)))
    path.chmod(0o600)
    output = StringIO()
    call_command(
        "approve_enrollment",
        approval_file=str(path),
        stdout=output,
    )
    assert "Approved" in output.getvalue()


def finish(client, claim, remember=False):
    approve(claim)
    response = client.post("/accounts/enrollment/", {"remember": "on"} if remember else {})
    assert response.status_code == 200, response.content
    code = re.search(r"<code>([A-Z2-9-]+)</code>", response.content.decode()).group(1)
    assert len(code.replace("-", "")) == 32
    assert response["Cache-Control"] == "no-store"
    return code


def claimed(remember=False):
    event = group()
    member = event.members.first()
    client = Client()
    code = finish(client, begin(client, member), remember)
    return event, member, client, code


def test_no_email_no_fake_verified_address_or_outbox():
    event = group()
    assert event.members.count() == 4
    assert event.members.filter(identity__email=None).count() == 4
    assert not EmailAddress.objects.exists()
    assert not PendingMail.objects.exists()
    assert all(not m.identity.user.has_usable_password() for m in event.members.all())


def test_public_invitation_and_previews_cannot_claim_or_authenticate():
    event = group()
    member = event.members.first()
    client = Client()
    for _ in range(3):
        assert client.get(f"/accounts/enroll/{member.id}/").status_code == 200
    assert not EnrollmentClaim.objects.exists()
    assert not event.members.filter(claimed_at__isnull=False).exists()
    claim = begin(client, member)
    assert "_auth_user_id" not in client.session
    assert client.get("/api/me/events").status_code == 401
    assert client.post("/accounts/enrollment/", {}).status_code == 409
    claim.refresh_from_db()
    assert claim.approved_at is None and claim.used_at is None


def test_operator_approval_is_not_available_to_web_or_without_private_key(monkeypatch):
    claim = begin(Client(), group().members.first())
    client = Client()
    for path in ("/internal/approve-enrollment", "/accounts/approve-enrollment/"):
        assert client.post(path, {"claim_id": claim.id}).status_code == 404
    with pytest.raises(CommandError):
        call_command("approve_enrollment", approval_file="/missing/approval.json")
    monkeypatch.delenv("OPERATIONS_KEY")
    with pytest.raises(MaintenanceRequired):
        codes.approve(signed_approval(claim))


def test_wrong_person_browser_cannot_consume_approved_request_or_preempt_owner():
    member = group().members.first()
    attacker, owner = Client(), Client()
    bad = begin(attacker, member)
    good = begin(owner, member)
    approve(good)
    with pytest.raises(ValueError):
        codes.activate(good.id, attacker.session["code_enrollment"]["binding"])
    assert attacker.post("/accounts/enrollment/", {}).status_code == 409
    response = owner.post("/accounts/enrollment/", {})
    assert response.status_code == 200
    bad.refresh_from_db()
    assert bad.revoked_at
    assert attacker.get("/api/me/events").status_code == 401
    assert attacker.get("/accounts/enrollment/").status_code == 404
    assert owner.post("/accounts/enrollment/", {}).status_code == 404
    assert owner.get(f"/accounts/enroll/{member.id}/").status_code == 404


@pytest.mark.parametrize("condition", ["expired", "revoked", "inactive", "wrong_comparison"])
def test_independent_approval_rejects_stale_or_incorrect_requests(condition):
    member = group().members.first()
    claim = begin(Client(), member)
    comparison = claim.comparison
    if condition == "expired":
        claim.expires_at = timezone.now() - timedelta(seconds=1)
        claim.save()
    elif condition == "revoked":
        Invitation.objects.filter(pk=claim.invitation_id).update(revoked_at=timezone.now())
    elif condition == "inactive":
        Membership.objects.filter(pk=member.id).update(active=False)
    else:
        comparison = "WRONG"
    with pytest.raises(ValueError):
        codes.approve(signed_approval(claim, comparison))
    assert not AccessCredential.objects.exists()


def test_only_owner_sees_code_once_and_other_accounts_remain_private():
    event, member, client, code = claimed()
    assert "code_enrollment" not in client.session
    assert code not in json.dumps(dict(client.session))
    credential = AccessCredential.objects.get(identity=member.identity)
    assert credential.digest == codes.code_digest(code)
    assert code not in credential.digest
    assert UserSession.objects.filter(user=member.identity.user).count() == 1
    for row in Session.objects.all():
        assert code not in row.session_data
    for path in ("/", "/accounts/personal-access/", "/accounts/sessions/"):
        response = client.get(path)
        assert response.status_code == 200, response.content
        assert code not in response.content.decode()
    assert client.get("/accounts/email/").status_code == 404
    assert client.get("/api/me/events").status_code == 200
    stranger = event.members.exclude(pk=member.id).first()
    assert client.get(f"/api/me/profile?event_id={uuid.uuid4()}").status_code == 404
    assert stranger.claimed_at is None


@pytest.mark.parametrize("remember", [True, False])
def test_saved_code_returns_to_same_account_with_explicit_session_lifetime(remember):
    _, member, _, code = claimed()
    client = Client()
    response = client.post(
        "/accounts/personal-code/",
        {
            "code": code.lower(),
            **({"remember": "on"} if remember else {}),
        },
    )
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(member.identity.user_id)
    assert client.session.get_expire_at_browser_close() is not remember
    assert bool(response.cookies["noel_vault_session"]["max-age"]) is remember
    assert client.get("/api/me/events").status_code == 200


def test_rotation_requires_old_code_and_revokes_other_sessions_and_old_code():
    _, _, owner, old_code = claimed()
    other = Client()
    assert other.post("/accounts/personal-code/", {"code": old_code}).status_code == 302
    assert owner.post("/accounts/personal-access/", {"code": "wrong"}).status_code == 400
    response = owner.post("/accounts/personal-access/", {"code": old_code})
    assert response.status_code == 200
    new_code = re.search(r"<code>([A-Z2-9-]+)</code>", response.content.decode()).group(1)
    assert new_code != old_code
    assert other.get("/api/me/events").status_code == 401
    assert Client().post("/accounts/personal-code/", {"code": old_code}).status_code == 400
    assert Client().post("/accounts/personal-code/", {"code": new_code}).status_code == 302
    assert owner.get("/api/me/events").status_code == 200


def test_brute_force_rate_limit_and_csrf():
    client = Client()
    statuses = [
        client.post("/accounts/personal-code/", {"code": "WRONG"}).status_code for _ in range(12)
    ]
    assert 429 in statuses
    strict = Client(enforce_csrf_checks=True)
    assert strict.post("/accounts/personal-code/", {"code": "WRONG"}).status_code == 403


def test_feature_disabled_fails_closed_even_with_previously_remembered_session():
    _, member, client, code = claimed()
    with override_settings(WHATSAPP_ENROLLMENT_ENABLED=False):
        assert client.get("/api/me/events").status_code == 401
        assert Client().post("/accounts/personal-code/", {"code": code}).status_code == 404
        assert Client().get(f"/accounts/enroll/{member.id}/").status_code == 404


def test_restore_revokes_codes_and_claims_but_routine_verification_preserves_them():
    event, member, client, code = claimed()
    pending = begin(Client(), event.members.exclude(pk=member.id).first())
    approve(pending)
    enter_maintenance()
    recover(restored=False)
    resume()
    assert client.get("/api/me/events").status_code == 200
    enter_maintenance()
    recover(restored=True)
    resume()
    assert not AccessCredential.objects.filter(enabled=True).exists()
    assert client.get("/api/me/events").status_code == 401
    assert Client().post("/accounts/personal-code/", {"code": code}).status_code == 400
    pending.refresh_from_db()
    assert pending.revoked_at
    assert not EnrollmentVerifier.objects.filter(enabled=True).exists()
    public_path = Path(os.environ["NOEL_SYNTHETIC_VERIFIER_KEY"]).with_name("public.json")
    call_command(
        "enrollment_verifier", "grant", public_key_file=str(public_path), stdout=StringIO()
    )
    # Fresh independent recovery keeps the same user/membership; never a new draw.
    codes.recovery_invitation(member.id)
    replacement = Client()
    new_code = finish(replacement, begin(replacement, member))
    assert new_code != code
    assert replacement.session["_auth_user_id"] == str(member.identity.user_id)


def test_retention_purges_credentials_claims_and_email_free_accounts():
    event, member, _, _ = claimed()
    actor_id = member.identity.user_id
    event.celebration_at = timezone.now() - timedelta(days=91)
    event.save()
    enter_maintenance()
    purge_due()
    from django.contrib.auth import get_user_model

    assert not AccessCredential.objects.exists()
    assert not EnrollmentClaim.objects.exists()
    assert not get_user_model().objects.filter(pk=actor_id).exists()


def test_unappointed_or_revoked_verifier_and_organizer_key_cannot_approve():
    from cryptography.exceptions import InvalidSignature

    claim = begin(Client(), group().members.first())
    verifier = EnrollmentVerifier.objects.get()
    impostor = {
        "id": str(verifier.id),
        "private_key": tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"],
    }
    forged = sign_approval(impostor, claim.id, claim.comparison, settings.PUBLIC_ORIGIN)
    with pytest.raises(InvalidSignature):
        codes.approve(forged)
    verifier.enabled = False
    verifier.save()
    with pytest.raises(EnrollmentVerifier.DoesNotExist):
        codes.approve(signed_approval(claim))
    verifier.delete()
    with pytest.raises(EnrollmentVerifier.DoesNotExist):
        codes.approve(signed_approval(claim))
    assert not AccessCredential.objects.exists()


def test_staging_enrollment_with_secure_sessions_and_email_blocked():
    class SecureClient(Client):
        def post(self, *args, **kwargs):
            return super().post(*args, **kwargs, secure=True)

        def get(self, *args, **kwargs):
            return super().get(*args, **kwargs, secure=True)

    with override_settings(
        APP_ENV="staging",
        MAIL_PROVIDER="blocked",
        MAIL_LIVE_ENABLED=False,
        SESSION_COOKIE_SECURE=True,
        CSRF_COOKIE_SECURE=True,
        SECURE_SSL_REDIRECT=True,
        PUBLIC_ORIGIN="https://vault.example.invalid",
    ):
        member = group().members.first()
        client = SecureClient()
        code = finish(client, begin(client, member), remember=True)
        assert client.cookies["noel_vault_session"]["secure"]
        assert client.get("/api/me/events").status_code == 200
        other = SecureClient()
        assert other.post("/accounts/personal-code/", {"code": code}).status_code == 302
        assert not PendingMail.objects.filter(event=member.event).exists()


def test_code_members_follow_manifest_consent_and_sealed_durability_gates():
    from draw_cases import command
    from vault_core.draw_crypto import unseal
    from vault_core.draw_service import consent, run_one_draw
    from vault_core.durability import release
    from vault_core.models import DrawNotification, SealedDraw
    from vault_core.wishlists import save_list
    from wishlist_cases import items

    event = group()
    clients = []
    for member in event.members.all():
        client = Client()
        finish(client, begin(client, member))
        save_list(member, 0, items(), validate=True)
        clients.append(client)
    apply_command(command(event, "freeze"))
    event.refresh_from_db()
    for member in event.members.all():
        consent(member, event.manifest_version, event.manifest_digest)
    apply_command(command(event, "draw"))
    assert run_one_draw()
    draw = SealedDraw.objects.get(event=event)
    permutation = unseal(draw)["permutation"]
    assert DrawNotification.objects.filter(draw=draw, state="HELD", mail=None).count() == 4
    assert not PendingMail.objects.filter(event=event).exists()
    assert (
        clients[0]
        .post(
            "/api/me/recipient/reveal?event_id=" + str(event.id),
            {},
            content_type="application/json",
        )
        .status_code
        == 409
    )
    # Only this test's operator fixture supplies a receipt; real release still
    # requires confirm_draw_durability's physical backup/restore proof.
    release(draw.id, {"sealed_id": str(draw.id), "fixture": True})
    assert DrawNotification.objects.filter(draw=draw, state="IN_APP", mail=None).count() == 4
    assert unseal(SealedDraw.objects.get(pk=draw.id))["permutation"] == permutation
    assert not PendingMail.objects.filter(event=event).exists()

    assert (
        clients[0]
        .post(
            "/api/me/recipient/reveal?event_id=" + str(event.id),
            {},
            content_type="application/json",
        )
        .status_code
        == 200
    )


def test_verifier_revocation_blocks_approval_not_yet_activated():
    client = Client()
    claim = begin(client, group().members.first())
    approve(claim)
    verifier = EnrollmentVerifier.objects.get(pk=signed_approval(claim)["verifier_id"])
    call_command("enrollment_verifier", "revoke", verifier_id=str(verifier.id), stdout=StringIO())
    assert client.post("/accounts/enrollment/", {}).status_code == 409
    assert not AccessCredential.objects.exists()


@pytest.mark.concurrent_db
def test_two_concurrent_activations_issue_exactly_one_credential():
    from concurrent.futures import ThreadPoolExecutor

    from django.contrib.auth import get_user_model
    from django.db import close_old_connections
    from vault_core.models import VerifiedIdentity

    event = group()
    members = list(event.members.select_related("identity"))
    client = Client()
    claim = begin(client, members[0])
    approve(claim)
    binding = client.session["code_enrollment"]["binding"]

    def attempt():
        close_old_connections()
        try:
            codes.activate(claim.id, binding)
            return "activated"
        except ValueError:
            return "refused"
        finally:
            close_old_connections()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: attempt(), range(2))) == ["activated", "refused"]
        assert AccessCredential.objects.filter(identity=members[0].identity).count() == 1
    finally:
        PrivateEvent.objects.filter(pk=event.id).delete()
        VerifiedIdentity.objects.filter(pk__in=[m.identity_id for m in members]).delete()
        get_user_model().objects.filter(pk__in=[m.identity.user_id for m in members]).delete()
        EnrollmentVerifier.objects.all().delete()


@pytest.mark.concurrent_db
def test_native_old_backup_cannot_revive_rotated_code_or_verifier(tmp_path, monkeypatch):
    import psycopg
    from noel_backups import admin_config, backup, restore_isolated
    from psycopg import sql
    from vault_core.models import VerifiedIdentity

    values = tasks.config()
    for name, value in {
        "BACKUP_ENCRYPTION_KEY": values["VAULT_BACKUP_KEY"],
        "BACKUP_DB_USER": "noel_admin",
        "BACKUP_DB_PASSWORD": values["VAULT_DB_ADMIN_PASSWORD"],
        "PG_BIN": str(tasks.postgres_bin()),
    }.items():
        monkeypatch.setenv(name, value)
    event, member, _, old_code = claimed()
    identities = list(event.members.values_list("identity_id", flat=True))
    users = list(event.members.values_list("identity__user_id", flat=True))
    target = None
    try:
        enter_maintenance()
        archive = backup(tmp_path / "snapshots")
        recover(restored=False)
        resume()
        codes.rotate(member.identity.user, old_code)
        target = restore_isolated(archive)
        code = """
import django
django.setup()
from django.test import Client, override_settings
from noel_operations import enter_maintenance, recover, resume
from vault_core.models import AccessCredential, EnrollmentVerifier
assert AccessCredential.objects.filter(enabled=True).exists()
assert EnrollmentVerifier.objects.filter(enabled=True).exists()
assert Client().get('/').status_code == 503
enter_maintenance()
recover(restored=True)
assert not AccessCredential.objects.filter(enabled=True).exists()
assert not EnrollmentVerifier.objects.filter(enabled=True).exists()
resume()
with override_settings(FORCE_MAINTENANCE=False):
    assert Client().get('/health/ready').status_code == 200
print('RESTORED_CODE_AND_VERIFIER_REVOKED_PASS')
"""
        result = subprocess.run(
            [str(tasks.PYTHON), "-c", code],
            capture_output=True,
            text=True,
            timeout=90,
            env=os.environ
            | {
                "DB_NAME": target,
                "FORCE_MAINTENANCE": "true",
                "WHATSAPP_ENROLLMENT_ENABLED": "true",
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "RESTORED_CODE_AND_VERIFIER_REVOKED_PASS" in result.stdout
    finally:
        if target:
            with psycopg.connect(**admin_config(), autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(target))
                )
        PrivateEvent.objects.filter(pk=event.id).delete()
        VerifiedIdentity.objects.filter(pk__in=identities).delete()
        from django.contrib.auth import get_user_model

        get_user_model().objects.filter(pk__in=users).delete()
        EnrollmentVerifier.objects.all().delete()
        from vault_core.models import OperationsState

        OperationsState.objects.all().delete()
