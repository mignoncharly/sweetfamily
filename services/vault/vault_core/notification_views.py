import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .models import Membership, PendingMail
from .views import authenticated, error, membership


@require_http_methods(["GET", "PATCH"])
@authenticated
def preferences(request):
    try:
        member = membership(request)
        if request.method == "PATCH":
            data = json.loads(request.body)
            if set(data) != {"reminders_enabled"} or type(data["reminders_enabled"]) is not bool:
                raise ValueError()
            member.reminders_enabled = data["reminders_enabled"]
            member.save(update_fields=["reminders_enabled"])
        return JsonResponse(
            {
                "reminders_enabled": member.reminders_enabled,
                "event_reminders_enabled": member.event.reminders_enabled,
            }
        )
    except Membership.DoesNotExist:
        return error(status=404)
    except (ValueError, TypeError, KeyError):
        return error("Préférence invalide.")


@require_http_methods(["GET", "POST"])
@authenticated
def page(request):
    try:
        member = membership(request)
        if request.method == "POST":
            member.reminders_enabled = request.POST.get("reminders_enabled") == "on"
            member.save(update_fields=["reminders_enabled"])
        notices = (
            PendingMail.objects.filter(member=member)
            .exclude(category="AUTH")
            .order_by("-created_at")[:20]
        )
        kinds = {
            "INVITATION": "Invitation",
            "CONSENT": "Règles à confirmer",
            "DRAW_READY": "Tirage disponible",
            "LIST_REMINDER": "Mes trois souhaits",
            "PREPARATION": "Préparer le réveillon",
            "WISH_DIGEST": "Souhaits du groupe",
            "CANCELLED": "Annulation",
            "PURGE_NOTICE": "Suppression prochaine",
        }
        labels = {
            "SUBMITTED": "Soumis",
            "ACCEPTED": "Accepté par le fournisseur",
            "DELIVERED": "Remis au serveur email",
            "DEFERRED": "Différé",
            "REJECTED": "Rejeté",
            "FAILED": "Échec",
            "DELIVERY_UNKNOWN": "Envoi à vérifier",
        }
        rows = []
        for notice in notices.values("kind", "state", "delivery_status"):
            state = notice["delivery_status"]
            label = labels.get(state)
            if state == "NONE":
                label = {
                    "HELD": "Finalisation du tirage",
                    "EXPIRED": "Non envoyé : expiré ou devenu inutile",
                    "FAILED": "Échec",
                }.get(notice["state"], "En attente")
            rows.append(
                {"kind_label": kinds.get(notice["kind"], "Message de suivi"), "status_label": label}
            )
        return render(
            request,
            "vault/notifications.html",
            {
                "member": member,
                "notices": rows,
                "zoho": settings.MAIL_PROVIDER == "zoho",
                "simulation": settings.MAIL_PROVIDER == "mailpit",
            },
        )
    except Membership.DoesNotExist:
        return error(status=404)
