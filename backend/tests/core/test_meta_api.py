"""The four lookup endpoints under /api/v1/meta/ (SPEC section 8)."""

import pytest

pytestmark = pytest.mark.django_db


def test_countries(api, lookups):
    response = api.get("/api/v1/meta/countries/")

    body = response.json()
    assert response.status_code == 200
    assert [row["code"] for row in body] == ["DE", "GB", "IN", "NL", "SG", "US"]
    india = next(row for row in body if row["code"] == "IN")
    assert india["name"] == "India"
    assert india["currency_code"] == "INR"
    assert isinstance(india["min_gross_annual"], str)


def test_departments_sorted_by_name(api, lookups):
    body = api.get("/api/v1/meta/departments/").json()

    assert len(body) == 12
    assert [row["name"] for row in body] == sorted(row["name"] for row in body)
    assert body[0] == {"id": body[0]["id"], "code": "customer-support", "name": "Customer Support"}


def test_components_for_a_country_are_the_global_ones_plus_its_own(api, lookups):
    india = api.get("/api/v1/meta/components/", {"country": "IN"}).json()
    everything = api.get("/api/v1/meta/components/").json()

    assert [row["code"] for row in india] == [
        "BASE",
        "HRA",
        "ALLOWANCES",
        "TAX",
        "EMPLOYER_CONTRIBUTION",
    ]
    assert india[1]["country"] == "IN" and india[0]["country"] is None
    assert india[1]["kind"] == "earning"
    assert len(everything) == 10


def test_components_for_an_unknown_country_is_404(api, lookups):
    response = api.get("/api/v1/meta/components/", {"country": "XX"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown country_code: XX"}


def test_exchange_rates_on_a_date(api, rates):
    october = api.get("/api/v1/meta/exchange-rates/", {"on": "2026-10-07"}).json()
    september = api.get("/api/v1/meta/exchange-rates/", {"on": "2026-09-15"}).json()
    before_any = api.get("/api/v1/meta/exchange-rates/", {"on": "2020-01-01"}).json()

    assert october["on"] == "2026-10-07"
    assert len(october["rates"]) == 8
    assert october["rates"][0] == {
        "from_currency": "EUR",
        "to_currency": "USD",
        "rate": "1.17500000",
        "effective_from": "2026-10-01",
    }
    assert october["month_labels"] == {"USD": "October 2026 rates", "EUR": "October 2026 rates"}
    inr_usd = next(
        r for r in september["rates"] if (r["from_currency"], r["to_currency"]) == ("INR", "USD")
    )
    assert inr_usd == {
        "from_currency": "INR",
        "to_currency": "USD",
        "rate": "0.01195000",
        "effective_from": "2026-09-01",
    }
    assert september["month_labels"]["USD"] == "September 2026 rates"
    assert before_any["rates"] == september["rates"]


def test_exchange_rates_default_to_today_and_reject_a_bad_date(api, rates):
    today = api.get("/api/v1/meta/exchange-rates/").json()
    bad = api.get("/api/v1/meta/exchange-rates/", {"on": "2026-13-01"})

    assert today["on"] == "2026-10-07"
    assert bad.status_code == 400
    assert bad.json() == {"on": ["on must be a date in YYYY-MM-DD form, got 2026-13-01"]}


@pytest.mark.parametrize(
    "path",
    ["/api/v1/meta/countries/", "/api/v1/meta/components/", "/api/v1/meta/exchange-rates/"],
)
def test_meta_query_counts(api, rates, path, django_assert_num_queries):
    """User from the JWT plus one query; components with a country check the country first."""
    with django_assert_num_queries(2):
        api.get(path)
    with django_assert_num_queries(3):
        api.get("/api/v1/meta/components/", {"country": "SG"})
