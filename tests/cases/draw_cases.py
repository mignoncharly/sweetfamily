import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

import pytest
import tasks
from cryptography.exceptions import InvalidTag
from django.db import close_old_connections
from django.test import Client
from django.utils import timezone
from noel_contracts import sign
from vault_cases import claim, open_message, prepare
from vault_core.domain import apply_command
from vault_core.draw_crypto import unseal
from vault_core.draw_engine import InvalidRules, sample, validate_result
from vault_core.draw_service import (
    StateConflict,
    acquire_job,
    commit_result,
    consent,
    fail_job,
    reopen_failed,
    run_one_draw,
    withdraw,
)
from vault_core.models import (
    DrawJob,
    DrawNotification,
    PrivateEvent,
    RosterConsent,
    SealedDraw,
)
from vault_core.wishlists import save_list
from wishlist_cases import items


def command(event_obj, kind, **extra):
    event_obj.refresh_from_db()
    return sign(
        kind,
        {"event_id": str(event_obj.id), "version": event_obj.version, **extra},
        tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"],
    )


def group(freeze=True, ready=True):
    message = open_message()
    apply_command(message)
    event = PrivateEvent.objects.get(pk=message["payload"]["event_id"])
    for member in event.members.all():
        claim(member)
        save_list(member, 0, items(), validate=True)
    if freeze:
        apply_command(command(event, "freeze"))
    if freeze and ready:
        event.refresh_from_db()
        for member in event.members.all():
            consent(member, event.manifest_version, event.manifest_digest)
    event.refresh_from_db()
    return event


def start():
    event = group()
    apply_command(command(event, "draw"))
    event.refresh_from_db()
    return event


def result_for(lease):
    value = lease[2]
    return sample([m["id"] for m in value["members"]], value["exclusions"])


def test_manifest_complete_public_and_every_person_must_accept_exact_version():
    event = group(ready=False)
    assert event.state == "CONFIRMING"
    assert set(event.frozen_manifest) == {"event_id", "version", "event", "members", "exclusions"}
    assert "email" not in str(event.frozen_manifest) and "Canari" not in str(event.frozen_manifest)
    member = event.members.first()
    client = Client()
    client.force_login(member.identity.user)
    response = client.get(f"/api/me/roster?event_id={event.id}")
    assert response.status_code == 200, response.content
    assert len(response.json()["manifest"]["members"]) == 4
    assert client.get(f"/rules?event_id={event.id}").status_code == 200
    with pytest.raises(StateConflict):
        consent(member, event.manifest_version, "0" * 64)
    with pytest.raises(StateConflict):
        consent(member, True, event.manifest_digest)
    for member in event.members.all():
        consent(member, event.manifest_version, event.manifest_digest)
    event.refresh_from_db()
    assert event.state == "READY"
    assert RosterConsent.objects.filter(member__event=event).count() == 4


def test_rule_changes_invalidate_all_consents_and_never_reuse_manifest_version():
    event = group()
    old = event.manifest_version
    apply_command(command(event, "exclusions", exclusions=[]))
    event.refresh_from_db()
    assert event.state == "OPEN" and event.frozen_manifest is None
    assert not RosterConsent.objects.filter(member__event=event).exists()
    apply_command(command(event, "freeze"))
    event.refresh_from_db()
    assert event.manifest_version == old + 1
    with pytest.raises(StateConflict):
        consent(event.members.first(), old, event.manifest_digest)


def test_incomplete_lists_and_privacy_violating_exclusions_cannot_freeze():
    _, member = prepare()
    with pytest.raises(StateConflict):
        apply_command(command(member.event, "freeze"))
    event = group(freeze=False)
    ids = [str(m.id) for m in event.members.order_by("id")]
    apply_command(command(event, "exclusions", exclusions=[[ids[0], ids[2]], [ids[0], ids[3]]]))
    with pytest.raises(InvalidRules):
        apply_command(command(event, "freeze"))
    assert not DrawJob.objects.exists() and not SealedDraw.objects.exists()


def test_single_job_encrypted_atomic_seal_and_held_notifications():
    event = start()
    assert run_one_draw()
    event.refresh_from_db()
    record = SealedDraw.objects.get(event=event)
    assert event.state == "DRAWN" and record.release_state == "PENDING_DURABILITY"
    assert record.job.state == "SEALED" and not run_one_draw()
    value = unseal(record)
    validate_result([str(m.id) for m in event.members.all()], [], value["permutation"])
    assert bytes(record.ciphertext) != str(value).encode()
    assert (
        DrawNotification.objects.filter(draw=record, state="HELD", mail__state="HELD").count() == 4
    )
    apply_command(command(event, "draw"))
    assert (
        SealedDraw.objects.filter(event=event).count()
        == DrawJob.objects.filter(event=event).count()
        == 1
    )
    record.ciphertext = bytes(record.ciphertext)[:-1] + bytes([record.ciphertext[-1] ^ 1])
    with pytest.raises(InvalidTag):
        unseal(record)
    client = Client()
    client.force_login(event.members.first().identity.user)
    page = client.get(f"/rules?event_id={event.id}")
    assert "Finalisation du tirage" in page.content.decode()
    assert client.get(f"/api/me/roster?event_id={event.id}").status_code == 409


