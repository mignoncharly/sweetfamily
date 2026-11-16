from django.core.mail.backends.base import BaseEmailBackend


class DisabledBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise RuntimeError("Direct sending blocked; use the encrypted outbox")


class OutboxBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        import json
        from datetime import timedelta

        from allauth.account.models import EmailAddress
        from django.conf import settings
        from django.utils import timezone
        from noel_delivery import mac

        from .models import AuthMail
        from .secrets import encrypt

        count = 0
        for message in email_messages:
            if len(message.to) != 1 or message.cc or message.bcc or message.attachments:
                raise ValueError("Only one private recipient is supported")
            data = {
                "subject": message.subject,
                "body": message.body,
                "email": message.to[0],
                "from": settings.DEFAULT_FROM_EMAIL,
            }
            address = EmailAddress.objects.filter(email__iexact=message.to[0]).first()
            AuthMail.objects.create(
                user_id=address.user_id if address else None,
                payload=encrypt(json.dumps(data, ensure_ascii=False)),
                payload_mac=mac(data),
                expires_at=timezone.now() + timedelta(minutes=10),
                next_attempt_at=timezone.now(),
            )
            count += 1
        return count


def deliver_one():
    from noel_delivery import deliver_one as dispatch

    from .models import AuthMail, DeliveryReceipt
    from .secrets import decrypt, encrypt

    return dispatch(AuthMail, DeliveryReceipt, decrypt, encrypt)


def reconcile():
    from noel_delivery import reconcile_one

    from .models import AuthMail, DeliveryReceipt

    return reconcile_one(AuthMail, DeliveryReceipt)
