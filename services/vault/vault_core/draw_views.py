import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .draw_service import StateConflict, consent, current_manifest, withdraw
from .models import Membership, SealedDraw
from .views import authenticated, error, membership


@require_http_methods(["GET"])
@authenticated
def roster(request):
    try:
        member = membership(request)
        if member.event.state not in {"CONFIRMING", "READY"}:
            raise StateConflict("Aucune proposition gelée à confirmer.")
        value = current_manifest(member.event)
        return JsonResponse({"manifest": value, "manifest_digest": member.event.manifest_digest})
    except Membership.DoesNotExist:
        return error(status=404)
    except (ValueError, ValidationError):
        return error("Règles indisponibles ou modifiées.", 409)


@require_http_methods(["POST"])
@authenticated
def roster_consent(request):
    try:
        member = membership(request)
        data = json.loads(request.body)
        if set(data) != {"manifest_version", "manifest_digest"}:
            raise StateConflict("Version et empreinte requises.")
        event = consent(member, data["manifest_version"], data["manifest_digest"])
        return JsonResponse({"accepted": True, "state": event.state})
    except Membership.DoesNotExist:
        return error(status=404)
    except (ValueError, TypeError, KeyError, ValidationError):
        return error("Les règles ont changé ou ne sont pas disponibles.", 409)


@require_http_methods(["POST"])
@authenticated
def withdrawal(request):
    try:
        member = membership(request)
        if json.loads(request.body) != {"confirm": True}:
            raise StateConflict("Confirme les conséquences du retrait.")
        event = withdraw(member)
        return JsonResponse(
            {
                "state": event.state,
                "notice": "Un retrait annule un tirage lancé pour tout le groupe.",
            }
        )
    except Membership.DoesNotExist:
        return error(status=404)
    except (ValueError, TypeError, ValidationError):
        return error("Retrait indisponible ou non confirmé.", 409)


@require_http_methods(["GET", "POST"])
@authenticated
def rules_page(request):
    try:
        member = membership(request)
        record = SealedDraw.objects.filter(event=member.event).first()
        progress = (
            (
                "Tirage disponible"
                if record.release_state == "AVAILABLE"
                else "Finalisation du tirage"
            )
            if record and member.event.state in {"DRAWN", "CLOSED"}
            else {
                "OPEN": "Préparation",
                "CONFIRMING": "Confirmations attendues",
                "READY": "Groupe prêt",
                "DRAWING": "Calcul en cours",
                "CANCELLED": "Événement annulé",
                "CLOSED": "Événement terminé",
                "ARCHIVED": "Événement archivé",
            }.get(member.event.state, "Préparation")
        )
        value = (
            current_manifest(member.event)
            if member.event.state in {"CONFIRMING", "READY"}
            else None
        )
        names = {row["id"]: row["display_name"] for row in value["members"]} if value else {}
        exclusion_labels = [(names[g], names[r]) for g, r in value["exclusions"]] if value else []
        message = None
        status = 200
        if request.method == "POST":
            try:
                accepted_event = consent(
                    member,
                    int(request.POST.get("manifest_version", "")),
                    request.POST.get("manifest_digest", ""),
                )
                member.event = accepted_event
                from noel_ui import STATES

                progress = STATES.get(accepted_event.state, progress)
                message = "Ta confirmation est enregistrée."
            except (ValueError, TypeError):
                message = "La proposition a changé. Recharge les règles."
                status = 409
        return render(
            request,
            "vault/rules.html",
            {
                "member": member,
                "celebration_label": __import__("noel_ui")
                .local_value(member.event.celebration_at, member.event.timezone)
                .replace("T", " à "),
                "deadline_label": __import__("noel_ui")
                .local_value(member.event.wishlist_deadline, member.event.timezone)
                .replace("T", " à "),
                "manifest": value,
                "exclusion_labels": exclusion_labels,
                "digest": member.event.manifest_digest,
                "progress": progress,
                "message": message,
            },
            status=status,
        )
    except Membership.DoesNotExist:
        return error(status=404)
    except (ValueError, ValidationError):
        return error("Les règles ne sont pas disponibles.", 409)
