"""Public form primitives and status labels, with no service business data."""

import json
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pycountry
from django import forms
from django.conf import settings
from django.http import HttpRequest

STATES = {
    "DRAFT": "Brouillon",
    "PUBLISHING": "Envoi des invitations",
    "OPEN": "Préparation",
    "CONFIRMING": "Confirmations attendues",
    "READY": "Groupe prêt",
    "DRAWING": "Calcul en cours",
    "DRAWN": "Tirage scellé",
    "CLOSED": "Événement terminé",
    "CANCELLED": "Événement annulé",
    "ARCHIVED": "Archivé",
}
MAIL = {
    "NONE": "Aucun envoi en attente",
    "QUEUED": "En attente",
    "SUBMITTED": "Soumis",
    "ACCEPTED": "Accepté par le fournisseur",
    "DELIVERED": "Remis au serveur email",
    "DEFERRED": "Différé",
    "REJECTED": "Rejeté",
    "FAILED": "Échec",
    "DELIVERY_UNKNOWN": "Envoi à vérifier",
}
COUNTRIES = [
    (
        c.alpha_2,
        {
            "FR": "France",
            "DE": "Allemagne",
            "BE": "Belgique",
            "CH": "Suisse",
            "AT": "Autriche",
            "LU": "Luxembourg",
            "NL": "Pays-Bas",
        }.get(c.alpha_2, c.name)
        + " ("
        + c.alpha_2
        + ")",
    )
    for c in pycountry.countries
]
COUNTRIES.sort(key=lambda row: (row[0] not in {"FR", "DE"}, row[1]))


def context(request):
    return {
        "service_role": settings.SERVICE_ROLE,
        "staging": settings.APP_ENV == "staging",
        "mail_disabled": settings.MAIL_PROVIDER == "blocked",
        "whatsapp_enrollment": settings.WHATSAPP_ENROLLMENT_ENABLED,
        "personal_code_account": request.session.get("_auth_user_backend")
        == "vault_core.access_codes.AccessCodeBackend",
        "vault_origin": settings.VAULT_ORIGIN,
        "control_origin": settings.CONTROL_ORIGIN,
        "simulation": settings.MAIL_PROVIDER == "mailpit",
        "requires_form_js": request.path != "/"
        and not request.path.startswith(("/accounts/", "/join/")),
    }


def call_api(request, view, path, data, method="POST", **kwargs):
    # Original HTML POST has passed CSRF and authentication. No remote-user impersonation.
    child = HttpRequest()
    child.method = method
    child.path = path
    child.META = request.META.copy()
    child.META["CONTENT_TYPE"] = "application/json"
    child.META["HTTP_IDEMPOTENCY_KEY"] = request.POST.get("submission_id", "")
    child._body = json.dumps(data, ensure_ascii=False).encode()
    child.GET = request.GET.copy()
    child.COOKIES = request.COOKIES.copy()
    child.user = request.user
    child.session = request.session
    return view(child, **kwargs)


def local_value(value, zone):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(ZoneInfo(zone)).strftime("%Y-%m-%dT%H:%M")


def aware_local(value, zone):
    raw = datetime.fromisoformat(value)
    if raw.tzinfo is not None:
        return raw.isoformat()
    timezone = ZoneInfo(zone)
    options = []
    for fold in (0, 1):
        candidate = raw.replace(tzinfo=timezone, fold=fold)
        if candidate.astimezone(UTC).astimezone(timezone).replace(tzinfo=None) == raw:
            options.append(candidate)
    if not options or (len(options) == 2 and options[0].utcoffset() != options[1].utcoffset()):
        raise forms.ValidationError(
            "Cette heure est ambiguë ou inexistante avec le changement d'heure. "
            "Choisis une autre heure."
        )
    return options[0].isoformat()


class VersionForm(forms.Form):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    submission_id = forms.CharField(max_length=100, initial=uuid.uuid4, widget=forms.HiddenInput)


class EventForm(forms.Form):
    title = forms.CharField(label="Nom de l'événement", max_length=120)
    celebration_at = forms.CharField(
        label="Date et heure du réveillon",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        help_text="Heure dans le fuseau choisi ci-dessous.",
    )
    wishlist_deadline = forms.CharField(
        label="Date limite des souhaits",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    timezone = forms.CharField(
        label="Fuseau horaire",
        initial="Europe/Berlin",
        help_text="Par exemple Europe/Berlin ou Europe/Paris.",
    )
    shipping_included = forms.BooleanField(
        label="Les frais de port sont inclus dans le plafond de 49,99 €", required=False
    )
    handover = forms.CharField(
        label="Consigne pour le réveillon",
        max_length=500,
        initial="À recevoir chez toi et à apporter au réveillon.",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    reminders_enabled = forms.BooleanField(
        label="Activer les rappels proposés aux dates indiquées", required=False
    )
    confirm_reset = forms.BooleanField(
        label=(
            "Je comprends que les modifications avant tirage annulent toutes les "
            "confirmations du groupe"
        ),
        required=False,
    )

    def clean(self):
        data = super().clean()
        if "timezone" not in data:
            return data
        try:
            ZoneInfo(data["timezone"])
            for name in ("celebration_at", "wishlist_deadline"):
                if name in data:
                    data[name] = aware_local(data[name], data["timezone"])
            if all(
                key in data for key in ("celebration_at", "wishlist_deadline")
            ) and datetime.fromisoformat(data["wishlist_deadline"]) >= datetime.fromisoformat(
                data["celebration_at"]
            ):
                raise forms.ValidationError("L'échéance des souhaits doit précéder le réveillon.")
        except (ValueError, KeyError):
            raise forms.ValidationError("Vérifie les dates et le fuseau horaire.") from None
        return data

    def event_data(self):
        return {
            key: self.cleaned_data[key]
            for key in (
                "title",
                "celebration_at",
                "wishlist_deadline",
                "timezone",
                "shipping_included",
                "handover",
            )
        }


class MemberForm(VersionForm):
    display_name = forms.CharField(label="Nom affiché au groupe", max_length=80)
    country = forms.ChoiceField(label="Pays de commande et de réception", choices=COUNTRIES)
    email = forms.EmailField(
        label="Email personnel", help_text="Une boîte distincte et accessible à cette personne."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if settings.WHATSAPP_ENROLLMENT_ENABLED:
            self.fields["email"].required = False
            self.fields["email"].help_text = (
                "Facultatif : sans email, invitation WhatsApp privée et vérification "
                "par l'opérateur indépendant du coffre avant le premier accès."
            )

    def clean_email(self):
        return self.cleaned_data["email"] or None


class ConfirmForm(VersionForm):
    confirm = forms.BooleanField(label="Je confirme cette action et ses conséquences")
