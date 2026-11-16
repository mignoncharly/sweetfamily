import hashlib
import json
import re
import time
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
import tasks
from allauth.account.models import EmailAddress
from allauth.usersessions.models import UserSession
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client
from django.utils import timezone
from helpers import user
from noel_contracts import canonical, sign
from vault_core.domain import accept_invitation, apply_command, deliver_one, invite
from vault_core.models import Invitation, Membership, PendingMail, PrivateEvent
from vault_core.secrets import decrypt


def open_message():
    values = tasks.config()
    return sign(
        "open",
        {
            "event_id": str(uuid.uuid4()),
            "version": 1,
            "event": {
                "title": "Test",
                "celebration_at": "2026-12-24T18:00:00+01:00",
                "wishlist_deadline": "2026-12-01T18:00:00+01:00",
                "timezone": "Europe/Berlin",
                "shipping_included": False,
                "handover": "À apporter au réveillon.",
            },
            "members": [
                {
                    "id": str(uuid.uuid4()),
                    "display_name": f"Alex {i}",
                    "country": "FR" if i % 2 else "DE",
                    "email": f"alex{i}@example.invalid",
                }
                for i in range(4)
            ],
        },
        values["CONTROL_COMMAND_PRIVATE_KEY"],
    )


def prepare():
    message = open_message()
    apply_command(message)
    return message, Membership.objects.order_by("display_name").first()


def token(member):
    item = PendingMail.objects.get(invitation__member=member, state="QUEUED")
    body = json.loads(decrypt(item.payload))["body"]
    return re.search(r"/join/([A-Za-z0-9_-]+)", body).group(1)


