"""Organiser HTML flows. Business writes reuse the authenticated JSON application views."""

import csv
import io
import json
import time
import urllib.error
import uuid
from datetime import timedelta

from allauth.account.internal.flows.login import get_authentication_records
from allauth.account.models import EmailAddress
from allauth.mfa.utils import is_mfa_enabled
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from noel_contracts import digest
from noel_ui import (
    MAIL,
    STATES,
    ConfirmForm,
    EventForm,
    MemberForm,
    VersionForm,
    call_api,
    local_value,
)

from . import views
from .models import (
    ControlAudit,
    ControlCommand,
    EventDraft,
    Organizer,
    OwnershipTransfer,
    PortalSubmission,
    RosterProposal,
)


def gate(view):
    from functools import wraps

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        check = views.authenticated(lambda r: HttpResponse(status=204))(request)
        if check.status_code != 204:
            return render(
                request,
                "control/gate.html",
                {"notice": json.loads(check.content)["message"]},
                status=check.status_code,
            )
        return view(request, *args, **kwargs)

    return wrapped


def failed(form, response):
    data = json.loads(response.content)
    form.add_error(None, data.get("message", "Action non confirmée. Ta saisie est conservée."))


def render_form(request, title, form, button, notice="", status=200, event=None):
    return render(
        request,
        "control/form.html",
        {"title": title, "form": form, "button": button, "notice": notice, "event": event},
        status=status,
    )


def initial_event(event):
    return {
        "title": event.title,
        "celebration_at": local_value(event.celebration_at, event.timezone),
        "wishlist_deadline": local_value(event.wishlist_deadline, event.timezone),
        "timezone": event.timezone,
        "shipping_included": event.shipping_included,
        "handover": event.handover,
        "reminders_enabled": event.reminders_enabled,
    }


@require_http_methods(["GET"])
def home(request):
    events = (
        EventDraft.objects.filter(owner__user=request.user) if request.user.is_authenticated else []
    )
    rows = [{"event": e, "label": STATES.get(e.state, e.state)} for e in events]
    return render(request, "control/home.html", {"rows": rows})


class SetupForm(EventForm, VersionForm):
    pass


@require_http_methods(["GET", "POST"])
@gate
def create(request, source_id=None):
    source = None
    if source_id:
        try:
            source = views.owned(request, source_id)
        except EventDraft.DoesNotExist:
            return missing(request)
    initial = initial_event(source) if source else {}
    initial["version"] = 1
    form = SetupForm(request.POST if request.method == "POST" else None, initial=initial)
    form.fields.pop("confirm_reset")
    status = 200
    if request.method == "POST" and form.is_valid():
        data = form.event_data() | {"reminders_enabled": form.cleaned_data["reminders_enabled"]}
        body_digest = digest(
            "annual-copy" if source else "draft-create", dict(data, source=str(source_id))
        )
        try:
            with transaction.atomic():
                owner, _ = Organizer.objects.get_or_create(user=request.user)
                Organizer.objects.select_for_update().get(pk=owner.id)
                token = uuid.UUID(form.cleaned_data["submission_id"])
                old = PortalSubmission.objects.filter(pk=token).first()
                if old:
                    if old.owner_id != owner.id or old.body_digest != body_digest:
                        raise ValueError()
                    event = old.event
                else:
                    event = EventDraft.objects.create(owner=owner, copied_from=source, **data)
                    if source:
                        mapping = {}
                        for member in source.roster.filter(active=True):
                            copied = RosterProposal.objects.create(
                                event=event,
                                display_name=member.display_name,
                                email=member.email,
                                country=member.country,
                            )
                            mapping[str(member.id)] = str(copied.id)
                        event.exclusions = [
                            [mapping[g], mapping[r]]
                            for g, r in source.exclusions
                            if g in mapping and r in mapping
                        ]
                        event.save(update_fields=["exclusions"])
                    PortalSubmission.objects.create(
                        id=token, owner=owner, event=event, body_digest=body_digest
                    )
                    ControlAudit.objects.create(
                        event=event, category="annual_draft_copied" if source else "event_created"
                    )
            messages.success(
                request,
                (
                    "Brouillon créé. Vérifie chaque personne et ses dates avant les "
                    "nouvelles invitations."
                ),
            )
            return redirect("/events/" + str(event.id))
        except (ValueError, IntegrityError):
            form.add_error(
                None,
                (
                    "Cette demande est déjà liée à un autre contenu. Recharge avant de "
                    "créer un nouveau brouillon."
                ),
            )
            status = 409
    elif request.method == "POST":
        status = 400
    return render_form(
        request,
        "Préparer un nouvel événement" if not source else "Préparer une nouvelle édition",
        form,
        "Créer le brouillon",
        "Trois souhaits par personne, chacun à moins de 50 €. "
        "Aucune invitation ni attribution n'est créée automatiquement."
        + (
            (
                " Les personnes sont seulement reprises comme propositions : vérifie "
                "leurs coordonnées. Choisis les nouvelles dates."
            )
            if source
            else ""
        ),
        status,
    )


