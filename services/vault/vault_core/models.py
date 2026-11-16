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


class PrivateEvent(models.Model):
    reminders_enabled = models.BooleanField(default=False)
    reminder_version = models.PositiveIntegerField(default=1)
    wish_digest_day = models.DateField(null=True)
    frozen_manifest = models.JSONField(null=True)

    projection_version = models.PositiveIntegerField(default=0)
    next_projection_at = models.DateTimeField(default=timezone.now)
    id = models.UUIDField(primary_key=True, editable=False)
    title = models.CharField(max_length=120)
    celebration_at = models.DateTimeField()
    wishlist_deadline = models.DateTimeField()
    timezone = models.CharField(max_length=64)
    shipping_included = models.BooleanField()
    handover = models.CharField(max_length=500)
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=16, default="OPEN")
    manifest_version = models.PositiveIntegerField(null=True)
    manifest_digest = models.CharField(max_length=64, blank=True)


class VerifiedIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    email = models.EmailField(unique=True)
    verified_at = models.DateTimeField(null=True)


class Membership(models.Model):
    reminders_enabled = models.BooleanField(default=True)
    recipient_viewed = models.BooleanField(default=False)
    id = models.UUIDField(primary_key=True, editable=False)
    event = models.ForeignKey(PrivateEvent, on_delete=models.CASCADE, related_name="members")
    identity = models.ForeignKey(VerifiedIdentity, on_delete=models.PROTECT)
    display_name = models.CharField(max_length=80)
    country = models.CharField(max_length=2)
    claimed_at = models.DateTimeField(null=True)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "identity"], name="vault_event_identity"),
            models.UniqueConstraint(Lower("display_name"), "event", name="vault_display_name"),
        ]


class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Membership, on_delete=models.CASCADE)
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RosterConsent(models.Model):
    member = models.ForeignKey(Membership, on_delete=models.CASCADE)
    manifest_version = models.PositiveIntegerField()
    manifest_digest = models.CharField(max_length=64)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["member", "manifest_version"], name="consent_member_version"
            )
        ]


class InboundCommand(models.Model):
    id = models.UUIDField(primary_key=True, editable=False)
    nonce = models.CharField(max_length=100, unique=True)
    body_digest = models.CharField(max_length=64)
    response = models.JSONField()


class PendingMail(DeliveryRecord):
    identity = models.ForeignKey(VerifiedIdentity, null=True, on_delete=models.CASCADE)
    category = models.CharField(max_length=12, default="AUTH")
    invitation = models.ForeignKey(Invitation, null=True, on_delete=models.CASCADE)
    member = models.ForeignKey(Membership, null=True, on_delete=models.CASCADE)
    event = models.ForeignKey(PrivateEvent, null=True, on_delete=models.CASCADE)
    kind = models.CharField(max_length=24, blank=True)
    logical_version = models.CharField(max_length=100, blank=True)
    business_key = models.CharField(max_length=200, null=True, unique=True)
    resend_number = models.PositiveIntegerField(default=0)


class NotificationOutbox(PendingMail):
    class Meta:
        proxy = True


class DeliveryReceipt(ReceiptRecord):
    mail = models.ForeignKey(PendingMail, null=True, on_delete=models.SET_NULL)


class ScheduledNotification(models.Model):
    event = models.ForeignKey(PrivateEvent, on_delete=models.CASCADE)
    member = models.ForeignKey(Membership, on_delete=models.CASCADE)
    kind = models.CharField(max_length=24)
    version = models.PositiveIntegerField()
    logical_version = models.CharField(max_length=100)
    due_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    state = models.CharField(max_length=12, default="PENDING")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "member", "kind", "logical_version"],
                name="scheduled_notification_once",
            )
        ]


class SecurityEvent(models.Model):
    identity = models.ForeignKey(VerifiedIdentity, null=True, on_delete=models.SET_NULL)
    category = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)


