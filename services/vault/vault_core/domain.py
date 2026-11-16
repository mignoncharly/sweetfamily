import hashlib
import json
import secrets
import uuid
from datetime import timedelta

from allauth.account.fields import EmailField
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone
from noel_contracts import event_fields, member_fields

from .models import (
    Exclusion,
    InboundCommand,
    Invitation,
    Membership,
    PendingMail,
    PrivateEvent,
    RosterConsent,
    SecurityEvent,
    VerifiedIdentity,
)
from .secrets import encrypt


def identity_for(email):
    if email is None:
        if not settings.WHATSAPP_ENROLLMENT_ENABLED:
            raise ValueError("L'inscription sans email n'est pas activée par le coffre.")
        user = get_user_model().objects.create_user(username=uuid.uuid4().hex)
        return VerifiedIdentity.objects.create(user=user, email=None)
    email = EmailField().clean(email)
    identity = VerifiedIdentity.objects.filter(email=email).first()
    if identity:
        return identity
    account = (
        EmailAddress.objects.select_related("user")
        .filter(email=email, verified=True, primary=True)
        .first()
    )
    if account:
        # Event retention removes the private identity, but may retain the account
        # at its owner's request. Reuse that verified account for a new invitation.
        return VerifiedIdentity.objects.create(
            user=account.user, email=email, verified_at=timezone.now()
        )
    user = get_user_model().objects.create_user(username=uuid.uuid4().hex, email=email)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
    return VerifiedIdentity.objects.create(user=user, email=email)


def queue_mail(
    subject,
    body,
    email,
    expires_at,
    invitation=None,
    identity=None,
    category="AUTH",
    member=None,
    kind="",
    logical_version="",
    state="QUEUED",
    resend_number=0,
):
    identity = identity or (
        invitation.member.identity
        if invitation
        else VerifiedIdentity.objects.filter(email=email).first()
    )
    from noel_delivery import mac

    member = member or (invitation.member if invitation else None)
    kind = "INVITATION" if invitation else kind
    logical_version = str(invitation.id) if invitation else logical_version
    business_key = f"{member.event_id}:{member.id}:{kind}:{logical_version}" if member else None
    if business_key:
        old = PendingMail.objects.filter(business_key=business_key).first()
        if old:
            return old
    data = {"subject": subject, "body": body, "email": email, "from": settings.DEFAULT_FROM_EMAIL}
    return PendingMail.objects.create(
        identity=identity,
        category="INVITATION" if invitation else category,
        payload=encrypt(json.dumps(data, ensure_ascii=False)),
        payload_mac=mac(data),
        expires_at=expires_at,
        next_attempt_at=timezone.now(),
        invitation=invitation,
        member=member,
        event=member.event if member else None,
        kind=kind,
        logical_version=logical_version,
        business_key=business_key,
        state=state,
        resend_number=resend_number,
    )


def invite(member):
    now = timezone.now()
    if (
        Invitation.objects.filter(member=member, created_at__gte=now - timedelta(hours=1)).count()
        >= 3
    ):
        raise ValueError("Limite de réémission atteinte pour ce membre.")
    Invitation.objects.filter(member=member, used_at=None, revoked_at=None).update(revoked_at=now)
    token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        member=member,
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=now + timedelta(days=7),
    )
    if member.identity.email is None:
        # The public reference is not a login capability. Only the participant's
        # approved, browser-bound claim can consume this invitation.
        return invitation
    url = f"{settings.PUBLIC_ORIGIN}/join/{token}"
    queue_mail(
        "Noël Secret — invitation",
        f"Tu es invité à {member.event.title}.\n"
        f"Échéance : {member.event.wishlist_deadline.isoformat()}.\n"
        f"Rejoins le coffre indépendant : {url}\nVérifie ensuite ta boîte email. "
        "Le lien seul ne donne aucun accès privé.\nÀ recevoir chez toi et à apporter au réveillon.",
        member.identity.email,
        invitation.expires_at,
        invitation,
    )
    return invitation


