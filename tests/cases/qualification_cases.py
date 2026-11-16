"""Phase 9 scenarios. Fixtures are synthetic; availability never bypasses durability."""

import uuid

import pytest
import tasks
from django.test import Client
from draw_cases import command
from noel_contracts import sign
from vault_cases import claim, open_message
from vault_core.domain import apply_command
from vault_core.draw_crypto import unseal
from vault_core.draw_service import consent, run_one_draw
from vault_core.durability import release
from vault_core.models import PrivateEvent, SealedDraw
from vault_core.wishlists import save_list
from wishlist_cases import items


def eight_person_group():
    payload = open_message()["payload"]
    payload["members"] = [
        {
            "id": str(uuid.uuid4()),
            "display_name": f"Personne {i}",
            "country": "FR" if i % 2 else "DE",
            "email": f"qualification-{i}@example.invalid",
        }
        for i in range(8)
    ]
    apply_command(sign("open", payload, tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"]))
    event = PrivateEvent.objects.get(pk=payload["event_id"])
    for member in event.members.all():
        claim(member)
        save_list(member, 0, items(), validate=True)
    apply_command(command(event, "freeze"))
    event.refresh_from_db()
    for member in event.members.all():
        consent(member, event.manifest_version, event.manifest_digest)
    apply_command(command(event, "draw"))
    run_one_draw()
    return event, SealedDraw.objects.get(event=event)


def test_T01_eight_fr_de_members_only_see_their_own_bijective_assignment():
    event, draw = eight_person_group()
    # Explicit fixture proof; native restore is covered separately, without this shortcut.
    release(draw.id, {"sealed_id": str(draw.id), "fixture": True})
    pairs = unseal(draw)["permutation"]
    ids = {str(m.id) for m in event.members.all()}
    assert len(pairs) == 8 and {g for g, r in pairs} == ids and {r for g, r in pairs} == ids
    names = {str(m.id): m.display_name for m in event.members.all()}
    expected = dict(pairs)
    for member in event.members.all():
        client = Client()
        client.force_login(member.identity.user)
        response = client.get(f"/api/me/recipient?event_id={event.id}")
        assert (
            response.status_code == 200
            and response.json()["recipient"]["display_name"] == names[expected[str(member.id)]]
        )
        assert set(response.json()) == {"recipient", "revision", "wishes", "advice"}


def test_T21_availability_is_safe_get_and_cancellation_blocks_old_session():
    event, draw = eight_person_group()
    member = event.members.first()
    client = Client()
    client.force_login(member.identity.user)
    url = f"/api/me/availability?event_id={event.id}"
    assert client.get(url).json() == {"state": "DRAWN", "available": False}
    member.refresh_from_db()
    assert not member.recipient_viewed
    release(draw.id, {"sealed_id": str(draw.id), "fixture": True})
    assert client.get(url).json() == {"state": "DRAWN", "available": True}
    client.post(
        f"/api/me/recipient/reveal?event_id={event.id}", {}, content_type="application/json"
    )
    apply_command(command(event, "cancel", confirm=True))
    assert client.get(url).json() == {"state": "CANCELLED", "available": False}
    assert client.get(f"/api/me/recipient?event_id={event.id}").status_code == 409
    stranger = Client()
    assert stranger.get(url).status_code == 401
    assert client.get(url + "&member_id=" + str(member.id)).status_code == 400
    assert client.get(f"/api/me/availability?event_id={uuid.uuid4()}").status_code == 404


@pytest.mark.parametrize("count", [2, 3])
def test_T03_small_group_refused_before_private_data(count):
    payload = open_message()["payload"]
    payload["members"] = payload["members"][:count]
    with pytest.raises(ValueError, match="4 et 20"):
        apply_command(sign("open", payload, tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"]))
    assert not PrivateEvent.objects.filter(pk=payload["event_id"]).exists()
