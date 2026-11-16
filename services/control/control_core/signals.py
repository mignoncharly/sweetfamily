from allauth.account.signals import email_changed
from django.dispatch import receiver

from .models import AuthMail


@receiver(email_changed)
def expire_old_auth_mail(sender, user, **kwargs):
    AuthMail.objects.filter(user=user, state__in=["QUEUED", "RUNNING"]).update(
        state="EXPIRED", payload="", lease_until=None
    )
