"""GET /api/v1/insights/<name>/ over HTTP (SPEC section 8), with its query counts pinned."""

import pytest

from tests.insights.fixture import build_fixture

pytestmark = pytest.mark.django_db

URL = "/api/v1/insights/{}/"


@pytest.fixture
def people(lookups):
    return build_fixture()


def test_an_insight_answers_with_its_figures_as_text(api, people):
    response = api.get(URL.format("summary"), {"currency": "eur"})

    assert (response.status_code, response.json()) == (
        200,
        {
            "currency": "EUR",
            "rate_month": {"label": "October 2026 rates", "effective_from": "2026-10-01"},
            "headcount": 27,
            "total_cost": "1948360.00",
            "mean_gross": "64370.37",
            "median_gross": "60000.00",
            "countries": 4,
            "departments": 4,
        },
    )


def test_every_filter_reaches_the_query(api, people):
    response = api.get(
        URL.format("by-country"),
        {
            "country": "IN",
            "department": "customer-support",
            "include_exited": "true",
            "on": "2026-10-07",
        },
    )

    assert response.json()["rows"] == [
        {
            "country": {"code": "IN", "name": "India"},
            "headcount": 7,
            "total_cost": "217000.00",
            "median_gross": "30000.00",
            "share_pct": "100.0",
        }
    ]


@pytest.mark.parametrize(
    ("name", "queries"),
    [
        ("summary", 6),
        ("by-country", 6),
        ("by-department", 6),
        ("distribution", 5),
        ("by-level", 5),
        ("gender-gap", 5),
        ("trend", 5),
        ("cost-bridge", 5),
    ],
)
def test_an_insight_runs_a_fixed_number_of_queries(
    api, people, django_assert_num_queries, name, queries
):
    """The user, the countries, the departments, the rates, then one aggregate and one list of
    gross values, or the list alone, whatever the population."""
    with django_assert_num_queries(queries):
        response = api.get(URL.format(name))

    assert response.status_code == 200


def test_on_reaches_the_query(api, people):
    """The frozen today would hide a view that ignores `on`; on 2027-01-01 D5 has joined and U1's
    revision is current (DESIGN section 9)."""
    response = api.get(URL.format("summary"), {"on": "2027-01-01"})

    assert (response.json()["headcount"], response.json()["total_cost"]) == (28, "2618450.00")


def test_an_unknown_insight_is_a_404(api, people):
    response = api.get(URL.format("top-earners"))

    assert (response.status_code, response.json()) == (404, {"detail": "Not found."})


def test_an_insight_needs_a_signed_in_user(anon, people):
    response = anon.get(URL.format("summary"))

    assert (response.status_code, response.json()) == (
        401,
        {"detail": "Authentication credentials were not provided."},
    )


@pytest.mark.parametrize(
    ("params", "errors"),
    [
        ({"country": "XX"}, {"country": ["Unknown country_code: XX"]}),
        ({"department": "growth"}, {"department": ["Unknown department: growth"]}),
        (
            {"currency": "local"},
            {"currency": ["currency=local needs exactly one country in the filter"]},
        ),
        ({"currency": "gbp"}, {"currency": ["currency must be usd, eur or local, got gbp"]}),
        ({"on": "07/10/2026"}, {"on": ["on must be a date in YYYY-MM-DD form, got 07/10/2026"]}),
        (
            {"currency": "g" * 1000},
            {"currency": [f"currency must be usd, eur or local, got {'g' * 63}\u2026"]},
        ),
        ({"include_exited": "maybe"}, {"include_exited": ["include_exited must be true or false"]}),
    ],
)
def test_a_filter_that_names_nothing_is_a_400(api, people, params, errors):
    response = api.get(URL.format("summary"), params)

    assert (response.status_code, response.json()) == (400, errors)


# Card controls (D62)


@pytest.mark.parametrize(
    ("given", "measure"), [({}, "total_cost"), ({"measure": "headcount"}, "headcount")]
)
def test_trend_names_the_measure_its_card_draws(api, people, given, measure):
    response = api.get(URL.format("trend"), given)

    assert (response.status_code, response.json()["measure"]) == (200, measure)


def test_a_control_value_outside_its_list_is_a_400(api, people):
    response = api.get(URL.format("trend"), {"measure": "salary"})

    assert (response.status_code, response.json()) == (
        400,
        {"measure": ["measure must be total_cost or headcount, got salary"]},
    )
