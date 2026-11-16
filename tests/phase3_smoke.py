"""Synthetic end-to-end exercise against the real local apps, workers and Mailpit."""

import json
import subprocess
import uuid

import tasks


def execute(role, code, extra):
    result = subprocess.run(
        [str(tasks.PYTHON), "-c", code],
        env=tasks.environment(role) | extra,
        cwd=tasks.ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    return result.stdout


def run_smoke():
    label = "smoke-" + uuid.uuid4().hex
    record = tasks.LOCAL / (label + ".json")
    extra = {
        "SMOKE_LABEL": label,
        "SMOKE_RECORD": str(record),
        "SMOKE_EMAIL": label + "@example.invalid",
    }
    try:
        execute(
            "control",
            r"""
import django,sys,json,os
django.setup()
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/"tests/cases"))
from helpers import user,login_through_mailpit
from control_cases import event_data
from django.test import Client,override_settings
from control_core.models import EventDraft
with override_settings():
    actor=user(os.environ["SMOKE_EMAIL"])
    client=login_through_mailpit(Client(),actor)
    response=client.post("/api/events",event_data(),content_type="application/json")
    assert response.status_code==201
    event=response.json()
    Path(os.environ["SMOKE_RECORD"]).write_text(json.dumps({"event_id":event["id"]}))
    for i in range(8):
        email=(os.environ["SMOKE_EMAIL"] if i==0 else
               os.environ["SMOKE_LABEL"]+str(i)+"@example.invalid")
        response=client.post("/api/events/"+event["id"]+"/participants",
            {"version":event["version"],"display_name":"Alex "+str(i),
             "country":"FR" if i%2 else "DE","email":email},
            content_type="application/json")
        assert response.status_code==201
        event=response.json()
    response=client.post("/api/events/"+event["id"]+"/open",{"version":event["version"]},
        content_type="application/json",HTTP_IDEMPOTENCY_KEY=os.environ["SMOKE_LABEL"])
    assert response.status_code==200,response.content
    assert response.json()["state"]=="OPEN"
    Path(os.environ["SMOKE_RECORD"]).write_text(json.dumps({"event_id":event["id"],
        "control_cookies":{key:value.value for key,value in client.cookies.items()}}))
""",
            extra,
        )
        extra["SMOKE_EVENT_ID"] = json.loads(record.read_text())["event_id"]
        execute(
            "vault",
            r"""
import django,os,json,re,time,urllib.request
django.setup()
from django.test import Client
from django.utils import timezone
from vault_core.models import PrivateEvent,Membership
def delivered(pattern):
    started=time.monotonic()
    deadline=started+60
    while time.monotonic()<deadline:
        with urllib.request.urlopen("http://127.0.0.1:18025/api/v1/messages") as response:
            messages=json.load(response)["messages"]
        for row in messages:
            if row["From"]["Address"]!=os.environ["NOTIFICATION_FROM_EMAIL"]:
                continue
            if not any(address["Address"]==os.environ["SMOKE_EMAIL"] for address in row["To"]):
                continue
            message_url="http://127.0.0.1:18025/api/v1/message/"+row["ID"]
            with urllib.request.urlopen(message_url) as response:
                detail=json.load(response)
            match=re.search(pattern,detail["Text"])
            if match:
                if os.environ.get("NOEL_QUALIFICATION_DIR"):
                    from pathlib import Path
                    folder=Path(os.environ["NOEL_QUALIFICATION_DIR"])
                    target=folder/"smtp-local.json"
                    metrics=(json.loads(target.read_text()) if target.exists() else
                             {"transport":"actual local SMTP -> Mailpit","seconds":[]})
                    metrics["seconds"].append(round(time.monotonic()-started,4))
                    target.write_text(json.dumps(metrics,indent=2))
                return match.group(1)
        time.sleep(.2)
    raise AssertionError("Local email not received")
token=delivered(r"/join/([A-Za-z0-9_-]+)")
client=Client()
assert client.get("/join/"+token).status_code==200
client.post("/join/"+token)
response=client.post("/accounts/login/code/",{"email":os.environ["SMOKE_EMAIL"]})
assert response.status_code==302
code=delivered(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b")
assert client.post("/accounts/login/code/confirm/",{"code":code}).status_code==302
response=client.post("/api/me/invitations/accept")
assert response.status_code==201,response.content
assert len(client.get("/api/me/events").json()["events"])==1

from django.conf import settings
event_id=os.environ["SMOKE_EVENT_ID"]
assert client.get("/wishlist?event_id="+event_id).status_code==200
cookie="; ".join(key+"="+value.value for key,value in client.cookies.items())
headers={"Content-Type":"application/json","Cookie":cookie,
         "X-CSRFToken":client.cookies[settings.CSRF_COOKIE_NAME].value}
wishes=[{"slot":i,"title":"Canari souhait prive "+str(i),
    "url":"https://www.amazon.fr/dp/ARTICLE"+str(i),"price_eur_cents":4999,
    "currency":"EUR","price_date":timezone.localdate().isoformat(),"note":"",
    "exact_model":False,"equivalent_ok":True} for i in (1,2,3)]
url="http://127.0.0.1:8002/api/me/wishlist?event_id="+event_id
request=urllib.request.Request(url,data=json.dumps({"revision":0,"wishes":wishes}).encode(),
                               headers=headers,method="PUT")
with urllib.request.urlopen(request) as response:
    assert json.load(response)["revision"]==1
request=urllib.request.Request("http://127.0.0.1:8002/api/me/wishlist/validate?event_id="+event_id,
    data=b'{"revision":1}',headers=headers,method="POST")
with urllib.request.urlopen(request) as response:
    assert json.load(response)["state"]=="VALIDATED"
assert len(Membership.objects.filter(event_id=os.environ["SMOKE_EVENT_ID"]))==8
# Advance only this synthetic fixture's batching schedule, rather than waiting 15 minutes.
PrivateEvent.objects.filter(pk=os.environ["SMOKE_EVENT_ID"]).update(next_projection_at=timezone.now())
""",
            extra,
        )
        execute(
            "control",
            r"""
import django,os,time
django.setup()
from control_core.models import RosterProposal
deadline=time.monotonic()+30
while time.monotonic()<deadline:
    if RosterProposal.objects.filter(event_id=os.environ["SMOKE_EVENT_ID"],
            email=os.environ["SMOKE_EMAIL"],registration_confirmed=True,
            safeparticipantstatus__wishlist_complete=True).exists():
        break
    time.sleep(.2)
else:
    raise AssertionError("Safe status projection not received")
import json
from control_core.models import ControlCommand
assert "Canari souhait prive" not in json.dumps(list(
    ControlCommand.objects.filter(event_id=os.environ["SMOKE_EVENT_ID"]).values("payload")))
""",
            extra,
        )
        from phase5_smoke import run_draw_smoke

        run_draw_smoke(extra)
        from phase6_smoke import run_private_smoke

        run_private_smoke(extra)
    finally:
        if record.exists():
            extra["SMOKE_EVENT_ID"] = json.loads(record.read_text())["event_id"]
            execute(
                "vault",
                r"""
import django,os
django.setup()
from vault_core.models import PrivateEvent,VerifiedIdentity,SealedDraw
from allauth.usersessions.models import UserSession
SealedDraw.objects.filter(event_id=os.environ["SMOKE_EVENT_ID"]).delete()
PrivateEvent.objects.filter(pk=os.environ["SMOKE_EVENT_ID"]).delete()
for identity in VerifiedIdentity.objects.filter(email__startswith=os.environ["SMOKE_LABEL"]):
    for session in UserSession.objects.filter(user=identity.user):
        session.end()
    identity.user.delete()
""",
                extra,
            )
        execute(
            "control",
            r"""
import django,os
django.setup()
from control_core.models import EventDraft
from django.contrib.auth import get_user_model
from allauth.usersessions.models import UserSession
EventDraft.objects.filter(owner__user__email=os.environ["SMOKE_EMAIL"]).delete()
for actor in get_user_model().objects.filter(email=os.environ["SMOKE_EMAIL"]):
    for session in UserSession.objects.filter(user=actor):
        session.end()
    actor.delete()
""",
            extra,
        )
        record.unlink(missing_ok=True)