def missing(request):
    return render(
        request,
        "control/gate.html",
        {"notice": "Événement indisponible pour ce compte."},
        status=404,
    )


@require_http_methods(["GET"])
@gate
def dashboard(request, event_id):
    try:
        event = views.owned(request, event_id)
    except EventDraft.DoesNotExist:
        return missing(request)
    data = views.event_json(event)
    rows = []
    for member in data["members"]:
        member["mail_label"] = MAIL.get(member["notification_state"], "Envoi à vérifier")
        rows.append(member)
    active = [row for row in rows if row["active"]]
    pairs = []
    names = {row["id"]: row["display_name"] for row in active}
    for giver, recipient in event.exclusions:
        if giver in names and recipient in names:
            pairs.append((names[giver], names[recipient]))
    return render(
        request,
        "control/event.html",
        {
            "event": event,
            "state_label": STATES.get(event.state, event.state),
            "data": data,
            "people": rows,
            "active_count": len(active),
            "claimed_count": sum(row["registration_confirmed"] for row in active),
            "list_count": sum(row["wishlist_complete"] for row in active),
            "consent_count": sum(row["consent_received"] for row in active),
            "pending_commands": ControlCommand.objects.filter(
                event=event, delivered=False, rejected=False
            ),
            "pairs": pairs,
            "transfer": OwnershipTransfer.objects.filter(
                event=event, state__in=["PENDING", "APPLYING"]
            ).first(),
        },
    )


@require_http_methods(["GET", "POST"])
@gate
def rules(request, event_id):
    try:
        event = views.owned(request, event_id)
    except EventDraft.DoesNotExist:
        return missing(request)
    if event.state not in {"DRAFT", "OPEN", "CONFIRMING", "READY"}:
        return render_form(
            request,
            "Règles gelées",
            ConfirmForm(initial={"version": event.version}),
            "Indisponible",
            "Les règles ne changent plus après le début du tirage.",
            409,
            event,
        )
    form = SetupForm(
        request.POST if request.method == "POST" else None,
        initial=initial_event(event) | {"version": event.version},
    )
    # Reminders have their own explicit confirmation route after publication.
    form.fields.pop("reminders_enabled")
    status = 200
    if request.method == "POST" and form.is_valid():
        if event.state != "DRAFT" and not form.cleaned_data["confirm_reset"]:
            form.add_error("confirm_reset", "Confirme la réouverture des confirmations.")
            status = 400
        else:
            data = {"version": form.cleaned_data["version"], "event": form.event_data()}
            response = call_api(
                request,
                views.event_detail if event.state == "DRAFT" else views.lifecycle,
                f"/api/events/{event.id}",
                data,
                method="PATCH" if event.state == "DRAFT" else "POST",
                **(
                    {"event_id": event.id}
                    if event.state == "DRAFT"
                    else {"event_id": event.id, "action": "rules"}
                ),
            )
            if response.status_code == 200:
                messages.success(
                    request,
                    (
                        "Les règles sont enregistrées. Si nécessaire, chacun devra confirmer à "
                        "nouveau."
                    ),
                )
                return redirect("/events/" + str(event.id))
            failed(form, response)
            status = response.status_code
    elif request.method == "POST":
        status = 400
    return render_form(
        request,
        "Dates et règles du réveillon",
        form,
        "Enregistrer les règles",
        (
            "Une modification avant tirage annule toutes les confirmations. Changer"
            " les frais exige de revalider les listes."
        ),
        status,
        event,
    )


