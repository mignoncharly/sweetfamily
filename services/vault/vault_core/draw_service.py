import hashlib
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from noel_contracts import canonical, event_fields

from .draw_crypto import seal
from .draw_engine import InvalidRules, graph, sample, validate_privacy, validate_result
from .models import (
    DrawJob,
    DrawNotification,
    Exclusion,
    Invitation,
    Membership,
    PendingMail,
    PrivateEvent,
    RosterConsent,
    SealedDraw,
    Wishlist,
)
from .wishlists import snapshot, validate_items


class StateConflict(ValueError):
    pass


def bump(event):
    event.version += 1
    event.next_projection_at = timezone.now()
    event.save()


def invalidate(event):
    if (
        event.state not in {"OPEN", "CONFIRMING", "READY"}
        or SealedDraw.objects.filter(event=event).exists()
    ):
        raise StateConflict("Les règles ne sont plus modifiables.")
    event.state = "OPEN"
    event.frozen_manifest = None
    event.manifest_digest = ""
    # Keep the previous version as an epoch counter; never reuse a consent version.
    RosterConsent.objects.filter(member__event=event).delete()
    bump(event)


def eligible(event):
    from .access_codes import verified_identity

    members = list(
        event.members.filter(active=True).select_related("identity__user").order_by("id")
    )
    if not 4 <= len(members) <= 20:
        raise StateConflict("Il faut entre 4 et 20 personnes actives.")
    for member in members:
        if (
            member.claimed_at is None
            or not member.identity.user.is_active
            or not verified_identity(member.identity)
        ):
            raise StateConflict("Chaque personne doit rejoindre et faire vérifier son identité.")
        listing = Wishlist.objects.filter(member=member, state="VALIDATED").first()
        if listing is None:
            raise StateConflict("Chaque personne doit valider ses trois souhaits.")
        fields = {
            "slot",
            "title",
            "url",
            "price_eur_cents",
            "currency",
            "price_date",
            "note",
            "exact_model",
            "equivalent_ok",
        }
        validate_items([{k: row[k] for k in fields} for row in snapshot(listing)], complete=True)
    return members


def manifest(event, version):
    members = eligible(event)
    ids = {str(m.id) for m in members}
    excluded = sorted(
        [str(x.giver_id), str(x.recipient_id)] for x in Exclusion.objects.filter(event=event)
    )
    if any(g not in ids or r not in ids for g, r in excluded):
        raise StateConflict("Une exclusion concerne une personne retirée.")
    _, rows = graph(ids, excluded)
    validate_privacy(rows)
    return {
        "event_id": str(event.id),
        "version": version,
        "event": {
            "title": event.title,
            "celebration_at": event.celebration_at.isoformat(),
            "wishlist_deadline": event.wishlist_deadline.isoformat(),
            "timezone": event.timezone,
            "shipping_included": event.shipping_included,
            "handover": event.handover,
            "currency": "EUR",
            "max_price_cents": 4999,
            "wishes_required": 3,
        },
        "members": [
            {"id": str(m.id), "display_name": m.display_name, "country": m.country} for m in members
        ],
        "exclusions": excluded,
    }


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def current_manifest(event):
    if not event.frozen_manifest or not event.manifest_digest:
        raise StateConflict("Les règles ne sont pas gelées.")
    current = manifest(event, event.manifest_version)
    if fingerprint(current) != event.manifest_digest or current != event.frozen_manifest:
        raise StateConflict("Le groupe ou les règles ont changé.")
    return current


def ready(event):
    current_manifest(event)
    members = event.members.filter(active=True)
    return (
        RosterConsent.objects.filter(
            member__in=members,
            manifest_version=event.manifest_version,
            manifest_digest=event.manifest_digest,
        ).count()
        == members.count()
    )


