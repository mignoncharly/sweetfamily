import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from noel_delivery import DeliveryRecord, ReceiptRecord


class OperationsState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    maintenance = models.BooleanField(default=False)
    recovery_verified = models.BooleanField(default=False)


class DeletionTombstone(models.Model):
    event_id = models.UUIDField(primary_key=True)
    deleted_at = models.DateTimeField(default=timezone.now)


class EnvironmentIdentity(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    app_env = models.CharField(max_length=16)
    service_role = models.CharField(max_length=16)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="environment_singleton"),
            models.CheckConstraint(
                condition=models.Q(app_env__in=["local", "staging", "production"]),
                name="environment_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(service_role__in=["control", "vault"]), name="role_valid"
            ),
        ]


class AuthRateCache(models.Model):
    cache_key = models.CharField(max_length=255, primary_key=True)
    value = models.TextField()
    expires = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "auth_rate_cache"


class Organizer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)


class EventDraft(models.Model):
    exclusions = models.JSONField(default=list)
    copied_from = models.ForeignKey(
        "self", null=True, on_delete=models.SET_NULL, related_name="annual_copies"
    )
    reminders_enabled = models.BooleanField(default=False)
    ready_count = models.PositiveSmallIntegerField(default=0)
    manifest_version = models.PositiveIntegerField(null=True)
    draw_progress = models.CharField(max_length=24, default="NOT_STARTED")
    projection_version = models.PositiveIntegerField(default=0)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(Organizer, on_delete=models.PROTECT)
    title = models.CharField(max_length=120)
    celebration_at = models.DateTimeField()
    wishlist_deadline = models.DateTimeField()
    timezone = models.CharField(max_length=64, default="Europe/Berlin")
    shipping_included = models.BooleanField(default=False)
    handover = models.CharField(max_length=500)
    version = models.PositiveIntegerField(default=1)
    state = models.CharField(max_length=16, default="DRAFT")


class RosterProposal(models.Model):
    active = models.BooleanField(default=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(EventDraft, on_delete=models.CASCADE, related_name="roster")
    display_name = models.CharField(max_length=80)
    country = models.CharField(max_length=2)
    email = models.EmailField()
    registration_confirmed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), "event", name="control_event_email"),
            models.UniqueConstraint(Lower("display_name"), "event", name="control_display_name"),
        ]


class SafeParticipantStatus(models.Model):
    recipient_viewed = models.BooleanField(default=False)
    consent_received = models.BooleanField(default=False)
    wishlist_complete = models.BooleanField(default=False)
    member = models.OneToOneField(RosterProposal, on_delete=models.CASCADE, primary_key=True)
    registration_confirmed = models.BooleanField(default=False)
    notification_state = models.CharField(max_length=24, default="QUEUED")


class ControlCommand(models.Model):
    rejected = models.BooleanField(default=False)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(EventDraft, on_delete=models.CASCADE)
    idempotency_key = models.CharField(max_length=100)
    body_digest = models.CharField(max_length=64)
    payload = models.JSONField()
    kind = models.CharField(max_length=32)
    delivered = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "idempotency_key"], name="control_command_key")
        ]


class ControlAudit(models.Model):
    event = models.ForeignKey(EventDraft, on_delete=models.CASCADE)
    category = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)


class AuthMail(DeliveryRecord):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)


class DeliveryReceipt(ReceiptRecord):
    mail = models.ForeignKey(AuthMail, null=True, on_delete=models.SET_NULL)


class PortalSubmission(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    owner = models.ForeignKey(Organizer, on_delete=models.CASCADE)
    body_digest = models.CharField(max_length=64)
    event = models.ForeignKey(EventDraft, on_delete=models.CASCADE)


class OwnershipTransfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField(EventDraft, on_delete=models.CASCADE)
    proposed_by = models.ForeignKey(
        Organizer, on_delete=models.PROTECT, related_name="proposed_transfers"
    )
    target = models.ForeignKey(
        Organizer, on_delete=models.PROTECT, related_name="received_transfers"
    )
    owner_label = models.CharField(max_length=80)
    state = models.CharField(max_length=16, default="PENDING")
    expected_version = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
