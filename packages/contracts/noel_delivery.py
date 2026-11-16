"""Service-neutral outbox transport and receipts. No business models or retained credentials."""

import hashlib
import hmac
import json
import re
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connection, models, transaction
from django.db.models import Q
from django.utils import timezone
from noel_contracts import canonical

WINDOW = timedelta(hours=23, minutes=55)
LEASE = timedelta(seconds=90)
EVENTS = {
    "email.sent": "ACCEPTED",
    "email.delivered": "DELIVERED",
    "email.delivery_delayed": "DEFERRED",
    "email.bounced": "REJECTED",
    "email.complained": "REJECTED",
    "email.failed": "FAILED",
    "email.suppressed": "REJECTED",
}
PRIORITY = [
    "DELIVERED",
    "REJECTED",
    "FAILED",
    "DEFERRED",
    "ACCEPTED",
    "SUBMITTED",
    "DELIVERY_UNKNOWN",
    "NONE",
]


class DeliveryRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payload = models.TextField()
    expires_at = models.DateTimeField()
    next_attempt_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveSmallIntegerField(default=0)
    state = models.CharField(max_length=32, default="QUEUED")
    created_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True)
    first_attempt_at = models.DateTimeField(null=True)
    provider_id = models.CharField(max_length=100, null=True, unique=True)
    transport = models.CharField(max_length=12, blank=True)
    payload_mac = models.CharField(max_length=64, blank=True)
    transport_fingerprint = models.CharField(max_length=64, blank=True)
    delivery_status = models.CharField(max_length=24, default="NONE")
    ambiguous = models.BooleanField(default=False)
    reconciliation_attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True


class ReceiptRecord(models.Model):
    id = models.CharField(primary_key=True, max_length=100)
    provider_id = models.CharField(max_length=100, db_index=True)
    notification_ref = models.UUIDField(null=True)
    status = models.CharField(max_length=24)
    occurred_at = models.DateTimeField()
    body_mac = models.CharField(max_length=64)

    class Meta:
        abstract = True


def mac(value):
    raw = value if isinstance(value, bytes) else canonical(value)
    return hmac.new(
        settings.AUTH_DATA_KEY.encode(), b"noel-notification-v1:" + raw, hashlib.sha256
    ).hexdigest()


class DeliveryError(Exception):
    def __init__(self, permanent=False, ambiguous=False, delay=30):
        self.permanent = permanent
        self.ambiguous = ambiguous
        self.delay = max(2, min(delay, 3600))
        super().__init__("Mail transport unavailable")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def provider_request(path, method="GET", payload=None, key=None):
    if not settings.RESEND_API_KEY:
        raise DeliveryError(permanent=True)
    request = urllib.request.Request(
        "https://api.resend.com" + path,
        data=canonical(payload) if payload is not None else None,
        headers={
            "Authorization": "Bearer " + settings.RESEND_API_KEY,
            "Content-Type": "application/json",
            **({"Idempotency-Key": key} if key else {}),
        },
        method=method,
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            raw = response.read(65537)
            if len(raw) > 65536:
                raise DeliveryError(ambiguous=method == "POST")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        # Never retain/log response bodies (they may echo addresses or codes).
        if exc.code == 429:
            delay = exc.headers.get("Retry-After", "30") if exc.headers else "30"
            raise DeliveryError(delay=int(delay) if delay.isdigit() else 30) from None
        if exc.code == 409:
            raw = exc.read(4096)
            try:
                concurrent = json.loads(raw).get("name") == "concurrent_idempotent_requests"
            except (ValueError, TypeError, AttributeError):
                concurrent = False
            raise DeliveryError(permanent=not concurrent) from None
        raise DeliveryError(permanent=400 <= exc.code < 500, ambiguous=exc.code >= 500) from None
    except DeliveryError:
        raise
    except Exception:
        raise DeliveryError(ambiguous=method == "POST") from None


def check_live(data):
    from django.core.validators import validate_email

    if (
        settings.MAIL_PROVIDER != "resend"
        or not settings.MAIL_LIVE_ENABLED
        or not settings.MAIL_DNS_VERIFIED
        or not settings.MAIL_TRACKING_DISABLED
        or not settings.RESEND_WEBHOOK_SECRET
    ):
        raise DeliveryError(permanent=True)
    validate_email(data["from"])
    if (
        settings.APP_ENV != "production"
        and data["email"].casefold() not in settings.MAIL_TEST_RECIPIENTS
    ):
        raise DeliveryError(permanent=True)


def zoho_connection(data):
    from django.core.validators import validate_email

    if (
        not settings.MAIL_LIVE_ENABLED
        or not settings.SMTP_USERNAME
        or not settings.SMTP_PASSWORD
        or settings.SMTP_HOST not in {"smtp.zoho.eu", "smtppro.zoho.eu"}
        or (settings.SMTP_USE_SSL, settings.SMTP_USE_TLS, settings.SMTP_PORT)
        not in {(True, False, 465), (False, True, 587)}
    ):
        raise DeliveryError(permanent=True)
    validate_email(data["from"])
    if data["from"].casefold() != settings.SMTP_USERNAME.casefold():
        raise DeliveryError(permanent=True)
    if (
        settings.APP_ENV != "production"
        and data.get("email", "").casefold() not in settings.MAIL_TEST_RECIPIENTS
    ):
        raise DeliveryError(permanent=True)
    return get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        password=settings.SMTP_PASSWORD,
        use_ssl=settings.SMTP_USE_SSL,
        use_tls=settings.SMTP_USE_TLS,
        timeout=10,
    )


