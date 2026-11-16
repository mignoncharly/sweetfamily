"""Central authenticated envelopes. Local provider is configured; no KMS is connected."""

import base64
import json
import logging
import secrets
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import IntegrityError, transaction
from noel_contracts import canonical

from .models import DrawNonce, EventDataKey, PrivatePurchaseState, SecurityEvent, WishlistRevision


class MasterKeyProvider(Protocol):
    def wrap(self, key_id: str, nonce: bytes, data_key: bytes, context: bytes) -> bytes: ...
    def unwrap(self, key_id: str, nonce: bytes, wrapped: bytes, context: bytes) -> bytes: ...


class LocalMasterKeyProvider:
    def wrap(self, key_id, nonce, data_key, context):
        key = base64.urlsafe_b64decode(settings.DRAW_MASTER_KEYS[key_id])
        return AESGCM(key).encrypt(nonce, data_key, context)

    def unwrap(self, key_id, nonce, wrapped, context):
        key = base64.urlsafe_b64decode(settings.DRAW_MASTER_KEYS[key_id])
        return AESGCM(key).decrypt(nonce, wrapped, context)


provider: MasterKeyProvider = LocalMasterKeyProvider()


def reserve(key_ref):
    for _ in range(5):
        nonce = secrets.token_bytes(12)
        try:
            with transaction.atomic():
                DrawNonce.objects.create(key_ref=key_ref, nonce=nonce)
            return nonce
        except IntegrityError:
            if not DrawNonce.objects.filter(key_ref=key_ref, nonce=nonce).exists():
                raise
    raise RuntimeError("Nonce allocation unavailable")


def key_context(event_id):
    return f"private-key:v1:{event_id}".encode()


def event_key(event, create=False):
    # Mutations call under the event row lock; reads never generate replacement keys.
    record = EventDataKey.objects.filter(event=event).first()
    if record is None:
        if (
            not create
            or WishlistRevision.objects.filter(
                wishlist__member__event=event, schema_version=2
            ).exists()
            or PrivatePurchaseState.objects.filter(member__event=event).exists()
        ):
            raise KeyError("Event key unavailable")
        data_key = AESGCM.generate_key(bit_length=256)
        key_id = settings.DRAW_ACTIVE_KEY
        nonce = reserve("master:" + key_id)
        wrapped = provider.wrap(key_id, nonce, data_key, key_context(event.id))
        EventDataKey.objects.create(
            event=event, key_id=key_id, wrap_nonce=nonce, wrapped_key=wrapped
        )
        return data_key
    return provider.unwrap(
        record.key_id, bytes(record.wrap_nonce), bytes(record.wrapped_key), key_context(event.id)
    )


def encrypt(event, value, context):
    key = event_key(event, create=True)
    nonce = reserve("private:" + str(event.id))
    return nonce, AESGCM(key).encrypt(nonce, canonical(value), context)


def decrypt(event, nonce, ciphertext, context):
    raw = AESGCM(event_key(event)).decrypt(bytes(nonce), bytes(ciphertext), context)
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        raise KeyError("Invalid private envelope") from None


def alert_unavailable():
    # Category-only durable alert, no exception, model string, key, payload or association.
    SecurityEvent.objects.create(category="private_data_unavailable")
    logging.getLogger("vault.security").warning("private_data_unavailable")
