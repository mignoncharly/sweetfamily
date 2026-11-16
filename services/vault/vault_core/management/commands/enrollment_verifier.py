import base64
import json
import uuid
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from noel_operations import append_record, journal, lock

from vault_core.models import EnrollmentVerifier


class Command(BaseCommand):
    help = "Independent technical operator: explicitly grant/revoke enrollment approval only."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["grant", "revoke"])
        parser.add_argument("--public-key-file")
        parser.add_argument("--verifier-id")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            journal()
            lock()
            if options["action"] == "grant":
                value = json.loads(Path(options["public_key_file"]).read_text())
                if (
                    set(value) != {"id", "public_key"}
                    or value["public_key"] == settings.COMMAND_KEY
                ):
                    raise ValueError()
                Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(value["public_key"]))
                role, created = EnrollmentVerifier.objects.get_or_create(
                    id=value["id"], defaults={"public_key": value["public_key"]}
                )
                if not created and role.public_key != value["public_key"]:
                    raise ValueError()
            else:
                role = EnrollmentVerifier.objects.select_for_update().get(pk=options["verifier_id"])
            append_record(
                "verifier-" + str(role.id) + "-" + uuid.uuid4().hex,
                {
                    "kind": "verifier_role",
                    "verifier_id": str(role.id),
                    "action": options["action"],
                },
            )
            role.enabled = options["action"] == "grant"
            role.save()
        except Exception:
            raise CommandError(
                "Verifier role change refused; no organizer privilege is granted."
            ) from None
        self.stdout.write(
            "Independent vault operator approval role updated. No private access granted."
        )
