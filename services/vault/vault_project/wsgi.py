import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vault_project.settings")
from vault_core.hardening import harden_process  # noqa: E402

harden_process()
application = get_wsgi_application()
from vault_core.runtime import assert_runtime  # noqa: E402

assert_runtime()
