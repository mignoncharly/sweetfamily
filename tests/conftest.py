import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

workspace_temp = Path(__file__).resolve().parents[1] / ".local/pytest-tmp"
workspace_temp.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("PYTEST_DEBUG_TEMPROOT", str(workspace_temp))

# Test subprocesses always use local SMTP, even when the operator configures live credentials.
os.environ["NOEL_TEST_MAILPIT"] = "true"
