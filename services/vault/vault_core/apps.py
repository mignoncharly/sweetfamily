from django.apps import AppConfig


class VaultCoreConfig(AppConfig):
    name = "vault_core"

    def ready(self):
        from . import signals  # noqa: F401
