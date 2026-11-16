import base64
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import close_old_connections, connections
from django.test import Client, override_settings
from draw_cases import cleanup, command, start
from helpers import user
from vault_core.domain import apply_command, project_one
from vault_core.draw_crypto import unseal
from vault_core.draw_service import run_one_draw
from vault_core.durability import release
from vault_core.envelopes import event_key
from vault_core.key_operations import migrate_event, rotate_event
from vault_core.models import (
    DrawJob,
    EventDataKey,
    Membership,
    PrivatePurchaseState,
    SealedDraw,
    SecurityEvent,
    Wishlist,
    WishlistRevision,
)
from vault_core.private_space import purchase, recipient, save_purchase
from vault_core.wishlists import aad, save_list, snapshot
from wishlist_cases import items


def fixture(available=True):
    event = start()
    run_one_draw()
    draw = SealedDraw.objects.get(event=event)
    if available:
        # Explicit fixture proof; the real pg_dump/restore gate is exercised by draw_cases.
        release(draw.id, {"sealed_id": str(draw.id), "fixture": True})
    member = event.members.first()
    client = Client()
    client.force_login(member.identity.user)
    event.refresh_from_db()
    return event, member, client


def url(member, name="recipient"):
    return f"/api/me/{name}?event_id={member.event_id}"


def choice(member, state="ORDERED", note="PURCHASE_PRIVATE_CANARY"):
    value = recipient(member, reveal=True)
    return {
        "revision": 0,
        "wish_id": value["wishes"][0]["id"],
        "wish_revision": value["revision"],
        "state": state,
        "note": note,
    }


def test_get_never_marks_reveal_and_page_requires_explicit_post():
    event, member, client = fixture()
    data = client.get(url(member))
    assert data.status_code == 200
    assert set(data.json()) == {"recipient", "revision", "wishes", "advice"}
    assert set(data.json()["recipient"]) == {"display_name", "country"}
    assert len(data.json()["wishes"]) == 3
    member.refresh_from_db()
    assert not member.recipient_viewed
    page = client.get(f"/private?event_id={event.id}")
    assert b"Canari" not in page.content
    assert data.json()["recipient"]["display_name"] not in page.content.decode()
    for header, expected in [("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer")]:
        assert data[header] == expected
    assert "frame-ancestors 'none'" in data["Content-Security-Policy"]
    before = event.next_projection_at
    response = client.post(url(member, "recipient/reveal"), {}, content_type="application/json")
    assert response.status_code == 200
    member.refresh_from_db()
    event.refresh_from_db()
    assert member.recipient_viewed and event.next_projection_at == before
    assert (
        client.post(url(member, "recipient/reveal"), {}, content_type="application/json").json()
        == response.json()
    )


def test_each_member_only_receives_own_assignment_and_own_buying_country():
    event, _, _ = fixture()
    draw = SealedDraw.objects.get(event=event)
    expected = dict(unseal(draw)["permutation"])
    for member in event.members.all():
        client = Client()
        client.force_login(member.identity.user)
        data = client.get(url(member)).json()
        target = event.members.get(pk=expected[str(member.id)])
        assert data["recipient"]["display_name"] == target.display_name
        assert data["advice"]["buyer_country"] == member.country
        assert data["wishes"] == snapshot(Wishlist.objects.get(member=target))
        assert "permutation" not in json.dumps(data) and "email" not in json.dumps(data)
        assert not client.get(url(member) + "&recipient_id=" + str(target.id)).status_code == 200


def test_foreign_session_service_credentials_and_csrf_are_rejected():
    _, member, client = fixture()
    for endpoint in ("recipient", "purchase", "recipient/reveal"):
        request = (
            (
                lambda c, endpoint=endpoint: c.post(
                    url(member, endpoint), {}, content_type="application/json"
                )
            )
            if endpoint.endswith("reveal")
            else (lambda c, endpoint=endpoint: c.get(url(member, endpoint)))
        )
        assert request(Client()).status_code == 401
        stranger = Client()
        stranger.force_login(user("stranger" + endpoint.replace("/", "") + "@example.invalid"))
        assert request(stranger).status_code == 404
    assert (
        Client().get(url(member), HTTP_AUTHORIZATION="Bearer service-credential").status_code == 401
    )
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = client.cookies
    assert (
        strict.post(
            url(member, "recipient/reveal"), {}, content_type="application/json"
        ).status_code
        == 403
    )
    assert (
        strict.put(url(member, "purchase"), {}, content_type="application/json").status_code == 403
    )
    assert client.get("/api/me/giver?event_id=" + str(member.event_id)).status_code == 404
    assert client.get(url(member) + "&member_id=" + str(member.id)).status_code == 400


def test_pending_durability_cancelled_and_archived_reject_reads_and_writes():
    event, member, client = fixture(False)
    assert client.get(url(member)).status_code == 409
    assert client.get(url(member, "purchase")).status_code == 409
    assert (
        client.post(
            url(member, "recipient/reveal"), {}, content_type="application/json"
        ).status_code
        == 409
    )
    assert not Membership.objects.get(pk=member.pk).recipient_viewed
    apply_command(command(event, "cancel", confirm=True))
    assert client.get(url(member)).status_code == 409


