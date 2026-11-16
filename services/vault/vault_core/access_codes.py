"""Email-free access. Public invitations cannot authenticate or authorize recovery."""

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.backends import BaseBackend
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .models import (
    AccessCredential,
    EnrollmentClaim,
    EnrollmentVerifier,
    Invitation,
    Membership,
    PrivateEvent,
    SecurityEvent,
    VerifiedIdentity,
)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 symbols, five bits each.
BACKEND = "vault_core.access_codes.AccessCodeBackend"


def enabled():
    return settings.WHATSAPP_ENROLLMENT_ENABLED


def random_code(size=32):
    raw = "".join(secrets.choice(ALPHABET) for _ in range(size))
    return "-".join(raw[i : i + 4] for i in range(0, size, 4))


@sensitive_variables("code")
def code_digest(code):
    if not isinstance(code, str) or len(code) > 80:
        return ""
    value = code.replace("-", "").replace(" ", "").upper()
    if len(value) != 32 or any(c not in ALPHABET for c in value):
        return ""
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def verified_identity(identity):
    if identity.email is not None:
        return EmailAddress.objects.filter(
            user_id=identity.user_id, primary=True, verified=True
        ).exists()
    return (
        enabled()
        and identity.verified_at is not None
        and AccessCredential.objects.filter(identity=identity, enabled=True).exists()
    )


def verified_user(request):
    identity = VerifiedIdentity.objects.filter(user=request.user).first()
    if identity is None or identity.email is not None:
        return EmailAddress.objects.filter(user=request.user, primary=True, verified=True).exists()
    return (
        (
            enabled()
            and identity.verified_at is not None
            and AccessCredential.objects.filter(
                identity=identity, enabled=True, generation=request.session.get("access_generation")
            ).exists()
        )
        if request.session.get("access_generation")
        else False
    )


class AccessCodeBackend(BaseBackend):
    @sensitive_variables("access_secret")
    def authenticate(self, request, access_secret=None):
        if not enabled() or request is None:
            return None
        credential = (
            AccessCredential.objects.select_related("identity__user")
            .filter(digest=code_digest(access_secret), enabled=True, identity__email__isnull=True)
            .first()
        )
        if credential and credential.identity.user.is_active and credential.identity.verified_at:
            request.access_generation = str(credential.generation)
            return credential.identity.user
        return None

    def get_user(self, user_id):
        if not enabled():
            return None
        credential = (
            AccessCredential.objects.select_related("identity__user")
            .filter(identity__user_id=user_id, enabled=True, identity__email__isnull=True)
            .first()
        )
        if credential and credential.identity.user.is_active and credential.identity.verified_at:
            return credential.identity.user
        return None


def lock_invitation(invitation_id):
    preliminary = Invitation.objects.select_related("member").get(pk=invitation_id)
    event = PrivateEvent.objects.select_for_update().get(pk=preliminary.member.event_id)
    member = (
        Membership.objects.select_for_update()
        .select_related("identity__user")
        .get(pk=preliminary.member_id)
    )
    invitation = Invitation.objects.select_for_update().get(pk=invitation_id)
    if (
        not enabled()
        or member.identity.email is not None
        or not member.identity.user.is_active
        or not member.active
        or invitation.used_at
        or invitation.revoked_at
        or invitation.expires_at <= timezone.now()
        or (not invitation.recovery and (member.claimed_at or event.state != "OPEN"))
        or (invitation.recovery and event.state in {"CANCELLED", "CLOSED", "ARCHIVED"})
    ):
        raise ValueError("Invitation indisponible.")
    return invitation, member


@transaction.atomic
@sensitive_variables("binding")
def begin(invitation_id, binding):
    invitation, _ = lock_invitation(invitation_id)
    now = timezone.now()
    # A competing request must never seize the account or revoke another browser.
    if (
        EnrollmentClaim.objects.filter(
            invitation=invitation, created_at__gt=now - timedelta(hours=1)
        ).count()
        >= 20
    ):
        raise ValueError("Trop de demandes ; contacte l'opérateur indépendant.")
    return EnrollmentClaim.objects.create(
        invitation=invitation,
        binding_digest=hashlib.sha256(binding.encode()).hexdigest(),
        comparison=random_code(16),
        expires_at=min(invitation.expires_at, now + timedelta(hours=24)),
    )


