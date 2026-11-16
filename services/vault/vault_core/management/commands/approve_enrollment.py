import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from vault_core.access_codes import approve


class Command(BaseCommand):
    help = "Independent vault operator only; compare the participant's own browser in private."

    def add_arguments(self, parser):
        parser.add_argument("--approval-file", required=True)

    def handle(self, *args, **options):
        try:
            path = Path(options["approval_file"])
            if path.stat().st_size > 4096:
                raise ValueError()
            approve(json.loads(path.read_text()))
        except Exception:
            raise CommandError("Approval refused; inspect the request privately.") from None
        self.stdout.write(
            "Approved for 15 minutes. Only the requesting browser can activate access."
        )