@transaction.atomic
def consent(member, version, digest):
    event = PrivateEvent.objects.select_for_update().get(pk=member.event_id)
    if event.state not in {"CONFIRMING", "READY"} or type(version) is not int:
        raise StateConflict("Confirmation indisponible.")
    if version != event.manifest_version or digest != event.manifest_digest:
        raise StateConflict("Les règles ont changé. Consulte la version courante.")
    if not Membership.objects.filter(pk=member.pk, active=True, claimed_at__isnull=False).exists():
        raise StateConflict("Inscription requise.")
    current_manifest(event)
    RosterConsent.objects.get_or_create(
        member=member, manifest_version=version, defaults={"manifest_digest": digest}
    )
    if ready(event) and event.state != "READY":
        event.state = "READY"
        bump(event)
    return event


def rule_command(kind, payload):
    """Called inside the signed-command transaction; returns only a safe receipt."""
    base = {"event_id", "version"}
    extra = {
        "exclusions": {"exclusions"},
        "update_rules": {"event"},
        "freeze": set(),
        "draw": set(),
        "cancel": {"confirm"},
        "close": {"confirm"},
        "remove_member": {"member_id", "confirm"},
    }[kind]
    if set(payload) != base | extra or type(payload["version"]) is not int:
        raise StateConflict("Commande invalide.")
    event = PrivateEvent.objects.select_for_update().get(pk=payload["event_id"])
    if (
        kind == "draw"
        and event.state in {"DRAWING", "DRAWN"}
        and DrawJob.objects.filter(event=event).exists()
    ):
        # A second key cannot generate another job or result, even after completion.
        if payload["version"] > event.version:
            raise StateConflict("Version inconnue.")
        return event
    if payload["version"] != event.version:
        raise StateConflict("Version de l'événement périmée.")
    if kind in {"update_rules", "exclusions"}:
        if kind == "update_rules":
            event_fields(payload["event"])
            if event.shipping_included != payload["event"]["shipping_included"]:
                Wishlist.objects.filter(member__event=event).update(
                    state="DRAFT", validated_at=None
                )
            invalidate(event)
            for key, value in payload["event"].items():
                setattr(event, key, value)
            event.save()
            from .notifications import reschedule

            reschedule(event)
        else:
            active = {str(m.id): m for m in event.members.filter(active=True)}
            pairs = payload["exclusions"]
            if not isinstance(pairs, list) or len(pairs) > 380:
                raise StateConflict("Exclusions invalides.")
            normalized = set()
            for pair in pairs:
                if (
                    not isinstance(pair, list)
                    or len(pair) != 2
                    or any(not isinstance(x, str) for x in pair)
                ):
                    raise StateConflict("Exclusion invalide.")
                g, r = pair
                if g not in active or r not in active or g == r or (g, r) in normalized:
                    raise StateConflict("Exclusion invalide.")
                normalized.add((g, r))
            invalidate(event)
            Exclusion.objects.filter(event=event).delete()
            Exclusion.objects.bulk_create(
                [
                    Exclusion(event=event, giver=active[g], recipient=active[r])
                    for g, r in sorted(normalized)
                ]
            )
    elif kind == "freeze":
        if event.state not in {"OPEN", "CONFIRMING", "READY"}:
            raise StateConflict("Gel impossible.")
        value = manifest(event, (event.manifest_version or 0) + 1)
        event.manifest_version = value["version"]
        event.frozen_manifest = value
        event.manifest_digest = fingerprint(value)
        RosterConsent.objects.filter(member__event=event).delete()
        event.state = "CONFIRMING"
        bump(event)
        from .notifications import enqueue

        for member in event.members.filter(active=True):
            enqueue(member, "CONSENT", event.manifest_version)
    elif kind == "draw":
        if event.state != "READY" or not ready(event):
            raise StateConflict("Toutes les confirmations et listes valides sont requises.")
        job = DrawJob.objects.filter(event=event).first()
        if job and (job.state != "FAILED_FINAL" or SealedDraw.objects.filter(event=event).exists()):
            raise StateConflict("Un tirage existe déjà.")
        if job is None:
            DrawJob.objects.create(
                event=event, snapshot=event.frozen_manifest, snapshot_digest=event.manifest_digest
            )
        else:
            job.snapshot = event.frozen_manifest
            job.snapshot_digest = event.manifest_digest
            job.state = "PENDING"
            job.failure_code = ""
            job.lease_until = None
            job.next_attempt_at = timezone.now()
            job.save()
        event.state = "DRAWING"
        bump(event)
    elif kind == "remove_member":
        if payload["confirm"] is not True:
            raise StateConflict("Confirme les conséquences du retrait.")
        member = Membership.objects.get(event=event, pk=payload["member_id"], active=True)
        withdraw(member)
        event.refresh_from_db()
    elif kind == "cancel":
        if payload["confirm"] is not True:
            raise StateConflict("Confirme l'annulation pour tout le groupe.")
        cancel(event)
    elif kind == "close":
        if (
            payload["confirm"] is not True
            or event.state != "DRAWN"
            or not SealedDraw.objects.filter(event=event, release_state="AVAILABLE").exists()
        ):
            raise StateConflict("Clôture indisponible.")
        event.state = "CLOSED"
        bump(event)
    return event


