"""Operator-only migration and rewrapping. Never emits plaintext or rerolls."""

from django.conf import settings
from django.db import transaction

from . import envelopes
from .draw_crypto import context as draw_context
from .models import EventDataKey, PrivateEvent, SealedDraw, WishlistRevision
from .wishlists import aad, open_revision


@transaction.atomic
def migrate_event(event_id):
    event = PrivateEvent.objects.select_for_update().get(pk=event_id)
    for record in WishlistRevision.objects.filter(
        wishlist__member__event=event, schema_version=1
    ).select_related("wishlist__member__event"):
        value = open_revision(record.wishlist, record.revision)
        nonce, ciphertext = envelopes.encrypt(
            event, value, aad(record.wishlist, record.revision, 2)
        )
        record.schema_version = 2
        record.key_id = "evt:" + str(event.id)
        record.nonce = nonce
        record.ciphertext = ciphertext
        record.save(update_fields=["schema_version", "key_id", "nonce", "ciphertext"])


@transaction.atomic
def rotate_event(event_id, target_key_id):
    if target_key_id not in settings.DRAW_MASTER_KEYS:
        raise ValueError("Configured master key required")
    event = PrivateEvent.objects.select_for_update().get(pk=event_id)
    private = EventDataKey.objects.filter(event=event).first()
    if private and private.key_id != target_key_id:
        data_key = envelopes.event_key(event)
        nonce = envelopes.reserve("master:" + target_key_id)
        private.wrapped_key = envelopes.provider.wrap(
            target_key_id, nonce, data_key, envelopes.key_context(event.id)
        )
        private.wrap_nonce = nonce
        private.key_id = target_key_id
        private.save(update_fields=["key_id", "wrap_nonce", "wrapped_key"])
    draw = SealedDraw.objects.select_related("event", "job").filter(event=event).first()
    if draw and draw.key_id != target_key_id:
        context = draw_context(event, draw.job, "draw-key")
        data_key = envelopes.provider.unwrap(
            draw.key_id, bytes(draw.wrap_nonce), bytes(draw.wrapped_key), context
        )
        nonce = envelopes.reserve("master:" + target_key_id)
        draw.wrapped_key = envelopes.provider.wrap(target_key_id, nonce, data_key, context)
        draw.wrap_nonce = nonce
        draw.key_id = target_key_id
        draw.save(update_fields=["key_id", "wrap_nonce", "wrapped_key"])
    # Existing backups still contain their historical wrapped key: retain old master versions.
