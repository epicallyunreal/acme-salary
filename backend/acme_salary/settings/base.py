"""Settings shared by every environment. dev, prod and test override a few names.

Everything secret or host-specific comes from the environment (CLAUDE.md rule 10).
"""

import os
from datetime import timedelta
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parents[2]


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return default if value in (None, "") else value


def env_bool(name: str, default: bool) -> bool:
    raw = env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = env(name)
    if raw is None:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = env("SECRET_KEY")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "apps.accounts",
    "apps.core",
    "apps.employees",
    "apps.compensation",
    "apps.imports",
    "apps.insights",
    "apps.exports",
    "apps.audit",
    "apps.demo",
    "seed",
]

# No sessions and no Django auth middleware: the API authenticates with a JWT per request.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "apps.core.middleware.NoStoreApiMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "acme_salary.urls"
WSGI_APPLICATION = "acme_salary.wsgi.application"
TEMPLATES: list[dict] = []

# SQLite on a volume. Writers wait rather than fail during a long import approve (SPEC section 13).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL;",
            "timeout": 20,
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
# Applied to SEED_ADMIN_PASSWORD by seed_data. The minimum length stays at Django's eight so the
# spec's development default `change-me` is valid; production refuses placeholders in prod.py.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# WhiteNoise serves the built SPA from SPA_DIR at the site root. Django has no static files of
# its own, so there is no collectstatic and STATIC_URL only satisfies the middleware.
STATIC_URL = "/static/"
SPA_DIR = env("SPA_DIR")
WHITENOISE_ROOT = SPA_DIR
WHITENOISE_MAX_AGE = 60


def immutable_asset(path: str, url: str) -> bool:
    """Vite hashes every file under /assets/, so those get the one-year cache."""
    return url.startswith("/assets/")


WHITENOISE_IMMUTABLE_FILE_TEST = immutable_asset

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Content Security Policy (owner's directives at the step 1 close, D38). The refresh token lives
# in localStorage (D21), so a script injection is the threat this answers. style-src needs
# 'unsafe-inline' because MUI's Emotion injects styles at runtime.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "frame-ancestors": [CSP.NONE],
    "object-src": [CSP.NONE],
    # Neither falls back to default-src.
    "base-uri": [CSP.NONE],
    "form-action": [CSP.SELF],
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.handler",
    "DEFAULT_THROTTLE_RATES": {"login": "5/min", "reset": "5/hour"},
    # Fly's proxy is the one trusted hop, so a client cannot mint throttle buckets.
    "NUM_PROXIES": 1,
    "COERCE_DECIMAL_TO_STRING": True,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=12),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Keeps the session's end across rotations and revokes on reuse (SPEC F8, D21).
    "TOKEN_REFRESH_SERIALIZER": "apps.accounts.serializers.SessionRefreshSerializer",
}

# One gunicorn worker, so the in-process cache is shared by every thread and the login
# throttle counts correctly.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

SEED_ADMIN_PASSWORD = env("SEED_ADMIN_PASSWORD")

# The Demo data page's committed base file (F9, D72): the repository's folder locally, a copy in
# the image on Fly.
SAMPLE_DATA_DIR = env("SAMPLE_DATA_DIR", str(BASE_DIR.parent / "sample-data"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"level": "WARNING"}},
}
