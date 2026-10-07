"""Production in the container on Fly.io. Every host-specific value must be in the environment."""

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

for _name in ("SECRET_KEY", "ALLOWED_HOSTS", "SEED_ADMIN_PASSWORD"):
    if not globals().get(_name):
        raise ImproperlyConfigured(f"{_name} must be set in the environment")

# Fly terminates TLS and forwards the scheme in one trusted hop. force_https in fly.toml
# does the redirect at the edge, so Django does not redirect again.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# The domain is on the .dev HSTS preload list; the header restates what browsers already enforce.
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# W003: no cookies and no sessions, every request authenticates with a bearer token, so the
# CSRF middleware has nothing to protect. W008: Fly redirects to HTTPS at the edge.
SILENCED_SYSTEM_CHECKS = ["security.W003", "security.W008"]

SPA_DIR = env("SPA_DIR", "/app/spa")
WHITENOISE_ROOT = SPA_DIR