@require_http_methods(["GET", "POST"])
@gate
def person(request, event_id, member_id=None):
    try:
        event = views.owned(request, event_id)
        member = event.roster.get(pk=member_id) if member_id else None
    except (EventDraft.DoesNotExist, RosterProposal.DoesNotExist):
        return missing(request)
    if not member and event.state != "DRAFT":
        return missing(request)
    initial = {"version": event.version}
    if member:
        initial.update(display_name=member.display_name, country=member.country, email=member.email)
    form = MemberForm(request.POST if request.method == "POST" else None, initial=initial)
    if event.state != "DRAFT":
        form.fields["display_name"].disabled = True
        form.fields["country"].disabled = True
    status = 200
    if request.method == "POST" and form.is_valid():
        data = {
            key: form.cleaned_data[key] for key in ("version", "display_name", "country", "email")
        }
        if member and event.state == "DRAFT":
            try:
                with transaction.atomic():
                    locked = views.owned(request, event.id, True)
                    if locked.state != "DRAFT" or locked.version != data["version"]:
                        raise ValueError()
                    for key in ("display_name", "country", "email"):
                        setattr(member, key, data[key])
                    member.save()
                    locked.version += 1
                    locked.save(update_fields=["version"])
                response = HttpResponse(status=200)
            except (IntegrityError, ValueError):
                response = views.error("Nom/email déjà utilisé ou version modifiée.", 409)
        elif member:
            response = call_api(
                request,
                views.correct_member,
                "/api/participants/email",
                {"version": data["version"], "email": data["email"]},
                event_id=event.id,
                member_id=member.id,
            )
        else:
            response = call_api(
                request, views.add_member, "/api/participants", data, event_id=event.id
            )
        if response.status_code in {200, 201}:
            messages.success(
                request,
                (
                    "La proposition est enregistrée. Une identité déjà revendiquée ne peut "
                    "pas être remplacée."
                ),
            )
            return redirect("/events/" + str(event.id))
        failed(form, response)
        status = response.status_code
    elif request.method == "POST":
        status = 400
    return render_form(
        request,
        "Ajouter une personne" if not member else "Vérifier une proposition",
        form,
        "Enregistrer",
        "Après inscription, seul le participant modifie son email dans le coffre. "
        "Le portail ne voit que les coordonnées qu'il a proposées.",
        status,
        event,
    )


class ExclusionForm(ConfirmForm):
    giver = forms.ChoiceField(label="La personne qui offre")
    recipient = forms.ChoiceField(label="La personne qu'elle ne peut pas tirer")
    operation = forms.ChoiceField(
        label="Action", choices=[("add", "Ajouter l'exclusion"), ("remove", "Retirer l'exclusion")]
    )


@require_http_methods(["GET", "POST"])
@gate
def exclusions(request, event_id):
    try:
        event = views.owned(request, event_id)
    except EventDraft.DoesNotExist:
        return missing(request)
    form = ExclusionForm(
        request.POST if request.method == "POST" else None, initial={"version": event.version}
    )
    choices = [(str(m.id), m.display_name) for m in event.roster.filter(active=True)]
    form.fields["giver"].choices = form.fields["recipient"].choices = choices
    status = 200
    if request.method == "POST" and form.is_valid():
        row = [form.cleaned_data["giver"], form.cleaned_data["recipient"]]
        pairs = [
            pair for pair in event.exclusions if all(person in dict(choices) for person in pair)
        ]
        if row[0] == row[1]:
            form.add_error("recipient", "L'attribution à soi-même est déjà interdite.")
        else:
            if form.cleaned_data["operation"] == "add" and row not in pairs:
                pairs.append(row)
            if form.cleaned_data["operation"] == "remove" and row in pairs:
                pairs.remove(row)
            response = call_api(
                request,
                views.lifecycle,
                "/api/exclusions",
                {"version": form.cleaned_data["version"], "exclusions": pairs},
                event_id=event.id,
                action="exclusions",
            )
            if response.status_code == 200:
                return redirect("/events/" + str(event.id))
            failed(form, response)
            status = response.status_code
    elif request.method == "POST":
        status = 400
    return render_form(
        request,
        "Exclusions dirigées",
        form,
        "Appliquer l'exclusion",
        "L'exclusion va dans un seul sens. Toute modification rouvre les confirmations. "
        "Le coffre vérifiera aussi qu'aucune autre attribution ne devient déductible.",
        status,
        event,
    )