def send(data, notification_id, transport):
    if transport == "mailpit":
        if settings.APP_ENV != "local":
            raise DeliveryError(permanent=True)
        backend = settings.EMAIL_BACKEND
        if backend.endswith("OutboxBackend"):
            backend = "django.core.mail.backends.smtp.EmailBackend"
        with get_connection(backend=backend) as connection:
            EmailMultiAlternatives(
                subject=data["subject"],
                body=data["body"],
                from_email=data["from"],
                to=[data["email"]],
                connection=connection,
                headers={"Message-ID": f"<{settings.SERVICE_ROLE}.{notification_id}@noel.invalid>"},
            ).send()
        return "local:" + str(notification_id)
    if transport == "zoho":
        import smtplib

        try:
            with zoho_connection(data) as connection:
                sender_domain = data["from"].rsplit("@", 1)[1]
                accepted = EmailMultiAlternatives(
                    subject=data["subject"],
                    body=data["body"],
                    from_email=data["from"],
                    to=[data["email"]],
                    connection=connection,
                    headers={
                        "Message-ID": f"<{settings.SERVICE_ROLE}.{notification_id}@{sender_domain}>"
                    },
                ).send()
                if accepted != 1:
                    raise DeliveryError(ambiguous=True)
            return "smtp:" + str(notification_id)
        except (
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPSenderRefused,
            smtplib.SMTPRecipientsRefused,
        ) as exc:
            code = getattr(exc, "smtp_code", 550)
            raise DeliveryError(permanent=code >= 500) from None
        except smtplib.SMTPDataError as exc:
            raise DeliveryError(permanent=exc.smtp_code >= 500) from None
        except DeliveryError:
            raise
        except Exception:
            raise DeliveryError(ambiguous=True) from None
    check_live(data)
    value = provider_request(
        "/emails",
        "POST",
        {
            "from": data["from"],
            "to": [data["email"]],
            "subject": data["subject"],
            "text": data["body"],
            "tags": [{"name": "notification", "value": str(notification_id)}],
        },
        f"{settings.SERVICE_ROLE}/{notification_id}",
    )
    try:
        return str(uuid.UUID(value["id"]))
    except (ValueError, TypeError, KeyError):
        raise DeliveryError(ambiguous=True) from None


