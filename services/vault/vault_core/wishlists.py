import base64
import ipaddress
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlsplit, urlunsplit

import pycountry
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from noel_contracts import country

from . import envelopes
from .models import GiftWish, Membership, PrivateEvent, Wishlist, WishlistRevision


class WishlistInputError(ValueError):
    pass


class Conflict(ValueError):
    pass


class Unavailable(ValueError):
    pass


def merchants():
    # A local operator-maintained file only. Never resolve/fetch participant-supplied URLs.
    return json.loads(Path(settings.MERCHANT_ALLOWLIST).read_text(encoding="utf-8"))


def hostname(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 253
        or any(ord(c) < 33 for c in value)
    ):
        raise WishlistInputError("Domaine marchand invalide.")
    if any(c in value for c in "/:@\\%?#"):
        raise WishlistInputError("Domaine marchand invalide.")
    name = value.encode("idna").decode("ascii").lower()
    if name.startswith("www."):
        name = name[4:]
    if name.endswith((".", ".local", ".localhost", ".internal", ".invalid")) or "." not in name:
        raise WishlistInputError("Domaine marchand invalide.")
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise WishlistInputError("Adresse IP refusée.")
    if any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in name.split(".")
    ):
        raise WishlistInputError("Domaine marchand invalide.")
    return name


def merchant_url(value):
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or "\\" in value
        or any(ord(c) < 33 for c in value)
    ):
        raise WishlistInputError("Lien HTTPS marchand invalide.")
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise WishlistInputError("Lien HTTPS sans identifiants requis.")
    if parts.port not in (None, 443):
        raise WishlistInputError("Port non autorisé.")
    name = hostname(parts.hostname)
    if name not in merchants():
        raise WishlistInputError("Marchand non approuvé. Demande son ajout.")
    # Preserve all query parameters/variants. Do not silently strip a product-significant parameter.
    return urlunsplit(
        (
            "https",
            parts.hostname.encode("idna").decode("ascii").lower(),
            parts.path or "/",
            parts.query,
            parts.fragment,
        )
    ), name


def duplicate_key(url):
    parts = urlsplit(url)
    # Comparison only: tracking/fragment changes never create an extra gift idea.
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"}
    ]
    return (hostname(parts.hostname), parts.path or "/", tuple(sorted(query)))


def euro_cents(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d?)(?:[.,]\d{1,2})?", value):
        raise WishlistInputError("Prix EUR ambigu : deux décimales maximum.")
    whole, *fraction = re.split("[.,]", value)
    result = int(whole) * 100 + int((fraction[0] if fraction else "").ljust(2, "0") or "0")
    if not 1 <= result <= 4999:
        raise WishlistInputError("Chaque souhait doit coûter de 0,01 € à 49,99 €.")
    return result


def validate_items(items, complete=False):
    if not isinstance(items, list) or len(items) > 3 or (complete and len(items) != 3):
        raise WishlistInputError("Il faut exactement trois souhaits pour valider.")
    cleaned = []
    slots = set()
    links = set()
    expected = {
        "slot",
        "title",
        "url",
        "price_eur_cents",
        "currency",
        "price_date",
        "note",
        "exact_model",
        "equivalent_ok",
    }
    for item in items:
        if not isinstance(item, dict) or set(item) != expected:
            raise WishlistInputError("Champs de souhait invalides.")
        if type(item["slot"]) is not int or item["slot"] not in {1, 2, 3} or item["slot"] in slots:
            raise WishlistInputError("Emplacement invalide.")
        slots.add(item["slot"])
        for field, limit, required in (("title", 160, complete), ("note", 1000, False)):
            if (
                not isinstance(item[field], str)
                or len(item[field]) > limit
                or (required and not item[field].strip())
            ):
                raise WishlistInputError("Titre ou précision invalide.")
        if not (item["price_eur_cents"] is None and not complete) and (
            type(item["price_eur_cents"]) is not int or not 1 <= item["price_eur_cents"] <= 4999
        ):
            raise WishlistInputError("Prix entier requis entre 1 et 4 999 centimes.")
        if (
            not isinstance(item["currency"], str)
            or pycountry.currencies.get(alpha_3=item["currency"]) is None
        ):
            raise WishlistInputError("Devise ISO invalide.")
        if not isinstance(item["price_date"], str):
            raise WishlistInputError("Date du prix requise.")
        declared = date.fromisoformat(item["price_date"]) if item["price_date"] else None
        if complete and declared is None:
            raise WishlistInputError("Date du prix requise.")
        if declared and declared > timezone.localdate():
            raise WishlistInputError("La date du prix ne peut pas être future.")
        if any(type(item[k]) is not bool for k in ("exact_model", "equivalent_ok")):
            raise WishlistInputError("Choix de modèle invalide.")
        if item["exact_model"] and item["equivalent_ok"]:
            raise WishlistInputError("Choisis modèle exact ou équivalent, pas les deux.")
        if item["url"]:
            url, host = merchant_url(item["url"])
            key = duplicate_key(url)
            if key in links:
                raise WishlistInputError("Deux liens semblent désigner le même souhait.")
            links.add(key)
        elif item["url"] == "" and not complete:
            url, host = "", ""
        else:
            raise WishlistInputError("Lien marchand requis.")
        cleaned.append(
            dict(
                item,
                title=item["title"].strip(),
                url=url,
                merchant_domain=host,
                indicative=True,
                eur_estimate=item["currency"] != "EUR",
            )
        )
    return sorted(cleaned, key=lambda item: item["slot"])


