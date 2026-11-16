from allauth.account.adapter import DefaultAccountAdapter
from allauth.mfa.adapter import DefaultMFAAdapter

from .secrets import decrypt, encrypt


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return True


class MFAAdapter(DefaultMFAAdapter):
    def encrypt(self, text):
        return encrypt(text)

    def decrypt(self, text):
        return decrypt(text)

    def can_delete_authenticator(self, authenticator):
        from allauth.mfa.models import Authenticator

        from .models import EventDraft

        if (
            authenticator.type in {"totp", "webauthn"}
            and EventDraft.objects.filter(owner__user=authenticator.user).exists()
        ):
            return (
                Authenticator.objects.filter(user=authenticator.user, type__in=["totp", "webauthn"])
                .exclude(pk=authenticator.pk)
                .exists()
            )
        return super().can_delete_authenticator(authenticator)
