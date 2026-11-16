from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter

from .secrets import decrypt, encrypt


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix, email, context):
        from datetime import timedelta

        from django.utils import timezone

        from .domain import queue_mail

        message = self.render_mail(template_prefix, email, context)
        from .models import VerifiedIdentity

        identity = (
            VerifiedIdentity.objects.filter(user=self.request.user).first()
            if self.request.user.is_authenticated
            else None
        )
        queue_mail(
            message.subject,
            message.body,
            email,
            timezone.now() + timedelta(minutes=10),
            identity=identity,
            category="AUTH" if context.get("code") else "NOTICE",
        )

    def clean_email(self, email):
        from django.core.exceptions import ValidationError

        from .models import VerifiedIdentity

        query = VerifiedIdentity.objects.filter(email=email)
        if self.request and self.request.user.is_authenticated:
            query = query.exclude(user=self.request.user)
            if query.exists():
                raise ValidationError("Adresse indisponible.")
        return super().clean_email(email)

    def is_open_for_signup(self, request):
        return False


class MFAAdapter(DefaultMFAAdapter):
    def encrypt(self, text):
        return encrypt(text)

    def decrypt(self, text):
        return decrypt(text)
