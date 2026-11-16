"""Install the pinned Linux x86_64 uv binary into this project only."""

import hashlib
import io
import json
import platform
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        raise SystemExit("This helper supports Linux x86_64; install pinned uv for your platform")
    tool = json.loads((ROOT / "infra/tool-versions.json").read_text())["uv_linux_x86_64"]
    directory = ROOT / ".local/tools"
    directory.mkdir(parents=True, exist_ok=True)
    (ROOT / ".local").chmod(0o700)
    target = directory / "uv"
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != tool["binary_sha256"]:
            raise SystemExit("Existing project uv hash mismatch; refusing to replace it")
    else:
        with urllib.request.urlopen(tool["url"], timeout=60) as response:
            archive = response.read()
        if hashlib.sha256(archive).hexdigest() != tool["archive_sha256"]:
            raise SystemExit("uv archive hash mismatch")
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            content = tar.extractfile("uv-x86_64-unknown-linux-gnu/uv").read()
        if hashlib.sha256(content).hexdigest() != tool["binary_sha256"]:
            raise SystemExit("uv binary hash mismatch")
        target.write_bytes(content)
        target.chmod(0o700)
    print("Pinned project uv verified; no system paths or shell profiles changed")


if __name__ == "__main__":
    main()
