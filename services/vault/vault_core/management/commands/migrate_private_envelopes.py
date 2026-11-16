from django.core.management.base import BaseCommand, CommandError

from vault_core.hardening import harden_process
from vault_core.key_operations import migrate_event
from vault_core.models import PrivateEvent


class Command(BaseCommand):
    help = "Operator-only private envelope operation; no plaintext output."

    def add_arguments(self, parser):
        parser.add_argument("--event-id")

    def handle(self, *args, **options):
        harden_process()
        try:
            events = PrivateEvent.objects.all()
            if options["event_id"]:
                events = events.filter(pk=options["event_id"])
            if options["event_id"] and not events.exists():
                raise ValueError()
            for event_id in events.values_list("id", flat=True).iterator():
                migrate_event(event_id)
        except Exception:
            raise CommandError(
                "Opération non terminée ; conserver toutes les anciennes clés."
            ) from None
        self.stdout.write("Opération terminée. Conserver les clés nécessaires aux sauvegardes.")
