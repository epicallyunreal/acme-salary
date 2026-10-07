"""WSGI entry point used by gunicorn in the container."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "acme_salary.settings.prod")

application = get_wsgi_application()
