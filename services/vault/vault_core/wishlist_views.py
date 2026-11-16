import json

from cryptography.exceptions import InvalidTag
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .envelopes import alert_unavailable
from .models import Membership, MerchantRequest, WishlistRevision
from .views import authenticated, error, membership
from .wishlist_forms import WishFormSet
from .wishlists import (
    Conflict,
    Unavailable,
    WishlistInputError,
    get_list,
    hostname,
    save_list,
    shopping_advice,
    snapshot,
)

INPUT_FIELDS = {
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


def output(member, listing, selected=None):
    return {
        "revision": listing.revision if listing else 0,
        "state": listing.state if listing else "DRAFT",
        "viewed_revision": selected or (listing.revision if listing else 0),
        "wishes": snapshot(listing, selected) if listing else [],
        "shipping_included": member.event.shipping_included,
        "buyer_country": member.country,
        "notice": (
            "Prix et disponibilité indicatifs. Achat hors application, livraison chez l'acheteur."
        ),
    }


def read_body(request):
    if len(request.body) > 16384:
        raise WishlistInputError("Liste trop grande.")
    body = json.loads(request.body)
    if not isinstance(body, dict):
        raise WishlistInputError("Objet requis.")
    return body


@require_http_methods(["GET", "PUT"])
@authenticated
def wishlist(request):
    try:
        member = membership(request)
        listing = get_list(member)
        if member.event.state in {"CANCELLED", "ARCHIVED"}:
            return error("Événement indisponible.", 409)
        if request.method == "GET":
            selected = request.GET.get("revision")
            if selected is not None:
                selected = int(selected)
                if listing is None or not 1 <= selected <= listing.revision:
                    raise WishlistRevision.DoesNotExist()
            return JsonResponse(output(member, listing, selected))
        data = read_body(request)
        if set(data) != {"revision", "wishes"}:
            raise WishlistInputError("Champs de liste invalides.")
        listing = save_list(member, data["revision"], data["wishes"])
        return JsonResponse(output(member, listing))
    except Membership.DoesNotExist:
        return error(status=404)
    except WishlistRevision.DoesNotExist:
        return error("Révision indisponible.", 404)
    except Conflict as exc:
        return error(str(exc), 409)
    except (InvalidTag, Unavailable, KeyError):
        alert_unavailable()
        return error("Sauvegarde temporairement indisponible.", 503)
    except (ValueError, TypeError, ValidationError) as exc:
        return error(str(exc) if isinstance(exc, WishlistInputError) else "Liste invalide.")


@require_http_methods(["POST"])
@authenticated
def validate(request):
    try:
        member = membership(request)
        data = read_body(request)
        if set(data) != {"revision"}:
            raise WishlistInputError("Révision requise.")
        listing = get_list(member)
        items = snapshot(listing) if listing else []
        items = [{k: item[k] for k in INPUT_FIELDS} for item in items]
        listing = save_list(member, data["revision"], items, validate=True)
        return JsonResponse(output(member, listing))
    except Membership.DoesNotExist:
        return error(status=404)
    except Conflict as exc:
        return error(str(exc), 409)
    except (InvalidTag, Unavailable, KeyError):
        alert_unavailable()
        return error("Sauvegarde temporairement indisponible.", 503)
    except (ValueError, TypeError, ValidationError) as exc:
        return error(str(exc) if isinstance(exc, WishlistInputError) else "Liste invalide.")


@require_http_methods(["POST"])
@authenticated
@transaction.atomic
def merchant_request(request):
    try:
        member = membership(request)
        data = read_body(request)
        if set(data) != {"hostname"}:
            raise WishlistInputError("Domaine requis.")
        name = hostname(data["hostname"])
        Membership.objects.select_for_update().get(pk=member.pk)
        if MerchantRequest.objects.filter(member=member).count() >= 10:
            return error("Dix demandes maximum par événement.", 429)
        MerchantRequest.objects.get_or_create(member=member, hostname=name)
        return JsonResponse({"requested": True}, status=202)
    except Membership.DoesNotExist:
        return error(status=404)
    except (ValueError, TypeError, KeyError, ValidationError):
        return error("Domaine invalide.")


@require_http_methods(["GET", "POST"])
@authenticated
def editor(request):
    try:
        member = membership(request)
        if member.event.state in {"CANCELLED", "ARCHIVED"}:
            return error("Événement indisponible.", 409)
        listing = get_list(member)
        items = snapshot(listing) if listing else []
        current = {i["slot"]: i for i in items}
        initial = []
        for slot in (1, 2, 3):
            item = current.get(slot, {})
            initial.append(
                dict(
                    item,
                    price=(
                        f"{item['price_eur_cents'] // 100}.{item['price_eur_cents'] % 100:02d}"
                        if item.get("price_eur_cents") is not None
                        else ""
                    ),
                )
            )
        formset = WishFormSet(request.POST if request.method == "POST" else None, initial=initial)
        message = None
        status = 200
        if request.method == "POST" and formset.is_valid():
            try:
                revision = int(request.POST.get("revision", ""))
                wishes = []
                for slot, form in enumerate(formset, 1):
                    row = form.cleaned_data
                    if not any(row.get(k) for k in ("title", "url", "price", "note")):
                        continue
                    wishes.append(
                        {
                            "slot": slot,
                            "title": row["title"],
                            "url": row["url"],
                            "price_eur_cents": row["price"],
                            "currency": row["currency"],
                            "price_date": row["price_date"].isoformat()
                            if row["price_date"]
                            else "",
                            "note": row["note"],
                            "exact_model": row["exact_model"],
                            "equivalent_ok": row["equivalent_ok"],
                        }
                    )
                listing = save_list(
                    member, revision, wishes, validate=request.POST.get("action") == "validate"
                )
                items = snapshot(listing)
                message = (
                    "Tes trois souhaits sont validés."
                    if listing.state == "VALIDATED"
                    else "Brouillon sauvegardé."
                )
            except Conflict as exc:
                message = str(exc)
                status = 409
            except ValueError as exc:
                message = str(exc) if isinstance(exc, WishlistInputError) else "Liste invalide."
                status = 400
        elif request.method == "POST":
            status = 400
        return render(
            request,
            "vault/wishlist.html",
            {
                "member": member,
                "listing": listing,
                "formset": formset,
                "message": message,
                "saved": request.method == "POST" and status == 200,
                "advice": shopping_advice(items, member.country),
                "items": items,
                "submitted_revision": request.POST.get("revision")
                if request.method == "POST" and status != 200
                else None,
            },
            status=status,
        )
    except Membership.DoesNotExist:
        return error(status=404)
    except (InvalidTag, KeyError, Unavailable):
        alert_unavailable()
        return error("Liste temporairement indisponible.", 503)
    except (ValidationError, ValueError, TypeError):
        return error("Événement ou liste invalide.")