def login_code(client, member):
    response = client.post("/accounts/login/code/", {"email": member.identity.email})
    assert response.status_code == 302, response.content
    item = PendingMail.objects.filter(invitation=None).latest("next_attempt_at")
    body = json.loads(decrypt(item.payload))["body"]
    return re.search(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", body).group()


def claim(member):
    EmailAddress.objects.filter(user=member.identity.user).update(verified=True)
    return accept_invitation(
        member.identity.user, hashlib.sha256(token(member).encode()).hexdigest()
    )


def test_signed_commands_idempotency_and_closed_schema():
    message = open_message()
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        "/internal/commands", canonical(message), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    assert "token" not in response.content.decode()
    assert Invitation.objects.count() == 4
    assert (
        client.post(
            "/internal/commands", canonical(message), content_type="application/json"
        ).json()
        == response.json()
    )
    assert Invitation.objects.count() == 4
    forged = dict(message)
    forged["payload"] = dict(message["payload"], secret="bad")
    assert (
        client.post(
            "/internal/commands", canonical(forged), content_type="application/json"
        ).status_code
        == 403
    )
    assert client.get("/internal/commands").status_code == 405


def test_duplicate_box_rejected_before_any_invitation():
    message = open_message()
    message["payload"]["members"][1]["email"] = "ALEX0@example.invalid"
    with pytest.raises(ValueError):
        apply_command(message)
    assert Invitation.objects.count() == 0
    assert PrivateEvent.objects.count() == 0


def test_invitation_get_has_no_side_effect_and_interception_cannot_claim():
    _, member = prepare()
    raw = token(member)
    client = Client()
    assert client.get("/join/" + raw).status_code == 200
    assert not client.session.get("pending_invitation")
    assert not client.session.get("_auth_user_id")
    assert client.get("/api/me/events").status_code == 401
    assert client.post("/join/" + raw).status_code == 302
    assert client.post("/api/me/invitations/accept").status_code == 401
    attacker = user("attacker@example.invalid")
    client.force_login(attacker)
    assert client.post("/api/me/invitations/accept").status_code == 403
    assert Membership.objects.get(pk=member.pk).claimed_at is None
    assert raw not in Invitation.objects.get(member=member).token_digest


def test_real_allauth_code_verification_claim_and_profile_authorization():
    _, member = prepare()
    raw = token(member)
    client = Client()
    client.post("/join/" + raw)
    before = client.session.session_key
    code = login_code(client, member)
    assert all(code not in row.session_data for row in Session.objects.all())
    response = client.post("/accounts/login/code/confirm/", {"code": code})
    assert response.status_code == 302, response.content
    assert client.session.session_key != before
    assert EmailAddress.objects.get(user=member.identity.user).verified
    assert client.get("/api/me/events").json()["events"] == []
    assert b"Rejoindre" in client.get("/").content
    response = client.post("/api/me/invitations/accept")
    assert response.status_code == 201, response.content
    assert client.post("/api/me/invitations/accept").status_code == 403
    assert len(client.get("/api/me/events").json()["events"]) == 1
    assert client.get("/api/me/profile", {"event_id": str(uuid.uuid4())}).status_code == 404
    url = f"/api/me/profile?event_id={member.event_id}"
    profile = client.get(url).json()
    response = client.patch(
        url,
        {"revision": profile["revision"], "display_name": "Alex confirmé", "country": "DE"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert (
        client.patch(
            url,
            {"revision": profile["revision"], "display_name": "Autre", "country": "FR"},
            content_type="application/json",
        ).status_code
        == 409
    )
    assert client.get("/accounts/sessions/").status_code == 200
    assert UserSession.objects.filter(user=member.identity.user).exists()
    client.post("/accounts/logout/")
    assert client.get("/api/me/events").status_code == 401


@pytest.mark.parametrize("mode", ["expiry", "attempts"])
def test_login_code_expiry_and_five_attempt_limit(mode):
    _, member = prepare()
    client = Client()
    code = login_code(client, member)
    if mode == "expiry":
        with patch(
            "allauth.account.internal.flows.code_verification.time.time",
            return_value=time.time() + 601,
        ):
            client.post("/accounts/login/code/confirm/", {"code": code})
    else:
        for _ in range(5):
            client.post("/accounts/login/code/confirm/", {"code": "INVALID"})
        client.post("/accounts/login/code/confirm/", {"code": code})
    assert not client.session.get("_auth_user_id")


def test_expired_and_reissued_invitation():
    _, member = prepare()
    old = token(member)
    Invitation.objects.filter(member=member).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert Client().get("/join/" + old).status_code == 404
    invite(member)
    assert Client().get("/join/" + old).status_code == 404
    assert Invitation.objects.filter(member=member, revoked_at=None).count() == 1


def test_claimed_email_cannot_be_changed_by_signed_organizer():
    _, member = prepare()
    claim(member)
    message = sign(
        "correct_invitation",
        {
            "event_id": str(member.event_id),
            "version": 1,
            "member_id": str(member.id),
            "email": "replacement@example.invalid",
        },
        tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"],
    )
    response = Client().post(
        "/internal/commands", canonical(message), content_type="application/json"
    )
    assert response.status_code == 409
    assert Membership.objects.get(pk=member.id).identity.email == "alex0@example.invalid"


def test_unknown_login_uniform_response_and_no_public_signup():
    _, member = prepare()
    known = Client().post("/accounts/login/code/", {"email": member.identity.email})
    unknown = Client().post("/accounts/login/code/", {"email": "absent@example.invalid"})
    assert known.status_code == unknown.status_code == 302
    assert known.url == unknown.url
    assert (
        Client().post("/accounts/signup/", {"email": "outsider@example.invalid"}).status_code != 302
    )


def test_rate_limit_by_account_without_blocking_shared_family_ip():
    _, member = prepare()
    for _ in range(3):
        assert (
            Client().post("/accounts/login/code/", {"email": member.identity.email}).status_code
            == 302
        )
    assert (
        Client().post("/accounts/login/code/", {"email": member.identity.email}).status_code != 302
    )
    other = Membership.objects.order_by("display_name")[1]
    assert (
        Client().post("/accounts/login/code/", {"email": other.identity.email}).status_code == 302
    )


def test_private_session_cache_and_mfa_secrets_not_plaintext():
    from vault_core.models import AuthRateCache

    _, member = prepare()
    client = Client()
    code = login_code(client, member)
    assert all(code not in row.session_data for row in Session.objects.all())
    cache.set("private-code-canary", True, timeout=60)
    assert all("private-code-canary" not in row.cache_key for row in AuthRateCache.objects.all())
    assert "code" not in json.dumps({"names": [f.name for f in Invitation._meta.fields]})


def test_minimal_encrypted_mail_dispatch_and_revocation():
    from django.core import mail

    _, member = prepare()
    old = token(member)
    invite(member)
    while deliver_one():
        pass
    assert all(old not in msg.body for msg in mail.outbox)
    assert len(mail.outbox) == 4
    assert all(item.payload == "" for item in PendingMail.objects.all())


def test_fresh_signature_with_same_id_different_content_conflicts():
    message, _ = prepare()
    altered = json.loads(json.dumps(message["payload"]))
    altered["event"]["title"] = "Autre"
    changed = sign("open", altered, tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"], message["id"])
    assert (
        Client()
        .post("/internal/commands", canonical(changed), content_type="application/json")
        .status_code
        == 409
    )
    assert PrivateEvent.objects.get().title == "Test"


def test_email_change_requires_recent_authentication_and_revokes_sessions():
    from vault_core.models import VerifiedIdentity

    _, member = prepare()
    client = Client()
    code = login_code(client, member)
    client.post("/accounts/login/code/confirm/", {"code": code})
    actor = member.identity.user
    # Age the upstream authentication record: sensitive changes must challenge again.
    session = client.session
    for record in session["account_authentication_methods"]:
        record["at"] = time.time() - 601
    session.save()
    response = client.post(
        "/accounts/email/", {"action_add": "", "email": "newbox@example.invalid"}
    )
    assert response.status_code == 302
    assert "reauthenticate" in response.url
    assert not EmailAddress.objects.filter(user=actor, email="newbox@example.invalid").exists()

    # Complete a real new-box verification through the upstream email management views.
    fresh = Client()
    code = login_code(fresh, member)
    fresh.post("/accounts/login/code/confirm/", {"code": code})
    old_session = fresh.session.session_key

    response = fresh.post("/accounts/reauthenticate/code/", {"recipient": member.identity.email})
    assert response.status_code == 302
    item = PendingMail.objects.filter(invitation=None).latest("next_attempt_at")
    reauthentication = re.search(
        r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", json.loads(decrypt(item.payload))["body"]
    ).group()
    assert (
        fresh.post("/accounts/reauthenticate/code/confirm/", {"code": reauthentication}).status_code
        == 302
    )
    response = fresh.post(
        "/accounts/email/", {"action_add": "", "email": "verified-new@example.invalid"}
    )
    assert response.status_code == 302
    item = PendingMail.objects.filter(invitation=None).latest("next_attempt_at")
    verification = re.search(
        r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", json.loads(decrypt(item.payload))["body"]
    ).group()
    response = fresh.post(response.url, {"code": verification})
    assert response.status_code == 302
    assert not Session.objects.filter(session_key=old_session).exists()
    assert VerifiedIdentity.objects.get(user=actor).email == "verified-new@example.invalid"


def test_unclaimed_email_correction_revokes_old_link_and_preserves_other_members():
    message, member = prepare()
    old = token(member)
    correction = sign(
        "correct_invitation",
        {
            "event_id": str(member.event_id),
            "version": 1,
            "member_id": str(member.id),
            "email": "correct+family@example.invalid",
        },
        tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"],
    )
    response = Client().post(
        "/internal/commands", canonical(correction), content_type="application/json"
    )
    assert response.status_code == 200
    member.refresh_from_db()
    assert member.identity.email == "correct+family@example.invalid"
    assert Client().get("/join/" + old).status_code == 404
    assert Membership.objects.count() == 4
    assert (
        Client()
        .post("/internal/commands", canonical(correction), content_type="application/json")
        .json()
        == response.json()
    )


def test_revoke_other_sessions_and_preserve_current_session():
    _, member = prepare()
    clients = [Client(), Client()]
    for client in clients:
        code = login_code(client, member)
        client.post("/accounts/login/code/confirm/", {"code": code})
    first = clients[0].session.session_key
    second = clients[1].session.session_key
    assert clients[1].post("/accounts/sessions/", {}).status_code == 302
    assert not Session.objects.filter(session_key=first).exists()
    assert Session.objects.filter(session_key=second).exists()


def test_reissue_limit_is_enforced_by_vault():
    _, member = prepare()
    invite(member)
    invite(member)
    with pytest.raises(ValueError):
        invite(member)
    assert Invitation.objects.filter(member=member).count() == 3


def test_malformed_signed_member_id_is_a_neutral_refusal():
    message = open_message()
    message["payload"]["members"][0]["id"] = 123
    message = sign("open", message["payload"], tasks.config()["CONTROL_COMMAND_PRIVATE_KEY"])
    response = Client().post(
        "/internal/commands", canonical(message), content_type="application/json"
    )
    assert response.status_code == 409
    assert PrivateEvent.objects.count() == 0


def test_nonce_cannot_be_replayed_for_another_command():
    original, _ = prepare()
    with patch("noel_contracts.secrets.token_urlsafe", return_value=original["nonce"]):
        duplicate = open_message()
    response = Client().post(
        "/internal/commands", canonical(duplicate), content_type="application/json"
    )
    assert response.status_code == 409
    assert PrivateEvent.objects.count() == 1
