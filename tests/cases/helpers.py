import os
import re
import time

from allauth.account.models import EmailAddress
from allauth.mfa import app_settings
from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
)
from django.contrib.auth import get_user_model
from django.core import mail


def user(email="person@example.invalid"):
    actor = get_user_model().objects.create_user(username=email, email=email)
    EmailAddress.objects.create(user=actor, email=email, verified=True, primary=True)
    return actor


def login_with_code(client, actor, mfa=False):
    secret = generate_totp_secret() if mfa else None
    if secret:
        TOTP.activate(actor, secret)
    response = client.post("/accounts/login/code/", {"email": actor.email})
    assert response.status_code == 302
    code = re.search(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", mail.outbox[-1].body).group()
    response = client.post("/accounts/login/code/confirm/", {"code": code})
    if secret:
        assert response.status_code == 302
        otp = format_hotp_value(hotp_value(secret, int(time.time()) // app_settings.TOTP_PERIOD))
        response = client.post("/accounts/2fa/authenticate/", {"code": otp})
    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(actor.pk)
    return client


def login_through_mailpit(client, actor):
    """Actual control outbox -> worker -> SMTP -> Mailpit, then genuine email/TOTP auth."""
    import json
    import time
    import urllib.request

    from django.conf import settings

    secret = generate_totp_secret()
    TOTP.activate(actor, secret)
    assert client.post("/accounts/login/code/", {"email": actor.email}).status_code == 302
    code = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not code:
        with urllib.request.urlopen(
            os.environ["NOEL_MAILPIT_URL"] + "/api/v1/messages"
        ) as response:
            messages = json.load(response)["messages"]
        for row in messages:
            if row["From"]["Address"] != settings.DEFAULT_FROM_EMAIL:
                continue
            if not any(address["Address"] == actor.email for address in row["To"]):
                continue
            with urllib.request.urlopen(
                os.environ["NOEL_MAILPIT_URL"] + "/api/v1/message/" + row["ID"]
            ) as response:
                body = json.load(response)["Text"]
            match = re.search(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", body)
            if match:
                code = match.group()
        if not code:
            time.sleep(0.2)
    assert code, "Authentication mail not received by local SMTP"
    assert client.post("/accounts/login/code/confirm/", {"code": code}).status_code == 302
    otp = format_hotp_value(hotp_value(secret, int(time.time()) // app_settings.TOTP_PERIOD))
    assert client.post("/accounts/2fa/authenticate/", {"code": otp}).status_code == 302
    assert client.session.get("_auth_user_id") == str(actor.id)
    return client
