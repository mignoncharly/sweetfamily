"""Neutral business notifications. No assignment, wish or purchase content is rendered."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from noel_delivery import deliver_one as dispatch
from noel_delivery import local_evening, reconcile_one
from noel_delivery import reminder_proposals as proposals

from .models import (
    DeliveryReceipt,
    PendingMail,
    PrivateEvent,
    RosterConsent,
    ScheduledNotification,
    SealedDraw,
    Wishlist,
)
from .secrets import decrypt, encrypt


class RateLimited(ValueError):
    pass


OPTIONAL = {"LIST_REMINDER", "PREPARATION", "WISH_DIGEST"}
TEXT = {
    "OWNERSHIP": (
        "organisation de l'événement",
        (
            "Le rôle d'organisation a changé. Ce rôle ne donne aucun accès "
            "supplémentaire aux attributions ou achats privés."
        ),
    ),
    "CONSENT": (
        "règles à confirmer",
        "Vérifie les personnes, pays, règles et exclusions du groupe, "
        "puis confirme la version courante.",
    ),
    "DRAW_READY": (
        "tirage disponible",
        "Ton tirage est prêt. Connecte-toi à ton espace pour découvrir à qui offrir ton cadeau.",
    ),
    "LIST_REMINDER": (
        "mes trois souhaits",
        "Pense à compléter et valider tes trois souhaits dans le coffre.",
    ),
    "PREPARATION": (
        "préparer le réveillon",
        "Pense à recevoir le cadeau chez toi et à l'apporter au réveillon.",
    ),
    "WISH_DIGEST": (
        "souhaits du groupe",
        "Les souhaits du groupe ont évolué. Vérifie les listes dans ton espace avant achat.",
    ),
    "CANCELLED": (
        "événement annulé",
        "L'événement est annulé. N'utilise plus ce tirage. "
        "L'annulation n'efface pas un cadeau déjà vu ou acheté.",
    ),
    "PURGE_NOTICE": (
        "suppression prochaine",
        "Les données privées de cet événement seront supprimées selon la règle annoncée. "
        "Consulte tes propres données dans le coffre avant cette échéance.",
    ),
}


def enqueue(
    member, kind, version, *, state="QUEUED", resend_number=0, expires_at=None, owner_label=None
):
    from .domain import queue_mail

    subject, body = TEXT[kind]
    if kind == "OWNERSHIP":
        body += f" Nouveau nom d'organisation annoncé : {owner_label}."
    if kind == "PURGE_NOTICE":
        day = member.event.celebration_at.astimezone(
            ZoneInfo(member.event.timezone)
        ).date() + timedelta(days=90)
        body += f" Date prévue : {day.isoformat()}."
    link = f"{settings.PUBLIC_ORIGIN}/?event_id={member.event_id}"
    return queue_mail(
        "Noël Secret — " + subject,
        body + "\n" + link,
        member.identity.email,
        expires_at or timezone.now() + timedelta(days=7),
        identity=member.identity,
        category="NOTICE",
        member=member,
        kind=kind,
        logical_version=str(version),
        state=state,
        resend_number=resend_number,
    )


def prelock(candidate):
    return (
        not candidate.event_id
        or PrivateEvent.objects.select_for_update(skip_locked=True)
        .filter(pk=candidate.event_id)
        .exists()
    )


def useful(member, kind, event, version=None):
    if not member.active or not member.identity.user.is_active:
        return False
    if kind == "CANCELLED":
        return event.state == "CANCELLED" and member.claimed_at is not None
    if kind in {"PURGE_NOTICE", "OWNERSHIP"}:
        return event.state != "ARCHIVED" and member.claimed_at is not None
    if event.state in {"CANCELLED", "ARCHIVED", "CLOSED"}:
        return False
    if kind in OPTIONAL and (not event.reminders_enabled or not member.reminders_enabled):
        return False
    if kind == "INVITATION":
        return event.state == "OPEN" and member.claimed_at is None
    if member.claimed_at is None:
        return False
    if kind == "CONSENT":
        return (
            event.state in {"CONFIRMING", "READY"}
            and not RosterConsent.objects.filter(
                member=member,
                manifest_version=event.manifest_version,
                manifest_digest=event.manifest_digest,
            ).exists()
        )
    if kind == "LIST_REMINDER":
        return (
            event.state in {"OPEN", "CONFIRMING", "READY"}
            and not Wishlist.objects.filter(member=member, state="VALIDATED").exists()
        )
    if kind in {"DRAW_READY", "PREPARATION", "WISH_DIGEST"}:
        if (
            event.state != "DRAWN"
            or not SealedDraw.objects.filter(event=event, release_state="AVAILABLE").exists()
        ):
            return False
        if kind == "PREPARATION":
            from .private_space import purchase_value

            return purchase_value(member)["state"] not in {"READY", "GIVEN"}
        return True
    return kind == "PURGE_NOTICE" and event.state not in {"ARCHIVED"}


def guard(item):
    if item.invitation_id:
        invitation = item.invitation
        if invitation.revoked_at or invitation.used_at or invitation.expires_at <= timezone.now():
            return False
    if item.event_id and item.member_id:
        import json

        if item.identity_id and json.loads(decrypt(item.payload))["email"] != item.identity.email:
            return False
        if not useful(item.member, item.kind, item.event):
            return False
        if item.kind == "CONSENT":
            if item.logical_version.startswith("resend-"):
                return item.logical_version.endswith(f":manifest-{item.event.manifest_version}")
            return item.logical_version == str(item.event.manifest_version)
        if item.kind in OPTIONAL:
            if item.logical_version.startswith("schedule-"):
                return item.logical_version.startswith(f"schedule-{item.event.reminder_version}:")
            if item.logical_version.startswith("resend-"):
                return item.logical_version.endswith(f":reminder-{item.event.reminder_version}")
    return True


def deliver_one():
    return dispatch(PendingMail, DeliveryReceipt, decrypt, encrypt, guard, prelock)


def reconcile():
    return reconcile_one(PendingMail, DeliveryReceipt)


def reschedule(event):
    event.reminder_version += 1
    event.save(update_fields=["reminder_version"])
    ScheduledNotification.objects.filter(event=event, state="PENDING").update(state="SKIPPED")
    PendingMail.objects.filter(event=event, kind__in=OPTIONAL, state="QUEUED").update(
        state="EXPIRED", payload=""
    )
    if not event.reminders_enabled:
        return
    for member in event.members.filter(active=True):
        for kind, days, due, expiry in proposals(event):
            ScheduledNotification.objects.get_or_create(
                event=event,
                member=member,
                kind=kind,
                logical_version=f"{event.reminder_version}:{days}",
                defaults={"version": event.reminder_version, "due_at": due, "expires_at": expiry},
            )


def schedule_digest(event):
    if event.state != "DRAWN" or not event.reminders_enabled:
        return
    zone = ZoneInfo(event.timezone)
    now = timezone.now()
    day = now.astimezone(zone).date()
    due = local_evening(day, zone)
    if due <= now:
        day += timedelta(days=1)
        due = local_evening(day, zone)
    event.wish_digest_day = day
    event.save(update_fields=["wish_digest_day"])
    for member in event.members.filter(active=True, claimed_at__isnull=False):
        ScheduledNotification.objects.get_or_create(
            event=event,
            member=member,
            kind="WISH_DIGEST",
            logical_version=day.isoformat(),
            defaults={
                "version": event.reminder_version,
                "due_at": due,
                "expires_at": due + timedelta(hours=24),
            },
        )


def schedule_one():
    now = timezone.now()
    candidate = (
        ScheduledNotification.objects.filter(state="PENDING", due_at__lte=now)
        .order_by("due_at")
        .first()
    )
    if candidate is None:
        return False
    with transaction.atomic():
        event = (
            PrivateEvent.objects.select_for_update(skip_locked=True)
            .filter(pk=candidate.event_id)
            .first()
        )
        if event is None:
            return False
        item = (
            ScheduledNotification.objects.select_for_update(skip_locked=True)
            .filter(pk=candidate.pk, state="PENDING")
            .first()
        )
        if item is None:
            return False
        try:
            valid = (
                item.expires_at > now
                and item.version == event.reminder_version
                and useful(item.member, item.kind, event)
            )
        except Exception:
            from .envelopes import alert_unavailable

            alert_unavailable()
            valid = False
        if valid:
            enqueue(
                item.member,
                item.kind,
                f"schedule-{item.version}:" + item.logical_version,
                expires_at=item.expires_at,
            )
        item.state = "ENQUEUED" if valid else "SKIPPED"
        item.save(update_fields=["state"])
        return True


def configure(event, enabled, deadline, celebration):
    if type(enabled) is not bool or event.state in {"CANCELLED", "CLOSED", "ARCHIVED"}:
        raise ValueError("Rappels indisponibles.")
    dates = [datetime.fromisoformat(value) for value in (deadline, celebration)]
    if dates[0] != event.wishlist_deadline or dates[1] != event.celebration_at:
        raise ValueError("Confirme les dates courantes avant d'activer les rappels.")
    event.reminders_enabled = enabled
    event.save(update_fields=["reminders_enabled"])
    reschedule(event)


def resend_notice(event, member_id, kind):
    from .domain import invite

    member = event.members.select_related("identity").get(pk=member_id, active=True)
    if kind not in {"INVITATION", "CONSENT", "DRAW_READY", "LIST_REMINDER", "PREPARATION"}:
        raise ValueError("Notification non autorisée.")
    # Manual reminders are explicit requested notices; preferences still apply to optional ones.
    if not useful(member, kind, event):
        raise ValueError("Cette notification n'est plus utile dans cet état.")
    recent = PendingMail.objects.filter(
        event=event, created_at__gte=timezone.now() - timedelta(hours=1), resend_number__gt=0
    )
    if recent.filter(member=member).count() >= 3 or recent.count() >= 40:
        raise RateLimited("Limite de renvoi atteinte.")
    if kind == "INVITATION":
        invitation = invite(member)
        mail = PendingMail.objects.get(invitation=invitation)
        mail.resend_number = 1
        mail.save(update_fields=["resend_number"])
    else:
        number = (
            PendingMail.objects.filter(event=event, member=member, resend_number__gt=0).count() + 1
        )
        version = f"resend-{number}"
        if kind == "CONSENT":
            version += f":manifest-{event.manifest_version}"
        if kind in OPTIONAL:
            version += f":reminder-{event.reminder_version}"
        enqueue(member, kind, version, resend_number=number)
