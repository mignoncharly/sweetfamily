import json
from unittest.mock import patch

from allauth.mfa.models import Authenticator
from control_core.models import ControlCommand, EventDraft
from django.contrib.sessions.models import Session
from django.test import Client
from helpers import login_with_code, user


def event_data():
    return {
        "title": "Réveillon",
        "celebration_at": "2026-12-24T18:00:00+01:00",
        "wishlist_deadline": "2026-12-01T18:00:00+01:00",
        "timezone": "Europe/Berlin",
        "shipping_included": False,
        "handover": "À apporter au réveillon.",
    }


def create(client):
    response = client.post("/api/events", event_data(), content_type="application/json")
    assert response.status_code == 201, response.content
    return response.json()


def test_email_alone_never_grants_organizer_privileges():
    actor = user()
    client = login_with_code(Client(), actor)
    assert (
        client.post("/api/events", event_data(), content_type="application/json").status_code == 403
    )


def test_real_totp_login_and_owned_event():
    actor = user()
    client = login_with_code(Client(), actor, mfa=True)
    data = create(client)
    assert EventDraft.objects.get(id=data["id"]).owner.user == actor
    assert client.get(f"/api/events/{data['id']}/status").status_code == 200
    assert (
        client.patch(
            f"/api/events/{data['id']}/status", {}, content_type="application/json"
        ).status_code
        == 405
    )
    assert Authenticator.objects.get(user=actor, type="totp").data["secret"].startswith("gAAAA")
    assert client.get("/accounts/2fa/").status_code == 200
    assert client.get("/accounts/sessions/").status_code == 200
    other = login_with_code(Client(), user("other@example.invalid"), mfa=True)
    assert other.get(f"/api/events/{data['id']}").status_code == 404
    assert len(other.get("/api/events").json()["events"]) == 0
    assert all(
        "account_authentication_methods" not in s.session_data for s in Session.objects.all()
    )


