from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from vault_core.access_codes import recovery_invitation


class Command(BaseCommand):
    help = "Independent operator only: start a new verification without changing any assignment."

    def add_arguments(self, parser):
        parser.add_argument("member_id")

    def handle(self, *args, **options):
        try:
            invitation = recovery_invitation(options["member_id"])
        except Exception:
            raise CommandError("Recovery refused.") from None
        self.stdout.write(
            f"Non-authenticating enrollment link: {settings.PUBLIC_ORIGIN}/accounts/enroll/"
            f"{invitation.member_id}/\n"
            "A fresh private identity check is required. No code is shown."
        )
