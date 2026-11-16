"""Shared outbox contract exercised independently in each service database."""

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

import pytest
from django.apps import apps
from django.conf import settings
from django.db import close_old_connections
from django.test import Client, override_settings
from django.utils import timezone
from noel_delivery import DeliveryError, deliver_one, mac, reconcile_one

ROLE = settings.SERVICE_ROLE
Mail = apps.get_model(ROLE + "_core", "AuthMail" if ROLE == "control" else "PendingMail")
Receipt = apps.get_model(ROLE + "_core", "DeliveryReceipt")
secret_module = __import__(ROLE + "_core.secrets", fromlist=["decrypt", "encrypt"])
SECRET = "whsec_" + base64.b64encode(secrets.token_bytes(32)).decode()


def queued(**extra):
    data = {
        "from": "notify@example.invalid",
        "email": "probe@example.invalid",
        "subject": "Notification neutre",
        "body": "Connecte-toi à ton espace.",
    }
    return Mail.objects.create(
        payload=secret_module.encrypt(json.dumps(data)),
        payload_mac=mac(data),
        expires_at=timezone.now() + timedelta(minutes=10),
        next_attempt_at=timezone.now(),
        **extra,
    )


def dispatch():
    return deliver_one(Mail, Receipt, secret_module.decrypt, secret_module.encrypt)


def ready(item):
    Mail.objects.filter(pk=item.id).update(next_attempt_at=timezone.now())


def live():
    return override_settings(
        MAIL_PROVIDER="resend",
        MAIL_LIVE_ENABLED=True,
        MAIL_DNS_VERIFIED=True,
        MAIL_TRACKING_DISABLED=True,
        RESEND_API_KEY="synthetic-only",
        RESEND_WEBHOOK_SECRET=SECRET,
        MAIL_TEST_RECIPIENTS={"probe@example.invalid"},
    )


def webhook(
    provider_id, kind="email.delivered", ref=None, message_id=None, stamp=None, secret=SECRET
):
    message_id = message_id or "msg_" + uuid.uuid4().hex
    stamp = str(stamp or int(time.time()))
    data = {
        "email_id": provider_id,
        "subject": "PRIVATE_PROVIDER_CANARY",
        "to": ["private@example.invalid"],
        "tags": {"notification": str(ref)} if ref else {},
    }
    raw = json.dumps(
        {"type": kind, "created_at": timezone.now().isoformat(), "data": data}, ensure_ascii=False
    ).encode()
    signed = message_id.encode() + b"." + stamp.encode() + b"." + raw
    signature = base64.b64encode(
        hmac.new(base64.b64decode(secret.removeprefix("whsec_")), signed, hashlib.sha256).digest()
    ).decode()
    return raw, {
        "HTTP_SVIX_ID": message_id,
        "HTTP_SVIX_TIMESTAMP": stamp,
        "HTTP_SVIX_SIGNATURE": "v1," + signature,
    }


def post_webhook(payload):
    raw, headers = payload
    return Client(enforce_csrf_checks=True).post(
        "/webhooks/resend", raw, content_type="application/json", **headers
    )


def test_lease_and_success_purge_payload_and_retain_safe_receipt():
    item = queued()
    with patch("noel_delivery.send", return_value=str(uuid.uuid4())) as send:
        assert dispatch()
        assert not dispatch()
        assert send.call_count == 1
    item.refresh_from_db()
    assert item.state == "SENT" and item.delivery_status == "SUBMITTED" and item.payload == ""
    assert item.attempts == 1 and item.lease_until is None


def test_ambiguous_retry_uses_same_key_body_and_sender():
    item = queued()
    seen = []

    def api(path, method, payload, key):
        seen.append((path, method, payload, key))
        if len(seen) == 1:
            raise DeliveryError(ambiguous=True)
        return {"id": str(uuid.uuid4())}

    with live(), patch("noel_delivery.provider_request", side_effect=api):
        assert dispatch()
        ready(item)
        with override_settings(DEFAULT_FROM_EMAIL="changed@example.invalid"):
            assert dispatch()
    assert len(seen) == 2 and seen[0] == seen[1]
    item.refresh_from_db()
    assert item.state == "SENT" and item.attempts == 2