ACTIONS = {
    "open": (
        "Envoyer les invitations",
        (
            "Une invitation personnelle sera envoyée à chaque personne proposée. "
            "Aucun tirage n'est lancé."
        ),
    ),
    "confirm-roster": (
        "Demander la confirmation du groupe",
        (
            "Toutes les personnes doivent avoir rejoint et validé trois souhaits. "
            "Le coffre vérifiera les règles et exclusions. Chaque personne accepte "
            "ensuite la même version."
        ),
    ),
    "draw": (
        "Lancer le tirage",
        (
            "Cette action est définitive après scellement. Les personnes et règles "
            "sont gelées. Un retard ou renvoi de courrier ne relance jamais le "
            "tirage."
        ),
    ),
    "cancel": (
        "Annuler pour tout le groupe",
        (
            "Les attributions ne seront pas remaniées. Tout le groupe est informé ;"
            " ce qui a été vu ou acheté ne peut pas être effacé."
        ),
    ),
    "close": (
        "Clôturer l'événement",
        (
            "Les lectures personnelles restent disponibles selon la conservation. "
            "Les achats ne seront plus modifiables."
        ),
    ),
    "remove-member": (
        "Retirer une personne",
        (
            "Avant tirage, toutes les confirmations sont annulées. Dès le calcul "
            "commencé, ce retrait annule tout l'événement."
        ),
    ),
    "resend-notice": (
        "Renvoyer un message neutre",
        (
            "Un renvoi limité ne change jamais le tirage. Un état inconnu peut déjà"
            " correspondre à un courrier reçu."
        ),
    ),
    "delete-proposal": (
        "Supprimer une proposition du brouillon",
        "Aucune invitation n'a encore été envoyée pour ce brouillon.",
    ),
}


class ActionForm(ConfirmForm):
    notice_type = forms.ChoiceField(
        label="Message à renvoyer",
        required=False,
        choices=[
            ("INVITATION", "Invitation"),
            ("LIST_REMINDER", "Mes trois souhaits"),
            ("CONSENT", "Règles à confirmer"),
            ("DRAW_READY", "Tirage disponible"),
            ("PREPARATION", "Préparation du réveillon"),
        ],
    )


@require_http_methods(["GET", "POST"])
@gate
def action(request, event_id, action, member_id=None):
    try:
        event = views.owned(request, event_id)
        member = event.roster.get(pk=member_id) if member_id else None
    except (EventDraft.DoesNotExist, RosterProposal.DoesNotExist):
        return missing(request)
    if action not in ACTIONS:
        return missing(request)
    form = ActionForm(
        request.POST if request.method == "POST" else None, initial={"version": event.version}
    )
    if action != "resend-notice":
        form.fields.pop("notice_type")
    status = 200
    if request.method == "POST" and form.is_valid():
        data = {"version": form.cleaned_data["version"]}
        if action in {"cancel", "close", "remove-member"}:
            data["confirm"] = True
        if action in {"remove-member", "resend-notice", "delete-proposal"}:
            if member is None:
                return missing(request)
            data["member_id"] = str(member.id)
        if action == "resend-notice":
            data["notice_type"] = form.cleaned_data["notice_type"]
        if action == "delete-proposal":
            try:
                with transaction.atomic():
                    locked = views.owned(request, event.id, True)
                    if locked.state != "DRAFT" or locked.version != data["version"]:
                        raise ValueError()
                    member.delete()
                    locked.version += 1
                    locked.save(update_fields=["version"])
                response = HttpResponse(status=200)
            except ValueError:
                response = views.error("Version ou état modifié.", 409)
        else:
            response = call_api(
                request,
                views.open_event if action == "open" else views.lifecycle,
                "/api/event-action",
                data,
                **(
                    {"event_id": event.id}
                    if action == "open"
                    else {"event_id": event.id, "action": action}
                ),
            )
        if response.status_code == 200:
            messages.success(
                request, "Action confirmée par le service. Les mises à jour sont regroupées."
            )
            return redirect("/events/" + str(event.id))
        failed(form, response)
        status = response.status_code
    elif request.method == "POST":
        status = 400
    return render_form(
        request,
        ACTIONS[action][0],
        form,
        ACTIONS[action][0],
        ACTIONS[action][1] + (" Personne : " + member.display_name + "." if member else ""),
        status,
        event,
    )


