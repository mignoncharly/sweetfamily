import hashlib
import json
import uuid
from functools import wraps

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from noel_contracts import country, verify

from .domain import accept_invitation, apply_command
from .draw_engine import InvalidRules
from .draw_service import StateConflict
from .models import Invitation, Membership, PrivateEvent
from .notifications import RateLimited


def error(message="Accès indisponible.", status=400):
    return JsonResponse(
        {"code": "request_refused", "message": message, "correlation_id": uuid.uuid4().hex},
        status=status,
    )


def authenticated(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return (
                error("Connecte-toi à ton espace personnel.", 401)
                if request.path.startswith("/api/")
                else render(
                    request,
                    "vault/unavailable.html",
                    {"notice": "Connecte-toi à ton espace personnel."},
                    status=401,
                )
            )
        from .access_codes import verified_user

        if not verified_user(request):
            return (
                error("Fais vérifier ton identité dans le coffre.", 403)
                if request.path.startswith("/api/")
                else render(
                    request,
                    "vault/unavailable.html",
                    {"notice": "Fais vérifier ton identité dans le coffre avant de continuer."},
                    status=403,
                )
            )
        return view(request, *args, **kwargs)

    return wrapped


def membership(request):
    return Membership.objects.select_related("event", "identity").get(
        event_id=request.GET.get("event_id"),
        identity__user=request.user,
        claimed_at__isnull=False,
        active=True,
    )


def home(request):
    members = (
        Membership.objects.filter(
            identity__user=request.user, claimed_at__isnull=False, active=True
        )
        if request.user.is_authenticated
        else []
    )
    from noel_ui import STATES

    for member in members:
        member.state_label = STATES.get(member.event.state, "Préparation")
    return render(
        request,
        "vault/home.html",
        {
            "members": members,
            "pending": bool(
                request.session.get("pending_invitation")
                or request.get_signed_cookie(
                    "noel_pending_invitation", default="", salt="pending-invitation", max_age=600
                )
            ),
        },
    )


@require_http_methods(["GET", "POST"])
def join(request, token):
    if len(token) > 100:
        return error(status=404)
    digest = hashlib.sha256(token.encode()).hexdigest()
    invitation = (
        Invitation.objects.select_related("member__event")
        .filter(
            token_digest=digest,
            revoked_at=None,
            used_at=None,
            expires_at__gt=timezone.now(),
            member__active=True,
            member__event__state="OPEN",
        )
        .first()
    )
    if invitation is None:
        return render(
            request,
            "vault/unavailable.html",
            {
                "notice": (
                    "Invitation expirée ou indisponible. "
                    "Demande une nouvelle invitation à l’organisateur."
                )
            },
            status=404,
        )
    if request.method == "GET":
        return render(request, "vault/join.html", {"event": invitation.member.event})
    request.session["pending_invitation"] = digest
    if not request.user.is_authenticated:
        response = redirect("account_request_login_code")
        response.set_signed_cookie(
            "noel_pending_invitation",
            digest,
            salt="pending-invitation",
            max_age=600,
            httponly=True,
            secure=settings.APP_ENV != "local",
            samesite="Lax",
        )
        return response
    return accept(request)


@require_http_methods(["POST"])
@authenticated
def accept(request):
    try:
        member = accept_invitation(
            request.user,
            request.session.get("pending_invitation")
            or request.get_signed_cookie(
                "noel_pending_invitation", default="", salt="pending-invitation", max_age=600
            ),
        )
        request.session.pop("pending_invitation", None)
        response = (
            redirect("/")
            if request.path != "/api/me/invitations/accept"
            else JsonResponse({"event_id": str(member.event_id), "joined": True}, status=201)
        )
        response.delete_cookie("noel_pending_invitation", samesite="Lax")
        return response
    except (Invitation.DoesNotExist, ValueError):
        return error("Invitation indisponible pour ce compte.", 403)


@require_http_methods(["GET"])
@authenticated
def my_events(request):
    return JsonResponse(
        {
            "events": [
                {
                    "id": str(m.event_id),
                    "title": m.event.title,
                    "state": m.event.state,
                    "display_name": m.display_name,
                    "country": m.country,
                }
                for m in Membership.objects.select_related("event").filter(
                    identity__user=request.user, claimed_at__isnull=False, active=True
                )
            ]
        }
    )


@require_http_methods(["GET", "PATCH"])
@authenticated
def profile(request):
    try:
        with transaction.atomic():
            member = membership(request)
            if request.method == "PATCH":
                data = json.loads(request.body)
                if set(data) != {"revision", "display_name", "country"}:
                    raise ValueError()
                # Serialize edits per event and invalidate its manifest atomically.
                event = PrivateEvent.objects.select_for_update().get(pk=member.event_id)
                member = Membership.objects.select_for_update().get(pk=member.pk)
                if data["revision"] != member.revision:
                    return error("Une autre fenêtre a modifié ton profil.", 409)
                if event.state not in {"OPEN", "CONFIRMING", "READY", "DRAWN"}:
                    return error("Profil non modifiable dans cet état.", 409)
                if not isinstance(data["display_name"], str):
                    raise ValueError()
                name = data["display_name"].strip()
                if not 1 <= len(name) <= 80:
                    raise ValueError()
                if event.state == "DRAWN" and name != member.display_name:
                    return error("Le nom du groupe est gelé après tirage.", 409)
                member.country = country(data["country"])
                member.display_name = name
                member.revision += 1
                member.save()
                if event.state in {"OPEN", "CONFIRMING", "READY"}:
                    from .draw_service import invalidate

                    invalidate(event)
            return JsonResponse(
                {
                    "display_name": member.display_name,
                    "country": member.country,
                    "email": member.identity.email,
                    "revision": member.revision,
                }
            )
    except Membership.DoesNotExist:
        return error(status=404)
    except (ValueError, ValidationError, TypeError, KeyError, IntegrityError):
        return error("Profil invalide ou nom déjà utilisé.")


@csrf_exempt
@require_http_methods(["POST"])
def commands(request):
    if len(request.body) > 65536:
        return error(status=413)
    try:
        message = verify(json.loads(request.body), settings.COMMAND_KEY)
    except Exception:
        return error("Commande non authentifiée.", 403)
    try:
        return JsonResponse(apply_command(message))
    except RateLimited as exc:
        return error(str(exc), 429)
    except (StateConflict, InvalidRules) as exc:
        return error(str(exc), 409)
    except (
        ValueError,
        ValidationError,
        TypeError,
        KeyError,
        IntegrityError,
        PrivateEvent.DoesNotExist,
        Membership.DoesNotExist,
    ):
        return error("Commande refusée.", 409)


def csrf_failure(request, reason=""):
    return error("Session expirée ou formulaire invalide. Recharge la page.", 403)
