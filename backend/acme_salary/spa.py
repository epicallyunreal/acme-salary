"""Catch-all view that returns the built React app's index.html (SPEC section 14).

WhiteNoise serves the files under SPA_DIR at the site root, and client-side routes such as
/employees/12 have no file, so they land here. Without a bundle (local development, where Vite
serves the app) the view is a plain 404.
"""

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse


def spa_index(request: HttpRequest) -> HttpResponse:
    spa_dir = getattr(settings, "SPA_DIR", None)
    if not spa_dir:
        raise Http404("No SPA bundle is configured")
    index = Path(spa_dir) / "index.html"
    if not index.is_file():
        raise Http404("The SPA bundle is missing")
    response = HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "max-age=60, public"
    return response
