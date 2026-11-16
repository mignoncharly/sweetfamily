from django.db import migrations


def forwards(apps, schema_editor):
    Mail = apps.get_model("vault_core", "PendingMail")
    for row in Mail.objects.filter(invitation__isnull=False).select_related("invitation__member"):
        member = row.invitation.member
        row.event_id = member.event_id
        row.member_id = member.id
        row.kind = "INVITATION"
        row.logical_version = str(row.invitation_id)
        row.business_key = f"{row.event_id}:{row.member_id}:INVITATION:{row.logical_version}"
        row.save(update_fields=["event", "member", "kind", "logical_version", "business_key"])
    Notice = apps.get_model("vault_core", "DrawNotification")
    for notice in Notice.objects.filter(mail__isnull=False).select_related("draw", "mail"):
        row = notice.mail
        row.event_id = notice.draw.event_id
        row.member_id = notice.member_id
        row.kind = "DRAW_READY"
        row.logical_version = str(notice.draw.manifest_version)
        row.business_key = f"{row.event_id}:{row.member_id}:DRAW_READY:{row.logical_version}"
        row.save(update_fields=["event", "member", "kind", "logical_version", "business_key"])


class Migration(migrations.Migration):
    dependencies = [("vault_core", "0009_notificationoutbox_membership_reminders_enabled_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
