import secrets
from unittest.mock import Mock, patch

import pytest
from cryptography.exceptions import InvalidTag
from django.test import Client
from django.utils import timezone
from vault_cases import claim, prepare
from vault_core.models import GiftWish, Wishlist, WishlistRevision
from vault_core.wishlists import (
    euro_cents,
    merchant_url,
    save_list,
    shopping_advice,
    snapshot,
)


def items():
    return [
        {
            "slot": i,
            "title": f"Canari cadeau privé {i}",
            "url": f"https://www.amazon.fr/dp/ARTICLE{i}?variant=blue",
            "price_eur_cents": 4999,
            "currency": "EUR",
            "price_date": timezone.localdate().isoformat(),
            "note": "Taille M",
            "exact_model": False,
            "equivalent_ok": True,
        }
        for i in (1, 2, 3)
    ]


def actor():
    _, member = prepare()
    claim(member)
    client = Client()
    client.force_login(member.identity.user)
    return member, client, f"/api/me/wishlist?event_id={member.event_id}"


def test_read_only_get_and_empty_draft():
    member, client, url = actor()
    assert client.get(url).json()["revision"] == 0
    assert Wishlist.objects.count() == 0
    response = client.put(url, {"revision": 0, "wishes": []}, content_type="application/json")
    assert response.status_code == 200
    assert len(GiftWish.objects.all()) == 3
    assert (
        client.post(
            f"/api/me/wishlist/validate?event_id={member.event_id}",
            {"revision": 1},
            content_type="application/json",
        ).status_code
        == 400
    )


@pytest.mark.parametrize("bad", [5000, 0, -1, True, 49.99, "4999", None])
def test_exact_integer_budget_rejects_bad_amount(bad):
    member, _, _ = actor()
    data = items()
    data[0]["price_eur_cents"] = bad
    with pytest.raises(ValueError):
        save_list(member, 0, data, validate=True)
    assert Wishlist.objects.count() == 0


@pytest.mark.parametrize("count", [2, 4])
def test_validation_requires_exactly_three(count):
    member, _, _ = actor()
    data = items()
    data = (data + [dict(data[0], slot=4)])[:count]
    with pytest.raises(ValueError):
        save_list(member, 0, data, validate=True)


