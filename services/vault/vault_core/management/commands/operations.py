from django.core.management.base import BaseCommand, CommandError
from noel_operations import (
    delete_account,
    enter_maintenance,
    initialize_journal,
    purge_due,
    recover,
    resume,
    status,
)


class Command(BaseCommand):
    help = "Operator-only maintenance, external deletion journal and restore verification."

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=[
                "init",
                "maintenance",
                "purge",
                "recover",
                "verify",
                "resume",
                "backup",
                "restore-isolated",
                "expire-backups",
                "delete-account",
                "status",
            ],
        )
        parser.add_argument("--directory")
        parser.add_argument("--archive")
        parser.add_argument("--user-id", type=int)

    def handle(self, *args, **options):
        from noel_backups import backup, expire_backups, restore_isolated

        actions = {
            "init": initialize_journal,
            "maintenance": enter_maintenance,
            "purge": purge_due,
            "recover": recover,
            "verify": lambda: recover(restored=False),
            "resume": resume,
            "backup": lambda: backup(options["directory"]),
            "restore-isolated": lambda: restore_isolated(options["archive"]),
            "expire-backups": lambda: expire_backups(options["directory"]),
            "delete-account": lambda: delete_account(options["user_id"]),
            "status": status,
        }
        try:
            result = actions[options["action"]]()
        except Exception:
            raise CommandError(
                "Operation failed; keep maintenance active and inspect privately."
            ) from None
        self.stdout.write(f"{options['action']}: completed; result={result}")
