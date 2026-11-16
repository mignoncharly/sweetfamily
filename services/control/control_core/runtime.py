from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import URLPattern, URLResolver, get_resolver

from .models import EnvironmentIdentity


def assert_routes(patterns=None):
    for pattern in patterns if patterns is not None else get_resolver().url_patterns:
        if any(w in str(pattern.pattern).lower() for w in ("diagnostic", "debug", "synthetic")):
            raise ImproperlyConfigured("Diagnostic routes forbidden")
        if isinstance(pattern, URLResolver):
            assert_routes(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            module = getattr(pattern.callback, "__module__", "")
            if any(w in module.lower() for w in ("diagnostic", "debug", "synthetic")):
                raise ImproperlyConfigured("Diagnostic handler forbidden")


def assert_runtime():
    assert_routes()
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        raise ImproperlyConfigured("Pending migrations")
    marker = EnvironmentIdentity.objects.filter(pk=1).first()
    if marker is None or (marker.app_env, marker.service_role) != (
        settings.APP_ENV,
        settings.SERVICE_ROLE,
    ):
        raise ImproperlyConfigured("Database environment identity mismatch")
