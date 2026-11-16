"""Operator-only retention and recovery. No recipient data in the external journal."""

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from django.apps import apps
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

LOCK = 73829104612


class MaintenanceRequired(RuntimeError):
    pass


def model(name):
    return apps.get_model(settings.SERVICE_ROLE + "_core", name)


def lock(exclusive=False):
    with connection.cursor() as cursor:
        suffix = "" if exclusive else "_shared"
        cursor.execute(f"SELECT pg_advisory_xact_lock{suffix}(%s)", [LOCK])


def paused():
    return (
        settings.FORCE_MAINTENANCE
        or model("OperationsState").objects.filter(pk=1, maintenance=True).exists()
    )


@contextmanager
def serving():
    # The exclusive operator lock drains complete HTTP requests and worker ticks.
    # Session-level shared lock preserves the outbox's commit-before-I/O boundaries.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock_shared(%s)", [LOCK])
    try:
        if paused():
            raise MaintenanceRequired("Service en maintenance.")
        yield
    finally:
        if connection.connection is not None and not connection.needs_rollback:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock_shared(%s)", [LOCK])


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/health/live":
            return self.get_response(request)
        try:
            with serving():
                return self.get_response(request)
        except (MaintenanceRequired, DatabaseError) as exc:
            status = "maintenance" if isinstance(exc, MaintenanceRequired) else "unavailable"
            response = JsonResponse({"status": status}, status=503)
            response["Cache-Control"] = "no-store"
            response["Retry-After"] = "60"
            return response


def journal():
    path = os.environ.get("OPERATIONS_DIRECTORY")
    key = os.environ.get("OPERATIONS_KEY")
    if not path or not key:
        raise MaintenanceRequired("Independent operations directory/key required.")
    root = Path(path).resolve() / settings.SERVICE_ROLE
    if not root.is_dir():
        raise MaintenanceRequired("Initialize the external operations journal first.")
    return root, Fernet(key.encode())


def initialize_journal():
    path = os.environ.get("OPERATIONS_DIRECTORY")
    if not path or not os.environ.get("OPERATIONS_KEY"):
        raise MaintenanceRequired("Independent operations directory/key required.")
    root = Path(path).resolve() / settings.SERVICE_ROLE
    root.mkdir(parents=True, exist_ok=False)
    append_record("anchor", {"created_at": timezone.now().isoformat()})


