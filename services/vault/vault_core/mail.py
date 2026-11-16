from django.core.mail.backends.base import BaseEmailBackend


class DisabledBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise RuntimeError("Direct sending blocked; use the encrypted outbox")
