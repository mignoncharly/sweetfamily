import json

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from noel_contracts import canonical

from .envelopes import provider, reserve


def context(event, job, kind):
    return f"{kind}:v1:{event.id}:{job.id}:{job.snapshot_digest}".encode()


def seal(event, job, permutation):
    key_id = settings.DRAW_ACTIVE_KEY
    data_key = AESGCM.generate_key(bit_length=256)
    wrap_nonce = reserve("master:" + key_id)
    nonce = reserve("dek:" + str(event.id))
    wrapped = provider.wrap(key_id, wrap_nonce, data_key, context(event, job, "draw-key"))
    ciphertext = AESGCM(data_key).encrypt(
        nonce,
        canonical({"manifest_version": event.manifest_version, "permutation": permutation}),
        context(event, job, "draw"),
    )
    return {
        "key_id": key_id,
        "wrap_nonce": wrap_nonce,
        "wrapped_key": wrapped,
        "nonce": nonce,
        "ciphertext": ciphertext,
    }


def unseal(record):
    # Internal helper for later authorized reads and tests; no business/debug endpoint.
    if record.schema_version != 1:
        raise KeyError("Unsupported sealed schema")
    data_key = provider.unwrap(
        record.key_id,
        bytes(record.wrap_nonce),
        bytes(record.wrapped_key),
        context(record.event, record.job, "draw-key"),
    )
    return json.loads(
        AESGCM(data_key).decrypt(
            bytes(record.nonce), bytes(record.ciphertext), context(record.event, record.job, "draw")
        )
    )