def expire(item, unknown=False):
    item.state = "DELIVERY_UNKNOWN" if unknown else "EXPIRED"
    item.delivery_status = "DELIVERY_UNKNOWN" if unknown else item.delivery_status
    item.payload = ""
    item.lease_until = None
    item.save()


def apply_facts(item, receipts):
    facts = receipts.objects.filter(provider_id=item.provider_id)
    facts.filter(mail=None).update(mail=item)
    statuses = set(facts.values_list("status", flat=True))
    if not statuses:
        return False
    statuses.add(item.delivery_status)
    item.delivery_status = next(status for status in PRIORITY if status in statuses)
    item.state = "SENT"
    item.payload = ""
    item.lease_until = None
    item.save()
    return True


def deliver_one(
    model, receipts, decrypt, encrypt, guard=lambda item: True, prelock=lambda candidate: True
):
    now = timezone.now()
    eligible = Q(state="QUEUED", next_attempt_at__lte=now) | Q(
        state="RUNNING", lease_until__lte=now
    )
    candidate = model.objects.filter(eligible).order_by("next_attempt_at").first()
    if candidate is None:
        return False
    with transaction.atomic():
        if not prelock(candidate):
            return False
        item = (
            model.objects.select_for_update(skip_locked=True)
            .filter(pk=candidate.pk)
            .filter(eligible)
            .first()
        )
        if item is None:
            return False
        try:
            allowed = item.expires_at > now and guard(item)
        except Exception:
            import logging

            logging.getLogger("mail.security").warning("notification_preflight_failed")
            item.state = "FAILED"
            item.delivery_status = "FAILED"
            item.payload = ""
            item.lease_until = None
            item.save()
            return True
        if not allowed:
            expire(item, unknown=item.ambiguous)
            return True
        if (
            item.transport == "zoho"
            and item.first_attempt_at
            and (item.ambiguous or item.state == "RUNNING")
        ):
            expire(item, unknown=True)
            return True
        # Lost acknowledgement is never retried outside the provider's idempotency window.
        if item.first_attempt_at and (now - item.first_attempt_at >= WINDOW or item.attempts >= 5):
            expire(item, unknown=True)
            return True
        try:
            data = json.loads(decrypt(item.payload))
            if item.first_attempt_at is None and "from" not in data:
                data["from"] = settings.DEFAULT_FROM_EMAIL
                item.payload = encrypt(json.dumps(data, ensure_ascii=False))
            digest = mac(data)
            if item.payload_mac and not hmac.compare_digest(item.payload_mac, digest):
                raise ValueError()
            if set(data) != {"from", "email", "subject", "body"}:
                raise ValueError()
            if any(not isinstance(data[k], str) for k in data):
                raise ValueError()
        except Exception:
            item.state = "FAILED"
            item.payload = ""
            item.lease_until = None
            item.save()
            return True
        credentials = (
            {"key": settings.RESEND_API_KEY}
            if settings.MAIL_PROVIDER == "resend"
            else {
                "host": settings.SMTP_HOST,
                "user": settings.SMTP_USERNAME,
                "key": settings.SMTP_PASSWORD,
            }
            if settings.MAIL_PROVIDER == "zoho"
            else {}
        )
        fingerprint = mac(
            {"provider": settings.MAIL_PROVIDER, "credentials": credentials, "from": data["from"]}
        )
        if item.first_attempt_at and item.transport_fingerprint != fingerprint:
            expire(item, unknown=True)
            return True
        if item.first_attempt_at is None:
            item.transport_fingerprint = fingerprint
            item.first_attempt_at = now
            item.transport = settings.MAIL_PROVIDER
            item.payload_mac = digest
        if item.transport != settings.MAIL_PROVIDER:
            expire(item, unknown=True)
            return True
        prior_ambiguous = item.ambiguous or item.state == "RUNNING"
        item.ambiguous = True
        item.attempts += 1
        attempt = item.attempts
        item.state = "RUNNING"
        item.lease_until = now + LEASE
        item.save()
        item_id = item.id
        transport = item.transport
    # No database transaction/row lock is held across SMTP/HTTPS.
    provider_id = None
    failure = None
    try:
        provider_id = send(data, item_id, transport)
    except DeliveryError as exc:
        failure = exc
    except Exception:
        failure = DeliveryError(ambiguous=True)
    with transaction.atomic():
        item = model.objects.select_for_update().filter(pk=item_id).first()
        if item is None:
            return True
        if (
            item.state != "RUNNING"
            or item.attempts != attempt
            or item.lease_until is None
            or item.lease_until <= timezone.now()
        ):
            return True
        if failure:
            item.ambiguous = prior_ambiguous or failure.ambiguous
            if transport == "zoho" and item.ambiguous:
                item.state = "DELIVERY_UNKNOWN"
                item.delivery_status = "DELIVERY_UNKNOWN"
                item.payload = ""
            elif failure.permanent:
                item.state = "DELIVERY_UNKNOWN" if item.ambiguous else "FAILED"
                item.delivery_status = "DELIVERY_UNKNOWN" if item.ambiguous else "FAILED"
                item.payload = ""
            elif item.attempts >= 5:
                item.state = "DELIVERY_UNKNOWN" if item.ambiguous else "FAILED"
                item.delivery_status = "DELIVERY_UNKNOWN" if item.ambiguous else "FAILED"
                item.payload = ""
            else:
                item.state = "QUEUED"
                item.next_attempt_at = timezone.now() + timedelta(
                    seconds=max(failure.delay, 2**attempt)
                )
        else:
            item.provider_id = provider_id
            item.ambiguous = False
            item.state = "SENT"
            item.delivery_status = "SUBMITTED"
            item.payload = ""
        item.lease_until = None
        item.save()
        if provider_id:
            apply_facts(item, receipts)
    return True


