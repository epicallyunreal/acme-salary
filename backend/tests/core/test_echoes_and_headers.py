"""Client values echoed in error text are clipped, and the frame header reaches every response
(D68, D73)."""

import pytest

pytestmark = pytest.mark.django_db

LONG = "x" * 300
CUT = "x" * 63 + "\u2026"


def test_an_unknown_country_code_is_echoed_clipped(api, lookups):
    components = api.get("/api/v1/meta/components/", {"country": LONG})
    template = api.get("/api/v1/imports/template/", {"country": LONG})

    assert (components.status_code, components.json()["detail"]) == (
        404,
        f"Unknown country_code: {CUT}",
    )
    assert (template.status_code, template.json()["detail"]) == (
        404,
        f"Unknown country_code: {CUT.upper()}",
    )


@pytest.mark.parametrize("field", ["status", "ordering", "level"])
def test_an_invalid_filter_choice_is_echoed_clipped(api, lookups, field):
    response = api.get("/api/v1/employees/", {field: LONG})

    assert response.status_code == 400
    assert response.json()[field] == [
        f"Select a valid choice. {CUT} is not one of the available choices."
    ]


def test_the_json_export_echoes_its_filters_clipped_value_by_value(api, lookups):
    """A long list of real codes is recorded whole; one long value is cut on its own."""
    departments = ",".join(
        ["engineering", "sales", "marketing", "finance", "operations", "legal", "hr", "product"]
    )
    response = api.get(
        "/api/v1/exports/employees/",
        {"file": "json", "country": LONG, "department": departments},
    )

    assert response.status_code == 200
    assert response.json()["filters"]["country"] == CUT
    assert response.json()["filters"]["department"] == departments


def test_the_frame_header_sits_above_whitenoise_and_reaches_a_static_file(anon, settings, tmp_path):
    """Above WhiteNoise, so a file it serves carries X-Frame-Options as the API does (D73)."""
    order = settings.MIDDLEWARE
    frame = order.index("django.middleware.clickjacking.XFrameOptionsMiddleware")
    static = order.index("whitenoise.middleware.WhiteNoiseMiddleware")
    assert frame < static
    (tmp_path / "hello.txt").write_text("hello", encoding="utf-8")
    settings.WHITENOISE_ROOT = str(tmp_path)

    served = anon.get("/hello.txt")

    assert (served.status_code, served["X-Frame-Options"]) == (200, "DENY")
    assert anon.get("/healthz")["X-Frame-Options"] == "DENY"
