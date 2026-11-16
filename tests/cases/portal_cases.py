import uuid
from unittest.mock import patch

from control_cases import create, event_data
from control_core.models import ControlCommand, EventDraft, OwnershipTransfer, RosterProposal
from django.test import Client
from helpers import login_with_code, user


def token():
    return {"submission_id": str(uuid.uuid4()), "version": 1, "confirm": "on"}


def setup():
    client = login_with_code(Client(), user(), mfa=True)
    return client, EventDraft.objects.get(pk=create(client)["id"])


def test_optional_email_invitation_contains_no_login_or_reset_secret():
    from django.test import override_settings

    with override_settings(WHATSAPP_ENROLLMENT_ENABLED=True):
        client, event = setup()
        for i in range(4):
            event.refresh_from_db()
            response = client.post(
                f"/events/{event.id}/people/new",
                {
                    "version": event.version,
                    "submission_id": str(uuid.uuid4()),
                    "display_name": f"Sans email {i}",
                    "country": "FR",
                    "email": "",
                },
            )
            assert response.status_code == 302, response.content
        assert event.roster.filter(email=None).count() == 4
        event.state = "OPEN"
        event.save()
        response = client.get(f"/events/{event.id}")
        assert response.status_code == 200
        for member in event.roster.all():
            assert f"/accounts/enroll/{member.id}/" in response.content.decode()
        assert "personal-code" not in response.content.decode()
        event.roster.update(registration_confirmed=True)
        response = client.get(f"/events/{event.id}")
        assert "/accounts/enroll/" not in response.content.decode()


def test_html_creation_idempotent_bound_errors_and_csv_formula():
    c, e = setup()
    assert c.get("/events/new").status_code == 200
    data = event_data() | token()
    assert c.post("/events/new", data).status_code == 302
    assert c.post("/events/new", data).status_code == 302
    assert EventDraft.objects.count() == 2
    bad = data | {"title": ""}
    response = c.post("/events/new", bad)
    assert response.status_code == 400 and b'aria-invalid="true"' in response.content
    RosterProposal.objects.create(
        event=e, display_name="=1+2", country="FR", email="x@example.invalid"
    )
    response = c.get(f"/events/{e.id}/export")
    assert response.status_code == 200 and "'=1+2" in response.content.decode()
    assert "wish_id" not in response.content.decode()
    for path in (
        "",
        "/rules",
        "/people/new",
        "/exclusions",
        "/reminders",
        "/action/open",
        "/transfer",
    ):
        assert c.get(f"/events/{e.id}" + path).status_code == 200, path
    stranger = login_with_code(Client(), user("stranger@example.invalid"), mfa=True)
    assert stranger.get(f"/events/{e.id}").status_code == 404


def test_annual_copy_resets_all_participant_status_and_remaps_exclusions():
    c, e = setup()
    members = [
        RosterProposal.objects.create(
            event=e,
            display_name=f"Personne {i}",
            country="FR",
            email=f"{i}@example.invalid",
            registration_confirmed=True,
        )
        for i in range(2)
    ]
    e.exclusions = [[str(members[0].id), str(members[1].id)]]
    e.state = "DRAWN"
    e.save()
    response = c.post(f"/events/{e.id}/copy", event_data() | token())
    assert response.status_code == 302
    copied = EventDraft.objects.get(copied_from=e)
    assert copied.state == "DRAFT" and copied.projection_version == 0
    assert not copied.roster.filter(registration_confirmed=True).exists()
    assert set(copied.roster.values_list("id", flat=True)).isdisjoint(m.id for m in members)
    assert copied.exclusions and copied.exclusions != e.exclusions
    assert not ControlCommand.objects.filter(event=copied).exists()


