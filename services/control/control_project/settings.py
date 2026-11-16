import os
from base64 import urlsafe_b64decode
from pathlib import Path

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
APP_ENV = os.environ.get("APP_ENV")
SERVICE_ROLE = os.environ.get("SERVICE_ROLE")
if APP_ENV not in {"local", "staging", "production"} or SERVICE_ROLE != "control":
    raise ImproperlyConfigured("Invalid environment or service role")
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY requires at least 50 characters")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
if APP_ENV != "local" and DEBUG:
    raise ImproperlyConfigured("Debug forbidden outside local")
if os.environ.get("ENABLE_SYNTHETIC_DIAGNOSTICS", "false").lower() != "false":
    raise ImproperlyConfigured("Synthetic diagnostics not installed")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Explicit ALLOWED_HOSTS required")
if any(not os.environ.get(k) for k in ("DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST")):
    raise ImproperlyConfigured("Incomplete database configuration")
try:
    DB_CONN_MAX_AGE = int(os.environ.get("DB_CONN_MAX_AGE", "60"))
    if not 0 <= DB_CONN_MAX_AGE <= 300:
        raise ValueError()
except ValueError:
    raise ImproperlyConfigured("DB_CONN_MAX_AGE must be an integer from 0 to 300") from None
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ["DB_HOST"],
        "PORT": os.environ.get("DB_PORT", "5432"),
        "OPTIONS": {"connect_timeout": 5, "sslmode": os.environ.get("DB_SSLMODE", "prefer")},
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
        "CONN_HEALTH_CHECKS": True,
    }
}
if APP_ENV != "local" and DATABASES["default"]["OPTIONS"]["sslmode"] != "verify-full":
    raise ImproperlyConfigured("Nonlocal PostgreSQL requires verify-full TLS")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "control_core",
    "django.contrib.humanize",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.usersessions",
]
MIDDLEWARE = [
    "noel_operations.MaintenanceMiddleware",
    "control_core.middleware.SerializeAuthentication",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "control_core.middleware.PrivacyHeaders",
]
ROOT_URLCONF = "control_project.urls"
WSGI_APPLICATION = "control_project.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "fr"
TIME_ZONE = "UTC"
USE_TZ = True
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "assets"] if (BASE_DIR / "assets").exists() else []
SESSION_COOKIE_NAME = "noel_control_session"
CSRF_COOKIE_NAME = "noel_control_csrf"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = APP_ENV != "local"
CSRF_COOKIE_SECURE = APP_ENV != "local"
SECURE_SSL_REDIRECT = APP_ENV != "local"
SECURE_HSTS_SECONDS = 31536000 if APP_ENV != "local" else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = APP_ENV != "local"
SECURE_HSTS_PRELOAD = APP_ENV != "local"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"
X_FRAME_OPTIONS = "DENY"
# Only trust an independently operated proxy that removes spoofed forwarded headers.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if APP_ENV != "local" else None
# A fail-closed email backend until the phase-7 adapter exists. Never silently discard.
EMAIL_BACKEND = "control_core.mail.DisabledBackend"
if APP_ENV == "local":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = "127.0.0.1"
    EMAIL_PORT = int(os.environ.get("MAILPIT_SMTP_PORT", "11025"))
DEFAULT_FROM_EMAIL = "simulation@noel.invalid"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"safe": {"class": "logging.StreamHandler", "formatter": "safe"}},
    "formatters": {"safe": {"()": "control_core.logging.SafeFormatter"}},
    "root": {"handlers": ["safe"], "level": "INFO"},
    "loggers": {"django": {"handlers": ["safe"], "propagate": False, "level": "WARNING"}},
}

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = True
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_TIMEOUT = 600
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_MAX_ATTEMPTS = 5
ACCOUNT_LOGIN_BY_CODE_ENABLED = True
ACCOUNT_LOGIN_BY_CODE_TIMEOUT = 600
ACCOUNT_LOGIN_BY_CODE_MAX_ATTEMPTS = 5
ACCOUNT_LOGIN_BY_CODE_SUPPORTS_RESEND = 2
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_CONFIRM_EMAIL_ON_GET = False
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
ACCOUNT_EMAIL_NOTIFICATIONS = True
ACCOUNT_CHANGE_EMAIL = True
ACCOUNT_SESSION_REMEMBER = False
SESSION_COOKIE_AGE = 43200
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
ACCOUNT_RATE_LIMITS = {"request_login_code": "60/m/ip,3/m/key", "login": "60/m/ip"}
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes", "webauthn"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = APP_ENV == "local"
MFA_TOTP_ISSUER = "Noël Secret"
MFA_REAUTHENTICATION_REQUIRED = True
USERSESSIONS_TRACK_ACTIVITY = False
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_ADAPTER = "control_core.adapters.AccountAdapter"
MFA_ADAPTER = "control_core.adapters.MFAAdapter"
SESSION_ENGINE = "control_core.sessions"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "auth_rate_cache",
        "KEY_FUNCTION": "control_core.secrets.cache_key",
    }
}
AUTH_DATA_KEY = os.environ.get("AUTH_DATA_KEY", "")

