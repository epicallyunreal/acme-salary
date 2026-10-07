"""Local development: permissive defaults so `manage.py runserver` works with no .env."""

from .base import *

DEBUG = env_bool("DEBUG", True)
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key-do-not-deploy"
ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or ["http://localhost:5173"]
CSRF_TRUSTED_ORIGINS = CSRF_TRUSTED_ORIGINS or ["http://localhost:5173"]
SEED_ADMIN_PASSWORD = SEED_ADMIN_PASSWORD or "change-me"
