import json

from cryptography.exceptions import InvalidTag
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .draw_service import StateConflict
from .envelopes import alert_unavailable
from .models import Membership, SealedDraw
from .private_space import purchase, recipient, save_purchase
from .views import authenticated, error, membership
from .wishlists import Conflict


def actor(request):
    if set(request.GET) != {"event_id"} or len(request.GET.getlist("event_id")) != 1:
        raise ValueError("Événement explicite requis, sans autre identifiant.")
    return membership(request)


def body(request):
    if len(request.body) > 8192:
        raise ValueError("Requête trop grande.")
    value = json.loads(request.body)
    if not isinstance(value, dict):
        raise ValueError("Objet requis.")
    return value


def unavailable():
    alert_unavailable()
    return error("Espace privé temporairement indisponible. Aucun nouveau tirage n'est créé.", 503)


def boundary(view):
    from functools import wraps

    @wraps(view)
    def wrapped(request):
        try:
            return view(request)
        except Membership.DoesNotExist:
            return error(status=404)
        except (StateConflict, Conflict) as exc:
            if request.path == "/private":
                return render(
                    request,
                    "vault/private.html",
                    {"blocked": True, "message": str(exc)},
                    status=409,
                )
            return error(str(exc), 409)
        except (InvalidTag, KeyError, ObjectDoesNotExist, StopIteration):
            return unavailable()
        except (ValueError, TypeError, ValidationError):
            return error("Requête privée invalide.", 400)

    return wrapped


@require_http_methods(["GET"])
@authenticated
@boundary
def my_recipient(request):
    return JsonResponse(recipient(actor(request)))


@require_http_methods(["POST"])
@authenticated
@boundary
def reveal(request):
    member = actor(request)
    if body(request) != {}:
        raise ValueError()
    return JsonResponse(recipient(member, reveal=True))


@require_http_methods(["GET", "PUT"])
@authenticated
@boundary
def my_purchase(request):
    member = actor(request)
    return JsonResponse(
        purchase(member) if request.method == "GET" else save_purchase(member, body(request))
    )


@require_http_methods(["GET", "POST"])
@authenticated
@boundary
def private_page(request):
    member = actor(request)
    if member.event.state not in {"DRAWN", "CLOSED"}:
        return render(
            request,
            "vault/private.html",
            {
                "member": member,
                "blocked": True,
                "message": "Événement annulé : aucun cadeau à consulter."
                if member.event.state == "CANCELLED"
                else (
                    "Le tirage n’est pas encore disponible. Consulte les règles "
                    "pour suivre la préparation."
                ),
            },
        )
    value = None
    preparation = None
    message = None
    status = 200
    if request.method == "POST":
        if request.POST.get("action") == "reveal":
            value = recipient(member, reveal=True)
            preparation = purchase(member)
        elif request.POST.get("action") in {"purchase", "refresh"}:
            value = recipient(member)
            previous = purchase(member)
            chosen = request.POST.get("wish_id") or None
            selected_version = (
                previous["wish_revision"]
                if chosen == previous["wish_id"] and request.POST["action"] != "refresh"
                else value["revision"]
            )
            try:
                preparation = save_purchase(
                    member,
                    {
                        "revision": int(request.POST.get("revision", "")),
                        "state": request.POST.get("state"),
                        "wish_id": chosen,
                        "wish_revision": selected_version if chosen else None,
                        "note": request.POST.get("note", ""),
                    },
                )
                message = "Ta préparation privée est enregistrée."
            except (ValueError, Conflict, StateConflict):
                status = 409
                preparation = previous
                preparation["note"] = request.POST.get("note", "")[:1000]
                preparation["revision"] = request.POST.get("revision", "")
                preparation["state"] = request.POST.get("state", "")
                preparation["wish_id"] = chosen
                message = (
                    "La préparation a changé ou la saisie est invalide. Vérifie avant de renvoyer."
                )
        else:
            raise ValueError()
    return render(
        request,
        "vault/private.html",
        {"member": member, "result": value, "preparation": preparation, "message": message},
        status=status,
    )


@require_http_methods(["GET"])
@authenticated
@boundary
def availability(request):
    member = actor(request)
    state = member.event.state
    available = (
        state in {"DRAWN", "CLOSED"}
        and SealedDraw.objects.filter(event=member.event, release_state="AVAILABLE").exists()
    )
    return JsonResponse({"state": state, "available": available})
