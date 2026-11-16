from django.core.management.base import BaseCommand

from control_core.runtime import assert_runtime


class Command(BaseCommand):
    def handle(self, *args, **options):
        assert_runtime()
        self.stdout.write("Runtime checks passed")
