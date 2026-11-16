"""Maximum-size cryptographic draw timing; never saves the generated permutation."""

import json
import os
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/vault"))
from vault_core.draw_engine import sample, validate_result  # noqa: E402


def measure(directory):
    samples = []
    for _ in range(3):
        ids = [str(i) for i in range(20)]
        started = time.perf_counter()
        result = sample(ids, [], timeout=60)
        validate_result(ids, [], result)
        samples.append(round(time.perf_counter() - started, 6))
    data = {
        "participants": 20,
        "runs": 3,
        "seconds": samples,
        "limit_seconds": 60,
        "target_met": max(samples) < 60,
        "exclusions": 0,
        "rng": "production secrets.randbelow",
        "host": {
            "os": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "logical_cpus": os.cpu_count(),
        },
        "resource_limits": "none; not the proposed 2 vCPU/4 GiB production configuration",
    }
    (Path(directory) / "engine.json").write_text(json.dumps(data, indent=2), encoding="utf8")


if __name__ == "__main__":
    measure(sys.argv[1])
