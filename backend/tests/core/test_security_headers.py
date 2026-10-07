"""The Content-Security-Policy header (D38) on API and page responses."""

import pytest

pytestmark = pytest.mark.django_db

EXPECTED = {
    "default-src 'self'",
    "script-src 'self'",
    "connect-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "frame-ancestors 'none'",
    "object-src 'none'",
}


def directives(response) -> set[str]:
    return {part.strip() for part in response["Content-Security-Policy"].split(";") if part.strip()}


def test_api_responses_carry_the_policy(api):
    assert directives(api.get("/api/v1/auth/me/")) == EXPECTED


def test_the_health_check_and_the_spa_carry_the_policy(client):
    assert directives(client.get("/healthz")) == EXPECTED
    assert directives(client.get("/employees/12")) == EXPECTED
