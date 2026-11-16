"""Explicit neutral mail probe, excluded from production archives."""

import argparse
import os
import subprocess
import sys

import tasks

CODE = r"""
import django,os,json
from datetime import timedelta
django.setup()
from django.conf import settings
from django.utils import timezone
from django.core.mail import EmailMessage
if settings.APP_ENV not in {'local','staging'} or settings.MAIL_PROVIDER not in {'resend','zoho'}:
    raise RuntimeError('Probe requires configured non-production transport')
from noel_delivery import check_live,reconcile_one
address=os.environ.get('NOEL_PROBE_TO','')
identifier=os.environ.get('NOEL_PROBE_ID','')
if settings.SERVICE_ROLE=='vault':
    from vault_core.models import PendingMail as Mail,DeliveryReceipt
    from vault_core.domain import queue_mail
    from vault_core.notifications import deliver_one
else:
    from control_core.models import AuthMail as Mail,DeliveryReceipt
    from control_core.mail import OutboxBackend,deliver_one
if identifier:
    item=Mail.objects.get(pk=identifier)
    if item.provider_id and item.transport=="resend":
        from noel_delivery import reconcile_notification
        reconcile_notification(Mail,DeliveryReceipt,item.id)
        item.refresh_from_db()
else:
    data={'from':settings.DEFAULT_FROM_EMAIL,'email':address}
    if settings.MAIL_PROVIDER=='resend':
        check_live(data)
    else:
        from noel_delivery import zoho_connection
        connection=zoho_connection(data) # validates settings only; the dispatch opens it once
    subject='Noël Secret — vérification du transport'
    body='Essai autorisé de notification. Aucun tirage, souhait ou achat dans ce message.'
    if settings.SERVICE_ROLE=='vault':
        item=queue_mail(subject,body,address,timezone.now()+timedelta(minutes=10),category='NOTICE')
    else:
        from noel_delivery import mac
        from control_core.secrets import encrypt
        payload={'subject':subject,'body':body,'email':address,'from':settings.DEFAULT_FROM_EMAIL}
        item=Mail.objects.create(payload=encrypt(json.dumps(payload)),payload_mac=mac(payload),
            expires_at=timezone.now()+timedelta(minutes=10),next_attempt_at=timezone.now())
    # Process only this probe's logical message, preserving normal application work.
    from noel_delivery import deliver_one as dispatch
    from importlib import import_module
    secrets=import_module(settings.SERVICE_ROLE+'_core.secrets')
    class ProbeRows:
        class Rows:
            def filter(self,*args,**kwargs):
                return Mail.objects.filter(pk=item.id).filter(*args,**kwargs)
            def select_for_update(self,*args,**kwargs):
                return Mail.objects.select_for_update(*args,**kwargs).filter(pk=item.id)
        objects=Rows()
    dispatch(ProbeRows,DeliveryReceipt,secrets.decrypt,secrets.encrypt)
    item.refresh_from_db()
print(json.dumps({'notification_id':str(item.id),'submission':item.state,'delivery':item.delivery_status}))
"""


def main():
    if not tasks.in_project_environment():
        raise SystemExit(subprocess.call([str(tasks.PYTHON), __file__, *sys.argv[1:]]))
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=tasks.ROLES)
    parser.add_argument("--to")
    parser.add_argument("--notification")
    parser.add_argument("--confirm-authorised", action="store_true")
    parser.add_argument("--configured-environment", action="store_true")
    args = parser.parse_args()
    if not args.notification and (not args.to or not args.confirm_authorised):
        parser.error("Queueing a live probe requires --to and --confirm-authorised")
    env = os.environ.copy() if args.configured_environment else tasks.environment(args.role)
    if env.get("SERVICE_ROLE") != args.role:
        raise SystemExit("Configured service role does not match --role")
    env.update(NOEL_PROBE_TO=args.to or "", NOEL_PROBE_ID=args.notification or "")
    result = subprocess.run(
        [str(tasks.PYTHON), "-c", CODE], env=env, cwd=tasks.ROOT, capture_output=True, text=True
    )
    if result.returncode:
        raise SystemExit(
            "Probe not confirmed. Check provider configuration; no delivery success claimed."
        )
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