def aad(wishlist, revision, version=1):
    context = f"wishlist:v{version}:{wishlist.member.event_id}:{wishlist.member_id}"
    return f"{context}:{wishlist.id}:{revision}".encode()


def open_revision(wishlist, revision):
    record = wishlist.history.get(revision=revision)
    if record.schema_version == 2:
        return envelopes.decrypt(
            wishlist.member.event, record.nonce, record.ciphertext, aad(wishlist, revision, 2)
        )
    if record.schema_version != 1:
        raise KeyError("Unsupported envelope")
    key = settings.WISHLIST_KEYS[record.key_id]
    raw = AESGCM(base64.urlsafe_b64decode(key)).decrypt(
        bytes(record.nonce), bytes(record.ciphertext), aad(wishlist, revision)
    )
    return json.loads(raw)


def snapshot(wishlist, revision=None):
    selected = wishlist.revision if revision is None else revision
    if selected == 0:
        return []
    return open_revision(wishlist, selected)


def get_list(member):
    # Explicitly authorized read; GET must not create a list or slots.
    listing = Wishlist.objects.filter(member=member).first()
    if listing is not None:
        # The caller already authorized and loaded this member (usually with its event).
        # Reuse it for envelope AAD instead of reloading member/event during every read.
        listing.member = member
    return listing


@transaction.atomic
def save_list(member, expected_revision, items, validate=False):
    event = PrivateEvent.objects.select_for_update().get(pk=member.event_id)
    current_member = Membership.objects.get(pk=member.pk, active=True, claimed_at__isnull=False)
    current_member.event = event
    if event.state not in {"OPEN", "CONFIRMING", "READY", "DRAWN"}:
        raise Conflict("La liste n'est pas modifiable dans cet état.")
    if type(expected_revision) is not int:
        raise WishlistInputError("Révision entière requise.")
    wishlist = get_list(current_member)
    if (wishlist.revision if wishlist else 0) != expected_revision:
        raise Conflict("Une autre fenêtre a modifié tes souhaits. Recharge la version courante.")
    if wishlist is None:
        wishlist = Wishlist.objects.create(member=current_member)
        GiftWish.objects.bulk_create([GiftWish(wishlist=wishlist, slot=i) for i in (1, 2, 3)])
    # Once validated, edits keep exactly three valid wishes, including after draw.
    complete = validate or wishlist.state == "VALIDATED" or event.state == "DRAWN"
    cleaned = validate_items(items, complete=complete)
    ids = {slot.slot: str(slot.id) for slot in wishlist.slots.all()}
    for item in cleaned:
        item["id"] = ids[item["slot"]]
        item["shipping_included"] = event.shipping_included
    revision = wishlist.revision + 1
    nonce, encrypted = envelopes.encrypt(event, cleaned, aad(wishlist, revision, 2))
    WishlistRevision.objects.create(
        wishlist=wishlist,
        revision=revision,
        schema_version=2,
        key_id="evt:" + str(event.id),
        nonce=nonce,
        ciphertext=encrypted,
    )
    wishlist.revision = revision
    wishlist.state = "VALIDATED" if complete else "DRAFT"
    wishlist.validated_at = timezone.now() if complete else None
    wishlist.save()
    from .notifications import schedule_digest

    schedule_digest(event)
    return wishlist


def shopping_advice(wishes, buyer_country):
    country(buyer_country)
    approved = merchants()
    result = []
    for wish in wishes:
        searches = [
            {
                "name": m["name"],
                "url": m["search"] + quote(wish["title"]),
            }
            for m in approved.values()
            if m["country"] == buyer_country and m.get("search")
        ]
        result.append(
            {
                "slot": wish["slot"],
                "copy_text": wish["title"],
                "reference_url": wish["url"],
                "merchant_domain": wish["merchant_domain"],
                "searches": searches,
            }
        )
    return {
        "buyer_country": buyer_country,
        "notice": (
            "Ce lien sert de référence. Vérifie le même article sur une boutique "
            "qui livre chez toi."
        ),
        "delivery": "À recevoir chez toi et à apporter au réveillon.",
        "price_notice": (
            "Prix, frais et disponibilité indicatifs. Aucun anonymat garanti chez le marchand."
        ),
        "items": result,
    }
