from django.apps import AppConfig


class ControlCoreConfig(AppConfig):
    name = "control_core"

    def ready(self):
        from . import signals  # noqa: F401
