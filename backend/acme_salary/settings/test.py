"""pytest settings: in-memory SQLite, fast password hashing, no SPA bundle."""

from .base import *

DEBUG = False
SECRET_KEY = TEST_ONLY_SECRET_KEY
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173"]
SEED_ADMIN_PASSWORD = "change-me"

DATABASES["default"]["NAME"] = ":memory:"
# WAL is a file-level journal; on an in-memory database the pragma is a no-op, so drop it rather
# than run a statement that means nothing.
DATABASES["default"]["OPTIONS"].pop("init_command")

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

SPA_DIR = None
WHITENOISE_ROOT = None