def test_ambiguous_after_window_does_not_resend():
    item = queued(
        first_attempt_at=timezone.now() - timedelta(hours=24), transport="resend", ambiguous=True
    )
    with live(), patch("noel_delivery.send") as send:
        assert dispatch()
        send.assert_not_called()
    item.refresh_from_db()
    assert item.state == item.delivery_status == "DELIVERY_UNKNOWN" and item.payload == ""


def test_expired_code_never_reaches_transport():
    item = queued()
    Mail.objects.filter(pk=item.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
    with patch("noel_delivery.send") as send:
        assert dispatch()
        send.assert_not_called()
    item.refresh_from_db()
    assert item.state == "EXPIRED" and item.payload == ""


def test_payload_tampering_is_rejected_before_send():
    item = queued()
    Mail.objects.filter(pk=item.pk).update(
        payload=secret_module.encrypt(json.dumps({"from": "x", "body": "changed"}))
    )
    with patch("noel_delivery.send") as send:
        assert dispatch()
        send.assert_not_called()
    item.refresh_from_db()
    assert item.state == "FAILED"


@pytest.mark.parametrize(
    "failure,state",
    [
        (DeliveryError(permanent=True), "FAILED"),
        (DeliveryError(ambiguous=True), "DELIVERY_UNKNOWN"),
    ],
)
def test_permanent_and_exhausted_failures_are_honest(failure, state):
    item = queued(attempts=4)
    with patch("noel_delivery.send", side_effect=failure):
        dispatch()
    item.refresh_from_db()
    assert item.state == state and item.payload == ""


def test_crash_after_provider_acceptance_retries_same_logical_message():
    item = queued()
    attempts = []
    provider_id = str(uuid.uuid4())

    def send(data, notification_id, transport):
        attempts.append((data, notification_id, transport))
        if len(attempts) == 1:
            raise SystemExit("Simulated worker death")
        return provider_id

    with patch("noel_delivery.send", side_effect=send):
        with pytest.raises(SystemExit):
            dispatch()
        item.refresh_from_db()
        assert item.state == "RUNNING"
        Mail.objects.filter(pk=item.id).update(lease_until=timezone.now() - timedelta(seconds=1))
        assert dispatch()
    assert attempts[0] == attempts[1]
    item.refresh_from_db()
    assert item.state == "SENT" and item.attempts == 2


def test_real_sdk_verifies_raw_signature_deduplicates_and_preserves_delivered_fact():
    item = queued(first_attempt_at=timezone.now(), transport="resend", state="RUNNING")
    provider_id = str(uuid.uuid4())
    delivered = webhook(provider_id, ref=item.id)
    with override_settings(RESEND_WEBHOOK_SECRET=SECRET):
        assert post_webhook(delivered).status_code == 200
        assert post_webhook(delivered).status_code == 200
        assert post_webhook(webhook(provider_id, "email.sent", item.id)).status_code == 200
    item.refresh_from_db()
    assert item.provider_id == provider_id and item.delivery_status == "DELIVERED"
    assert item.state == "SENT" and item.payload == "" and Receipt.objects.count() == 2
    assert "PRIVATE_PROVIDER_CANARY" not in json.dumps(list(Receipt.objects.values()), default=str)
    assert "private@example.invalid" not in json.dumps(list(Receipt.objects.values()), default=str)


@pytest.mark.parametrize(
    "kind,status",
    [
        ("email.bounced", "REJECTED"),
        ("email.failed", "FAILED"),
        ("email.delivery_delayed", "DEFERRED"),
        ("email.sent", "ACCEPTED"),
    ],
)
def test_delivery_events_have_distinct_facts(kind, status):
    provider_id = str(uuid.uuid4())
    item = queued(first_attempt_at=timezone.now(), transport="resend", provider_id=provider_id)
    with override_settings(RESEND_WEBHOOK_SECRET=SECRET):
        assert post_webhook(webhook(provider_id, kind)).status_code == 200
    item.refresh_from_db()
    assert item.delivery_status == status


def test_forged_stale_modified_and_conflicting_webhooks_rejected():
    provider_id = str(uuid.uuid4())
    with override_settings(RESEND_WEBHOOK_SECRET=SECRET):
        assert post_webhook(webhook(provider_id, stamp=int(time.time()) - 601)).status_code == 403
        forged = webhook(
            provider_id, secret="whsec_" + base64.b64encode(secrets.token_bytes(32)).decode()
        )
        assert post_webhook(forged).status_code == 403
        original = webhook(provider_id)
        assert post_webhook((original[0] + b" ", original[1])).status_code == 403
        assert post_webhook(original).status_code == 200
        conflict = webhook(provider_id, "email.sent", message_id=original[1]["HTTP_SVIX_ID"])
        assert post_webhook(conflict).status_code == 403
    assert Receipt.objects.count() == 1


def test_unmatched_webhook_persists_before_later_provider_response_binds_it():
    item = queued()
    provider_id = str(uuid.uuid4())
    with override_settings(RESEND_WEBHOOK_SECRET=SECRET):
        assert post_webhook(webhook(provider_id)).status_code == 200
    assert Receipt.objects.get().mail_id is None
    with patch("noel_delivery.send", return_value=provider_id):
        dispatch()
    item.refresh_from_db()
    assert Receipt.objects.get().mail_id == item.id and item.delivery_status == "DELIVERED"


def test_reconciliation_reads_provider_fact_and_never_resends():
    provider_id = str(uuid.uuid4())
    item = queued(
        state="DELIVERY_UNKNOWN",
        delivery_status="DELIVERY_UNKNOWN",
        transport="resend",
        provider_id=provider_id,
    )
    with patch(
        "noel_delivery.provider_request",
        return_value={"id": provider_id, "last_event": "delivered"},
    ) as get:
        assert reconcile_one(Mail, Receipt)
        assert get.call_args.args == (f"/emails/{provider_id}",)
    item.refresh_from_db()
    assert item.delivery_status == "DELIVERED" and item.payload == ""


@pytest.mark.concurrent_db
def test_two_workers_cannot_dispatch_the_same_lease():
    item = queued()
    started = Event()
    finish = Event()

    def send(*args):
        started.set()
        assert finish.wait(15)
        return str(uuid.uuid4())

    def worker():
        close_old_connections()
        try:
            return dispatch()
        finally:
            close_old_connections()

    try:
        with (
            patch("noel_delivery.send", side_effect=send),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(worker)
            assert started.wait(10)
            second = pool.submit(worker)
            try:
                assert second.result(timeout=10) is False
            finally:
                finish.set()
            assert first.result(timeout=10)
        assert Mail.objects.get(pk=item.id).attempts == 1
    finally:
        finish.set()
        Receipt.objects.filter(mail=item).delete()
        Mail.objects.filter(pk=item.pk).delete()


def test_https_transport_uses_fixed_endpoint_bound_timeout_and_idempotency_header():
    from email.message import Message
    from urllib.error import HTTPError

    from noel_delivery import NoRedirect, provider_request

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n):
            return b'{"id":"opaque-provider-response"}'

    with (
        override_settings(RESEND_API_KEY="synthetic-only"),
        patch("urllib.request.OpenerDirector.open", return_value=Response()) as send,
    ):
        assert (
            provider_request("/emails", "POST", {"text": "PRIVATE_TRANSPORT_CANARY"}, "stable-key")[
                "id"
            ]
            == "opaque-provider-response"
        )
        request = send.call_args.args[0]
        assert request.full_url == "https://api.resend.com/emails"
        assert request.get_header("Idempotency-key") == "stable-key"
        assert send.call_args.kwargs["timeout"] == 10
    assert NoRedirect().redirect_request(None, None, None, None, None, None) is None
    headers = Message()
    headers["Retry-After"] = "17"
    with (
        override_settings(RESEND_API_KEY="synthetic-only"),
        patch(
            "urllib.request.OpenerDirector.open",
            side_effect=HTTPError("fixed", 429, "hidden", headers, None),
        ),
    ):
        with pytest.raises(DeliveryError) as failure:
            provider_request("/emails", "POST", {}, "stable-key")
        assert failure.value.delay == 17 and not failure.value.permanent


def test_missing_provider_id_can_only_be_bound_by_proven_notification_tag():
    from noel_delivery import reconcile_notification

    item = queued(
        state="DELIVERY_UNKNOWN",
        delivery_status="DELIVERY_UNKNOWN",
        transport="resend",
        first_attempt_at=timezone.now(),
    )
    provider_id = str(uuid.uuid4())
    response = {
        "id": provider_id,
        "last_event": "delivered",
        "tags": [{"name": "notification", "value": str(uuid.uuid4())}],
    }
    with patch("noel_delivery.provider_request", return_value=response):
        with pytest.raises(ValueError):
            reconcile_notification(Mail, Receipt, item.id, provider_id)
        item.refresh_from_db()
        assert item.provider_id is None
        response["tags"][0]["value"] = str(item.id)
        assert reconcile_notification(Mail, Receipt, item.id, provider_id) == "DELIVERED"


def test_zoho_ambiguous_send_never_retries_automatically():
    item = queued()
    with (
        override_settings(MAIL_PROVIDER="zoho"),
        patch("noel_delivery.send", side_effect=DeliveryError(ambiguous=True)) as send,
    ):
        assert dispatch()
        assert not dispatch()
        send.assert_called_once()
    item.refresh_from_db()
    assert item.state == item.delivery_status == "DELIVERY_UNKNOWN" and item.payload == ""


def test_zoho_worker_death_is_unknown_not_an_unsafe_second_smtp_send():
    item = queued(
        state="RUNNING",
        transport="zoho",
        first_attempt_at=timezone.now(),
        lease_until=timezone.now() - timedelta(seconds=1),
        ambiguous=True,
    )
    with override_settings(MAIL_PROVIDER="zoho"), patch("noel_delivery.send") as send:
        assert dispatch()
        send.assert_not_called()
    item.refresh_from_db()
    assert item.state == "DELIVERY_UNKNOWN"


def test_zoho_requires_tls_known_eu_host_and_authorised_inbox():
    from noel_delivery import zoho_connection

    data = {"from": "probe@example.invalid", "email": "probe@example.invalid"}
    with override_settings(
        SMTP_HOST="attacker.invalid",
        MAIL_LIVE_ENABLED=True,
        SMTP_USERNAME="probe@example.invalid",
        SMTP_PASSWORD="synthetic-only",
    ):
        with pytest.raises(DeliveryError):
            zoho_connection(data)
    with override_settings(
        SMTP_HOST="smtp.zoho.eu",
        MAIL_LIVE_ENABLED=True,
        SMTP_USERNAME="probe@example.invalid",
        SMTP_PASSWORD="synthetic-only",
        SMTP_PORT=465,
        SMTP_USE_SSL=True,
        SMTP_USE_TLS=False,
        MAIL_TEST_RECIPIENTS={"probe@example.invalid"},
    ):
        with patch("noel_delivery.get_connection") as connection:
            zoho_connection(data)
            assert connection.call_args.kwargs["use_ssl"]
            assert connection.call_args.kwargs["timeout"] == 10
            with pytest.raises(DeliveryError):
                zoho_connection(dict(data, email="other@example.invalid"))


def test_changed_provider_credentials_do_not_retry_in_a_different_account():
    item = queued()
    with live(), patch("noel_delivery.send", side_effect=DeliveryError(ambiguous=True)) as send:
        assert dispatch()
        ready(item)
        with override_settings(RESEND_API_KEY="another-account-synthetic-key"):
            assert dispatch()
        send.assert_called_once()
    item.refresh_from_db()
    assert item.state == "DELIVERY_UNKNOWN"


def test_deleted_inflight_mail_is_not_recreated_or_resent():
    item = queued()

    def send(*args):
        Mail.objects.filter(pk=item.id).delete()
        return str(uuid.uuid4())

    with patch("noel_delivery.send", side_effect=send):
        assert dispatch()
        assert not dispatch()
    assert not Mail.objects.filter(pk=item.id).exists()


def test_zoho_ack_is_submitted_only_and_uses_single_recipient():
    item = queued()
    messages = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_messages(self, items):
            messages.extend(items)
            return 1

    with (
        override_settings(MAIL_PROVIDER="zoho"),
        patch("noel_delivery.zoho_connection", return_value=Connection()),
    ):
        assert dispatch()
    item.refresh_from_db()
    assert item.state == "SENT" and item.delivery_status == "SUBMITTED"
    assert (
        messages[0].to == ["probe@example.invalid"] and not messages[0].cc and not messages[0].bcc
    )
    assert str(item.id) in messages[0].extra_headers["Message-ID"]
