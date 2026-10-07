"""Response headers the settings cannot express per path."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class NoStoreApiMiddleware:
    """`Cache-Control: no-store` on every /api/ response, so salary data never sits in a browser's
    disk cache on a shared machine. Pages and assets keep WhiteNoise's caching."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
