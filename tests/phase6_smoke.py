"""Private HTTP, real durability release and complete portal-dump boundary check."""

from phase3_smoke import execute


def run_private_smoke(extra):
    execute(
        "vault",
        r"""
import django,os,sys,json,urllib.request
from pathlib import Path
django.setup()
sys.path.insert(0,str(Path.cwd()/"scripts"))
import tasks
from django.conf import settings
from django.test import Client
from django.utils import timezone
from vault_core.durability import backup_and_verify
from noel_operations import initialize_journal
from cryptography.fernet import Fernet
import tempfile
os.environ.update(OPERATIONS_DIRECTORY=tempfile.mkdtemp(prefix="noel-smoke-journal-"),
                  OPERATIONS_KEY=Fernet.generate_key().decode())
initialize_journal()
from vault_core.models import Membership,PrivateEvent
values=tasks.config()
os.environ.update(BACKUP_ENCRYPTION_KEY=values["VAULT_BACKUP_KEY"],BACKUP_DB_USER="noel_admin",
    BACKUP_DB_PASSWORD=values["VAULT_DB_ADMIN_PASSWORD"],
    PG_BIN=str(tasks.ROOT/".local/tools/postgresql/pgsql/bin"))
backup_and_verify(os.environ["SMOKE_EVENT_ID"],tasks.LOCAL/"smoke-backups")
member=Membership.objects.get(event_id=os.environ["SMOKE_EVENT_ID"],identity__email=os.environ["SMOKE_EMAIL"])
client=Client()
client.force_login(member.identity.user)
assert client.get("/private?event_id="+str(member.event_id)).status_code==200
cookie="; ".join(key+"="+value.value for key,value in client.cookies.items())
headers={"Content-Type":"application/json","Cookie":cookie,
         "X-CSRFToken":client.cookies[settings.CSRF_COOKIE_NAME].value}
def request(path,method="GET",data=None):
    req=urllib.request.Request("http://127.0.0.1:8002/api/me/"+path+"?event_id="+str(member.event_id),
        data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
    with urllib.request.urlopen(req) as response:
        assert response.headers["Cache-Control"]=="no-store"
        assert response.headers["Referrer-Policy"]=="no-referrer"
        return json.load(response)
value=request("recipient")
member.refresh_from_db()
assert not member.recipient_viewed
assert request("recipient/reveal","POST",{})==value
note="PRIVATE_PURCHASE_"+os.environ["SMOKE_LABEL"]
body={"revision":0,"state":"READY","wish_id":value["wishes"][0]["id"],
      "wish_revision":value["revision"],"note":note}
assert request("purchase","PUT",body)["state"]=="READY"
record_path=Path(os.environ["SMOKE_RECORD"])
record=json.loads(record_path.read_text())
record["private_wish_id"]=body["wish_id"]
record_path.write_text(json.dumps(record))
# Force only this synthetic fixture's periodic schedule for a bounded smoke duration.
PrivateEvent.objects.filter(pk=member.event_id).update(next_projection_at=timezone.now())
""",
        extra,
    )
    execute(
        "control",
        r"""
import django,os,sys,time,json,subprocess
from pathlib import Path
django.setup()
sys.path.insert(0,str(Path.cwd()/"scripts"))
import tasks
from control_core.models import EventDraft,RosterProposal
end=time.monotonic()+30
while time.monotonic()<end:
    event=EventDraft.objects.get(pk=os.environ["SMOKE_EVENT_ID"])
    if event.ready_count==1 and RosterProposal.objects.filter(event=event,
            email=os.environ["SMOKE_EMAIL"],safeparticipantstatus__recipient_viewed=True).exists():
        break
    time.sleep(.2)
else:
    raise AssertionError("Private safe aggregates not projected")
values=tasks.config()
env=os.environ.copy()
env.update(PGHOST="127.0.0.1",PGPORT=str(tasks.DB_PORTS["control"]),PGDATABASE="noel_control",
    PGUSER="noel_admin",PGPASSWORD=values["CONTROL_DB_ADMIN_PASSWORD"])
dump=subprocess.run([tasks.executable("pg_dump"),"--format=plain"],env=env,
                    capture_output=True,check=True).stdout
record=json.loads(Path(os.environ["SMOKE_RECORD"]).read_text())
for canary in ("PRIVATE_PURCHASE_"+os.environ["SMOKE_LABEL"],record["private_wish_id"],
               "Canari cadeau privé", "Canari souhait prive"):
    assert canary.encode() not in dump,"Private canary crossed portal boundary"
""",
        extra,
    )
