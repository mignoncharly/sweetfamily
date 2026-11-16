"""Scan tracked/source files only; do not display matches containing secrets."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = (
    subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    .stdout.decode()
    .split("\0")
)
patterns = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bre_[A-Za-z0-9]{25,}\b"),
]
secrets = []
env = ROOT / ".env"
if env.exists():
    secrets = [
        line.split("=", 1)[1]
        for line in env.read_text().splitlines()
        if "=" in line and len(line.split("=", 1)[1]) >= 32
    ]
for encoded in list(secrets):
    try:
        decoded = json.loads(encoded)
    except ValueError:
        continue
    if isinstance(decoded, dict):
        secrets.extend(
            value for value in decoded.values() if isinstance(value, str) and len(value) >= 32
        )
failures = []
for name in paths:
    path = ROOT / name
    if not name or not path.is_file():
        continue
    content = path.read_bytes()
    if any(p.search(content.decode("utf-8", errors="ignore")) for p in patterns):
        failures.append(name)
    if any(secret.encode() in content for secret in secrets):
        failures.append(name)
if failures:
    print("Secret scan failed in: " + ", ".join(sorted(set(failures))), file=sys.stderr)
    raise SystemExit(1)
print("Source secret scan passed (patterns and local generated-secret canaries)")