class Wishlist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.OneToOneField(Membership, on_delete=models.CASCADE)
    revision = models.PositiveIntegerField(default=0)
    state = models.CharField(max_length=12, default="DRAFT")
    validated_at = models.DateTimeField(null=True)


class GiftWish(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="slots")
    slot = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["wishlist", "slot"], name="wish_stable_slot"),
            models.CheckConstraint(
                condition=models.Q(slot__gte=1, slot__lte=3), name="wish_slot_range"
            ),
        ]


class WishlistRevision(models.Model):
    schema_version = models.PositiveSmallIntegerField(default=1)
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="history")
    revision = models.PositiveIntegerField()
    key_id = models.CharField(max_length=40)
    nonce = models.BinaryField(max_length=12)
    ciphertext = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["wishlist", "revision"], name="wish_revision_unique"),
            models.UniqueConstraint(fields=["key_id", "nonce"], name="wish_nonce_unique"),
        ]


class MerchantRequest(models.Model):
    member = models.ForeignKey(Membership, on_delete=models.CASCADE)
    hostname = models.CharField(max_length=253)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["member", "hostname"], name="merchant_request_unique")
        ]


class WishlistNonce(models.Model):
    key_id = models.CharField(max_length=40)
    nonce = models.BinaryField(max_length=12)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key_id", "nonce"], name="wish_key_nonce_reserved")
        ]


class Exclusion(models.Model):
    event = models.ForeignKey(PrivateEvent, on_delete=models.CASCADE)
    giver = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="exclusions_given")
    recipient = models.ForeignKey(
        Membership, on_delete=models.CASCADE, related_name="exclusions_received"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "giver", "recipient"], name="exclusion_unique"
            ),
            models.CheckConstraint(
                condition=~models.Q(giver=models.F("recipient")), name="no_self_exclusion"
            ),
        ]


class DrawJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField(PrivateEvent, on_delete=models.CASCADE)
    state = models.CharField(max_length=24, default="PENDING")
    snapshot = models.JSONField()
    snapshot_digest = models.CharField(max_length=64)
    attempt = models.PositiveIntegerField(default=0)
    lease_until = models.DateTimeField(null=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    failure_code = models.CharField(max_length=32, blank=True)


class DrawNonce(models.Model):
    key_ref = models.CharField(max_length=100)
    nonce = models.BinaryField(max_length=12)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key_ref", "nonce"], name="draw_nonce_unique")
        ]


class SealedDraw(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.OneToOneField(PrivateEvent, on_delete=models.PROTECT)
    job = models.OneToOneField(DrawJob, on_delete=models.PROTECT)
    schema_version = models.PositiveSmallIntegerField(default=1)
    manifest_version = models.PositiveIntegerField()
    key_id = models.CharField(max_length=40)
    nonce = models.BinaryField(max_length=12)
    wrap_nonce = models.BinaryField(max_length=12)
    wrapped_key = models.BinaryField()
    ciphertext = models.BinaryField()
    release_state = models.CharField(max_length=24, default="PENDING_DURABILITY")
    backup_receipt = models.JSONField(null=True)


class DrawNotification(models.Model):
    draw = models.ForeignKey(SealedDraw, on_delete=models.CASCADE, related_name="notifications")
    member = models.ForeignKey(Membership, on_delete=models.CASCADE)
    state = models.CharField(max_length=12, default="HELD")
    mail = models.OneToOneField(PendingMail, null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["draw", "member"], name="draw_notification_unique")
        ]


class EventDataKey(models.Model):
    event = models.OneToOneField(PrivateEvent, on_delete=models.CASCADE, primary_key=True)
    key_id = models.CharField(max_length=40)
    wrap_nonce = models.BinaryField(max_length=12)
    wrapped_key = models.BinaryField()


class PrivatePurchaseState(models.Model):
    member = models.OneToOneField(Membership, on_delete=models.CASCADE, primary_key=True)
    revision = models.PositiveIntegerField()
    nonce = models.BinaryField(max_length=12)
    ciphertext = models.BinaryField()
