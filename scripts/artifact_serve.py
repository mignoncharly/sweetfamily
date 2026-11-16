import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ROLE_project.settings")
from noel_server import serve_application

if __name__ == "__main__":
    serve_application(
        "ROLE_project.wsgi:application",
        port=int(os.environ.get("PORT", "8000")),
        processes=int(os.environ.get("WEB_PROCESSES", "1")),
        threads=int(os.environ.get("WEB_THREADS", "4")),
    )
