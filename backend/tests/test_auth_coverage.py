"""Every route under /api/v1/ answers 401 without a token, except login and refresh (SPEC F8).

The test walks the URL resolver, so an endpoint added without authentication fails here, not in a
review.
"""

import re

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

pytestmark = pytest.mark.django_db

PUBLIC = {"api/v1/auth/login/", "api/v1/auth/refresh/"}
CONVERTER = re.compile(r"<(?:(?P<converter>[^>:]+):)?(?P<name>[^>]+)>")


def api_routes() -> list[str]:
    found: list[str] = []

    def walk(patterns, prefix: str) -> None:
        for entry in patterns:
            route = prefix + str(entry.pattern)
            if isinstance(entry, URLResolver):
                walk(entry.url_patterns, route)
            elif isinstance(entry, URLPattern) and route.startswith("api/v1/"):
                found.append(route)

    walk(get_resolver().url_patterns, "")
    return sorted(found)


def concrete(route: str) -> str:
    def fill(match: re.Match) -> str:
        return "1" if match.group("converter") == "int" else "x"

    return "/" + CONVERTER.sub(fill, route)


def test_the_route_list_is_what_the_step_expects():
    assert api_routes() == [
        "api/v1/auth/login/",
        "api/v1/auth/logout/",
        "api/v1/auth/me/",
        "api/v1/auth/refresh/",
        "api/v1/compensation/<int:pk>/",
        "api/v1/employees/",
        "api/v1/employees/<int:pk>/",
        "api/v1/employees/<int:pk>/audit/",
        "api/v1/employees/<int:pk>/compensation/",
        "api/v1/employees/<int:pk>/exit/",
        "api/v1/imports/",
        "api/v1/imports/<int:pk>/",
        "api/v1/imports/<int:pk>/rows/",
        "api/v1/imports/template/",
        "api/v1/meta/components/",
        "api/v1/meta/countries/",
        "api/v1/meta/departments/",
        "api/v1/meta/exchange-rates/",
    ]


@pytest.mark.parametrize("route", [r for r in api_routes() if r not in PUBLIC])
def test_protected_routes_answer_401_without_a_token(anon, route):
    for method in ("get", "post", "patch", "delete"):
        response = getattr(anon, method)(concrete(route))
        assert response.status_code == 401, (route, method, response.status_code)


@pytest.mark.parametrize("route", sorted(PUBLIC))
def test_public_routes_do_not_demand_a_token(anon, route):
    response = anon.post(concrete(route), {}, format="json")

    assert response.status_code == 400
