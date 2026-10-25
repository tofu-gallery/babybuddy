# Tofu (2026-10-25): this file is Tofu's addition; it is not part of upstream Baby Buddy.
#
# Settings for Tofu's app gallery copy of Baby Buddy (see TOFU.md at the repository root). The image sets
# DJANGO_SETTINGS_MODULE=babybuddy.settings.tofu. Where base.py reads an environment variable, a value the
# owner saves on the app's Keys & settings page still wins over the defaults below.
import hashlib
import os

from .base import *

# Tofu serves the copy over HTTPS at its own address, through Tofu's proxy, which sets X-Forwarded-Proto and
# X-Forwarded-Host. Reading them lets Django's CSRF check compare a form's Origin with the address the visitor
# used, which is the copy's Tofu address or a domain connected later.
if not os.environ.get("ALLOWED_HOSTS"):
    ALLOWED_HOSTS = ["*"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = bool(
    strtobool(os.environ.get("SESSION_COOKIE_SECURE") or "True")
)
CSRF_COOKIE_SECURE = bool(strtobool(os.environ.get("CSRF_COOKIE_SECURE") or "True"))

if os.environ.get("DATABASE_URL"):
    # Tofu's DATABASE_URL goes through a transaction pooler, which keeps no server-side cursors between
    # statements. Connections are kept for a minute and checked before reuse, so a request does not open a
    # new TLS connection to the pooler every time.
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
    DATABASES["default"]["CONN_MAX_AGE"] = 60
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

    # Tofu supplies no SECRET_KEY, so a copy derives one from DATABASE_URL, which Tofu keeps as a hidden
    # value. Changing DATABASE_URL later changes this key: everyone is signed out and unused password reset
    # links stop working. A SECRET_KEY the owner saves as a hidden value always wins.
    if not SECRET_KEY:
        SECRET_KEY = hashlib.sha256(
            ("baby-buddy-secret-key:" + os.environ["DATABASE_URL"]).encode()
        ).hexdigest()

# A copy has no lasting disk: an uploaded child photo would be lost at the next restart, and nothing serves
# MEDIA_ROOT outside DEBUG. Uploads stay off unless the owner sets ALLOW_UPLOADS=true together with a storage
# bucket (AWS_STORAGE_BUCKET_NAME and its keys, read by base.py).
BABY_BUDDY["ALLOW_UPLOADS"] = bool(
    strtobool(os.environ.get("ALLOW_UPLOADS") or "False")
)

# No admin/admin account: while the copy has no account at all, the login page asks for the first one, which
# becomes the administrator (babybuddy/first_account.py).
BABY_BUDDY["FIRST_ACCOUNT_SETUP"] = True

# Django's warnings and errors go to the app's runtime log (standard error), where the owner can read them on
# Tofu. Upstream keeps Django's default logging, which with DEBUG off only mails a request's error (a 500 and
# its traceback) to ADMINS, and a copy has none, so the log showed nothing about it. Warnings include a form
# refused by the CSRF check, with the reason, and a page not found.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django": {"handlers": ["console"], "level": "WARNING"}},
}
