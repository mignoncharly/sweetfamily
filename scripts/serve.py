import importlib
import sys
from pathlib import Path

from waitress import serve

role = sys.argv[1]
if role not in {"control", "vault"}:
    raise SystemExit("Invalid role")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / role))
application = importlib.import_module(f"{role}_project.wsgi").application
serve(
    application,
    host="127.0.0.1",
    port=int(sys.argv[2]) if len(sys.argv) > 2 else {"control": 8001, "vault": 8002}[role],
    threads=4,
    clear_untrusted_proxy_headers=True,
)
