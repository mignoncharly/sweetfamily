import secrets

from allauth.core.ratelimit import consume
from allauth.usersessions.models import UserSession
from django import forms
from django.contrib.auth import authenticate, login
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from django.views.decorators.http import require_http_methods

from . import access_codes as codes
from .models import AccessCredential, EnrollmentClaim, EnrollmentVerifier, Invitation
from .views import authenticated, error


class EnrollmentForm(forms.Form):
    confirm = forms.BooleanField(label="C'est bien moi ; je demande mon accès personnel")


class RememberForm(forms.Form):
    remember = forms.BooleanField(
        required=False, label="Garder ma connexion 30 jours sur cet appareil personnel"
    )


class LoginForm(RememberForm):
    code = forms.CharField(
        label="Mon code personnel",
        max_length=80,
        strip=True,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "spellcheck": "false"}
        ),
    )


def gate():
    if not codes.enabled():
        raise Http404


def establish(request, user, generation, remember):
    login(request, user, backend=codes.BACKEND)
    request.session.cycle_key()
    request.session["access_generation"] = generation
    request.session.set_expiry(30 * 24 * 60 * 60 if remember else 0)
    UserSession.objects.purge_and_list(user)
    UserSession.objects.create_from_request(request)


@require_http_methods(["GET", "POST"])
def invitation(request, member_id):
    gate()
    item = (
        Invitation.objects.select_related("member__event", "member__identity")
        .filter(
            member_id=member_id,
            member__active=True,
            member__identity__email=None,
            used_at=None,
            revoked_at=None,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )
    if not item or (not item.recovery and item.member.claimed_at):
        return error("Invitation expirée ou déjà utilisée. Reprends avec ton code personnel.", 404)
    form = EnrollmentForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if not consume(request, action="enrollment"):
            return error("Trop de demandes ; réessaie plus tard.", 429)
        binding = secrets.token_urlsafe(32)
        try:
            claim = codes.begin(item.id, binding)
        except ValueError:
            return error("Demande indisponible ; contacte l'opérateur indépendant.", 409)
        request.session.cycle_key()
        request.session["code_enrollment"] = {"claim_id": str(claim.id), "binding": binding}
        return redirect("/accounts/enrollment/")
    return render(
        request,
        "vault/enrollment_invitation.html",
        {
            "member": item.member,
            "form": form,
            "recovery": item.recovery,
        },
        status=400 if request.method == "POST" else 200,
    )


@require_http_methods(["GET", "POST"])
@sensitive_variables("context", "code")
def enrollment(request):
    gate()
    context = request.session.get("code_enrollment", {})
    try:
        claim = codes.bound_claim(context.get("claim_id"), context.get("binding"))
        item = claim.invitation
        if item.used_at or item.revoked_at or item.expires_at <= timezone.now():
            raise ValueError()
    except (EnrollmentClaim.DoesNotExist, ValidationError, ValueError, TypeError):
        return error("Demande indisponible. Ouvre ton invitation sur cet appareil.", 404)
    form = RememberForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if not consume(request, action="enrollment"):
            return error("Trop de demandes ; réessaie plus tard.", 429)
        try:
            with transaction.atomic():
                user, code, generation = codes.activate(claim.id, context["binding"])
                request.session.pop("code_enrollment", None)
                establish(request, user, generation, form.cleaned_data["remember"])
        except (
            ValueError,
            EnrollmentClaim.DoesNotExist,
            Invitation.DoesNotExist,
            EnrollmentVerifier.DoesNotExist,
        ):
            return error("La vérification indépendante doit être confirmée avant l'accès.", 409)
        return render(request, "vault/personal_code.html", {"personal_code": code})
    return render(request, "vault/enrollment_pending.html", {"claim": claim, "form": form})


@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("code")
@sensitive_variables("code")
def code_login(request):
    gate()
    form = LoginForm(request.POST if request.method == "POST" else None)
    status = 200
    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["code"]
        if not consume(request, action="access_code", key=codes.code_digest(code)):
            return error("Trop de tentatives ; réessaie plus tard.", 429)
        with transaction.atomic():
            # Serialize authentication with rotation/recovery and hold the lock
            # until the encrypted Django session has actually been saved.
            AccessCredential.objects.select_for_update().filter(
                digest=codes.code_digest(code)
            ).first()
            user = authenticate(request, access_secret=code)
            if user is not None:
                establish(request, user, request.access_generation, form.cleaned_data["remember"])
                return redirect("/")
        form.add_error(
            "code", "Code indisponible. Vérifie ta copie ou contacte le coffre indépendant."
        )
        status = 400
    elif request.method == "POST":
        status = 400
    return render(request, "vault/code_login.html", {"form": form}, status=status)


@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("code")
@sensitive_variables("code")
@authenticated
def personal_access(request):
    gate()
    form = LoginForm(request.POST if request.method == "POST" else None)
    status = 200
    if request.method == "POST" and form.is_valid():
        if not consume(request, action="code_rotation", user=request.user):
            return error("Trop de tentatives ; réessaie plus tard.", 429)
        try:
            with transaction.atomic():
                code, generation = codes.rotate(request.user, form.cleaned_data["code"])
                establish(request, request.user, generation, form.cleaned_data["remember"])
            return render(request, "vault/personal_code.html", {"personal_code": code})
        except (ValueError, AccessCredential.DoesNotExist):
            form.add_error("code", "Ton code actuel est nécessaire pour le remplacer.")
            status = 400
    return render(request, "vault/personal_access.html", {"form": form}, status=status)
