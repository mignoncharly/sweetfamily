from django.core.management.base import BaseCommand, CommandError

from vault_core.durability import backup_and_verify


class Command(BaseCommand):
    help = "Sauvegarde chiffrée, restauration isolée et libération du tirage scellé."

    def add_arguments(self, parser):
        parser.add_argument("event_id")
        parser.add_argument("--directory", required=True)

    def handle(self, *args, **options):
        try:
            backup_and_verify(options["event_id"], options["directory"])
        except Exception:
            raise CommandError("Durabilité non confirmée ; le résultat reste retenu.") from None
        self.stdout.write("Sauvegarde restaurée et résultat libéré.")