def append_record(name, data):
    root, cipher = journal()
    record = {"schema": 1, "role": settings.SERVICE_ROLE, **data}
    raw = json.dumps(record, sort_keys=True).encode()
    destination = root / (name + ".fernet")
    if destination.exists():
        existing = json.loads(cipher.decrypt(destination.read_bytes()))
        if existing != record:
            raise MaintenanceRequired("Journal record conflict.")
        return
    # Atomic rename only after fsync; an incomplete temporary record blocks recovery.
    temporary = root / (name + ".pending")
    with temporary.open("xb") as stream:
        stream.write(cipher.encrypt(raw))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)
    if os.name != "nt":
        descriptor = os.open(root, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def records():
    root, cipher = journal()
    if not (root / "anchor.fernet").exists() or list(root.glob("*.pending")):
        raise MaintenanceRequired("Incomplete journal; operator recovery required.")
    result = []
    for path in sorted(root.glob("*.fernet")):
        data = json.loads(cipher.decrypt(path.read_bytes()))
        if data.get("schema") != 1 or data.get("role") != settings.SERVICE_ROLE:
            raise MaintenanceRequired("Wrong journal role/schema.")
        result.append(data)
    return result


@transaction.atomic
def enter_maintenance():
    lock(exclusive=True)
    state, _ = model("OperationsState").objects.get_or_create(pk=1)
    state.maintenance = True
    state.recovery_verified = False
    state.save()


def require_maintenance():
    state = model("OperationsState").objects.select_for_update().filter(pk=1).first()
    if state is None or not state.maintenance:
        raise MaintenanceRequired("Enter maintenance first.")
    return state


def event_model():
    return model("PrivateEvent" if settings.SERVICE_ROLE == "vault" else "EventDraft")


def draw_fingerprint(draw):
    # Rotation may change the wrapped key, but never the sealed payload or its nonce.
    return hashlib.sha256(bytes(draw.nonce) + bytes(draw.ciphertext)).hexdigest()


def remember_draw(draw):
    append_record(
        "sealed-" + str(draw.id),
        {
            "kind": "sealed",
            "event_id": str(draw.event_id),
            "sealed_id": str(draw.id),
            "fingerprint": draw_fingerprint(draw),
        },
    )


def delete_event(event_id):
    # The external tombstone is flushed BEFORE deletion commits. Retrying is safe.
    existing = next(
        (
            item
            for item in records()
            if item.get("kind") == "deleted" and item["event_id"] == str(event_id)
        ),
        None,
    )
    defaults = {"deleted_at": parse_datetime(existing["deleted_at"])} if existing else {}
    tombstone, _ = model("DeletionTombstone").objects.get_or_create(
        event_id=event_id, defaults=defaults
    )
    append_record(
        "deleted-" + str(event_id),
        {
            "kind": "deleted",
            "event_id": str(event_id),
            "deleted_at": tombstone.deleted_at.isoformat(),
        },
    )
    if settings.SERVICE_ROLE == "vault":
        mail_ids = model("PendingMail").objects.filter(event_id=event_id).values("id")
        model("DeliveryReceipt").objects.filter(mail_id__in=mail_ids).delete()
        identity_ids = list(
            model("Membership")
            .objects.filter(event_id=event_id)
            .values_list("identity_id", flat=True)
        )
        # Explicit order for PROTECT, without weakening ordinary deletion protections.
        model("SealedDraw").objects.filter(event_id=event_id).delete()
        event_model().objects.filter(pk=event_id).delete()
        for identity in model("VerifiedIdentity").objects.filter(pk__in=identity_ids):
            if not model("Membership").objects.filter(identity=identity).exists():
                user = identity.user
                model("SecurityEvent").objects.filter(identity=identity).delete()
                # Preserve registered accounts until their owner requests account removal.
                from allauth.account.models import EmailAddress

                if not EmailAddress.objects.filter(user=user, verified=True).exists():
                    user.delete()
                else:
                    identity.delete()
    else:
        event_model().objects.filter(pk=event_id).delete()


@transaction.atomic
def purge_due():
    lock(exclusive=True)
    state = require_maintenance()
    records()  # Missing/corrupt journal fails before any deletion.
    state.recovery_verified = False
    state.save()
    due = list(
        event_model()
        .objects.filter(celebration_at__lte=timezone.now() - timedelta(days=90))
        .values_list("pk", flat=True)
    )
    for event_id in due:
        delete_event(event_id)
    cutoff = timezone.now() - timedelta(days=30)
    model("DeliveryReceipt").objects.filter(occurred_at__lte=cutoff).delete()
    mail = model("PendingMail" if settings.SERVICE_ROLE == "vault" else "AuthMail")
    mail.objects.filter(created_at__lte=cutoff, expires_at__lte=timezone.now()).delete()
    if settings.SERVICE_ROLE == "vault":
        model("SecurityEvent").objects.filter(created_at__lte=cutoff).delete()
    from django.contrib.sessions.models import Session

    Session.objects.filter(expire_date__lte=timezone.now()).delete()
    apps.get_model("usersessions", "UserSession").objects.filter(last_seen_at__lte=cutoff).delete()
    return len(due)


@transaction.atomic
def recover(restored=True):
    lock(exclusive=True)
    state = require_maintenance()
    entries = records()
    deleted = {uuid.UUID(item["event_id"]) for item in entries if item.get("kind") == "deleted"}
    for event_id in deleted:
        # Use the original date so replay never rewrites or extends journal records.
        entry = next(
            item
            for item in entries
            if item.get("kind") == "deleted" and uuid.UUID(item["event_id"]) == event_id
        )
        model("DeletionTombstone").objects.get_or_create(
            event_id=event_id, defaults={"deleted_at": parse_datetime(entry["deleted_at"])}
        )
        delete_event(event_id)
    purge_due()
    for entry in entries:
        if entry.get("kind") == "account_deleted":
            delete_account(entry["user_id"])
    deleted |= set(model("DeletionTombstone").objects.values_list("event_id", flat=True))
    if settings.SERVICE_ROLE == "vault":
        from vault_core.draw_crypto import unseal
        from vault_core.draw_engine import validate_result

        expected = {
            item["event_id"]: item
            for item in entries
            if item.get("kind") == "sealed" and uuid.UUID(item["event_id"]) not in deleted
        }
        draws = model("SealedDraw").objects.select_related("event", "job")
        actual = {str(draw.event_id): draw for draw in draws}
        for event_id, item in expected.items():
            draw = actual.get(event_id)
            if (
                draw is None
                or str(draw.id) != item["sealed_id"]
                or draw_fingerprint(draw) != item["fingerprint"]
            ):
                raise MaintenanceRequired("Previously sealed draw missing or changed; incident.")
        for draw in actual.values():
            value = unseal(draw)
            snapshot = draw.job.snapshot
            validate_result(
                [m["id"] for m in snapshot["members"]], snapshot["exclusions"], value["permutation"]
            )
            remember_draw(draw)
        from vault_core.private_space import purchase_value
        from vault_core.wishlists import open_revision

        for revision in model("WishlistRevision").objects.select_related("wishlist__member__event"):
            open_revision(revision.wishlist, revision.revision)
        for purchase in model("PrivatePurchaseState").objects.select_related("member__event"):
            purchase_value(purchase.member)
        # Fence pre-restore workers; never retry a sealed job.
        if restored:
            model("DrawJob").objects.exclude(state="SEALED").update(
                state="FAILED_FINAL", failure_code="RESTORE_REVIEW", lease_until=None
            )
            model("ScheduledNotification").objects.filter(state="PENDING").update(state="SKIPPED")
            model("PrivateEvent").objects.update(reminders_enabled=False)
        mail_model = model("PendingMail")
    else:
        # Old queued commands could already have taken effect after this backup.
        if restored:
            model("ControlCommand").objects.filter(delivered=False).update(rejected=True)
            model("OwnershipTransfer").objects.exclude(state="ACCEPTED").delete()
        mail_model = model("AuthMail")
    # Even QUEUED may have been submitted after the restored snapshot. Hold ALL
    # non-final messages; no provider idempotency window is assumed after restore.
    if restored:
        mail_model.objects.exclude(state__in=["SENT", "FAILED", "EXPIRED", "CANCELLED"]).update(
            state="DELIVERY_UNKNOWN",
            delivery_status="DELIVERY_UNKNOWN",
            ambiguous=True,
            lease_until=None,
        )
        from django.contrib.sessions.models import Session

        Session.objects.all().delete()
        model("AuthRateCache").objects.all().delete()
    from allauth.mfa.utils import decrypt as decrypt_factor

    for factor in apps.get_model("mfa", "Authenticator").objects.all():
        for field in ("secret", "seed"):
            if field in factor.data:
                decrypt_factor(factor.data[field])
        for code in factor.data.get("migrated_codes", []):
            decrypt_factor(code)
    state.recovery_verified = True
    state.save()
    return {
        "deleted_events": len(deleted),
        "mail_held": mail_model.objects.filter(state="DELIVERY_UNKNOWN").count(),
    }


@transaction.atomic
def resume():
    lock(exclusive=True)
    state = require_maintenance()
    if not state.recovery_verified:
        raise MaintenanceRequired("Run recovery verification before resuming.")
    records()
    state.maintenance = False
    state.recovery_verified = False
    state.save()


@transaction.atomic
def delete_account(user_id):
    """Only after the operator has verified the owner's request; never during an exchange."""
    from importlib import import_module

    from django.contrib.auth import get_user_model
    from django.contrib.sessions.models import Session
    from noel_delivery import mac

    lock(exclusive=True)
    require_maintenance()
    user = get_user_model().objects.select_for_update().filter(pk=user_id).first()
    if user is None:
        return
    fingerprint = mac({"user_id": user.pk, "email": user.email})
    previous = [
        item
        for item in records()
        if item.get("kind") == "account_deleted" and item["user_id"] == user.pk
    ]
    if any(item["fingerprint"] != fingerprint for item in previous):
        raise MaintenanceRequired("Restored account identity changed; incident review required.")
    if settings.SERVICE_ROLE == "vault":
        if model("Membership").objects.filter(identity__user=user).exists():
            raise MaintenanceRequired("Apply event withdrawal/cancellation and retention first.")
        model("SecurityEvent").objects.filter(identity__user=user).delete()
    else:
        if model("EventDraft").objects.filter(owner__user=user).exists():
            raise MaintenanceRequired("Transfer or retain existing events first.")
        if (
            model("OwnershipTransfer").objects.filter(target__user=user).exists()
            or model("OwnershipTransfer").objects.filter(proposed_by__user=user).exists()
        ):
            raise MaintenanceRequired("Resolve organization transfers first.")
    append_record(
        "account-" + str(user.pk),
        {
            "kind": "account_deleted",
            "user_id": user.pk,
            "fingerprint": fingerprint,
            "deleted_at": previous[0]["deleted_at"] if previous else timezone.now().isoformat(),
        },
    )
    store = import_module(settings.SESSION_ENGINE).SessionStore()
    for session in Session.objects.all().iterator():
        if store.decode(session.session_data).get("_auth_user_id") == str(user.pk):
            session.delete()
    user.delete()
    state = require_maintenance()
    state.recovery_verified = False
    state.save()


def status():
    """Aggregate local supervision only; never returns identity or assignment fields."""
    from django.db.models import Min

    mail = model("PendingMail" if settings.SERVICE_ROLE == "vault" else "AuthMail")
    queued = mail.objects.filter(state__in=["QUEUED", "RUNNING", "HELD"])
    oldest = queued.aggregate(value=Min("created_at"))["value"]
    result = {
        "maintenance": paused(),
        "queue_depth": queued.count(),
        "oldest_queued_seconds": max(0, int((timezone.now() - oldest).total_seconds()))
        if oldest
        else 0,
        "expired_leases": mail.objects.filter(
            state="RUNNING", lease_until__lt=timezone.now()
        ).count(),
        "delivery_unknown": mail.objects.filter(delivery_status="DELIVERY_UNKNOWN").count(),
        "rejected": mail.objects.filter(delivery_status="REJECTED").count(),
    }
    if settings.SERVICE_ROLE == "vault":
        result["blocked_draws"] = (
            model("DrawJob").objects.filter(state__in=["FAILED_FINAL", "FAILED_RETRYABLE"]).count()
        )
        result["pending_durability"] = (
            model("SealedDraw").objects.filter(release_state="PENDING_DURABILITY").count()
        )
    return result