def cancel(event):
    from .models import ScheduledNotification
    from .notifications import enqueue

    if event.state in {"CLOSED", "ARCHIVED", "CANCELLED"}:
        raise StateConflict("Événement déjà terminé.")
    event.state = "CANCELLED"
    bump(event)
    DrawJob.objects.filter(event=event).exclude(state="SEALED").update(
        state="FAILED_FINAL", lease_until=None, failure_code="EVENT_CANCELLED"
    )
    PendingMail.objects.filter(invitation__member__event=event, state="QUEUED").update(
        state="EXPIRED", payload=""
    )
    DrawNotification.objects.filter(draw__event=event).update(state="CANCELLED")
    PendingMail.objects.filter(drawnotification__draw__event=event, state="QUEUED").update(
        state="EXPIRED", payload=""
    )
    Invitation.objects.filter(member__event=event, used_at=None, revoked_at=None).update(
        revoked_at=timezone.now()
    )
    for member in event.members.filter(active=True, claimed_at__isnull=False).select_related(
        "identity"
    ):
        enqueue(member, "CANCELLED", event.version)
    ScheduledNotification.objects.filter(event=event, state="PENDING").update(state="SKIPPED")
    PendingMail.objects.filter(event=event, state__in=["HELD", "QUEUED", "RUNNING"]).exclude(
        kind="CANCELLED"
    ).update(state="EXPIRED", payload="", lease_until=None)


@transaction.atomic
def withdraw(member):
    event = PrivateEvent.objects.select_for_update().get(pk=member.event_id)
    member = Membership.objects.select_for_update().get(pk=member.pk, event=event, active=True)
    if event.state in {"DRAWING", "DRAWN"}:
        cancel(event)
    else:
        invalidate(event)
        member.active = False
        member.save(update_fields=["active"])
        Exclusion.objects.filter(event=event).filter(Q(giver=member) | Q(recipient=member)).delete()
        Invitation.objects.filter(member=member, used_at=None).update(revoked_at=timezone.now())
        PendingMail.objects.filter(invitation__member=member, state="QUEUED").update(
            state="EXPIRED", payload=""
        )
    return event


@transaction.atomic
def acquire_job():
    now = timezone.now()
    eligible_jobs = Q(
        drawjob__state__in=["PENDING", "FAILED_RETRYABLE"], drawjob__next_attempt_at__lte=now
    ) | Q(drawjob__state="RUNNING", drawjob__lease_until__lte=now)
    event = (
        PrivateEvent.objects.filter(eligible_jobs, state="DRAWING")
        .select_for_update(skip_locked=True, of=("self",))
        .order_by("id")
        .first()
    )
    if event is None:
        return None
    job = DrawJob.objects.select_for_update().get(event=event)
    job.attempt += 1
    job.state = "RUNNING"
    job.lease_until = now + timedelta(seconds=settings.DRAW_LEASE_SECONDS)
    job.save(update_fields=["attempt", "state", "lease_until"])
    return job.id, job.attempt, job.snapshot, job.snapshot_digest