def record_webhook(request, model, receipts):
    import resend

    raw = request.body
    if not settings.RESEND_WEBHOOK_SECRET or len(raw) > 65536:
        raise ValueError()
    message_id = request.headers.get("svix-id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", message_id):
        raise ValueError()
    signatures = " ".join(
        s for s in request.headers.get("svix-signature", "").split() if s.startswith("v1,")
    )
    event = resend.Webhooks.verify(
        {
            "payload": raw.decode("utf8"),
            "headers": {
                "id": message_id,
                "timestamp": request.headers.get("svix-timestamp", ""),
                "signature": signatures,
            },
            "webhook_secret": settings.RESEND_WEBHOOK_SECRET,
        }
    )
    if event.get("type") not in EVENTS:
        return
    provider_id = str(uuid.UUID(event["data"]["email_id"]))
    occurred = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
    if occurred.tzinfo is None or occurred > timezone.now() + timedelta(minutes=5):
        raise ValueError()
    tags = event["data"].get("tags", {})
    if isinstance(tags, list):
        tags = {tag["name"]: tag["value"] for tag in tags}
    try:
        ref = uuid.UUID(tags.get("notification", ""))
    except (ValueError, TypeError):
        ref = None
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                [
                    int.from_bytes(hashlib.sha256(message_id.encode()).digest()[:8], "big")
                    % (1 << 63)
                ],
            )
        old = receipts.objects.filter(pk=message_id).first()
        if old:
            if not hmac.compare_digest(old.body_mac, mac(raw)):
                raise ValueError()
            return
        record = receipts.objects.create(
            id=message_id,
            provider_id=provider_id,
            notification_ref=ref,
            status=EVENTS[event["type"]],
            occurred_at=occurred,
            body_mac=mac(raw),
        )
        candidates = Q(provider_id=provider_id)
        if ref:
            candidates |= Q(pk=ref, provider_id=None, first_attempt_at__isnull=False)
        item = model.objects.select_for_update().filter(candidates, transport="resend").first()
        if item:
            item.provider_id = provider_id
            item.save(update_fields=["provider_id"])
            record.mail = item
            record.save(update_fields=["mail"])
            apply_facts(item, receipts)