@transaction.atomic
def approve(approval):
    """Operator process only: journal key is deliberately absent from web/worker env."""
    from noel_operations import append_record, journal, lock, paused

    journal()
    lock()
    if paused():
        raise ValueError("Le coffre est en maintenance.")
    from noel_enrollment_approval import verify_approval

    verifier = EnrollmentVerifier.objects.select_for_update().get(
        pk=approval["verifier_id"], enabled=True
    )
    verify_approval(approval, verifier.public_key, settings.PUBLIC_ORIGIN)
    claim_id, comparison = approval["claim_id"], approval["comparison"]
    preliminary = EnrollmentClaim.objects.get(pk=claim_id)
    _, member = lock_invitation(preliminary.invitation_id)
    claim = EnrollmentClaim.objects.select_for_update().get(pk=claim_id)
    now = timezone.now()
    if (
        claim.used_at
        or claim.revoked_at
        or claim.expires_at <= now
        or claim.approved_at
        or not hmac.compare_digest(claim.comparison, comparison.upper())
    ):
        raise ValueError("Demande indisponible ou comparaison incorrecte.")
    # Minimal approval receipt, fsynced before SQL, with no bearer secret/contact.
    append_record(
        "enrollment-" + str(claim.id),
        {
            "kind": "enrollment_approved",
            "claim_id": str(claim.id),
            "event_id": str(member.event_id),
            "verifier_id": str(verifier.id),
            "approved_at": now.isoformat(),
        },
    )
    claim.approved_at = now
    claim.approved_by = verifier
    claim.expires_at = min(claim.expires_at, now + timedelta(minutes=15))
    claim.save(update_fields=["approved_at", "approved_by", "expires_at"])
    SecurityEvent.objects.create(identity=member.identity, category="enrollment_approved")


@sensitive_variables("binding")
def bound_claim(claim_id, binding):
    claim = EnrollmentClaim.objects.select_related("invitation__member__event").get(pk=claim_id)
    if not isinstance(binding, str) or not hmac.compare_digest(
        claim.binding_digest, hashlib.sha256(binding.encode()).hexdigest()
    ):
        raise ValueError("Autre navigateur.")
    if claim.used_at or claim.revoked_at or claim.expires_at <= timezone.now():
        raise ValueError("Demande expirée.")
    return claim


@transaction.atomic
@sensitive_variables("binding", "code")
def activate(claim_id, binding):
    preliminary = EnrollmentClaim.objects.get(pk=claim_id)
    if preliminary.approved_by_id is None:
        raise ValueError("Vérification indépendante nécessaire.")
    EnrollmentVerifier.objects.select_for_update().get(pk=preliminary.approved_by_id, enabled=True)
    invitation, member = lock_invitation(preliminary.invitation_id)
    EnrollmentClaim.objects.select_for_update().get(pk=claim_id)
    claim = bound_claim(claim_id, binding)
    if claim.approved_at is None:
        raise ValueError("La vérification indépendante n'est pas terminée.")
    code = random_code()
    generation = uuid.uuid4()
    AccessCredential.objects.update_or_create(
        identity=member.identity,
        defaults={
            "digest": code_digest(code),
            "generation": generation,
            "enabled": True,
        },
    )
    now = timezone.now()
    member.claimed_at = member.claimed_at or now
    member.save(update_fields=["claimed_at"])
    VerifiedIdentity.objects.filter(pk=member.identity_id).update(verified_at=now)
    invitation.used_at = now
    invitation.save(update_fields=["used_at"])
    claim.used_at = now
    claim.save(update_fields=["used_at"])
    EnrollmentClaim.objects.filter(invitation__member=member, used_at=None, revoked_at=None).update(
        revoked_at=now
    )
    Invitation.objects.filter(member=member, used_at=None, revoked_at=None).update(revoked_at=now)
    SecurityEvent.objects.create(identity=member.identity, category="code_activated")
    return member.identity.user, code, str(generation)


@transaction.atomic
@sensitive_variables("current_code", "code")
def rotate(user, current_code):
    credential = AccessCredential.objects.select_for_update().get(
        identity__user=user, identity__email__isnull=True, enabled=True
    )
    if not hmac.compare_digest(credential.digest, code_digest(current_code)):
        raise ValueError("Code incorrect.")
    code = random_code()
    credential.digest = code_digest(code)
    credential.generation = uuid.uuid4()
    credential.save()
    SecurityEvent.objects.create(identity=credential.identity, category="code_rotated")
    return code, str(credential.generation)


@transaction.atomic
def recovery_invitation(member_id):
    from noel_operations import append_record, journal, lock, paused

    journal()
    lock()
    if not enabled() or paused():
        raise ValueError("Inscription indisponible.")
    preliminary = Membership.objects.get(pk=member_id)
    event = PrivateEvent.objects.select_for_update().get(pk=preliminary.event_id)
    member = Membership.objects.select_for_update().select_related("identity").get(pk=member_id)
    if (
        member.identity.email is not None
        or not member.claimed_at
        or not member.active
        or event.state in {"CANCELLED", "CLOSED", "ARCHIVED"}
    ):
        raise ValueError("Récupération indisponible.")
    now = timezone.now()
    invitation_id = uuid.uuid4()
    append_record(
        "recovery-" + str(invitation_id),
        {
            "kind": "code_recovery",
            "event_id": str(member.event_id),
            "invitation_id": str(invitation_id),
            "created_at": now.isoformat(),
        },
    )
    Invitation.objects.filter(member=member, used_at=None, revoked_at=None).update(revoked_at=now)
    return Invitation.objects.create(
        id=invitation_id,
        member=member,
        token_digest=hashlib.sha256(secrets.token_bytes(32)).hexdigest(),
        recovery=True,
        expires_at=now + timedelta(days=1),
    )
