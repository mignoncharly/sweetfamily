from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from control_core.models import EnvironmentIdentity


class Command(BaseCommand):
    help = "Bind a new database once; never rebind a restored or foreign database."

    def handle(self, *args, **options):
        with transaction.atomic():
            marker, _ = EnvironmentIdentity.objects.get_or_create(
                pk=1, defaults={"app_env": settings.APP_ENV, "service_role": settings.SERVICE_ROLE}
            )
            if (marker.app_env, marker.service_role) != (settings.APP_ENV, settings.SERVICE_ROLE):
                raise CommandError("Database environment identity mismatch")
        self.stdout.write("Environment identity verified")
