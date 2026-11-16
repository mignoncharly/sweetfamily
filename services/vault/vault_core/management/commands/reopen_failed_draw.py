from django.core.management.base import BaseCommand, CommandError

from vault_core.draw_service import reopen_failed


class Command(BaseCommand):
    help = "Rouvre uniquement un calcul définitivement échoué et jamais scellé."

    def add_arguments(self, parser):
        parser.add_argument("event_id")

    def handle(self, *args, **options):
        try:
            reopen_failed(options["event_id"])
        except Exception:
            raise CommandError("Réouverture interdite.") from None
        self.stdout.write("Groupe rouvert ; nouveau manifeste et confirmations obligatoires.")