def test_stale_lease_cannot_seal_and_attempts_increase():
    event = start()
    first = acquire_job()
    assert acquire_job() is None
    DrawJob.objects.filter(event=event).update(lease_until=timezone.now() - timedelta(seconds=1))
    second = acquire_job()
    assert second[1] > first[1]
    with pytest.raises(StateConflict):
        commit_result(first[0], first[1], first[3], result_for(first))
    commit_result(second[0], second[1], second[3], result_for(second))
    assert SealedDraw.objects.filter(event=event).count() == 1


def test_atomic_failure_never_leaves_partial_result_or_outbox():
    event = start()
    with patch("vault_core.draw_service.DrawNotification.objects.create", side_effect=RuntimeError):
        assert run_one_draw()
    assert not SealedDraw.objects.exists() and not DrawNotification.objects.exists()
    job = DrawJob.objects.get(event=event)
    assert job.state == "FAILED_RETRYABLE"
    DrawJob.objects.filter(pk=job.id).update(next_attempt_at=timezone.now())
    assert run_one_draw()
    assert SealedDraw.objects.get(event=event).job.attempt == 2


def test_retry_after_commit_does_not_reroll_even_if_worker_loses_reply():
    event = start()
    original = commit_result

    def lost_reply(*args):
        original(*args)
        raise ConnectionError()

    with patch("vault_core.draw_service.commit_result", side_effect=lost_reply):
        assert run_one_draw()
    record = SealedDraw.objects.get(event=event)
    before = bytes(record.ciphertext)
    assert not run_one_draw()
    record.refresh_from_db()
    assert bytes(record.ciphertext) == before and record.job.attempt == 1


def test_withdrawal_under_four_blocks_freeze_and_withdrawal_during_draw_cancels_everyone():
    event = group()
    withdraw(event.members.first())
    event.refresh_from_db()
    assert event.state == "OPEN" and event.members.filter(active=True).count() == 3
    with pytest.raises(StateConflict):
        apply_command(command(event, "freeze"))
    second = start()
    lease = acquire_job()
    withdraw(second.members.first())
    second.refresh_from_db()
    assert second.state == "CANCELLED"
    with pytest.raises(StateConflict):
        commit_result(lease[0], lease[1], lease[3], result_for(lease))
    assert not SealedDraw.objects.exists()


def test_cancel_sealed_preserves_ciphertext_and_reopen_is_for_unsealed_failure_only():
    event = start()
    lease = acquire_job()
    fail_job(lease[0], lease[1], final=True)
    reopen_failed(event.id)
    event.refresh_from_db()
    assert event.state == "OPEN" and not event.manifest_digest
    assert not RosterConsent.objects.filter(member__event=event).exists()
    apply_command(command(event, "freeze"))
    event.refresh_from_db()
    for member in event.members.all():
        consent(member, event.manifest_version, event.manifest_digest)
    apply_command(command(event, "draw"))
    run_one_draw()
    record = SealedDraw.objects.get(event=event)
    before = bytes(record.ciphertext)
    with pytest.raises(StateConflict):
        reopen_failed(event.id)
    apply_command(command(event, "cancel", confirm=True))
    record.refresh_from_db()
    assert bytes(record.ciphertext) == before and record.event.state == "CANCELLED"
    assert DrawNotification.objects.filter(draw=record, state="CANCELLED").count() == 4


def cleanup(event):
    from django.contrib.auth import get_user_model

    users = list(event.members.values_list("identity__user_id", flat=True))
    SealedDraw.objects.filter(event=event).delete()
    PrivateEvent.objects.filter(pk=event.id).delete()
    get_user_model().objects.filter(pk__in=users).delete()


@pytest.mark.concurrent_db
@pytest.mark.parametrize("same_request", [True, False])
def test_twenty_simultaneous_same_signed_requests_and_two_workers(same_request):
    event = group()
    message = command(event, "draw")
    messages = [message if same_request else command(event, "draw") for _ in range(20)]

    def request(index):
        close_old_connections()
        try:
            return apply_command(messages[index])
        finally:
            close_old_connections()

    def acquire(_):
        close_old_connections()
        try:
            return acquire_job()
        finally:
            close_old_connections()

    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            replies = list(pool.map(request, range(20)))
        assert all(reply == replies[0] for reply in replies)
        assert DrawJob.objects.filter(event=event).count() == 1
        with ThreadPoolExecutor(max_workers=2) as pool:
            leases = [lease for lease in pool.map(acquire, range(2)) if lease]
        assert len(leases) == 1
        commit_result(leases[0][0], leases[0][1], leases[0][3], result_for(leases[0]))
        assert SealedDraw.objects.filter(event=event).count() == 1
    finally:
        cleanup(event)


