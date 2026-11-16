import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "control_project.settings")
application = get_wsgi_application()
from control_core.runtime import assert_runtime  # noqa: E402

assert_runtime()
