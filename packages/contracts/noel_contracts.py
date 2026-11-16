"""Public validation and wire format only; no service models or retained secrets."""

import base64
import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pycountry
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def country(value):
    if not isinstance(value, str) or pycountry.countries.get(alpha_2=value) is None:
        raise ValueError("Pays ISO invalide.")
    return value


def event_fields(data):
    if set(data) != {
        "title",
        "celebration_at",
        "wishlist_deadline",
        "timezone",
        "shipping_included",
        "handover",
    }:
        raise ValueError("Champs d'événement invalides.")
    for key, limit in (("title", 120), ("handover", 500)):
        if not isinstance(data[key], str) or not 1 <= len(data[key].strip()) <= limit:
            raise ValueError("Texte d'événement invalide.")
    if type(data["shipping_included"]) is not bool:
        raise ValueError("Règle de frais invalide.")
    ZoneInfo(data["timezone"])
    dates = [datetime.fromisoformat(data[k]) for k in ("celebration_at", "wishlist_deadline")]
    if any(d.tzinfo is None for d in dates) or dates[1] >= dates[0]:
        raise ValueError("Dates avec fuseau et échéance antérieure requises.")
    return data


def member_fields(data):
    if set(data) != {"id", "display_name", "country", "email"}:
        raise ValueError("Champs de membre invalides.")
    if not isinstance(data["id"], str):
        raise ValueError("Identifiant de membre invalide.")
    uuid.UUID(data["id"])
    if (
        not isinstance(data["display_name"], str)
        or not 1 <= len(data["display_name"].strip()) <= 80
    ):
        raise ValueError("Nom d'affichage invalide.")
    country(data["country"])
    return data


def digest(kind, payload):
    return hashlib.sha256(canonical({"type": kind, "payload": payload})).hexdigest()


def sign(kind, payload, private_key, command_id=None):
    message = {
        "id": str(command_id or uuid.uuid4()),
        "schema_version": 1,
        "timestamp": int(time.time()),
        "nonce": secrets.token_urlsafe(24),
        "type": kind,
        "payload": payload,
        "body_digest": digest(kind, payload),
    }
    message["signature"] = base64.urlsafe_b64encode(
        Ed25519PrivateKey.from_private_bytes(base64.urlsafe_b64decode(private_key)).sign(
            canonical(message)
        )
    ).decode()
    return message


def verify(message, public_key):
    if set(message) != {
        "id",
        "schema_version",
        "timestamp",
        "nonce",
        "type",
        "payload",
        "body_digest",
        "signature",
    }:
        raise ValueError("Enveloppe invalide.")
    if message["schema_version"] != 1 or type(message["timestamp"]) is not int:
        raise ValueError("Version invalide.")
    if abs(time.time() - message["timestamp"]) > 300:
        raise ValueError("Commande expirée.")
    uuid.UUID(message["id"])
    if not isinstance(message["nonce"], str) or not 24 <= len(message["nonce"]) <= 100:
        raise ValueError("Nonce invalide.")
    unsigned = {k: v for k, v in message.items() if k != "signature"}
    Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(public_key)).verify(
        base64.urlsafe_b64decode(message["signature"]), canonical(unsigned)
    )
    if message["body_digest"] != digest(message["type"], message["payload"]):
        raise ValueError("Empreinte invalide.")
    return message


def validate_projection(data):
    if set(data) - {"event_version"} != {
        "event_id",
        "projection_version",
        "event_state",
        "manifest_version",
        "draw_progress",
        "members",
        "ready_count",
    }:
        raise ValueError("Projection invalide.")
    if "event_version" in data and (
        type(data["event_version"]) is not int or data["event_version"] < 1
    ):
        raise ValueError("Version publique invalide.")
    uuid.UUID(data["event_id"])
    if type(data["projection_version"]) is not int or data["projection_version"] < 1:
        raise ValueError("Version invalide.")
    if data["event_state"] not in {
        "DRAFT",
        "OPEN",
        "CONFIRMING",
        "READY",
        "DRAWING",
        "DRAWN",
        "CLOSED",
        "ARCHIVED",
        "CANCELLED",
    }:
        raise ValueError("État invalide.")
    if data["manifest_version"] is not None and (
        type(data["manifest_version"]) is not int or data["manifest_version"] < 1
    ):
        raise ValueError("Manifeste invalide.")
    if data["draw_progress"] not in {
        "NOT_STARTED",
        "PROCESSING",
        "FINALIZING",
        "AVAILABLE",
        "ACTION_REQUIRED",
    }:
        raise ValueError("Progression invalide.")
    if not isinstance(data["members"], list) or len(data["members"]) > 20:
        raise ValueError("Membres invalides.")
    seen = set()
    for member in data["members"]:
        if set(member) - {"active"} != {
            "member_ref",
            "registration_confirmed",
            "wishlist_complete",
            "consent_received",
            "notification_state",
            "recipient_viewed",
        }:
            raise ValueError("Champ de membre interdit.")
        if "active" in member and type(member["active"]) is not bool:
            raise ValueError("Statut d'inscription invalide.")
        uuid.UUID(member["member_ref"])
        if member["member_ref"] in seen:
            raise ValueError("Membre dupliqué.")
        seen.add(member["member_ref"])
        if any(
            type(member[key]) is not bool
            for key in (
                "registration_confirmed",
                "wishlist_complete",
                "consent_received",
                "recipient_viewed",
            )
        ):
            raise ValueError("État de membre invalide.")
        if member["notification_state"] not in {
            "NONE",
            "QUEUED",
            "SUBMITTED",
            "ACCEPTED",
            "DELIVERED",
            "DEFERRED",
            "REJECTED",
            "FAILED",
            "DELIVERY_UNKNOWN",
        }:
            raise ValueError("Notification invalide.")
    if type(data["ready_count"]) is not int or not 0 <= data["ready_count"] <= len(seen):
        raise ValueError("Total invalide.")
    return data