def test_draft_transfer_requires_both_recent_mfa_accounts_and_only_changes_owner():
    c, e = setup()
    target = user("target@example.invalid")
    other = login_with_code(Client(), target, mfa=True)
    response = c.post(
        f"/events/{e.id}/transfer", token() | {"email": target.email, "owner_label": "Éloïse"}
    )
    assert response.status_code == 302, response.content
    ticket = OwnershipTransfer.objects.get(event=e)
    response = other.post("/transfers", token() | {"transfer_id": str(ticket.id)})
    assert response.status_code == 302, response.content
    e.refresh_from_db()
    assert e.owner.user == target
    assert c.get(f"/events/{e.id}").status_code == 404
    assert other.post("/transfers", token() | {"transfer_id": str(ticket.id)}).status_code == 302
    assert not ControlCommand.objects.exists()


def test_published_transfer_retries_identical_command_on_uncertain_response():
    c, e = setup()
    e.state = "OPEN"
    e.save()
    target = user("target@example.invalid")
    other = login_with_code(Client(), target, mfa=True)
    assert (
        c.post(
            f"/events/{e.id}/transfer", token() | {"email": target.email, "owner_label": "Éloïse"}
        ).status_code
        == 302
    )
    ticket = OwnershipTransfer.objects.get(event=e)
    with patch("control_core.views.send_command", side_effect=TimeoutError):
        assert (
            other.post("/transfers", token() | {"transfer_id": str(ticket.id)}).status_code == 503
        )
    e.refresh_from_db()
    assert e.owner.user != target
    command = ControlCommand.objects.get()
    ticket.refresh_from_db()
    assert ticket.state == "APPLYING"
    with patch(
        "control_core.views.send_command", return_value={"version": 2, "state": "OPEN"}
    ) as send:
        assert (
            other.post("/transfers", token() | {"transfer_id": str(ticket.id)}).status_code == 302
        )
        assert send.call_args.args[0].id == command.id
    e.refresh_from_db()
    assert e.owner.user == target and e.version == 2
    assert ControlCommand.objects.count() == 1


def test_local_time_validation_and_csrf_boundary():
    from noel_ui import EventForm

    form = EventForm(
        event_data()
        | {"celebration_at": "2026-10-25T02:30", "wishlist_deadline": "2026-10-01T18:00"}
    )
    assert not form.is_valid() and "ambiguë" in str(form.errors)
    assert (
        Client(enforce_csrf_checks=True).post("/events/new", event_data() | token()).status_code
        == 403
    )


def test_non_definitive_transfer_http_error_keeps_reservation_and_retry_form():
    import urllib.error

    c, e = setup()
    e.state = "OPEN"
    e.save()
    target = user("target@example.invalid")
    other = login_with_code(Client(), target, mfa=True)
    assert (
        c.post(
            f"/events/{e.id}/transfer", token() | {"email": target.email, "owner_label": "Éloïse"}
        ).status_code
        == 302
    )
    ticket = OwnershipTransfer.objects.get(event=e)
    with patch(
        "control_core.views.send_command",
        side_effect=urllib.error.HTTPError("https://coffre.invalid", 503, "Unavailable", {}, None),
    ):
        response = other.post("/transfers", token() | {"transfer_id": str(ticket.id)})
    assert response.status_code == 503 and str(ticket.id).encode() in response.content
    ticket.refresh_from_db()
    assert ticket.state == "APPLYING"
    assert not ControlCommand.objects.get().rejected


def test_open_retry_uses_original_command_and_reduced_api_request():
    c, e = setup()
    for i in range(4):
        RosterProposal.objects.create(
            event=e, display_name=f"P {i}", country="FR", email=f"{i}@example.invalid"
        )
    with patch("control_core.views.send_command", side_effect=TimeoutError):
        response = c.post(f"/events/{e.id}/action/open", token())
    assert response.status_code == 503
    command = ControlCommand.objects.get()
    data = {"submission_id": command.idempotency_key, "version": 1, "confirm": "on"}
    with patch(
        "control_core.views.send_command", return_value={"version": 1, "state": "OPEN"}
    ) as send:
        response = c.post(f"/events/{e.id}/retry/{command.id}", data)
    assert response.status_code == 302, response.content
    assert send.call_args.args[0].id == command.id
    assert ControlCommand.objects.count() == 1