def test_purchase_ciphertext_and_history_comparison_survive_wishlist_edit():
    event, member, client = fixture()
    data = choice(member)
    response = client.put(url(member, "purchase"), data, content_type="application/json")
    assert response.status_code == 200, response.content
    original = response.json()
    record = PrivatePurchaseState.objects.get(member=member)
    for secret in (data["note"], data["wish_id"], "ORDERED"):
        assert secret.encode() not in bytes(record.ciphertext)
    target_id = dict(unseal(SealedDraw.objects.get(event=event))["permutation"])[str(member.id)]
    target = event.members.get(pk=target_id)
    new = items()
    new[0]["title"] = "Nouvelle référence après choix"
    save_list(target, 1, new)
    current = client.get(url(member, "purchase")).json()
    assert current["wishlist_changed"] and current["selected_wish"] == original["selected_wish"]
    data.update(revision=1, state="RECEIVED")
    assert (
        client.put(url(member, "purchase"), data, content_type="application/json").status_code
        == 200
    )
    assert (
        client.put(url(member, "purchase"), data, content_type="application/json").status_code
        == 409
    )
    target_client = Client()
    target_client.force_login(target.identity.user)
    assert target_client.get(url(target, "purchase")).json()["note"] == ""
    assert "PURCHASE_PRIVATE_CANARY" not in target_client.get(url(target)).content.decode()


@pytest.mark.parametrize(
    "field,value",
    [
        ("state", "INVALID"),
        ("revision", True),
        ("wish_revision", True),
        ("wish_id", "foreign-id"),
        ("note", "x" * 1001),
    ],
)
def test_purchase_rejects_invalid_or_foreign_choice(field, value):
    _, member, client = fixture()
    data = choice(member)
    data[field] = value
    assert client.put(
        url(member, "purchase"), data, content_type="application/json"
    ).status_code in {400, 409}
    assert not PrivatePurchaseState.objects.exists()


def test_unrevealed_write_rejected_and_closed_read_only():
    event, member, client = fixture()
    value = client.get(url(member)).json()
    data = {
        "revision": 0,
        "state": "ORDERED",
        "note": "",
        "wish_id": value["wishes"][0]["id"],
        "wish_revision": 1,
    }
    assert (
        client.put(url(member, "purchase"), data, content_type="application/json").status_code
        == 409
    )
    client.post(url(member, "recipient/reveal"), {}, content_type="application/json")
    assert (
        client.put(url(member, "purchase"), data, content_type="application/json").status_code
        == 200
    )
    apply_command(command(event, "close", confirm=True))
    assert client.get(url(member)).status_code == 200
    assert client.get(url(member, "purchase")).status_code == 200
    assert (
        client.put(
            url(member, "purchase"), dict(data, revision=1), content_type="application/json"
        ).status_code
        == 409
    )


@pytest.mark.parametrize("kind", ["draw", "wishlist", "purchase", "key"])
def test_corrupt_envelope_fails_closed_with_neutral_alert_without_reroll(kind):
    event, member, client = fixture()
    data = choice(member)
    save_purchase(member, data)
    before = SealedDraw.objects.get(event=event)
    target_id = dict(unseal(before)["permutation"])[str(member.id)]
    record = {
        "draw": before,
        "wishlist": WishlistRevision.objects.get(wishlist__member_id=target_id),
        "purchase": PrivatePurchaseState.objects.get(member=member),
        "key": EventDataKey.objects.get(event=event),
    }[kind]
    field = "wrapped_key" if kind == "key" else "ciphertext"
    value = bytes(getattr(record, field))
    setattr(record, field, value[:-1] + bytes([value[-1] ^ 1]))
    record.save(update_fields=[field])
    endpoint = "purchase" if kind == "purchase" else "recipient"
    response = client.get(url(member, endpoint))
    assert response.status_code == 503, response.content
    assert b"CANARY" not in response.content and b"Traceback" not in response.content
    assert SecurityEvent.objects.filter(category="private_data_unavailable").exists()
    assert DrawJob.objects.get(event=event).state == "SEALED" and not run_one_draw()
    assert SealedDraw.objects.filter(event=event).count() == 1


def test_substitution_between_members_and_events_fails():
    event, member, _ = fixture()
    save_purchase(member, choice(member))
    other = event.members.exclude(pk=member.id).first()
    source = PrivatePurchaseState.objects.get(member=member)
    PrivatePurchaseState.objects.create(
        member=other, revision=source.revision, nonce=source.nonce, ciphertext=source.ciphertext
    )
    with pytest.raises(InvalidTag):
        purchase(other)
    other_event, _, _ = fixture()
    source_key = EventDataKey.objects.get(event=event)
    EventDataKey.objects.filter(event=other_event).update(
        wrapped_key=source_key.wrapped_key,
        wrap_nonce=source_key.wrap_nonce,
        key_id=source_key.key_id,
    )
    with pytest.raises(InvalidTag):
        event_key(other_event)


