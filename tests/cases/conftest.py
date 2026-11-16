import pytest
from django.core.cache import cache
from django.db import transaction
from django.test import override_settings


@pytest.fixture(autouse=True)
def operations_journal(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from noel_operations import initialize_journal

    monkeypatch.setenv("OPERATIONS_DIRECTORY", str(tmp_path / "journal"))
    monkeypatch.setenv("OPERATIONS_KEY", Fernet.generate_key().decode())
    initialize_journal()


@pytest.fixture(autouse=True)
def isolate(django_db_blocker, request):
    with (
        django_db_blocker.unblock(),
        override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"),
    ):
        if request.node.get_closest_marker("concurrent_db"):
            cache.clear()
            yield
            return
        with transaction.atomic():
            from django.core import mail

            mail.outbox = []
            cache.clear()
            yield
            transaction.set_rollback(True)
