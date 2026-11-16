from django.contrib.sessions.backends.db import SessionStore as DatabaseSession

from .secrets import decrypt, encrypt


class SessionStore(DatabaseSession):
    def encode(self, session_dict):
        return encrypt(super().encode(session_dict))

    def decode(self, session_data):
        try:
            return super().decode(decrypt(session_data))
        except Exception:
            return {}