@pytest.mark.concurrent_db
def test_real_encrypted_native_backup_restores_before_release_and_is_idempotent(tmp_path):
    from vault_core.durability import backup_and_verify

    event = start()
    values = tasks.config()
    env = {
        "BACKUP_ENCRYPTION_KEY": values["VAULT_BACKUP_KEY"],
        "BACKUP_DB_USER": "noel_admin",
        "BACKUP_DB_PASSWORD": values["VAULT_DB_ADMIN_PASSWORD"],
        "PG_BIN": str(tasks.ROOT / ".local/tools/postgresql/pgsql/bin"),
    }
    try:
        run_one_draw()
        record = SealedDraw.objects.get(event=event)
        with (
            patch.dict(os.environ, env),
            patch("vault_core.durability.subprocess.run", side_effect=RuntimeError),
        ):
            with pytest.raises(RuntimeError):
                backup_and_verify(event.id, tmp_path)
        record.refresh_from_db()
        assert record.release_state == "PENDING_DURABILITY"
        assert DrawNotification.objects.filter(draw=record, mail__state="HELD").count() == 4
        with patch.dict(os.environ, env):
            receipt = backup_and_verify(event.id, tmp_path)
            assert backup_and_verify(event.id, tmp_path) == receipt
        record.refresh_from_db()
        assert record.release_state == "AVAILABLE" and record.backup_receipt == receipt
        assert (
            DrawNotification.objects.filter(draw=record, state="QUEUED", mail__isnull=False).count()
            == 4
        )
        assert len(list(tmp_path.glob("*.pgdump.fernet"))) == 1
        apply_command(command(event, "close", confirm=True))
        event.refresh_from_db()
        assert event.state == "CLOSED"
    finally:
        cleanup(event)


def test_snapshot_fence_and_invalid_result_cannot_seal():
    event = start()
    lease = acquire_job()
    job = DrawJob.objects.get(event=event)
    old = dict(job.snapshot)
    job.snapshot = dict(old, version=999)
    job.save(update_fields=["snapshot"])
    with pytest.raises(StateConflict):
        commit_result(lease[0], lease[1], lease[3], result_for(lease))
    job.snapshot = old
    job.save(update_fields=["snapshot"])
    ids = [str(m.id) for m in event.members.all()]
    with pytest.raises(InvalidRules):
        commit_result(lease[0], lease[1], lease[3], [(mid, mid) for mid in ids])
    assert not SealedDraw.objects.exists() and not DrawNotification.objects.exists()
    commit_result(lease[0], lease[1], lease[3], result_for(lease))


def test_shipping_change_requires_revalidation_and_profile_change_invalidates_consent():
    event = group()
    member = event.members.first()
    client = Client()
    client.force_login(member.identity.user)
    response = client.patch(
        f"/api/me/profile?event_id={event.id}",
        {"revision": member.revision, "display_name": member.display_name, "country": "BE"},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    event.refresh_from_db()
    assert event.state == "OPEN" and not RosterConsent.objects.filter(member__event=event).exists()
    rules = {
        key: getattr(event, key) for key in ("title", "timezone", "shipping_included", "handover")
    }
    rules.update(
        celebration_at=event.celebration_at.isoformat(),
        wishlist_deadline=event.wishlist_deadline.isoformat(),
    )
    rules["shipping_included"] = True
    apply_command(command(event, "update_rules", event=rules))
    assert not event.members.filter(wishlist__state="VALIDATED").exists()
    with pytest.raises(StateConflict):
        apply_command(command(event, "freeze"))


def test_consent_api_csrf_foreign_member_and_wrong_manifest():
    event = group(ready=False)
    member = event.members.first()
    url = f"/api/me/roster-consent?event_id={event.id}"
    data = {"manifest_version": event.manifest_version, "manifest_digest": event.manifest_digest}
    assert Client().post(url, data, content_type="application/json").status_code == 401
    client = Client()
    client.force_login(member.identity.user)
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = client.cookies
    assert strict.post(url, data, content_type="application/json").status_code == 403
    assert (
        client.post(url, dict(data, extra=True), content_type="application/json").status_code == 409
    )
    assert (
        client.post(
            url, dict(data, manifest_digest="bad"), content_type="application/json"
        ).status_code
        == 409
    )
    assert client.post(url, data, content_type="application/json").status_code == 200
    assert client.get(f"/api/me/roster?event_id={event.id}").status_code == 200
    from helpers import user

    stranger = user("stranger@example.invalid")
    client.force_login(stranger)
    assert client.get(f"/api/me/roster?event_id={event.id}").status_code == 404
    assert client.post(url, data, content_type="application/json").status_code == 404


def test_sealed_country_change_keeps_result_and_name_is_frozen():
    event = start()
    run_one_draw()
    member = event.members.first()
    record = SealedDraw.objects.get(event=event)
    before = bytes(record.ciphertext)
    client = Client()
    client.force_login(member.identity.user)
    url = f"/api/me/profile?event_id={event.id}"
    data = {"revision": member.revision, "display_name": "Changed", "country": "BE"}
    assert client.patch(url, data, content_type="application/json").status_code == 409
    data["display_name"] = member.display_name
    assert client.patch(url, data, content_type="application/json").status_code == 200
    record.refresh_from_db()
    assert bytes(record.ciphertext) == before
