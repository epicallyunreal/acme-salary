"""Production in the container on Fly.io. Every host-specific value must be in the environment."""

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

for _name in ("SECRET_KEY", "ALLOWED_HOSTS", "SEED_ADMIN_PASSWORD"):
    if not globals().get(_name):
        raise ImproperlyConfigured(f"{_name} must be set in the environment")
# Without it, or relative, the database would land on the machine's ephemeral root filesystem
# (D73).
if not (env("DATABASE_PATH") or "").startswith("/"):
    raise ImproperlyConfigured("DATABASE_PATH must be set in the environment, as an absolute path")

# A copied-but-unedited .env.example must not boot in production: the key signs every JWT.
PLACEHOLDERS = {
    "replace-with-a-long-random-string",
    "change-me",
    "dev-only-insecure-key-do-not-deploy",
    TEST_ONLY_SECRET_KEY,
}
if SECRET_KEY in PLACEHOLDERS or len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5:
    raise ImproperlyConfigured(
        "SECRET_KEY must be at least 50 random characters, not a placeholder"
    )
if SEED_ADMIN_PASSWORD in PLACEHOLDERS:
    raise ImproperlyConfigured("SEED_ADMIN_PASSWORD must not be the example value")

# Fly terminates TLS and forwards the scheme in one trusted hop. force_https in fly.toml
# does the redirect at the edge, so Django does not redirect again.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
# W003: no cookies and no sessions, every request authenticates with a bearer token, so the
# CSRF middleware has nothing to protect. W004: the .dev zone is on the browsers' HSTS preload
# list, so the header would restate what they already enforce. W008: Fly redirects to HTTPS at
# the edge.
SILENCED_SYSTEM_CHECKS = ["security.W003", "security.W004", "security.W008"]

SPA_DIR = env("SPA_DIR", "/app/spa")
WHITENOISE_ROOT = SPA_DIR
