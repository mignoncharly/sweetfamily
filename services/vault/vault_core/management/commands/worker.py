import signal
import threading

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from noel_operations import MaintenanceRequired, serving

from vault_core.domain import deliver_one, project_one
from vault_core.draw_service import run_one_draw
from vault_core.notifications import reconcile, schedule_one
from vault_core.runtime import assert_runtime


class Command(BaseCommand):
    help = "Compute fenced draw jobs, dispatch local mail and batch safe projections."

    def handle(self, *args, **options):
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        assert_runtime()
        self.stdout.write("Vault draw, mail and safe projection worker running")
        while not stop.wait(1):
            close_old_connections()
            assert_runtime()
            try:
                with serving():
                    run_one_draw()
                    schedule_one()
                    deliver_one()
                    reconcile()
                    project_one()
            except MaintenanceRequired:
                continue