class ReminderForm(ConfirmForm):
    enabled = forms.BooleanField(label="Activer les rappels facultatifs proposés", required=False)


@require_http_methods(["GET", "POST"])
@gate
def reminders(request, event_id):
    try:
        event = views.owned(request, event_id)
    except EventDraft.DoesNotExist:
        return missing(request)
    form = ReminderForm(
        request.POST if request.method == "POST" else None,
        initial={"version": event.version, "enabled": event.reminders_enabled},
    )
    from noel_delivery import reminder_proposals

    dates = " ; ".join(
        due.astimezone(__import__("zoneinfo").ZoneInfo(event.timezone)).strftime("%d/%m/%Y à %H:%M")
        for _, _, due, _ in reminder_proposals(event)
    )
    status = 200
    if request.method == "POST" and form.is_valid():
        response = call_api(
            request,
            views.lifecycle,
            "/api/reminders",
            {
                "version": form.cleaned_data["version"],
                "enabled": form.cleaned_data["enabled"],
                "wishlist_deadline": event.wishlist_deadline.isoformat(),
                "celebration_at": event.celebration_at.isoformat(),
            },
            event_id=event.id,
            action="reminders",
        )
        if response.status_code == 200:
            return redirect("/events/" + str(event.id))
        failed(form, response)
        status = response.status_code
    return render_form(
        request,
        "Dates des rappels",
        form,
        "Confirmer ces dates et préférences",
        "Dates proposées dans "
        + event.timezone
        + " : "
        + dates
        + ". Chaque participant peut désactiver les rappels facultatifs.",
        status,
        event,
    )


def csv_cell(value):
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


@require_http_methods(["GET"])
@gate
def export(request, event_id):
    try:
        event = views.owned(request, event_id)
    except EventDraft.DoesNotExist:
        return missing(request)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_ALL)
    keys = [
        "display_name",
        "country",
        "email",
        "active",
        "registration_confirmed",
        "wishlist_complete",
        "consent_received",
        "notification_state",
        "recipient_viewed",
    ]
    writer.writerow(
        [
            "Nom proposé",
            "Pays proposé",
            "Email proposé",
            "Actif",
            "Inscription",
            "Liste complète",
            "Règles confirmées",
            "Notification",
            "Consultation déclarée",
        ]
    )
    for member in views.event_json(event)["members"]:
        writer.writerow([csv_cell(member[k]) for k in keys])
    response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="suivi-noel.csv"'
    return response


def recent(request):
    records = get_authentication_records(request, request.user)
    cutoff = time.time() - 300
    return any(
        row.get("method") in {"code", "password"} and row.get("at", 0) >= cutoff for row in records
    ) and any(row.get("method") == "mfa" and row.get("at", 0) >= cutoff for row in records)


class TransferForm(ConfirmForm):
    email = forms.EmailField(
        label="Email du prochain organisateur",
        help_text="Son compte portail doit être vérifié et protégé par un second facteur.",
    )
    owner_label = forms.CharField(label="Nom annoncé au groupe", max_length=80)


