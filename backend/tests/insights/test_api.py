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
            "from": "2025-10-08",
            "to": "2026-10-07",
            "currency": "EUR",
            "rate_month": {"label": "October 2026 rates", "effective_from": "2026-10-01"},
            "headcount": 27,
            "total_cost": "1948360.00",
            "mean_gross": "64370.37",
            "median_gross": "60000.00",
            "countries": 4,
            "departments": 4,
            # The 27 for all 365 days of the period, 1,948,360, their annual cost, and X1 until
            # 30 June, 266 days of 105,600, 76,957.8082: 2,025,317.8082, quantised once (D64, D69).
            "spent": {"headcount": 28, "total_cost": "2025317.81"},
        },
    )


def test_every_filter_reaches_the_query(api, people):
    response = api.get(
        URL.format("by-country"),
        {
            "country": "IN",
            "department": "customer-support",
            "include_exited": "true",
            "to": "2026-10-07",
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
        ("summary", 7),
        ("by-country", 6),
        ("by-department", 6),
        ("distribution", 5),
        ("by-level", 5),
        ("gender-gap", 5),
        ("trend", 5),
        ("cost-bridge", 5),
        ("by-tenure", 5),
        ("cost-mix", 6),
    ],
)
def test_an_insight_runs_a_fixed_number_of_queries(
    api, people, django_assert_num_queries, name, queries
):
    """The user, the countries, the departments, the rates, then one aggregate and one list of
    gross values, or the list alone, whatever the population. The summary reads the period's
    spans as well, for its spend (D64)."""
    with django_assert_num_queries(queries):
        response = api.get(URL.format(name))

    assert response.status_code == 200


def test_to_reaches_the_query(api, people):
    """The frozen today would hide a view that ignores `to`; on 2027-01-01 D5 has joined and U1's
    revision is current (DESIGN section 9, D64)."""
    response = api.get(URL.format("summary"), {"to": "2027-01-01"})

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
        ({"to": "07/10/2026"}, {"to": ["to must be a date in YYYY-MM-DD form, got 07/10/2026"]}),
        ({"from": "2020-03-31"}, {"from": ["from must be on or after 2020-04-01, got 2020-03-31"]}),
        ({"to": "2101-01-01"}, {"to": ["to must be on or before 2100-12-31, got 2101-01-01"]}),
        ({"from": "2026-10-08"}, {"from": ["from must be on or before to"]}),
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


@pytest.mark.parametrize("name", ["trend", "cost-bridge"])
def test_a_period_before_the_cut_off_is_a_400_where_the_dates_reach_back(api, lookups, name):
    """D70: the period starts no earlier than the reporting cut-off, 1 April 2020, and a `to`
    within a year of it does not pull the default `from` before it."""
    response = api.get(URL.format(name), {"from": "0001-01-01"})

    assert (response.status_code, response.json()) == (
        400,
        {"from": ["from must be on or after 2020-04-01, got 0001-01-01"]},
    )
    early = api.get(URL.format(name), {"to": "2020-06-30"})
    assert (early.status_code, early.json()["from"]) == (200, "2020-04-01")


# Card controls (D62)


@pytest.mark.parametrize(
    ("given", "measure"), [({}, "total_cost"), ({"measure": "headcount"}, "headcount")]
)
def test_trend_names_the_measure_its_card_draws(api, people, given, measure):
    response = api.get(URL.format("trend"), given)

    assert (response.status_code, response.json()["measure"]) == (200, measure)


@pytest.mark.parametrize(
    ("name", "params", "errors"),
    [
        (
            "trend",
            {"measure": "salary"},
            {"measure": ["measure must be total_cost or headcount, got salary"]},
        ),
        (
            "by-tenure",
            {"level": "9"},
            {"level": ["level must be all, 1, 2, 3, 4, 5 or 6, got 9"]},
        ),
        (
            "cost-mix",
            {"view": "net"},
            {"view": ["view must be cost or take_home, got net"]},
        ),
        (
            "gender-gap",
            {"view": "pie"},
            {"view": ["view must be pay_gap, bonus, quartiles or by_level, got pie"]},
        ),
    ],
)
def test_a_control_value_outside_its_list_is_a_400(api, people, name, params, errors):
    response = api.get(URL.format(name), params)

    assert (response.status_code, response.json()) == (400, errors)


@pytest.mark.parametrize("view", ["pay_gap", "bonus", "quartiles", "by_level"])
def test_each_gender_view_runs_a_fixed_number_of_queries(
    api, people, django_assert_num_queries, view
):
    """The user, the countries, the departments, the rates and one list of values (D62)."""
    with django_assert_num_queries(5):
        response = api.get(URL.format("gender-gap"), {"view": view})

    assert (response.status_code, response.json()["view"]) == (200, view)
