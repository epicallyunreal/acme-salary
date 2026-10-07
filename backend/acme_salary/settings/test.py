"""pytest settings: in-memory SQLite, fast password hashing, no SPA bundle."""

from .base import *

DEBUG = False
SECRET_KEY = "test-only-key"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173"]
SEED_ADMIN_PASSWORD = "change-me"

DATABASES["default"]["NAME"] = ":memory:"
DATABASES["default"]["OPTIONS"].pop("init_command")

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

SPA_DIR = None
WHITENOISE_ROOT = None