@require_http_methods(["GET", "POST"])
@gate
def propose_transfer(request, event_id):
    try:
        event = views.owned(request, event_id)
    except EventDraft.DoesNotExist:
        return missing(request)
    form = TransferForm(
        request.POST if request.method == "POST" else None, initial={"version": event.version}
    )
    status = 200
    if request.method == "POST" and form.is_valid():
        if not recent(request):
            form.add_error(
                None,
                (
                    "Reconnecte-toi par code et second facteur depuis moins de cinq minutes"
                    " avant le transfert."
                ),
            )
            status = 403
        else:
            try:
                with transaction.atomic():
                    event = views.owned(request, event.id, True)
                    if event.version != form.cleaned_data["version"] or event.state in {
                        "ARCHIVED",
                        "PUBLISHING",
                        "DRAWING",
                    }:
                        raise ValueError()
                    address = EmailAddress.objects.select_related("user").get(
                        email__iexact=form.cleaned_data["email"], primary=True, verified=True
                    )
                    if (
                        not address.user.is_active
                        or address.user_id == request.user.id
                        or not is_mfa_enabled(address.user)
                    ):
                        raise ValueError()
                    target, _ = Organizer.objects.get_or_create(user=address.user)
                    OwnershipTransfer.objects.filter(event=event).delete()
                    OwnershipTransfer.objects.create(
                        event=event,
                        proposed_by=event.owner,
                        target=target,
                        owner_label=form.cleaned_data["owner_label"],
                        expected_version=event.version,
                        expires_at=timezone.now() + timedelta(hours=48),
                    )
                messages.success(
                    request,
                    (
                        "Proposition enregistrée pour 48 heures. La personne doit se connecter "
                        "au portail et l'accepter ; aucun accès privé n'est transféré."
                    ),
                )
                return redirect("/events/" + str(event.id))
            except (ValueError, EmailAddress.DoesNotExist):
                form.add_error(
                    None,
                    (
                        "Version modifiée ou compte cible indisponible : vérifier email, second"
                        " facteur et inscription au portail."
                    ),
                )
                status = 409
    return render_form(
        request,
        "Transférer uniquement l'organisation",
        form,
        "Proposer le transfert",
        (
            "Le destinataire accepte sous réauthentification. Le groupe sera "
            "informé après confirmation. "
            "Aucune session, attribution ou identité du coffre ne sera transférée."
        ),
        status,
        event,
    )


@require_http_methods(["GET", "POST"])
@gate
def transfers(request):
    notice = None
    status = 200
    if request.method == "POST":
        form = ConfirmForm(request.POST)
        if not form.is_valid() or not recent(request):
            notice = "Reconnecte-toi avec code et second facteur, puis confirme la proposition."
            status = 403
        else:
            try:
                peek = OwnershipTransfer.objects.select_related("event").get(
                    pk=request.POST.get("transfer_id"), target__user=request.user
                )
                if peek.state == "ACCEPTED" and peek.event.owner.user_id == request.user.id:
                    return redirect("/events/" + str(peek.event_id))
                with transaction.atomic():
                    event = EventDraft.objects.select_for_update().get(pk=peek.event_id)
                    ticket = OwnershipTransfer.objects.select_for_update().get(
                        pk=peek.id, target__user=request.user, state__in=["PENDING", "APPLYING"]
                    )
                    if ticket.state == "PENDING" and (
                        ticket.expires_at <= timezone.now()
                        or event.version != ticket.expected_version
                    ):
                        raise ValueError()
                    if event.owner_id != ticket.proposed_by_id:
                        raise ValueError()
                    command = None
                    if event.state != "DRAFT":
                        body = {
                            "event_id": str(event.id),
                            "version": ticket.expected_version,
                            "transfer_ref": str(ticket.id),
                            "owner_label": ticket.owner_label,
                        }
                        command, _ = ControlCommand.objects.get_or_create(
                            event=event,
                            idempotency_key="transfer-" + str(ticket.id),
                            defaults={
                                "kind": "ownership_changed",
                                "payload": body,
                                "body_digest": digest("ownership_changed", body),
                            },
                        )
                    ticket.state = "APPLYING"
                    ticket.save(update_fields=["state"])
                result = views.send_command(command) if command and not command.delivered else None
                with transaction.atomic():
                    event = EventDraft.objects.select_for_update().get(pk=ticket.event_id)
                    ticket = OwnershipTransfer.objects.select_for_update().get(
                        pk=ticket.id, state="APPLYING", target__user=request.user
                    )
                    if event.owner_id != ticket.proposed_by_id:
                        raise ValueError()
                    if result and result["version"] >= event.version:
                        event.version = result["version"]
                        event.state = result["state"]
                    event.owner = ticket.target
                    event.save()
                    ticket.state = "ACCEPTED"
                    ticket.save(update_fields=["state"])
                    if command:
                        command.delivered = True
                        command.save(update_fields=["delivered"])
                    ControlAudit.objects.create(event=event, category="ownership_transferred")
                messages.success(
                    request,
                    (
                        "Tu gères désormais l'organisation. Le coffre garde les mêmes "
                        "participants, sessions et attributions."
                    ),
                )
                return redirect("/events/" + str(event.id))
            except urllib.error.HTTPError as exc:
                if exc.code in {400, 403, 409, 422}:
                    with transaction.atomic():
                        event = EventDraft.objects.select_for_update().get(pk=ticket.event_id)
                        OwnershipTransfer.objects.filter(pk=ticket.id, state="APPLYING").update(
                            state="REJECTED"
                        )
                        if command:
                            command.rejected = True
                            command.save(update_fields=["rejected"])
                    notice = (
                        "Le coffre a refusé cette version. L’ancien organisateur doit "
                        "proposer un nouveau transfert."
                    )
                    status = 409
                else:
                    notice = "Réponse non définitive du coffre. Reprends la même proposition."
                    status = 503
            except (urllib.error.URLError, TimeoutError):
                notice = (
                    "Confirmation du coffre non reçue. La demande reste réservée : reprends"
                    " la même proposition, sans nouveau transfert."
                )
                status = 503
            except (OwnershipTransfer.DoesNotExist, ValueError, ValidationError, IntegrityError):
                notice = (
                    "Proposition expirée, déjà traitée ou version modifiée. Demande une "
                    "nouvelle proposition à l'organisateur."
                )
                status = 409
    tickets = []
    for ticket in OwnershipTransfer.objects.filter(
        target__user=request.user, state__in=["PENDING", "APPLYING"]
    ).select_related("event"):
        tickets.append(
            {
                "ticket": ticket,
                "form": ConfirmForm(
                    initial={"version": ticket.expected_version}, auto_id=f"id_{ticket.id}_%s"
                ),
            }
        )
    return render(
        request, "control/transfers.html", {"tickets": tickets, "notice": notice}, status=status
    )