def test_revision_history_stable_ids_foreign_currency_and_ciphers():
    member, client, url = actor()
    data = items()
    data[0]["currency"] = "USD"
    response = client.put(url, {"revision": 0, "wishes": data}, content_type="application/json")
    assert response.status_code == 200, response.content
    original = response.json()
    response = client.post(
        f"/api/me/wishlist/validate?event_id={member.event_id}",
        {"revision": 1},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["state"] == "VALIDATED"
    assert response.json()["wishes"][0]["eur_estimate"] is True
    data[0]["title"] = "Remplacement disponible"
    result = client.put(url, {"revision": 2, "wishes": data}, content_type="application/json")
    assert result.status_code == 200
    assert [i["id"] for i in result.json()["wishes"]] == [i["id"] for i in original["wishes"]]
    assert (
        client.get(url + "&revision=1").json()["wishes"][0]["title"]
        == original["wishes"][0]["title"]
    )
    assert (
        client.put(
            url, {"revision": 2, "wishes": data}, content_type="application/json"
        ).status_code
        == 409
    )
    listing = Wishlist.objects.get(member=member)
    for revision in listing.history.all():
        assert b"Canari" not in bytes(revision.ciphertext)
        assert b"amazon.fr" not in bytes(revision.ciphertext)
    revision = listing.history.get(revision=3)
    other_member = member.event.members.exclude(pk=member.pk).first()
    other = Wishlist.objects.create(member=other_member, revision=1)
    WishlistRevision.objects.create(
        wishlist=other,
        revision=1,
        key_id=revision.key_id,
        schema_version=revision.schema_version,
        nonce=secrets.token_bytes(12),
        ciphertext=revision.ciphertext,
    )
    with pytest.raises(InvalidTag):
        snapshot(other)


@pytest.mark.parametrize(
    "url",
    [
        "http://amazon.fr/item",
        "javascript:alert(1)",
        "https://amazon.fr.evil.test/p",
        "https://amazon.fr@evil.test/p",
        "https://user:pass@amazon.fr/p",
        "https://127.0.0.1/p",
        "https://[::1]/p",
        "https://amazon.fr:8080/p",
        "https://amzn.to/short",
        "https://amazon.fr./p",
        "https://localhost/p",
        "https://amazon.fr\\@evil.test/p",
        "https://amazon.fr/\nheader",
    ],
)
def test_bad_urls_rejected_without_fetch(url):
    with patch("urllib.request.urlopen", side_effect=AssertionError("No network fetch permitted")):
        with pytest.raises(ValueError):
            merchant_url(url)


def test_duplicate_tracking_preserves_reference_variants():
    member, _, _ = actor()
    data = items()
    data[0]["url"] = "https://amazon.fr/p?color=blue&utm_source=family"
    data[1]["url"] = "https://www.amazon.fr/p?utm_source=mail&color=blue#detail"
    with pytest.raises(ValueError):
        save_list(member, 0, data, validate=True)
    data[1]["url"] = "https://amazon.fr/p?color=red"
    listing = save_list(member, 0, data, validate=True)
    assert "utm_source=family" in snapshot(listing)[0]["url"]


def test_exact_model_and_equivalent_conflict():
    member, _, _ = actor()
    data = items()
    data[0]["exact_model"] = True
    with pytest.raises(ValueError):
        save_list(member, 0, data, validate=True)


def test_post_draw_keeps_three_and_state_and_country_drives_shopping():
    member, client, url = actor()
    data = items()
    listing = save_list(member, 0, data, validate=True)
    event = member.event
    event.state = "DRAWN"
    event.save(update_fields=["state"])
    data[1]["title"] = "Produit de remplacement"
    listing = save_list(member, listing.revision, data)
    assert snapshot(listing)[1]["title"] == "Produit de remplacement"
    with pytest.raises(ValueError):
        save_list(member, listing.revision, data[:2])
    event.refresh_from_db()
    assert event.state == "DRAWN"
    advice = shopping_advice(snapshot(listing), "DE")
    assert advice["buyer_country"] == "DE"
    assert all(".de/" in search["url"] for item in advice["items"] for search in item["searches"])
    assert advice["items"][0]["reference_url"].startswith("https://www.amazon.fr/")
    for state in ("DRAWING", "CLOSED", "CANCELLED", "ARCHIVED"):
        event.state = state
        event.save(update_fields=["state"])
        assert client.put(
            url, {"revision": listing.revision, "wishes": data}, content_type="application/json"
        ).status_code in (409, 503)


def test_nonowner_and_service_credential_cannot_read_wishes():
    member, client, url = actor()
    save_list(member, 0, items(), validate=True)
    other = member.event.members.exclude(pk=member.pk).first()
    second = Client()
    second.force_login(other.identity.user)
    # Even a verified account with an unclaimed invitation has no membership access.
    from allauth.account.models import EmailAddress

    EmailAddress.objects.filter(user=other.identity.user).update(verified=True)
    assert second.get(url).status_code == 404
    assert Client().get(url, HTTP_AUTHORIZATION="service-credential").status_code == 401
    assert (
        client.get(url + "&participant_id=" + str(other.pk))
        .json()["wishes"][0]["title"]
        .startswith("Canari")
    )


def test_nonce_collision_retries_before_encrypting():
    member, _, _ = actor()
    listing = save_list(member, 0, items(), validate=True)
    old = bytes(listing.history.first().nonce)
    new = secrets.token_bytes(12)

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from vault_core.envelopes import event_key

    data_key = event_key(member.event)
    cipher = Mock(wraps=AESGCM(data_key))
    with (
        patch("vault_core.envelopes.secrets.token_bytes", side_effect=[old, new]),
        patch("vault_core.envelopes.AESGCM", return_value=cipher),
        patch("vault_core.envelopes.event_key", return_value=data_key),
    ):
        listing = save_list(member, 1, items())
    assert [call.args[0] for call in cipher.encrypt.call_args_list] == [new]
    assert bytes(listing.history.get(revision=2).nonce) == new


@pytest.mark.parametrize("amount,expected", [("49,99", 4999), ("0.01", 1), ("12.3", 1230)])
def test_french_price_entry(amount, expected):
    assert euro_cents(amount) == expected


@pytest.mark.parametrize("amount", ["50", "49.999", "NaN", "1,000", "1e1", " 49,99", "-1", "0"])
def test_ambiguous_price_rejected(amount):
    with pytest.raises(ValueError):
        euro_cents(amount)


def test_html_escape_csrf_requests_and_no_mutation_on_get():
    member, client, _ = actor()
    data = items()
    data[0]["title"] = "<script>alert(1)</script>"
    save_list(member, 0, data, validate=True)
    response = client.get(f"/wishlist?event_id={member.event_id}")
    assert response.status_code == 200
    assert b"<script>alert(1)</script>" not in response.content
    assert b"&lt;script&gt;" in response.content
    assert b"noopener noreferrer" in response.content
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = client.cookies
    assert (
        strict.post(
            f"/api/me/wishlist/validate?event_id={member.event_id}",
            {"revision": 1},
            content_type="application/json",
        ).status_code
        == 403
    )
    with patch("urllib.request.urlopen", side_effect=AssertionError("No fetch")):
        response = client.post(
            f"/api/me/merchant-requests?event_id={member.event_id}",
            {"hostname": "newshop.example.com"},
            content_type="application/json",
        )
        assert response.status_code == 202
    assert client.get(f"/api/me/wishlist?event_id={member.event_id}").json()["revision"] == 1


def test_partial_draft_and_safe_form_resubmission():
    member, client, url = actor()
    data = items()[:1]
    data[0].update(title="Idée à compléter", url="", price_eur_cents=None, price_date="")
    result = client.put(url, {"revision": 0, "wishes": data}, content_type="application/json")
    assert result.status_code == 200
    assert client.get(f"/wishlist?event_id={member.event_id}").status_code == 200
    assert (
        client.post(
            f"/api/me/wishlist/validate?event_id={member.event_id}",
            {"revision": 1},
            content_type="application/json",
        ).status_code
        == 400
    )
    form = {
        "revision": "1",
        "action": "validate",
        "form-TOTAL_FORMS": "3",
        "form-INITIAL_FORMS": "3",
        "form-MIN_NUM_FORMS": "3",
        "form-MAX_NUM_FORMS": "3",
    }
    for i, item in enumerate(items()):
        for key, value in item.items():
            if key in {"slot", "price_eur_cents", "exact_model", "equivalent_ok"}:
                continue
            form[f"form-{i}-{key}"] = value
        form[f"form-{i}-price"] = "49,99"
    response = client.post(f"/wishlist?event_id={member.event_id}", form)
    assert response.status_code == 200, response.content
    assert client.get(url).json()["state"] == "VALIDATED"
    assert client.get(url).json()["revision"] == 2
    response = client.post(f"/wishlist?event_id={member.event_id}", form)
    assert response.status_code == 409
    assert b'value="1"' in response.content


@pytest.mark.concurrent_db
def test_two_real_database_requests_cannot_overwrite_each_other():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections
    from vault_core.models import VerifiedIdentity

    member, _, url = actor()
    listing = save_list(member, 0, items(), validate=True)
    barrier = Barrier(2)

    def writer(label):
        close_old_connections()
        try:
            client = Client()
            client.force_login(member.identity.user)
            data = items()
            data[0]["title"] = label
            barrier.wait(timeout=10)
            return client.put(
                url, {"revision": 1, "wishes": data}, content_type="application/json"
            ).status_code
        finally:
            connections.close_all()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(writer, ["Fenêtre A", "Fenêtre B"]))
        assert sorted(results) == [200, 409]
        listing.refresh_from_db()
        assert listing.revision == 2
        assert listing.history.count() == 2
    finally:
        identities = list(member.event.members.values_list("identity_id", flat=True))
        member.event.delete()
        for identity in VerifiedIdentity.objects.filter(id__in=identities):
            identity.user.delete()
