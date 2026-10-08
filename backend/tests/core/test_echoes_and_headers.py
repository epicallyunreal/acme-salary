"""Client values echoed in error text are clipped, and the frame header reaches every response
(D68, D73)."""

import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db

LONG = "x" * 300


def test_an_unknown_country_code_is_echoed_clipped(api, lookups):
    components = api.get("/api/v1/meta/components/", {"country": LONG})
    template = api.get("/api/v1/imports/template/", {"country": LONG})

    for response in (components, template):
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail.lower().startswith("unknown country_code: " + "x" * 10)
        assert detail.endswith("\u2026") and len(detail) < 100


def test_an_invalid_filter_choice_is_echoed_clipped(api, lookups):
    response = api.get("/api/v1/employees/", {"status": LONG})

    assert response.status_code == 400
    (message,) = response.json()["status"]
    assert "is not one of the available choices" in message
    assert "\u2026" in message and len(message) < 160


def test_the_json_export_echoes_its_filters_clipped(api, lookups):
    response = api.get("/api/v1/exports/employees/", {"file": "json", "country": LONG})

    assert response.status_code == 200
    country = response.json()["filters"]["country"]
    assert country.endswith("\u2026") and len(country) == 64


def test_the_frame_header_sits_above_whitenoise_and_reaches_the_api(anon):
    """Above WhiteNoise, so a static file carries X-Frame-Options as the API does."""
    order = settings.MIDDLEWARE
    frame = order.index("django.middleware.clickjacking.XFrameOptionsMiddleware")
    static = order.index("whitenoise.middleware.WhiteNoiseMiddleware")

    assert frame < static
    assert anon.get("/healthz")["X-Frame-Options"] == "DENY"