def reconcile_one(model, receipts):
    now = timezone.now()
    with transaction.atomic():
        item = (
            model.objects.select_for_update(skip_locked=True)
            .filter(
                transport="resend",
                provider_id__isnull=False,
                reconciliation_attempts__lt=5,
                delivery_status__in=["DELIVERY_UNKNOWN", "SUBMITTED", "ACCEPTED", "DEFERRED"],
                next_attempt_at__lte=now,
            )
            .filter(Q(lease_until=None) | Q(lease_until__lte=now))
            .first()
        )
        if item is None:
            return False
        item.lease_until = now + LEASE
        item.reconciliation_attempts += 1
        item.save(update_fields=["lease_until", "reconciliation_attempts"])
        item_id = item.id
        provider_id = item.provider_id
    status = None
    try:
        data = provider_request("/emails/" + str(uuid.UUID(provider_id)))
        if str(uuid.UUID(data["id"])) != provider_id:
            raise ValueError()
        status = EVENTS.get("email." + data["last_event"])
    except Exception:
        pass
    with transaction.atomic():
        item = model.objects.select_for_update().filter(pk=item_id).first()
        if item is None:
            return True
        if status:
            receipts.objects.get_or_create(
                id="lookup-" + str(uuid.uuid4()),
                defaults={
                    "mail": item,
                    "provider_id": provider_id,
                    "status": status,
                    "occurred_at": now,
                    "body_mac": mac({"id": provider_id, "status": status}),
                },
            )
            apply_facts(item, receipts)
        item.lease_until = None
        item.next_attempt_at = timezone.now() + timedelta(minutes=15)
        item.save(update_fields=["lease_until", "next_attempt_at"])
    return True


def reconcile_notification(model, receipts, notification_id, provider_id=None):
    item = model.objects.get(pk=notification_id, transport="resend", first_attempt_at__isnull=False)
    candidate = str(uuid.UUID(provider_id or item.provider_id))
    data = provider_request("/emails/" + candidate)
    if str(uuid.UUID(data["id"])) != candidate:
        raise ValueError()
    tags = data.get("tags", {})
    if isinstance(tags, list):
        tags = {row["name"]: row["value"] for row in tags}
    if item.provider_id is None and tags.get("notification") != str(item.id):
        raise ValueError()
    status = EVENTS.get("email." + data["last_event"])
    if not status:
        raise ValueError()
    with transaction.atomic():
        item = model.objects.select_for_update().get(pk=notification_id)
        if item.provider_id not in {None, candidate}:
            raise ValueError()
        item.provider_id = candidate
        item.save(update_fields=["provider_id"])
        receipts.objects.create(
            id="lookup-" + str(uuid.uuid4()),
            provider_id=candidate,
            mail=item,
            status=status,
            occurred_at=timezone.now(),
            body_mac=mac({"id": candidate, "status": status}),
        )
        apply_facts(item, receipts)
    return item.delivery_status


def local_evening(day, zone):
    naive = datetime.combine(day, time(18))
    # Choose the first occurrence; advance through a rare nonexistent wall-clock interval.
    for _ in range(181):
        candidate = naive.replace(tzinfo=zone, fold=0)
        if candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == naive:
            return candidate.astimezone(UTC)
        naive += timedelta(minutes=1)
    raise ValueError("Invalid local reminder time")


def reminder_proposals(event):
    zone = ZoneInfo(event.timezone)
    result = []
    for field, kind, offsets in (
        ("wishlist_deadline", "LIST_REMINDER", (7, 2)),
        ("celebration_at", "PREPARATION", (7, 1)),
    ):
        target = getattr(event, field)
        if isinstance(target, str):
            target = datetime.fromisoformat(target)
        for days in offsets:
            due = local_evening(target.astimezone(zone).date() - timedelta(days=days), zone)
            result.append((kind, days, due, min(due + timedelta(hours=24), target)))
    return result