@transaction.atomic
def commit_result(job_id, attempt, expected_digest, permutation):
    initial = DrawJob.objects.get(pk=job_id)
    event = PrivateEvent.objects.select_for_update().get(pk=initial.event_id)
    job = DrawJob.objects.select_for_update().get(pk=job_id)
    if (
        event.state != "DRAWING"
        or job.state != "RUNNING"
        or job.attempt != attempt
        or job.lease_until is None
        or job.lease_until <= timezone.now()
        or job.snapshot_digest != expected_digest
        or event.manifest_digest != expected_digest
        or SealedDraw.objects.filter(event=event).exists()
    ):
        raise StateConflict("Bail ou version périmés.")
    if fingerprint(job.snapshot) != expected_digest or event.frozen_manifest != job.snapshot:
        raise StateConflict("Snapshot incohérent.")
    members = [m["id"] for m in job.snapshot["members"]]
    validate_result(members, job.snapshot["exclusions"], permutation)
    record = SealedDraw.objects.create(
        event=event,
        job=job,
        manifest_version=event.manifest_version,
        **seal(event, job, permutation),
    )
    from .notifications import enqueue

    for member in event.members.filter(id__in=members):
        mail = enqueue(member, "DRAW_READY", event.manifest_version, state="HELD")
        DrawNotification.objects.create(draw=record, member=member, mail=mail)

    event.state = "DRAWN"
    bump(event)
    job.state = "SEALED"
    job.lease_until = None
    job.failure_code = ""
    job.save()
    return record


@transaction.atomic
def fail_job(job_id, attempt, final=False):
    initial = DrawJob.objects.get(pk=job_id)
    event = PrivateEvent.objects.select_for_update().get(pk=initial.event_id)
    job = DrawJob.objects.select_for_update().get(pk=job_id)
    if event.state != "DRAWING" or job.state != "RUNNING" or job.attempt != attempt:
        return
    job.state = "FAILED_FINAL" if final or attempt >= 3 else "FAILED_RETRYABLE"
    job.failure_code = "RULES_REJECTED" if final else "COMPUTATION_FAILED"
    job.lease_until = None
    job.next_attempt_at = timezone.now() + timedelta(seconds=2 ** min(attempt, 10))
    job.save()
    event.next_projection_at = timezone.now()
    event.save(update_fields=["next_projection_at"])


def run_one_draw():
    lease = acquire_job()
    if lease is None:
        return False
    job_id, attempt, value, digest = lease
    try:
        result = sample(
            [row["id"] for row in value["members"]],
            value["exclusions"],
            timeout=settings.DRAW_TIMEOUT_SECONDS,
        )
        commit_result(job_id, attempt, digest, result)
    except InvalidRules:
        fail_job(job_id, attempt, final=True)
    except Exception:
        # No permutation, traceback, random state or private payload is logged or persisted.
        fail_job(job_id, attempt)
    return True


@transaction.atomic
def reopen_failed(event_id):
    event = PrivateEvent.objects.select_for_update().get(pk=event_id)
    job = DrawJob.objects.select_for_update().get(event=event)
    if (
        event.state != "DRAWING"
        or job.state != "FAILED_FINAL"
        or SealedDraw.objects.filter(event=event).exists()
    ):
        raise StateConflict("Réouverture interdite.")
    job.attempt += 1
    job.lease_until = None
    job.save(update_fields=["attempt", "lease_until"])
    event.state = "OPEN"
    event.frozen_manifest = None
    event.manifest_digest = ""
    RosterConsent.objects.filter(member__event=event).delete()
    bump(event)
