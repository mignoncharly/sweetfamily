import sys
from pathlib import Path

import tasks
from noel_server import serve_application

role = sys.argv[1]
if role not in {"control", "vault"}:
    raise SystemExit("Invalid role")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / role))
serve_application(
    f"{role}_project.wsgi:application",
    port=int(sys.argv[2]) if len(sys.argv) > 2 else tasks.WEB_PORTS[role],
    processes=tasks.WEB_PROCESSES,
    threads=tasks.WEB_THREADS,
)
