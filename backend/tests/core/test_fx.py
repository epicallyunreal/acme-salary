from datetime import date
from decimal import Decimal

import pytest

from apps.core.exceptions import Invalid
from apps.core.fx import MissingRate, RateTable, resolve_reporting_currency
from apps.core.models import Country

pytestmark = pytest.mark.django_db

OCTOBER = date(2026, 10, 7)
SEPTEMBER = date(2026, 9, 15)
LONG_AGO = date(2020, 1, 1)


def test_load_picks_the_row_effective_on_the_date(rates):
    assert RateTable.load(OCTOBER).rate("INR", "USD") == Decimal("0.01200")
    assert RateTable.load(SEPTEMBER).rate("INR", "USD") == Decimal("0.01195")
    assert RateTable.load(OCTOBER).effective_from("INR", "USD") == date(2026, 10, 1)


def test_a_date_before_the_earliest_row_uses_the_earliest_rate(rates):
    table = RateTable.load(LONG_AGO)

    assert table.rate("INR", "USD") == Decimal("0.01195")
    assert table.effective_from("INR", "USD") == date(2026, 9, 1)


def test_identity_rate_is_one(rates):
    table = RateTable.load(OCTOBER)

    assert table.rate("USD", "USD") == Decimal("1")
    assert table.effective_from("USD", "USD") is None
    assert table.convert(Decimal("100.00"), "EUR", "EUR") == Decimal("100.00")


def test_direct_pair_to_eur(rates):
    assert RateTable.load(OCTOBER).convert(Decimal("1000000.00"), "INR", "EUR") == Decimal(
        "10210.00"
    )


def test_a_pair_without_a_direct_row_routes_through_usd(rates):
    table = RateTable.load(OCTOBER)

    # 1 GBP = 1.3450 USD and 1 SGD = 0.7810 USD, so 1,000 GBP = 1,722.15 SGD.
    assert table.convert(Decimal("1000.00"), "GBP", "SGD") == Decimal("1722.15")
    assert table.effective_from("GBP", "SGD") == date(2026, 10, 1)


def test_usd_to_a_local_currency_uses_the_inverse_of_the_seeded_leg(rates):
    # 1 INR = 0.012 USD, so 100 USD = 8,333.33 INR.
    assert RateTable.load(OCTOBER).convert(Decimal("100.00"), "USD", "INR") == Decimal("8333.33")


def test_an_unknown_pair_raises_a_400(rates):
    with pytest.raises(MissingRate) as excinfo:
        RateTable.load(OCTOBER).rate("XXX", "USD")

    assert excinfo.value.errors == {"currency": ["no exchange rate from XXX to USD"]}


def test_convert_quantises_half_up_once(rates):
    table = RateTable.load(OCTOBER)

    assert table.convert(Decimal("1450000.00"), "INR", "USD") == Decimal("17400.00")
    assert table.convert(Decimal("100000.55"), "INR", "USD") == Decimal("1200.01")


def test_case_expression_gives_each_currency_its_rate_in_sql(rates):
    table = RateTable.load(OCTOBER)

    rows = dict(
        Country.objects.annotate(r=table.case_expression("USD", "currency_code")).values_list(
            "code", "r"
        )
    )

    assert rows == {
        "IN": Decimal("0.01200"),
        "US": Decimal("1"),
        "GB": Decimal("1.3450"),
        "DE": Decimal("1.1750"),
        "NL": Decimal("1.1750"),
        "SG": Decimal("0.7810"),
    }


def test_month_label_names_the_newest_rate_month_feeding_the_currency(rates):
    assert RateTable.load(OCTOBER).month_label("USD") == "October 2026 rates"
    assert RateTable.load(SEPTEMBER).month_label("EUR") == "September 2026 rates"
    assert RateTable.load(OCTOBER).month_label("INR") == "local currency (INR)"


def test_rows_lists_one_row_per_pair(rates):
    rows = RateTable.load(OCTOBER).rows()

    assert len(rows) == 8
    assert {row["effective_from"] for row in rows} == {date(2026, 10, 1)}
    assert rows[0] == {
        "from_currency": "EUR",
        "to_currency": "USD",
        "rate": Decimal("1.1750"),
        "effective_from": date(2026, 10, 1),
    }


CURRENCIES = {"IN": "INR", "US": "USD"}


@pytest.mark.parametrize(
    ("currency", "countries", "expected"),
    [(None, [], "USD"), ("usd", ["IN", "US"], "USD"), ("EUR", [], "EUR"), ("local", ["IN"], "INR")],
)
def test_resolve_reporting_currency(currency, countries, expected):
    assert resolve_reporting_currency(currency, countries, CURRENCIES) == expected


@pytest.mark.parametrize(
    ("currency", "countries", "message"),
    [
        ("local", ["IN", "US"], "currency=local needs exactly one country in the filter"),
        ("local", [], "currency=local needs exactly one country in the filter"),
        ("local", ["XX"], "Unknown country_code: XX"),
        ("gbp", [], "currency must be usd, eur or local, got gbp"),
    ],
)
def test_resolve_reporting_currency_rejects(currency, countries, message):
    with pytest.raises(Invalid) as excinfo:
        resolve_reporting_currency(currency, countries, CURRENCIES)

    assert [m for messages in excinfo.value.errors.values() for m in messages] == [message]
