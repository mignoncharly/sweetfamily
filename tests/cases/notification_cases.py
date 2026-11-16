import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.db import close_old_connections
from django.test import Client
from django.utils import timezone
from draw_cases import cleanup, command, group
from private_cases import fixture
from vault_cases import claim, prepare
from vault_core.domain import apply_command
from vault_core.models import DrawJob, PendingMail, ScheduledNotification, SealedDraw, Wishlist
from vault_core.notifications import (
    configure,
    deliver_one,
    enqueue,
    proposals,
    reschedule,
    schedule_digest,
    schedule_one,
)
from vault_core.secrets import decrypt
from vault_core.wishlists import save_list
from wishlist_cases import items


def enable(event):
    configure(event, True, event.wishlist_deadline.isoformat(), event.celebration_at.isoformat())


def test_reminders_default_off_and_dates_require_explicit_confirmation():
    _, member = prepare()
    event = member.event
    assert not event.reminders_enabled and not ScheduledNotification.objects.exists()
    with pytest.raises(ValueError):
        configure(event, True, "2027-01-01T00:00:00Z", event.celebration_at.isoformat())
    enable(event)
    assert ScheduledNotification.objects.filter(event=event, state="PENDING").count() == 16
    assert all(
        row.due_at.astimezone(ZoneInfo(event.timezone)).hour == 18
        for row in ScheduledNotification.objects.all()
    )


@pytest.mark.parametrize(
    "celebration,hours",
    [("2026-10-30T18:00:00+01:00", [16, 17]), ("2026-04-02T18:00:00+02:00", [17, 16])],
)
def test_reminders_follow_local_calendar_across_dst(celebration, hours):
    _, member = prepare()
    event = member.event
    event.celebration_at = datetime.fromisoformat(celebration)
    values = [row for row in proposals(event) if row[0] == "PREPARATION"]
    assert [row[2].hour for row in values] == hours
    assert all(row[2].astimezone(ZoneInfo("Europe/Berlin")).hour == 18 for row in values)


def test_due_job_enqueues_once_and_checks_current_preferences_again_at_send():
    _, member = prepare()
    claim(member)
    event = member.event
    enable(event)
    job = ScheduledNotification.objects.filter(member=member, kind="LIST_REMINDER").first()
    ScheduledNotification.objects.filter(pk=job.pk).update(
        due_at=timezone.now() - timedelta(minutes=1), expires_at=timezone.now() + timedelta(hours=1)
    )
    assert schedule_one() and not schedule_one()
    notice = PendingMail.objects.get(member=member, kind="LIST_REMINDER")
    assert notice.business_key and "Canari" not in decrypt(notice.payload)
    member.reminders_enabled = False
    member.save(update_fields=["reminders_enabled"])
    # Remove unrelated invitation work only in this fixture.
    PendingMail.objects.exclude(pk=notice.pk).update(state="EXPIRED", payload="")
    with patch("noel_delivery.send") as send:
        assert deliver_one()
        send.assert_not_called()
    notice.refresh_from_db()
    assert notice.state == "EXPIRED"


@pytest.mark.parametrize("reason", ["complete", "opt_out", "late", "withdrawn", "version"])
def test_scheduler_skips_obsolete_or_unneeded_jobs(reason):
    _, member = prepare()
    claim(member)
    event = member.event
    enable(event)
    job = ScheduledNotification.objects.filter(member=member, kind="LIST_REMINDER").first()
    job.due_at = timezone.now() - timedelta(minutes=1)
    job.expires_at = timezone.now() + timedelta(hours=1)
    if reason == "complete":
        save_list(member, 0, items(), validate=True)
    if reason == "opt_out":
        member.reminders_enabled = False
        member.save()
    if reason == "late":
        job.expires_at = timezone.now() - timedelta(seconds=1)
    if reason == "withdrawn":
        member.active = False
        member.save()
    if reason == "version":
        job.version += 1
    job.save()
    assert schedule_one()
    job.refresh_from_db()
    assert job.state == "SKIPPED" and not PendingMail.objects.filter(kind="LIST_REMINDER").exists()


def test_rule_change_invalidates_old_schedules_and_pending_optional_notice():
    event = group(freeze=False)
    enable(event)
    old = event.reminder_version
    member = event.members.first()
    enqueue(member, "PREPARATION", "old")
    rules = {
        key: getattr(event, key) for key in ("title", "timezone", "shipping_included", "handover")
    }
    rules.update(
        celebration_at=(event.celebration_at + timedelta(days=1)).isoformat(),
        wishlist_deadline=event.wishlist_deadline.isoformat(),
    )
    apply_command(command(event, "update_rules", event=rules))
    event.refresh_from_db()
    assert event.reminder_version > old
    assert not ScheduledNotification.objects.filter(
        event=event, version=old, state="PENDING"
    ).exists()
    assert PendingMail.objects.get(kind="PREPARATION").state == "EXPIRED"


def test_freeze_queues_versioned_consent_notice_without_wishes():
    event = group(ready=False)
    notices = PendingMail.objects.filter(event=event, kind="CONSENT")
    assert notices.count() == 4
    assert all(row.logical_version == str(event.manifest_version) for row in notices)
    assert all(
        "Canari" not in decrypt(row.payload) and "amazon" not in decrypt(row.payload)
        for row in notices
    )


