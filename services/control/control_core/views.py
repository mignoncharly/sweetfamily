import json
import urllib.error
import urllib.request
import uuid
from functools import wraps

from allauth.account.fields import EmailField
from allauth.account.internal.flows.login import get_authentication_records
from allauth.account.models import EmailAddress
from allauth.core.ratelimit import consume
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from noel_contracts import (
    canonical,
    country,
    digest,
    event_fields,
    sign,
    validate_projection,
    verify,
)

from .models import (
    ControlAudit,
    ControlCommand,
    EventDraft,
    Organizer,
    OwnershipTransfer,
    RosterProposal,
    SafeParticipantStatus,
)


def error(message, status=400):
    return JsonResponse(
        {"code": "request_refused", "message": message, "correlation_id": uuid.uuid4().hex},
        status=status,
    )


def authenticated(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error("Connecte-toi à ton compte.", 401)
        if not EmailAddress.objects.filter(user=request.user, verified=True, primary=True).exists():
            return error("Vérifie ton email.", 403)
        records = get_authentication_records(request, request.user)
        if not any(row.get("method") in {"code", "password"} for row in records):
            return error("Connecte-toi par email puis valide ton second facteur.", 403)
        if not is_mfa_enabled(request.user) or not any(
            row.get("method") == "mfa" for row in get_authentication_records(request, request.user)
        ):
            return error("Active la double authentification puis reconnecte-toi.", 403)
        return view(request, *args, **kwargs)

    return wrapped


def payload(request):
    if len(request.body) > 65536:
        raise ValueError("Requête trop grande.")
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError("Objet requis.")
    return data


def event_json(event):
    statuses = {
        row.member_id: row for row in SafeParticipantStatus.objects.filter(member__event=event)
    }
    return {
        "id": str(event.id),
        "title": event.title,
        "celebration_at": event.celebration_at.isoformat()
        if hasattr(event.celebration_at, "isoformat")
        else event.celebration_at,
        "wishlist_deadline": event.wishlist_deadline.isoformat()
        if hasattr(event.wishlist_deadline, "isoformat")
        else event.wishlist_deadline,
        "timezone": event.timezone,
        "state": event.state,
        "version": event.version,
        "manifest_version": event.manifest_version,
        "draw_progress": event.draw_progress,
        "ready_count": event.ready_count,
        "reminders_enabled": event.reminders_enabled,
        "members": [
            {
                "id": str(m.id),
                "active": m.active,
                "display_name": m.display_name,
                "country": m.country,
                "email": m.email,
                "registration_confirmed": m.registration_confirmed,
                "wishlist_complete": getattr(statuses.get(m.id), "wishlist_complete", False),
                "consent_received": getattr(statuses.get(m.id), "consent_received", False),
                "recipient_viewed": getattr(statuses.get(m.id), "recipient_viewed", False),
                "notification_state": getattr(statuses.get(m.id), "notification_state", "NONE"),
            }
            for m in event.roster.order_by("display_name")
        ],
    }


def owned(request, event_id, lock=False):
    query = EventDraft.objects.select_for_update() if lock else EventDraft.objects
    event = query.get(id=event_id, owner__user=request.user)
    if lock and OwnershipTransfer.objects.filter(event=event, state="APPLYING").exists():
        raise ValueError("Transfert d'organisation en cours. Réessaie après sa confirmation.")
    return event


def home(request):
    events = (
        EventDraft.objects.filter(owner__user=request.user) if request.user.is_authenticated else []
    )
    return render(request, "control/home.html", {"events": events})


@require_http_methods(["GET", "POST"])
@authenticated
def events(request):
    if request.method == "GET":
        return JsonResponse(
            {"events": [event_json(e) for e in EventDraft.objects.filter(owner__user=request.user)]}
        )
    try:
        data = payload(request)
        reminders = data.pop("reminders_enabled", False)
        if type(reminders) is not bool:
            raise ValueError()
        event_fields(data)
        owner, _ = Organizer.objects.get_or_create(user=request.user)
        event = EventDraft.objects.create(owner=owner, reminders_enabled=reminders, **data)
        ControlAudit.objects.create(event=event, category="event_created")
        return JsonResponse(event_json(event), status=201)
    except (ValueError, ValidationError, TypeError, KeyError):
        return error("Vérifie les champs, dates et fuseau de l'événement.")


@require_http_methods(["GET", "PATCH"])
@authenticated
def event_detail(request, event_id):
    try:
        with transaction.atomic():
            event = owned(request, event_id, True)
            if request.method == "GET":
                return JsonResponse(event_json(event))
            data = payload(request)
            if (
                set(data) != {"version", "event"}
                or data["version"] != event.version
                or event.state != "DRAFT"
            ):
                return error("Version ou état incompatible.", 409)
            event_fields(data["event"])
            for key, value in data["event"].items():
                setattr(event, key, value)
            event.version += 1
            event.save()
            return JsonResponse(event_json(event))
    except EventDraft.DoesNotExist:
        return error("événement indisponible.", 404)
    except (ValueError, ValidationError, TypeError, KeyError):
        return error("Modification invalide.")


@require_http_methods(["POST"])
@authenticated
def add_member(request, event_id):
    try:
        with transaction.atomic():
            event = owned(request, event_id, True)
            data = payload(request)
            if set(data) != {"version", "display_name", "country", "email"}:
                raise ValueError()
            if data["version"] != event.version or event.state != "DRAFT":
                return error("Version ou état incompatible.", 409)
            if event.roster.count() >= 20:
                return error("Maximum 20 personnes.")
            if not isinstance(data["display_name"], str):
                raise ValueError()
            name = data["display_name"].strip()
            if not 1 <= len(name) <= 80:
                raise ValueError()
            RosterProposal.objects.create(
                event=event,
                display_name=name,
                country=country(data["country"]),
                email=optional_member_email(data["email"]),
            )
            event.version += 1
            event.save(update_fields=["version"])
            return JsonResponse(event_json(event), status=201)
    except EventDraft.DoesNotExist:
        return error("événement indisponible.", 404)
    except (ValueError, ValidationError, TypeError, KeyError, IntegrityError):
        return error("Vérifie le nom distinct, le pays et l'email personnel.")


def optional_member_email(value):
    if value is None and settings.WHATSAPP_ENROLLMENT_ENABLED:
        return None
    return EmailField().clean(value)


def send_command(command):
    message = sign(command.kind, command.payload, settings.COMMAND_KEY, command.id)
    req = urllib.request.Request(
        settings.VAULT_ORIGIN + "/internal/commands",
        data=canonical(message),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # An independently configured HTTPS origin is mandatory outside local development.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as response:
        data = json.loads(response.read(65537))
    if set(data) != {"event_id", "version", "state"} or data["event_id"] != str(command.event_id):
        raise ValueError("Réponse du coffre invalide.")
    return data


@require_http_methods(["POST"])
@authenticated
def open_event(request, event_id):
    if not consume(request, action="invite_open", user=request.user):
        return error("Trop de demandes, réessaie plus tard.", 429)
    try:
        data = payload(request)
        if set(data) != {"version"} or not isinstance(data["version"], int):
            raise ValueError()
        key = request.headers.get("Idempotency-Key", "")
        if not 1 <= len(key) <= 100:
            raise ValueError()
        with transaction.atomic():
            event = owned(request, event_id, True)
            command = ControlCommand.objects.filter(event=event, idempotency_key=key).first()
            if command:
                if command.kind != "open" or command.payload["version"] != data["version"]:
                    return error("Conflit d'idempotence.", 409)
            else:
                if event.state != "DRAFT" or event.version != data["version"]:
                    return error("Version ou état incompatible.", 409)
                if not 4 <= event.roster.count() <= 20:
                    return error("Il faut entre 4 et 20 personnes.")
                body = {
                    "event_id": str(event.id),
                    "version": event.version,
                    "reminders_enabled": event.reminders_enabled,
                    "exclusions": event.exclusions,
                    "event": {
                        k: getattr(event, k)
                        for k in ("title", "timezone", "shipping_included", "handover")
                    },
                    "members": [
                        {
                            "id": str(m.id),
                            "display_name": m.display_name,
                            "country": m.country,
                            "email": m.email,
                        }
                        for m in event.roster.order_by("id")
                    ],
                }
                body["event"].update(
                    celebration_at=event.celebration_at.isoformat(),
                    wishlist_deadline=event.wishlist_deadline.isoformat(),
                )
                command = ControlCommand.objects.create(
                    event=event,
                    idempotency_key=key,
                    payload=body,
                    kind="open",
                    body_digest=digest("open", body),
                )
                event.state = "PUBLISHING"
                event.save(update_fields=["state"])
        if not command.delivered:
            result = send_command(command)
            with transaction.atomic():
                event = owned(request, event_id, True)
                command.delivered = True
                command.save(update_fields=["delivered"])
                if result["version"] >= event.version:
                    event.state = result["state"]
                    event.version = result["version"]
                    event.save()
                ControlAudit.objects.create(event=event, category="invitations_requested")
        return JsonResponse(event_json(EventDraft.objects.get(pk=event_id)))
    except EventDraft.DoesNotExist:
        return error("événement indisponible.", 404)
    except urllib.error.HTTPError as exc:
        if exc.code not in {400, 403, 409, 422}:
            return error("Réponse du coffre non définitive. Reprends la même demande.", 503)
        if exc.code in {400, 403, 409, 422}:
            with transaction.atomic():
                event = owned(request, event_id, True)
                if event.state == "PUBLISHING":
                    event.state = "DRAFT"
                    event.save(update_fields=["state"])
                command.rejected = True
                command.save(update_fields=["rejected"])
        return error(
            "Commande refusée par le coffre. Vérifie le brouillon avant une nouvelle demande.", 409
        )
    except (urllib.error.URLError, TimeoutError):
        return error("Coffre indisponible. Réessaie avec la même clé.", 503)
    except (ValueError, ValidationError, TypeError, KeyError, IntegrityError):
        return error("Commande invalide ou conflit.", 409)


@require_http_methods(["POST"])
@authenticated
def correct_member(request, event_id, member_id):
    if not consume(request, action="invite_correction", user=request.user):
        return error("Trop de corrections, réessaie plus tard.", 429)
    try:
        data = payload(request)
        key = request.headers.get("Idempotency-Key", "")
        if set(data) != {"version", "email"} or not 1 <= len(key) <= 100:
            raise ValueError()
        email = optional_member_email(data["email"])
        with transaction.atomic():
            event = owned(request, event_id, True)
            member = event.roster.get(pk=member_id)
            body = {
                "event_id": str(event.id),
                "member_id": str(member.id),
                "version": data["version"],
                "email": email,
            }
            command = ControlCommand.objects.filter(event=event, idempotency_key=key).first()
            if command and command.body_digest != digest("correct_invitation", body):
                return error("Conflit d'idempotence.", 409)
            if not command:
                if (
                    event.state != "OPEN"
                    or event.version != data["version"]
                    or member.registration_confirmed
                ):
                    return error("Identité ou version non modifiable.", 409)
                if (
                    email is not None
                    and event.roster.filter(email=email).exclude(pk=member_id).exists()
                ):
                    raise ValueError()
                command = ControlCommand.objects.create(
                    event=event,
                    idempotency_key=key,
                    kind="correct_invitation",
                    payload=body,
                    body_digest=digest("correct_invitation", body),
                )
        if not command.delivered:
            result = send_command(command)
            with transaction.atomic():
                event = owned(request, event_id, True)
                member.email = email
                member.save(update_fields=["email"])
                if result["version"] >= event.version:
                    event.version = result["version"]
                    event.save(update_fields=["version"])
                command.delivered = True
                command.save(update_fields=["delivered"])
        return JsonResponse(event_json(event))
    except (EventDraft.DoesNotExist, RosterProposal.DoesNotExist):
        return error("événement indisponible.", 404)
    except urllib.error.HTTPError:
        return error("Commande refusée par le coffre.", 409)
    except (urllib.error.URLError, TimeoutError):
        return error("Coffre indisponible.", 503)
    except (ValueError, ValidationError, TypeError, KeyError, IntegrityError):
        return error("Correction refusée.", 409)


@csrf_exempt
@require_http_methods(["POST"])
def status_projection(request):
    try:
        if len(request.body) > 65536:
            return error("Projection trop grande.", 413)
        message = verify(json.loads(request.body), settings.PROJECTION_KEY)
        if message["type"] != "status_projection":
            raise ValueError()
        data = validate_projection(message["payload"])
    except Exception:
        return error("Projection refusée.", 403)
    try:
        with transaction.atomic():
            event = EventDraft.objects.select_for_update().get(pk=data["event_id"])
            if data["projection_version"] <= event.projection_version:
                return JsonResponse({"accepted": True})
            members = {str(m.id): m for m in event.roster.all()}
            if set(members) != {m["member_ref"] for m in data["members"]}:
                return error("Références invalides.", 409)
            for row in data["members"]:
                member = members[row["member_ref"]]
                member.active = row.get("active", True)
                member.registration_confirmed = row["registration_confirmed"]
                member.save(update_fields=["registration_confirmed", "active"])
                SafeParticipantStatus.objects.update_or_create(
                    member=member,
                    defaults={
                        "registration_confirmed": row["registration_confirmed"],
                        "notification_state": row["notification_state"],
                        "wishlist_complete": row["wishlist_complete"],
                        "consent_received": row["consent_received"],
                        "recipient_viewed": row["recipient_viewed"],
                    },
                )
            event.ready_count = data["ready_count"]
            event.projection_version = data["projection_version"]
            if data.get("event_version", 0) >= event.version:
                event.version = data["event_version"]
                event.state = data["event_state"]
                event.manifest_version = data["manifest_version"]
                event.draw_progress = data["draw_progress"]
            event.save(
                update_fields=[
                    "projection_version",
                    "ready_count",
                    "version",
                    "state",
                    "manifest_version",
                    "draw_progress",
                ]
            )
        return JsonResponse({"accepted": True})
    except EventDraft.DoesNotExist:
        return error("Événement indisponible.", 404)


@require_http_methods(["GET"])
def event_status(request, event_id):
    return event_detail(request, event_id)


def csrf_failure(request, reason=""):
    return error("Session expirée ou formulaire invalide. Recharge la page.", 403)


@require_http_methods(["POST"])
@authenticated
def lifecycle(request, event_id, action):
    kinds = {
        "exclusions": "exclusions",
        "rules": "update_rules",
        "confirm-roster": "freeze",
        "draw": "draw",
        "cancel": "cancel",
        "close": "close",
        "remove-member": "remove_member",
        "reminders": "configure_reminders",
        "resend-notice": "resend_notice",
    }
    if action not in kinds:
        return error("Action inconnue.", 404)
    kind = kinds[action]
    try:
        data = payload(request)
        extra = {
            "exclusions": {"exclusions"},
            "update_rules": {"event"},
            "freeze": set(),
            "draw": set(),
            "cancel": {"confirm"},
            "close": {"confirm"},
            "remove_member": {"member_id", "confirm"},
            "configure_reminders": {"enabled", "wishlist_deadline", "celebration_at"},
            "resend_notice": {"member_id", "notice_type"},
        }[kind]
        if set(data) != {"version"} | extra or type(data.get("version")) is not int:
            raise ValueError()
        key = request.headers.get("Idempotency-Key", "")
        if not 1 <= len(key) <= 100:
            raise ValueError()
        body = dict(data, event_id=str(event_id))
        with transaction.atomic():
            event = owned(request, event_id, True)
            command = ControlCommand.objects.filter(event=event, idempotency_key=key).first()
            if command:
                if command.body_digest != digest(kind, body):
                    return error("Conflit d'idempotence.", 409)
            else:
                command = ControlCommand.objects.create(
                    event=event,
                    idempotency_key=key,
                    kind=kind,
                    payload=body,
                    body_digest=digest(kind, body),
                )
        if not command.delivered:
            result = send_command(command)
            with transaction.atomic():
                event = owned(request, event_id, True)
                if result["version"] >= event.version:
                    event.state = result["state"]
                    event.version = result["version"]
                    if kind == "configure_reminders":
                        event.reminders_enabled = data["enabled"]
                    elif kind == "exclusions":
                        event.exclusions = data["exclusions"]
                    elif kind == "update_rules":
                        for field, value in data["event"].items():
                            setattr(event, field, value)
                    event.save()
                command.delivered = True
                command.save(update_fields=["delivered"])
                ControlAudit.objects.create(event=event, category=kind)
        return JsonResponse(event_json(EventDraft.objects.get(pk=event_id)))
    except EventDraft.DoesNotExist:
        return error("Événement indisponible.", 404)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read(4096))
            reason = body.get("message", "Commande refusée.")
            if not isinstance(reason, str) or len(reason) > 500:
                reason = "Commande refusée."
        except Exception:
            reason = "Commande refusée."
        return error(reason, 429 if exc.code == 429 else 409)
    except (urllib.error.URLError, TimeoutError):
        return error("Coffre indisponible. Réessaie avec la même clé.", 503)
    except (ValueError, TypeError, KeyError, IntegrityError, ValidationError):
        return error("Commande invalide.", 409)


@require_http_methods(["GET", "POST"])
@authenticated
def reminder_settings(request, event_id):
    if request.method == "POST":
        return lifecycle(request, event_id, "reminders")
    try:
        from zoneinfo import ZoneInfo

        from noel_delivery import reminder_proposals

        event = owned(request, event_id)
        rows = [
            {
                "type": kind,
                "days_before": days,
                "local_datetime": due.astimezone(ZoneInfo(event.timezone)).isoformat(),
            }
            for kind, days, due, _ in reminder_proposals(event)
        ]
        return JsonResponse(
            {
                "version": event.version,
                "enabled": event.reminders_enabled,
                "wishlist_deadline": event.wishlist_deadline.isoformat(),
                "celebration_at": event.celebration_at.isoformat(),
                "proposals": rows,
                "notice": "Aucun rappel automatique sans activation explicite "
                "et confirmation des dates.",
            }
        )
    except EventDraft.DoesNotExist:
        return error("Événement indisponible.", 404)
