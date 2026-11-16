from allauth.account.signals import email_changed, login_code_rejected
from allauth.usersessions.models import UserSession
from django.dispatch import receiver
from django.utils import timezone

from .models import Invitation, PendingMail, SecurityEvent, VerifiedIdentity


@receiver(email_changed)
def email_updated(sender, request, user, to_email_address, **kwargs):
    identity = VerifiedIdentity.objects.get(user=user)
    if identity.email == to_email_address.email:
        identity.verified_at = timezone.now()
        identity.save(update_fields=["verified_at"])
        return
    identity.email = to_email_address.email
    identity.verified_at = timezone.now()
    identity.save(update_fields=["email", "verified_at"])
    Invitation.objects.filter(member__identity=identity, used_at=None, revoked_at=None).update(
        revoked_at=timezone.now()
    )
    PendingMail.objects.filter(
        identity=identity, category="AUTH", state__in=["QUEUED", "RUNNING"]
    ).update(state="EXPIRED", payload="")
    for session in UserSession.objects.filter(user=user):
        session.end()
    request.session.flush()
    SecurityEvent.objects.create(identity=identity, category="email_changed_sessions_revoked")


@receiver(login_code_rejected)
def code_rejected(sender, user, **kwargs):
    if user is not None:
        identity = VerifiedIdentity.objects.filter(user=user).first()
        if identity:
            SecurityEvent.objects.create(identity=identity, category="login_code_rejected")