def test_rotation_keeps_ciphertexts_associations_and_old_backup_key_readable():
    event, member, _ = fixture()
    save_purchase(member, choice(member))
    draw = SealedDraw.objects.get(event=event)
    old_draw = SealedDraw.objects.get(pk=draw.id)
    expected = unseal(draw)
    cipher = bytes(draw.ciphertext)
    wishlist = Wishlist.objects.get(member=member)
    wishes = snapshot(wishlist)
    purchase_before = purchase(member)
    keys = settings.DRAW_MASTER_KEYS | {"v2": Fernet.generate_key().decode()}
    with override_settings(DRAW_MASTER_KEYS=keys, DRAW_ACTIVE_KEY="v2"):
        rotate_event(event.id, "v2")
        rotate_event(event.id, "v2")
        draw.refresh_from_db()
        assert draw.key_id == EventDataKey.objects.get(event=event).key_id == "v2"
        assert bytes(draw.ciphertext) == cipher and unseal(draw) == expected
        assert snapshot(wishlist) == wishes and purchase(member) == purchase_before
        # Historical backup keeps v1 wrapping and remains readable while v1 is authorized.
        assert unseal(old_draw) == expected
        with override_settings(DRAW_MASTER_KEYS={"v2": keys["v2"]}):
            assert unseal(draw) == expected and snapshot(wishlist) == wishes
            with pytest.raises(KeyError):
                unseal(old_draw)


def test_legacy_wishlist_migrates_atomically_without_new_revision():
    event, member, _ = fixture()
    listing = Wishlist.objects.get(member=member)
    record = listing.history.get(revision=1)
    expected = snapshot(listing)
    nonce = b"legacy-test!"  # 12 bytes
    key = base64.urlsafe_b64decode(settings.WISHLIST_KEYS["v1"])
    record.ciphertext = AESGCM(key).encrypt(nonce, json.dumps(expected).encode(), aad(listing, 1))
    record.nonce = nonce
    record.key_id = "v1"
    record.schema_version = 1
    record.save()
    assert snapshot(listing) == expected
    migrate_event(event.id)
    migrate_event(event.id)
    record.refresh_from_db()
    listing.refresh_from_db()
    assert record.schema_version == 2 and listing.revision == 1 and snapshot(listing) == expected
    assert record.key_id == "evt:" + str(event.id)


def test_ready_projection_only_has_aggregate_and_reveal_boolean():
    event, member, _ = fixture()
    save_purchase(member, choice(member, "READY"))
    captured = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n):
            return b'{"accepted":true}'

    def send(request, timeout):
        captured.append(json.loads(request.data)["payload"])
        return Reply()

    from django.utils import timezone
    from vault_core.models import PrivateEvent

    PrivateEvent.objects.filter(pk=event.id).update(next_projection_at=timezone.now())
    with patch("urllib.request.OpenerDirector.open", side_effect=send):
        project_one()
    payload = captured[0]
    assert payload["ready_count"] == 1
    row = next(row for row in payload["members"] if row["member_ref"] == str(member.id))
    assert row["recipient_viewed"]
    assert "PURCHASE_PRIVATE_CANARY" not in json.dumps(payload)
    assert not any(
        key in json.dumps(payload)
        for key in ("wish_id", "wish_revision", "selected_wish", "ORDERED")
    )


def test_private_html_escapes_notes_and_keeps_title_neutral():
    event, member, client = fixture()
    page = client.post(f"/private?event_id={event.id}", {"action": "reveal"})
    assert page.status_code == 200, page.content
    assert "Mon cadeau à préparer" in page.content.decode()
    data = choice(member, note="<script>PRIVATE_NOTE</script>")
    save_purchase(member, data)
    page = client.post(f"/private?event_id={event.id}", {"action": "reveal"})
    assert b"&lt;script&gt;PRIVATE_NOTE&lt;/script&gt;" in page.content
    assert b"<script>PRIVATE_NOTE</script>" not in page.content


@pytest.mark.concurrent_db
def test_two_purchase_updates_have_one_conflict_without_lost_state():
    event, member, _ = fixture()
    data = choice(member)
    barrier = Barrier(2)

    def writer(state):
        close_old_connections()
        try:
            client = Client()
            client.force_login(member.identity.user)
            barrier.wait(timeout=10)
            return client.put(
                url(member, "purchase"), dict(data, state=state), content_type="application/json"
            ).status_code
        finally:
            connections.close_all()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(writer, ["READY", "ORDERED"])) == [200, 409]
        assert PrivatePurchaseState.objects.get(member=member).revision == 1
    finally:
        cleanup(event)


def test_missing_event_key_is_never_silently_replaced():
    event, member, client = fixture()
    recipient(member, reveal=True)
    EventDataKey.objects.filter(event=event).delete()
    response = client.put(
        url(member, "purchase"),
        {"revision": 0, "state": "NOT_STARTED", "wish_id": None, "wish_revision": None, "note": ""},
        content_type="application/json",
    )
    assert response.status_code == 503
    assert not EventDataKey.objects.filter(event=event).exists()
    assert not PrivatePurchaseState.objects.filter(member=member).exists()
