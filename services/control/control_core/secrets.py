from cryptography.fernet import Fernet
from django.conf import settings


def encrypt(value):
    return Fernet(settings.AUTH_DATA_KEY.encode()).encrypt(value.encode()).decode()


def decrypt(value):
    return Fernet(settings.AUTH_DATA_KEY.encode()).decrypt(value.encode()).decode()


def cache_key(key, key_prefix, version):
    import hashlib
    import hmac

    raw = f"{key_prefix}:{version}:{key}".encode()
    return hmac.new(settings.AUTH_DATA_KEY.encode(), raw, hashlib.sha256).hexdigest()
