"""Offline signing tool for an appointed independent verifier. No database/network access."""

import argparse
import base64
import json
import os
import stat
import sys
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages/contracts"))
from noel_enrollment_approval import sign_approval  # noqa: E402


def write_private(path, value):
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
        json.dump(value, stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init")
    init.add_argument("--directory", type=Path, required=True)
    sign = commands.add_parser("sign")
    sign.add_argument("--key-file", type=Path, required=True)
    sign.add_argument("--claim-id", type=uuid.UUID, required=True)
    sign.add_argument("--comparison", required=True)
    sign.add_argument("--vault-origin", required=True)
    sign.add_argument("--identity-verified", action="store_true", required=True)
    sign.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    if options.action == "init":
        options.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        key = Ed25519PrivateKey.generate()
        identity = {
            "id": str(uuid.uuid4()),
            "public_key": base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode(),
        }
        write_private(options.directory / "public.json", identity)
        write_private(
            options.directory / "private.json",
            identity
            | {
                "private_key": base64.urlsafe_b64encode(key.private_bytes_raw()).decode(),
            },
        )
        print("Created verifier key files. Transfer public.json only to the vault operator.")
    else:
        if os.name != "nt" and stat.S_IMODE(options.key_file.stat().st_mode) & 0o077:
            parser.error("Private key file must not be accessible to other users.")
        identity = json.loads(options.key_file.read_text())
        approval = sign_approval(
            identity, options.claim_id, options.comparison, options.vault_origin
        )
        write_private(options.output, approval)
        print(
            "Approval file created; valid for five minutes. No personal access code is generated."
        )


if __name__ == "__main__":
    main()