def test_versioning_duplicate_names_emails_and_budget_roster_bounds():
    client = login_with_code(Client(), user(), mfa=True)
    event = create(client)
    for i in range(4):
        response = client.post(
            f"/api/events/{event['id']}/participants",
            {
                "version": event["version"],
                "display_name": f"Alex {i}",
                "country": "FR" if i % 2 else "DE",
                "email": f"alex{i}@example.invalid",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        event = response.json()
    bad = {
        "version": event["version"],
        "display_name": "Alex bis",
        "country": "FR",
        "email": "ALEX0@example.invalid",
    }
    assert (
        client.post(
            f"/api/events/{event['id']}/participants", bad, content_type="application/json"
        ).status_code
        == 400
    )
    bad["email"] = "new@example.invalid"
    bad["country"] = "XX"
    assert (
        client.post(
            f"/api/events/{event['id']}/participants", bad, content_type="application/json"
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/events/{event['id']}",
            {"version": 1, "event": event_data()},
            content_type="application/json",
        ).status_code
        == 409
    )
    with patch("control_core.views.send_command", side_effect=TimeoutError):
        response = client.post(
            f"/api/events/{event['id']}/open",
            {"version": event["version"]},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="open-1",
        )
    assert response.status_code == 503
    assert ControlCommand.objects.count() == 1
    command = ControlCommand.objects.get()
    with patch(
        "control_core.views.send_command",
        return_value={"event_id": event["id"], "version": event["version"], "state": "OPEN"},
    ):
        assert (
            client.post(
                f"/api/events/{event['id']}/open",
                {"version": event["version"]},
                content_type="application/json",
                HTTP_IDEMPOTENCY_KEY="open-1",
            ).status_code
            == 200
        )
    assert ControlCommand.objects.count() == 1
    assert "token" not in json.dumps(command.payload)
    client.logout()
    assert client.get("/api/events").status_code == 401


def test_csrf_and_bad_input():
    client = login_with_code(Client(), user(), mfa=True)
    strict = Client(enforce_csrf_checks=True)
    strict.cookies = client.cookies
    assert (
        strict.post("/api/events", event_data(), content_type="application/json").status_code == 403
    )
    data = event_data()
    data["wishlist_deadline"] = data["celebration_at"]
    assert client.post("/api/events", data, content_type="application/json").status_code == 400
    data = event_data()
    data["timezone"] = "Invalid/Timezone"
    assert client.post("/api/events", data, content_type="application/json").status_code == 400
    data = event_data()
    data["owner"] = "foreign"
    assert client.post("/api/events", data, content_type="application/json").status_code == 400


def test_final_organizer_factor_cannot_be_deleted():
    from control_core.adapters import MFAAdapter

    actor = user()
    client = login_with_code(Client(), actor, mfa=True)
    create(client)
    assert not MFAAdapter().can_delete_authenticator(
        Authenticator.objects.get(user=actor, type="totp")
    )


def test_signup_and_email_forms_are_french():
    client = Client()
    assert client.get("/accounts/signup/").status_code == 200
    assert b'lang="fr"' in client.get("/accounts/login/code/").content


def test_signed_status_projection_is_closed_and_monotonic():
    import uuid

    import tasks
    from control_core.models import Organizer, RosterProposal
    from noel_contracts import canonical, sign

    actor = user()
    event = EventDraft.objects.create(owner=Organizer.objects.create(user=actor), **event_data())
    member = RosterProposal.objects.create(
        event=event, display_name="Alex", country="FR", email=actor.email
    )
    data = {
        "event_id": str(event.id),
        "event_version": 5,
        "projection_version": 2,
        "event_state": "OPEN",
        "manifest_version": None,
        "draw_progress": "NOT_STARTED",
        "ready_count": 1,
        "members": [
            {
                "member_ref": str(member.id),
                "registration_confirmed": True,
                "wishlist_complete": True,
                "consent_received": False,
                "notification_state": "SUBMITTED",
                "recipient_viewed": True,
            }
        ],
    }
    key = tasks.config()["VAULT_PROJECTION_PRIVATE_KEY"]

    def post(payload):
        return Client(enforce_csrf_checks=True).post(
            "/internal/status-projections",
            canonical(sign("status_projection", payload, key)),
            content_type="application/json",
        )

    assert post(data).status_code == 200
    member.refresh_from_db()
    assert member.registration_confirmed
    event.refresh_from_db()
    assert event.version == 5 and event.state == "OPEN"
    from control_core.models import SafeParticipantStatus

    assert SafeParticipantStatus.objects.get(member=member).wishlist_complete
    assert SafeParticipantStatus.objects.get(member=member).recipient_viewed
    assert event.ready_count == 1
    assert post(dict(data, projection_version=1)).status_code == 200
    assert post(dict(data, recipient_id=str(uuid.uuid4()))).status_code == 403
    foreign = dict(data, projection_version=3)
    foreign["members"] = [dict(data["members"][0], member_ref=str(uuid.uuid4()))]
    assert post(foreign).status_code == 409


def test_draw_command_requires_mfa_owned_event_and_closed_payload_and_idempotency():
    client = login_with_code(Client(), user(), mfa=True)
    event = create(client)
    url = f"/api/events/{event['id']}/draw"
    body = {"version": event["version"]}
    assert client.post(url, body, content_type="application/json").status_code == 409
    assert (
        client.post(
            url,
            dict(body, recipient_id="private"),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="draw-1",
        ).status_code
        == 409
    )
    assert not ControlCommand.objects.exists()
    with patch("control_core.views.send_command", side_effect=TimeoutError):
        assert (
            client.post(
                url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="draw-1"
            ).status_code
            == 503
        )
    with patch(
        "control_core.views.send_command",
        return_value={"event_id": event["id"], "version": event["version"] + 1, "state": "DRAWING"},
    ) as send:
        assert (
            client.post(
                url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="draw-1"
            ).status_code
            == 200
        )
        assert (
            client.post(
                url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="draw-1"
            ).status_code
            == 200
        )
        assert send.call_count == 1
    assert (
        client.post(
            url, {"version": 999}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="draw-1"
        ).status_code
        == 409
    )
    other = login_with_code(Client(), user("other@example.invalid"), mfa=True)
    assert (
        other.post(
            url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="draw-2"
        ).status_code
        == 404
    )