@require_http_methods(["GET", "POST"])
@gate
def retry(request, event_id, command_id):
    try:
        event = views.owned(request, event_id)
        command = ControlCommand.objects.get(
            pk=command_id, event=event, delivered=False, rejected=False
        )
    except (EventDraft.DoesNotExist, ControlCommand.DoesNotExist):
        return missing(request)
    initial = {"version": command.payload["version"], "submission_id": command.idempotency_key}
    form = ConfirmForm(request.POST if request.method == "POST" else None, initial=initial)
    status = 200
    if request.method == "POST" and form.is_valid():
        kinds = {
            "freeze": "confirm-roster",
            "update_rules": "rules",
            "remove_member": "remove-member",
            "resend_notice": "resend-notice",
            "configure_reminders": "reminders",
        }
        if command.kind == "ownership_changed":
            form.add_error(
                None,
                "Le prochain organisateur reprend cette proposition depuis « Transferts reçus ».",
            )
            status = 409
        elif (
            form.cleaned_data["submission_id"] != command.idempotency_key
            or form.cleaned_data["version"] != command.payload["version"]
        ):
            form.add_error(None, "Conserve la demande enregistrée à l'identique.")
            status = 409
        else:
            data = {k: v for k, v in command.payload.items() if k != "event_id"}
            target = views.lifecycle
            kwargs = {"event_id": event.id, "action": kinds.get(command.kind, command.kind)}
            if command.kind == "open":
                target = views.open_event
                kwargs = {"event_id": event.id}
                data = {"version": command.payload["version"]}
            elif command.kind == "correct_invitation":
                target = views.correct_member
                kwargs = {"event_id": event.id, "member_id": data.pop("member_id")}
            response = call_api(request, target, "/api/retry", data, **kwargs)
            if response.status_code == 200:
                return redirect("/events/" + str(event.id))
            failed(form, response)
            status = response.status_code
    return render_form(
        request,
        "Reprendre une demande sans la doubler",
        form,
        "Reprendre la même demande",
        (
            "La réponse réseau a pu être perdue après traitement. Cette reprise "
            "conserve l'identifiant et le contenu initiaux."
        ),
        status,
        event,
    )


def help_page(request):
    return render(request, "control/help.html")