@transaction.atomic
def apply_command(message):
    lock_key = uuid.UUID(message["id"]).int % (1 << 63)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
    old = InboundCommand.objects.select_for_update().filter(pk=message["id"]).first()
    if InboundCommand.objects.filter(nonce=message["nonce"]).exclude(pk=message["id"]).exists():
        raise ValueError("Nonce déjà utilisé.")
    if old:
        if old.body_digest != message["body_digest"]:
            raise ValueError("Conflit d'idempotence.")
        return old.response
    if InboundCommand.objects.filter(nonce=message["nonce"]).exists():
        raise ValueError("Nonce déjà utilisé.")
    payload = message["payload"]
    from .models import DeletionTombstone

    if DeletionTombstone.objects.filter(event_id=payload.get("event_id")).exists():
        raise ValueError("Événement supprimé ; nouvelle identité requise.")
    if message["type"] == "open":
        if set(payload) - {"reminders_enabled", "exclusions"} != {
            "event_id",
            "version",
            "event",
            "members",
        }:
            raise ValueError("Proposition invalide.")
        event_fields(payload["event"])
        if type(payload.get("reminders_enabled", False)) is not bool:
            raise ValueError("Activation explicite requise.")
        if type(payload["version"]) is not int or payload["version"] < 1:
            raise ValueError("Version invalide.")
        if not isinstance(payload["members"], list) or not 4 <= len(payload["members"]) <= 20:
            raise ValueError("Il faut entre 4 et 20 personnes.")
        names = set()
        emails = set()
        ids = set()
        for data in payload["members"]:
            member_fields(data)
            email = EmailField().clean(data["email"]) if data["email"] is not None else None
            name = data["display_name"].strip().casefold()
            if (email is not None and email in emails) or name in names or data["id"] in ids:
                raise ValueError("Noms d'affichage et emails doivent être distincts.")
            emails.add(email)
            names.add(name)
            ids.add(data["id"])
        if PrivateEvent.objects.filter(pk=payload["event_id"]).exists():
            raise ValueError("événement déjà ouvert.")
        exclusions = payload.get("exclusions", [])
        if not isinstance(exclusions, list) or len(exclusions) > 380:
            raise ValueError("Exclusions invalides.")
        for pair in exclusions:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or any(item not in ids for item in pair)
                or pair[0] == pair[1]
            ):
                raise ValueError("Exclusions invalides.")
        event = PrivateEvent.objects.create(
            id=payload["event_id"],
            version=payload["version"],
            reminders_enabled=payload.get("reminders_enabled", False),
            **payload["event"],
        )
        event.refresh_from_db()
        for data in payload["members"]:
            member = Membership.objects.create(
                id=data["id"],
                event=event,
                identity=identity_for(data["email"]),
                display_name=data["display_name"].strip(),
                country=data["country"],
            )
            invite(member)
        Exclusion.objects.bulk_create(
            [
                Exclusion(event=event, giver_id=g, recipient_id=r)
                for g, r in {tuple(pair) for pair in exclusions}
            ]
        )
        from .notifications import reschedule

        reschedule(event)
    elif message["type"] == "correct_invitation":
        if set(payload) != {"event_id", "version", "member_id", "email"}:
            raise ValueError("Correction invalide.")
        if type(payload["version"]) is not int:
            raise ValueError("Version invalide.")
        event = PrivateEvent.objects.select_for_update().get(pk=payload["event_id"])
        if event.state != "OPEN" or event.version != payload["version"]:
            raise ValueError("Version ou état incompatible.")
        member = Membership.objects.select_for_update().get(pk=payload["member_id"], event=event)
        if member.claimed_at is not None:
            raise ValueError("Identité déjà revendiquée.")
        # Reissuing a non-authenticating reference must not create another identity.
        identity = (
            member.identity
            if payload["email"] is None and member.identity.email is None
            else identity_for(payload["email"])
        )
        if Membership.objects.filter(event=event, identity=identity).exclude(pk=member.pk).exists():
            raise ValueError("Email déjà utilisé dans cet événement.")
        member.identity = identity
        member.save(update_fields=["identity"])
        invite(member)
        event.version += 1
        event.save(update_fields=["version"])
        RosterConsent.objects.filter(member__event=event).delete()
    elif message["type"] == "ownership_changed":
        from .draw_service import StateConflict, bump
        from .notifications import enqueue

        if set(payload) != {"event_id", "version", "transfer_ref", "owner_label"}:
            raise ValueError("Commande invalide.")
        uuid.UUID(payload["transfer_ref"])
        if (
            not isinstance(payload["owner_label"], str)
            or not 1 <= len(payload["owner_label"].strip()) <= 80
        ):
            raise ValueError("Nom d'organisation invalide.")
        event = PrivateEvent.objects.select_for_update().get(pk=payload["event_id"])
        if (
            type(payload["version"]) is not int
            or payload["version"] != event.version
            or event.state in {"ARCHIVED", "DRAWING"}
        ):
            raise StateConflict("Version ou état incompatible.")
        for member in event.members.filter(active=True, claimed_at__isnull=False):
            enqueue(
                member, "OWNERSHIP", payload["transfer_ref"], owner_label=payload["owner_label"]
            )
        bump(event)
    elif message["type"] in {"configure_reminders", "resend_notice"}:
        from .draw_service import StateConflict, bump
        from .notifications import configure, resend_notice

        kind = message["type"]
        expected = {"event_id", "version"} | (
            {"enabled", "wishlist_deadline", "celebration_at"}
            if kind == "configure_reminders"
            else {"member_id", "notice_type"}
        )
        if set(payload) != expected or type(payload["version"]) is not int:
            raise ValueError("Commande invalide.")
        event = PrivateEvent.objects.select_for_update().get(pk=payload["event_id"])
        if payload["version"] != event.version:
            raise StateConflict("Version périmée.")
        if kind == "configure_reminders":
            configure(
                event, payload["enabled"], payload["wishlist_deadline"], payload["celebration_at"]
            )
        else:
            resend_notice(event, payload["member_id"], payload["notice_type"])
        bump(event)
    elif message["type"] in {
        "update_rules",
        "exclusions",
        "freeze",
        "draw",
        "cancel",
        "close",
        "remove_member",
    }:
        from .draw_service import rule_command

        event = rule_command(message["type"], payload)
    else:
        raise ValueError("Commande non autorisée.")
    response = {"event_id": str(event.id), "version": event.version, "state": event.state}
    InboundCommand.objects.create(
        id=message["id"],
        nonce=message["nonce"],
        body_digest=message["body_digest"],
        response=response,
    )
    return response