try:
    Fernet(AUTH_DATA_KEY.encode())
except (ValueError, TypeError):
    raise ImproperlyConfigured("Valid independent AUTH_DATA_KEY required") from None
COMMAND_KEY = os.environ.get("COMMAND_KEY", "")
if not COMMAND_KEY:
    raise ImproperlyConfigured("Command signing/verification key required")
PUBLIC_ORIGIN = os.environ.get("PUBLIC_ORIGIN", "")
VAULT_ORIGIN = os.environ.get("VAULT_ORIGIN", "")
if APP_ENV != "local" and not PUBLIC_ORIGIN.startswith("https://"):
    raise ImproperlyConfigured("Independent HTTPS origin required")

EMAIL_TIMEOUT = 10

PROJECTION_KEY = os.environ.get("PROJECTION_KEY", "")
CONTROL_ORIGIN = os.environ.get("CONTROL_ORIGIN", "")

ACCOUNT_REAUTHENTICATION_REQUIRED = True

# Key material and trust destinations are checked before any request is served.
try:
    if len(urlsafe_b64decode(COMMAND_KEY)) != 32 or len(urlsafe_b64decode(PROJECTION_KEY)) != 32:
        raise ValueError()
except (ValueError, TypeError):
    raise ImproperlyConfigured("Invalid service signing key material") from None
if APP_ENV != "local" and (
    not VAULT_ORIGIN.startswith("https://") or not CONTROL_ORIGIN.startswith("https://")
):
    raise ImproperlyConfigured("Independent HTTPS service origins required")

MFA_RECOVERY_CODES_SHOW_ONCE = True

ACCOUNT_RATE_LIMITS.update(invite_open="10/h/user,30/h/ip", invite_correction="30/h/user,60/h/ip")

CSRF_FAILURE_VIEW = "control_core.views.csrf_failure"
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[Noël Secret] "

# Credentials/senders are independent per service. Missing live configuration fails closed.
MAIL_PROVIDER = os.environ.get("MAIL_PROVIDER", "mailpit" if APP_ENV == "local" else "blocked")
MAIL_LIVE_ENABLED = os.environ.get("MAIL_LIVE_ENABLED") == "true"
MAIL_DNS_VERIFIED = os.environ.get("MAIL_DNS_VERIFIED") == "true"
MAIL_TRACKING_DISABLED = os.environ.get("MAIL_TRACKING_DISABLED") == "true"
MAIL_TEST_RECIPIENTS = {
    email.strip().casefold()
    for email in os.environ.get("MAIL_TEST_RECIPIENTS", "").split(",")
    if email.strip()
}
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_WEBHOOK_SECRET = os.environ.get("RESEND_WEBHOOK_SECRET", "")
RESEND_DOMAIN_ID = os.environ.get("RESEND_DOMAIN_ID", "")
DEFAULT_FROM_EMAIL = os.environ.get("NOTIFICATION_FROM_EMAIL", "simulation@noel.invalid")
if APP_ENV == "local" or (MAIL_PROVIDER in {"resend", "zoho"} and MAIL_LIVE_ENABLED):
    EMAIL_BACKEND = "control_core.mail.OutboxBackend"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.zoho.eu")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "true") == "true"
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "false") == "true"

TEMPLATES[0]["OPTIONS"]["context_processors"].append("noel_ui.context")

if os.environ.get("FORCE_MAINTENANCE", "false") not in {"true", "false"}:
    raise ImproperlyConfigured("FORCE_MAINTENANCE must be true or false")
FORCE_MAINTENANCE = os.environ.get("FORCE_MAINTENANCE", "false") == "true"
