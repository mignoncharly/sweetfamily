from django.core.management.base import BaseCommand, CommandError
from noel_delivery import reconcile_notification

from vault_core.models import DeliveryReceipt, PendingMail


class Command(BaseCommand):
    help = "Read-only provider lookup; records facts without resending mail."

    def add_arguments(self, parser):
        parser.add_argument("notification_id")
        parser.add_argument("--provider-id")

    def handle(self, *args, **options):
        try:
            status = reconcile_notification(
                PendingMail, DeliveryReceipt, options["notification_id"], options["provider_id"]
            )
        except Exception:
            raise CommandError("Réconciliation non confirmée ; aucun message renvoyé.") from None
        self.stdout.write("Fait fournisseur enregistré : " + status)