def test_daily_digest_fans_out_to_group_once_without_owner_or_buyer_reference():
    event, member, _ = fixture()
    enable(event)
    listing = Wishlist.objects.get(member=member)
    save_list(member, listing.revision, items())
    schedule_digest(event)
    jobs = ScheduledNotification.objects.filter(event=event, kind="WISH_DIGEST")
    assert jobs.count() == 4 and len(set(jobs.values_list("due_at", flat=True))) == 1
    jobs.update(
        due_at=timezone.now() - timedelta(seconds=1), expires_at=timezone.now() + timedelta(hours=1)
    )
    for _ in range(4):
        assert schedule_one()
    assert not schedule_one()
    notices = PendingMail.objects.filter(event=event, kind="WISH_DIGEST")
    assert notices.count() == 4
    for row in notices:
        data = json.loads(decrypt(row.payload))
        assert "Canari" not in data["body"] and member.display_name not in data["body"]
    schedule_digest(event)
    assert ScheduledNotification.objects.filter(event=event, kind="WISH_DIGEST").count() == 4


def test_manual_resend_is_limited_idempotent_and_preserves_sealed_result():
    event, member, _ = fixture()
    before = bytes(SealedDraw.objects.get(event=event).ciphertext)
    message = command(event, "resend_notice", member_id=str(member.id), notice_type="DRAW_READY")
    assert apply_command(message) == apply_command(message)
    for _ in range(2):
        apply_command(
            command(event, "resend_notice", member_id=str(member.id), notice_type="DRAW_READY")
        )
    with pytest.raises(ValueError):
        apply_command(
            command(event, "resend_notice", member_id=str(member.id), notice_type="DRAW_READY")
        )
    assert PendingMail.objects.filter(member=member, resend_number__gt=0).count() == 3
    assert bytes(SealedDraw.objects.get(event=event).ciphertext) == before
    assert DrawJob.objects.filter(event=event).count() == 1


def test_cancellation_expires_held_and_queued_work_and_creates_only_neutral_notices():
    event, member, _ = fixture()
    enable(event)
    apply_command(command(event, "cancel", confirm=True))
    assert not ScheduledNotification.objects.filter(event=event, state="PENDING").exists()
    assert (
        not PendingMail.objects.filter(event=event, state__in=["QUEUED", "HELD"])
        .exclude(kind="CANCELLED")
        .exists()
    )
    notices = PendingMail.objects.filter(event=event, kind="CANCELLED")
    assert notices.count() == 4 and all("Canari" not in decrypt(row.payload) for row in notices)


def test_personal_preferences_are_csrf_protected_and_show_simulation():
    _, member = prepare()
    claim(member)
    client = Client()
    client.force_login(member.identity.user)
    url = f"/api/me/notification-preferences?event_id={member.event_id}"
    assert client.get(url).json()["reminders_enabled"]
    assert (
        client.patch(url, {"reminders_enabled": False}, content_type="application/json").status_code
        == 200
    )
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = client.cookies
    assert (
        strict.patch(url, {"reminders_enabled": True}, content_type="application/json").status_code
        == 403
    )
    response = client.get(f"/notifications?event_id={member.event_id}")
    assert response.status_code == 200 and b"Simulation" in response.content


@pytest.mark.concurrent_db
def test_two_schedulers_create_only_one_outbox_row():
    event = group(freeze=False)
    member = event.members.first()
    enable(event)
    Wishlist.objects.filter(member=member).update(state="DRAFT")
    job = ScheduledNotification.objects.filter(
        event=event, member=member, kind="LIST_REMINDER"
    ).first()
    ScheduledNotification.objects.filter(pk=job.pk).update(
        due_at=timezone.now() - timedelta(minutes=1), expires_at=timezone.now() + timedelta(hours=1)
    )

    def worker(_):
        close_old_connections()
        try:
            return schedule_one()
        finally:
            close_old_connections()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        assert results.count(True) == 1
        assert PendingMail.objects.filter(member=member, kind="LIST_REMINDER").count() == 1
    finally:
        cleanup(event)


def test_stale_inflight_reminder_cannot_restart_after_dates_changed():
    _, member = prepare()
    claim(member)
    event = member.event
    enable(event)
    job = ScheduledNotification.objects.filter(member=member, kind="LIST_REMINDER").first()
    ScheduledNotification.objects.filter(pk=job.pk).update(
        due_at=timezone.now() - timedelta(minutes=1), expires_at=timezone.now() + timedelta(hours=1)
    )
    assert schedule_one()
    notice = PendingMail.objects.get(member=member, kind="LIST_REMINDER")
    PendingMail.objects.filter(pk=notice.id).update(
        state="RUNNING", lease_until=timezone.now() - timedelta(seconds=1), ambiguous=True
    )
    reschedule(event)
    PendingMail.objects.exclude(pk=notice.id).update(state="EXPIRED", payload="")
    with patch("noel_delivery.send") as send:
        assert deliver_one()
        send.assert_not_called()
    notice.refresh_from_db()
    assert notice.state == "DELIVERY_UNKNOWN"
