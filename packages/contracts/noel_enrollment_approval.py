"""Offline verifier signatures, separate from the organizer command credentials."""

import base64
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from noel_contracts import canonical


def sign_approval(identity, claim_id, comparison, vault_origin):
    now = int(time.time())
    payload = {
        "role": "Independent vault operator",
        "verifier_id": identity["id"],
        "claim_id": str(claim_id),
        "comparison": comparison.upper(),
        "vault_origin": vault_origin,
        "identity_verified": True,
        "issued_at": now,
        "expires_at": now + 300,
    }
    key = Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(identity["private_key"]))
    return payload | {"signature": base64.urlsafe_b64encode(key.sign(canonical(payload))).decode()}


def verify_approval(approval, public_key, vault_origin):
    if set(approval) != {
        "role",
        "verifier_id",
        "claim_id",
        "comparison",
        "vault_origin",
        "identity_verified",
        "issued_at",
        "expires_at",
        "signature",
    }:
        raise ValueError("Approval schema invalid.")
    now = int(time.time())
    if (
        approval["role"] != "Independent vault operator"
        or approval["identity_verified"] is not True
        or approval["vault_origin"] != vault_origin
        or type(approval["issued_at"]) is not int
        or type(approval["expires_at"]) is not int
        or not now - 300 <= approval["issued_at"] <= now + 30
        or not now < approval["expires_at"] <= approval["issued_at"] + 300
    ):
        raise ValueError("Approval scope/expiry invalid.")
    payload = {k: v for k, v in approval.items() if k != "signature"}
    Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(public_key)).verify(
        base64.urlsafe_b64decode(approval["signature"]), canonical(payload)
    )
