from email.utils import parseaddr

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from noel_delivery import provider_request


class Command(BaseCommand):
    help = "Read-only verification of configured sending domain and tracking policy."

    def handle(self, *args, **options):
        import uuid

        try:
            if settings.MAIL_PROVIDER == "zoho":
                from noel_delivery import zoho_connection

                address = next(iter(settings.MAIL_TEST_RECIPIENTS), settings.DEFAULT_FROM_EMAIL)
                with zoho_connection({"from": settings.DEFAULT_FROM_EMAIL, "email": address}):
                    pass
                self.stdout.write(
                    "TLS/authentification SMTP vérifiés ; aucun email envoyé. "
                    "La livraison en boîte reste non vérifiée."
                )
                return
            domain_id = str(uuid.UUID(settings.RESEND_DOMAIN_ID))
            domain = provider_request("/domains/" + domain_id)
            sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rsplit("@", 1)[1].casefold()
            if (
                domain["status"] != "verified"
                or domain["name"].casefold() != sender
                or domain.get("open_tracking") is not False
                or domain.get("click_tracking") is not False
            ):
                raise ValueError()
            records = domain.get("records", [])
            for kind in ("SPF", "DKIM"):
                if not any(
                    row.get("record") == kind and row.get("status") == "verified" for row in records
                ):
                    raise ValueError()
        except Exception:
            raise CommandError("Domaine ou politique non vérifiés. Aucun message envoyé.") from None
        self.stdout.write(
            "Domaine/SPF/DKIM et suivi désactivé vérifiés. "
            "Vérifier aussi DMARC, les webhooks et une boîte autorisée."
        )
