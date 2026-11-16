"""Draw transport/worker smoke. Seven extra identities are explicitly synthetic fixtures."""

from phase3_smoke import execute


def run_draw_smoke(extra):
    execute(
        "vault",
        r"""
import django,os,sys,json
from pathlib import Path
django.setup()
sys.path.insert(0,str(Path.cwd()/"tests/cases"))
sys.path.insert(0,str(Path.cwd()/"scripts"))
from wishlist_cases import items
from vault_core.models import Membership
from vault_core.wishlists import save_list
from allauth.account.models import EmailAddress
from django.utils import timezone
# The first actor completed real SMTP/login/claim; prepare only the other synthetic actors.
for member in Membership.objects.filter(event_id=os.environ["SMOKE_EVENT_ID"]):
    if member.claimed_at is None:
        EmailAddress.objects.filter(user=member.identity.user).update(verified=True)
        member.claimed_at=timezone.now()
        member.save(update_fields=["claimed_at"])
        save_list(member,0,items(),validate=True)
""",
        extra,
    )
    execute(
        "control",
        r"""
import django,os,sys,json
from pathlib import Path
django.setup()
sys.path.insert(0,str(Path.cwd()/"tests/cases"))
sys.path.insert(0,str(Path.cwd()/"scripts"))
from helpers import login_with_code
from django.contrib.auth import get_user_model
from django.test import Client,override_settings
from control_core.models import EventDraft
with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
    client=Client()
    saved=json.loads(Path(os.environ["SMOKE_RECORD"]).read_text())
    for key,value in saved["control_cookies"].items():
        client.cookies[key]=value
    event=EventDraft.objects.get(pk=os.environ["SMOKE_EVENT_ID"])
    response=client.post(f"/api/events/{event.id}/confirm-roster",{"version":event.version},
        content_type="application/json",HTTP_IDEMPOTENCY_KEY="freeze-"+os.environ["SMOKE_LABEL"])
    assert response.status_code==200,response.content
    assert response.json()["state"]=="CONFIRMING"
""",
        extra,
    )
    execute(
        "vault",
        r"""
import django,os,json,urllib.request
django.setup()
from django.conf import settings
from django.test import Client
from vault_core.models import PrivateEvent
# Verified fixture sessions exercise real HTTP + CSRF, not eight independent login ceremonies.
event=PrivateEvent.objects.get(pk=os.environ["SMOKE_EVENT_ID"])
for member in event.members.all():
    client=Client()
    client.force_login(member.identity.user)
    assert client.get(f"/rules?event_id={event.id}").status_code==200
    cookie="; ".join(key+"="+value.value for key,value in client.cookies.items())
    headers={"Content-Type":"application/json","Cookie":cookie,
             "X-CSRFToken":client.cookies[settings.CSRF_COOKIE_NAME].value}
    data={"manifest_version":event.manifest_version,"manifest_digest":event.manifest_digest}
    request=urllib.request.Request(os.environ["NOEL_VAULT_URL"]+f"/api/me/roster-consent?event_id={event.id}",
        data=json.dumps(data).encode(),headers=headers,method="POST")
    with urllib.request.urlopen(request) as response:
        assert json.load(response)["accepted"]
""",
        extra,
    )
    execute(
        "control",
        r"""
import django,os,sys,time,json
from pathlib import Path
django.setup()
sys.path.insert(0,str(Path.cwd()/"tests/cases"))
sys.path.insert(0,str(Path.cwd()/"scripts"))
from helpers import login_with_code
from django.contrib.auth import get_user_model
from django.test import Client,override_settings
from control_core.models import EventDraft
with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
    client=Client()
    saved=json.loads(Path(os.environ["SMOKE_RECORD"]).read_text())
    for key,value in saved["control_cookies"].items():
        client.cookies[key]=value
    event=EventDraft.objects.get(pk=os.environ["SMOKE_EVENT_ID"])
    # Only public expected version is obtained from the actual coffre receipt/projection.
    deadline=time.monotonic()+30
    while event.state!="READY" and time.monotonic()<deadline:
        time.sleep(.2)
        event.refresh_from_db()
    assert event.state=="READY"
    response=client.post(f"/api/events/{event.id}/draw",{"version":event.version},
        content_type="application/json",HTTP_IDEMPOTENCY_KEY="draw-"+os.environ["SMOKE_LABEL"])
    assert response.status_code==200,response.content
    assert response.json()["state"]=="DRAWING"
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        event.refresh_from_db()
        if event.state=="DRAWN" and event.draw_progress=="FINALIZING":
            break
        time.sleep(.2)
    else:
        raise AssertionError("Draw worker/safe projection not completed")
""",
        extra,
    )
    execute(
        "vault",
        r"""
import django,os
django.setup()
from vault_core.models import SealedDraw,DrawNotification
record=SealedDraw.objects.get(event_id=os.environ["SMOKE_EVENT_ID"])
assert record.release_state=="PENDING_DURABILITY" and record.job.state=="SEALED"
assert DrawNotification.objects.filter(draw=record,state="HELD",mail__state="HELD").count()==8
""",
        extra,
    )
