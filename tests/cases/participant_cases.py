from django.test import Client
from draw_cases import command, group
from private_cases import choice, fixture, url
from vault_core.domain import apply_command
from vault_core.models import PendingMail


def test_participant_forms_and_profile_conflict_keep_revision():
    event = group(freeze=False)
    member = event.members.first()
    c = Client()
    c.force_login(member.identity.user)
    for path in ("/profile", "/merchant", "/withdraw"):
        assert c.get(f"{path}?event_id={event.id}").status_code == 200
    path = f"/profile?event_id={event.id}"
    data = {"revision": member.revision, "display_name": "Élodie", "country": "DE"}
    assert c.post(path, data).status_code == 302
    response = c.post(path, data | {"display_name": "Saisie conservée"})
    assert response.status_code == 409 and "Saisie conservée" in response.content.decode()
    assert c.post(f"/merchant?event_id={event.id}", {"hostname": "example.org"}).status_code == 302


def test_private_conflict_retains_old_revision_and_all_edits_and_mask_control():
    event, member, c = fixture()
    path = f"/private?event_id={event.id}"
    assert b"data-hide-private" in c.post(path, {"action": "reveal"}).content
    data = choice(member)
    assert c.put(url(member, "purchase"), data, content_type="application/json").status_code == 200
    response = c.post(
        path,
        {
            "action": "purchase",
            "revision": 0,
            "state": "RECEIVED",
            "wish_id": data["wish_id"],
            "note": "Conserver ma note",
        },
    )
    text = response.content.decode()
    assert response.status_code == 409 and 'name="revision" value="0"' in text
    assert 'value="RECEIVED" selected' in text and "Conserver ma note" in text


def test_ownership_notice_preserves_group_manifest_and_assignments():
    event, member, c = fixture()
    before = event.frozen_manifest
    import uuid

    message = command(
        event, "ownership_changed", transfer_ref=str(uuid.uuid4()), owner_label="Élodie"
    )
    apply_command(message)
    apply_command(message)
    event.refresh_from_db()
    assert event.frozen_manifest == before
    assert PendingMail.objects.filter(event=event, kind="OWNERSHIP").count() == 4
    import json

    from vault_core.secrets import decrypt

    assert all(
        "Élodie" in json.loads(decrypt(m.payload))["body"]
        for m in PendingMail.objects.filter(event=event, kind="OWNERSHIP")
    )


def test_copied_public_exclusions_are_applied_when_opening_new_group():
    import tasks
    from noel_contracts import sign
    from vault_cases import open_message

    message = open_message()
    payload = message["payload"]
    ids = [row["id"] for row in payload["members"]]
    payload["exclusions"] = [[ids[0], ids[1]]]
    apply_command(sign("open", payload, tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"]))
    from vault_core.models import Exclusion

    assert (
        Exclusion.objects.filter(
            event_id=payload["event_id"], giver_id=ids[0], recipient_id=ids[1]
        ).count()
        == 1
    )


def test_owner_transfer_is_refused_during_draw_without_changing_job_or_version():
    import uuid

    import pytest
    from draw_cases import start
    from vault_core.draw_service import StateConflict
    from vault_core.models import DrawJob

    event = start()
    version = event.version
    with pytest.raises(StateConflict):
        apply_command(
            command(
                event, "ownership_changed", transfer_ref=str(uuid.uuid4()), owner_label="Élodie"
            )
        )
    event.refresh_from_db()
    assert event.version == version and event.state == "DRAWING"
    assert DrawJob.objects.get(event=event).state == "PENDING"
