import signal
import threading

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from noel_operations import MaintenanceRequired, serving

from control_core.mail import deliver_one, reconcile
from control_core.runtime import assert_runtime


class Command(BaseCommand):
    help = "Dispatch encrypted authentication outbox and reconcile provider receipts."

    def handle(self, *args, **options):
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        assert_runtime()
        self.stdout.write("Control authentication mail worker running")
        while not stop.wait(1):
            close_old_connections()
            assert_runtime()
            try:
                with serving():
                    deliver_one()
                    reconcile()
            except MaintenanceRequired:
                continue