@transaction.atomic
def accept_invitation(user, digest):
    invitation = (
        Invitation.objects.select_for_update()
        .select_related("member__event", "member__identity")
        .get(token_digest=digest, used_at=None, revoked_at=None, expires_at__gt=timezone.now())
    )
    member = Membership.objects.select_for_update().get(pk=invitation.member_id)
    if member.event.state != "OPEN" or not member.active or member.identity.user_id != user.pk:
        raise ValueError("Invitation indisponible.")
    if not EmailAddress.objects.filter(user=user, verified=True, primary=True).exists():
        raise ValueError("Vérifie ta boîte email.")
    if member.claimed_at:
        raise ValueError("Invitation déjà utilisée.")
    now = timezone.now()
    member.claimed_at = now
    member.save(update_fields=["claimed_at"])
    invitation.used_at = now
    invitation.save(update_fields=["used_at"])
    VerifiedIdentity.objects.filter(pk=member.identity_id).update(verified_at=now)
    SecurityEvent.objects.create(identity_id=member.identity_id, category="invitation_claimed")
    return member


def deliver_one():
    from .notifications import deliver_one as dispatch

    return dispatch()


@transaction.atomic
def project_one():
    import urllib.request

    from noel_contracts import canonical, sign, validate_projection

    now = timezone.now()
    event = (
        PrivateEvent.objects.select_for_update(skip_locked=True)
        .filter(next_projection_at__lte=now)
        .order_by("next_projection_at")
        .first()
    )
    if not event:
        return False
    rows = []
    from .models import DrawJob, SealedDraw, Wishlist

    for member in event.members.order_by("id"):
        mail = (
            PendingMail.objects.filter(event=event, member=member)
            .exclude(category="AUTH")
            .order_by("-created_at", "-id")
            .first()
        )
        state = (
            mail.delivery_status
            if mail and mail.delivery_status != "NONE"
            else "SUBMITTED"
            if mail and mail.state == "SENT"
            else "FAILED"
            if mail and mail.state == "FAILED"
            else "NONE"
            if mail and mail.state == "EXPIRED"
            else "QUEUED"
            if mail
            else "NONE"
        )
        rows.append(
            {
                "member_ref": str(member.id),
                "active": member.active,
                "registration_confirmed": member.claimed_at is not None,
                "wishlist_complete": Wishlist.objects.filter(
                    member=member, state="VALIDATED"
                ).exists(),
                "consent_received": RosterConsent.objects.filter(
                    member=member,
                    manifest_version=event.manifest_version,
                    manifest_digest=event.manifest_digest,
                ).exists(),
                "notification_state": state,
                "recipient_viewed": member.recipient_viewed,
            }
        )
    event.projection_version += 1
    job = DrawJob.objects.filter(event=event).first()
    sealed = SealedDraw.objects.filter(event=event).first()
    progress = (
        ("AVAILABLE" if sealed.release_state == "AVAILABLE" else "FINALIZING")
        if sealed
        else (
            "ACTION_REQUIRED"
            if job and job.state == "FAILED_FINAL"
            else "PROCESSING"
            if job
            else "NOT_STARTED"
        )
    )
    from .envelopes import alert_unavailable
    from .private_space import ready_total

    try:
        ready_count = ready_total(event)
    except Exception:
        alert_unavailable()
        event.next_projection_at = now + timedelta(seconds=30)
        event.save(update_fields=["next_projection_at"])
        return True
    body = {
        "event_version": event.version,
        "event_id": str(event.id),
        "projection_version": event.projection_version,
        "event_state": event.state,
        "manifest_version": event.manifest_version,
        "draw_progress": progress,
        "members": rows,
        "ready_count": ready_count,
    }
    validate_projection(body)
    request = urllib.request.Request(
        settings.CONTROL_ORIGIN + "/internal/status-projections",
        data=canonical(sign("status_projection", body, settings.PROJECTION_KEY)),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            if json.loads(response.read(1024)) != {"accepted": True}:
                raise ValueError()
    except Exception:
        event.next_projection_at = now + timedelta(seconds=30)
    else:
        event.next_projection_at = now + timedelta(minutes=15)
    event.save(update_fields=["next_projection_at", "projection_version"])
    return True
