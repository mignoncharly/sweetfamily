from django.db import transaction

from . import envelopes
from .draw_crypto import unseal
from .draw_engine import validate_result
from .draw_service import StateConflict, fingerprint
from .models import Membership, PrivateEvent, PrivatePurchaseState, SealedDraw, Wishlist
from .wishlists import Conflict, shopping_advice, snapshot

STATES = {"NOT_STARTED", "ORDERED", "RECEIVED", "READY", "GIVEN"}


def context(member, revision):
    return f"purchase:v1:{member.event_id}:{member.id}:{revision}".encode()


def authorized(member, write=False):
    event = PrivateEvent.objects.select_for_update().get(pk=member.event_id)
    member = Membership.objects.select_related("event").get(
        pk=member.pk, event=event, active=True, claimed_at__isnull=False
    )
    if event.state not in ({"DRAWN"} if write else {"DRAWN", "CLOSED"}):
        raise StateConflict("Espace privé indisponible dans cet état.")
    record = SealedDraw.objects.select_related("event", "job").get(event=event)
    if record.release_state != "AVAILABLE":
        raise StateConflict("Finalisation du tirage. Réessaie plus tard.")
    if (
        fingerprint(record.job.snapshot) != record.job.snapshot_digest
        or event.manifest_digest != record.job.snapshot_digest
        or event.frozen_manifest != record.job.snapshot
    ):
        raise KeyError("Sealed snapshot mismatch")
    value = unseal(record)
    ids = [row["id"] for row in record.job.snapshot["members"]]
    try:
        validate_result(ids, record.job.snapshot["exclusions"], value["permutation"])
    except (ValueError, TypeError):
        raise KeyError("Invalid sealed result") from None
    if value["manifest_version"] != record.manifest_version:
        raise KeyError("Manifest mismatch")
    target_id = dict(value["permutation"])[str(member.id)]
    target = Membership.objects.get(pk=target_id, event=event, active=True)
    return member, target


def recipient_output(member, target):
    listing = Wishlist.objects.get(member=target, state="VALIDATED")
    wishes = snapshot(listing)
    return {
        "recipient": {"display_name": target.display_name, "country": target.country},
        "revision": listing.revision,
        "wishes": wishes,
        "advice": shopping_advice(wishes, member.country),
    }


@transaction.atomic
def recipient(member, reveal=False):
    member, target = authorized(member)
    value = recipient_output(member, target)
    if reveal and not member.recipient_viewed:
        member.recipient_viewed = True
        member.save(update_fields=["recipient_viewed"])
    return value


def purchase_value(member):
    record = PrivatePurchaseState.objects.filter(member=member).first()
    if record is None:
        return {
            "revision": 0,
            "state": "NOT_STARTED",
            "wish_id": None,
            "wish_revision": None,
            "note": "",
        }
    value = envelopes.decrypt(
        member.event, record.nonce, record.ciphertext, context(member, record.revision)
    )
    if set(value) != {"state", "wish_id", "wish_revision", "note"} or value["state"] not in STATES:
        raise KeyError("Invalid private record")
    return dict(value, revision=record.revision)


def purchase_output(member, target):
    value = purchase_value(member)
    listing = Wishlist.objects.get(member=target, state="VALIDATED")
    chosen = None
    if value["wish_id"]:
        chosen = next(
            row
            for row in snapshot(listing, value["wish_revision"])
            if row["id"] == value["wish_id"]
        )
    return dict(
        value,
        selected_wish=chosen,
        current_wishlist_revision=listing.revision,
        wishlist_changed=bool(chosen and value["wish_revision"] != listing.revision),
    )


@transaction.atomic
def purchase(member):
    member, target = authorized(member)
    return purchase_output(member, target)


@transaction.atomic
def save_purchase(member, data):
    member, target = authorized(member, write=True)
    if not member.recipient_viewed:
        raise StateConflict("Découvre explicitement ton cadeau à préparer avant de choisir.")
    if not isinstance(data, dict) or set(data) != {
        "revision",
        "state",
        "wish_id",
        "wish_revision",
        "note",
    }:
        raise ValueError("Champs d'achat invalides.")
    old = purchase_value(member)
    if type(data["revision"]) is not int or data["revision"] != old["revision"]:
        raise Conflict("Une autre fenêtre a modifié ta préparation. Recharge la version courante.")
    if not isinstance(data["state"], str) or data["state"] not in STATES:
        raise ValueError("État d'achat invalide.")
    if not isinstance(data["note"], str) or len(data["note"]) > 1000:
        raise ValueError("Note privée trop longue.")
    listing = Wishlist.objects.get(member=target, state="VALIDATED")
    if data["wish_id"] is None:
        if data["wish_revision"] is not None or data["state"] != "NOT_STARTED":
            raise ValueError("Choisis un souhait avant de préparer le cadeau.")
    else:
        revision = data["wish_revision"]
        if type(revision) is not int or not 1 <= revision <= listing.revision:
            raise ValueError("Révision de souhait invalide.")
        if revision != listing.revision and (data["wish_id"], revision) != (
            old["wish_id"],
            old["wish_revision"],
        ):
            raise Conflict("Les souhaits ont changé. Consulte la liste courante avant de choisir.")
        if not any(row["id"] == data["wish_id"] for row in snapshot(listing, revision)):
            raise ValueError("Choix indisponible pour ton espace.")
    revision = old["revision"] + 1
    value = {key: data[key] for key in ("state", "wish_id", "wish_revision", "note")}
    nonce, ciphertext = envelopes.encrypt(member.event, value, context(member, revision))
    PrivatePurchaseState.objects.update_or_create(
        member=member, defaults={"revision": revision, "nonce": nonce, "ciphertext": ciphertext}
    )
    return purchase_output(member, target)


def ready_total(event):
    if (
        event.state not in {"DRAWN", "CLOSED"}
        or not SealedDraw.objects.filter(event=event, release_state="AVAILABLE").exists()
    ):
        return 0
    return sum(
        purchase_value(member)["state"] in {"READY", "GIVEN"}
        for member in event.members.filter(active=True, privatepurchasestate__isnull=False)
    )
