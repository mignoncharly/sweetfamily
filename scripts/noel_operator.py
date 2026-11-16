"""Local native operator entry point; credentials are never passed to application workers."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import tasks


def main():
    if Path(sys.executable).resolve() != tasks.PYTHON.resolve():
        raise SystemExit(subprocess.call([str(tasks.PYTHON), __file__, *sys.argv[1:]]))
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "confirm-durability",
            "reopen-failed",
            "migrate-envelopes",
            "rotate-keys",
            "stage-master-key",
            "activate-master-key",
            "operations-init",
            "maintenance",
            "purge",
            "recover",
            "resume",
            "backup",
            "verify",
            "restore-isolated",
            "expire-backups",
            "delete-account",
            "status",
        ],
    )
    parser.add_argument("event_id", nargs="?")
    parser.add_argument("--to-key")
    parser.add_argument("--role", choices=tasks.ROLES, default="vault")
    parser.add_argument("--archive")
    parser.add_argument("--database")
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args()
    tasks.ensure_auth_secrets()
    values = tasks.config()
    if args.action in {
        "operations-init",
        "maintenance",
        "purge",
        "recover",
        "resume",
        "backup",
        "verify",
        "restore-isolated",
        "expire-backups",
        "delete-account",
        "status",
    }:
        env = tasks.environment(args.role)
        if args.database:
            if not re.fullmatch(r"noel_recovery_[a-f0-9]{32}", args.database):
                parser.error("Only an isolated recovery database may be selected")
            env.update(DB_NAME=args.database, FORCE_MAINTENANCE="true")
        env.update(
            OPERATIONS_DIRECTORY=str(tasks.LOCAL / "operations"),
            OPERATIONS_KEY=values[args.role.upper() + "_OPERATIONS_KEY"],
            BACKUP_ENCRYPTION_KEY=values[args.role.upper() + "_BACKUP_KEY"],
            BACKUP_DB_USER="noel_admin",
            BACKUP_DB_PASSWORD=values[args.role.upper() + "_DB_ADMIN_PASSWORD"],
            PG_BIN=str(tasks.ROOT / ".local/tools/postgresql/pgsql/bin"),
        )
        action = "init" if args.action == "operations-init" else args.action
        extra = ["--directory", str(tasks.LOCAL / "backups" / args.role)]
        if args.archive:
            extra.extend(["--archive", args.archive])
        if args.user_id is not None:
            extra.extend(["--user-id", str(args.user_id)])
        tasks.run(
            [
                tasks.PYTHON,
                tasks.ROOT / f"services/{args.role}/manage.py",
                "operations",
                action,
                *extra,
            ],
            env=env,
        )
        return
    if args.action in {"stage-master-key", "activate-master-key"}:
        if not args.to_key or not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", args.to_key):
            parser.error("--to-key requires an opaque version identifier")
        keys = json.loads(values["VAULT_MASTER_KEYS"])
        if args.action == "stage-master-key":
            from cryptography.fernet import Fernet

            keys.setdefault(args.to_key, Fernet.generate_key().decode())
            values["VAULT_MASTER_KEYS"] = json.dumps(keys)
        else:
            if args.to_key not in keys:
                parser.error("Stage this master version first")
            values["VAULT_ACTIVE_MASTER_KEY"] = args.to_key
        (tasks.ROOT / ".env").write_text(
            "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
        )
        print(
            "Local master configuration updated; retain old versions. "
            "Restart vault processes after activation."
        )
        return
    if not args.event_id:
        parser.error("event_id is required")
    env = tasks.environment("vault")
    command = "reopen_failed_draw"
    extra = []
    if args.action == "confirm-durability":
        command = "confirm_draw_durability"
        env.update(
            BACKUP_ENCRYPTION_KEY=values["VAULT_BACKUP_KEY"],
            BACKUP_DB_USER="noel_admin",
            BACKUP_DB_PASSWORD=values["VAULT_DB_ADMIN_PASSWORD"],
            PG_BIN=str(tasks.ROOT / ".local/tools/postgresql/pgsql/bin"),
            OPERATIONS_DIRECTORY=str(tasks.LOCAL / "operations"),
            OPERATIONS_KEY=values["VAULT_OPERATIONS_KEY"],
        )
        extra = ["--directory", str(tasks.ROOT / ".local/backups/vault")]
    if args.action == "migrate-envelopes":
        command = "migrate_private_envelopes"
        extra = ["--event-id", args.event_id]
    elif args.action == "rotate-keys":
        if not args.to_key:
            parser.error("--to-key required")
        command = "rotate_private_keys"
        extra = ["--event-id", args.event_id, "--to-key", args.to_key]
    event_args = [] if args.action in {"migrate-envelopes", "rotate-keys"} else [args.event_id]
    tasks.run(
        [tasks.PYTHON, tasks.ROOT / "services/vault/manage.py", command, *event_args, *extra],
        env=env,
    )


if __name__ == "__main__":
    main()
