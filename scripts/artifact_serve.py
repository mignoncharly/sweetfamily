import os
import sys
from pathlib import Path

from waitress import serve

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ROLE_project.settings")
from ROLE_project.wsgi import application

if __name__ == "__main__":
    serve(
        application,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        threads=4,
        clear_untrusted_proxy_headers=True,
    )
