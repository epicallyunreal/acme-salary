"""The insights against DESIGN section 9's fixture. Every figure below was worked out by hand from
that table and is written as a literal; none is computed by the code under test."""

from datetime import date
from decimal import Decimal

import pytest

from apps.core import fx
from apps.core.exceptions import Invalid
from apps.core.money import render
from apps.employees import services as employees
from apps.insights import queries
from tests.factories import CompensationRecordFactory, EmployeeFactory, country
from tests.insights.fixture import build_fixture, us_lines

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 7)
NEW_YEAR = date(2027, 1, 1)
USD_RATES = {"label": "October 2026 rates", "effective_from": "2026-10-01"}
EUR_RATES = {"label": "October 2026 rates", "effective_from": "2026-10-01"}


@pytest.fixture
def people(lookups):
    return build_fixture()


def filters(**given) -> queries.InsightFilters:
    lookups = queries.Lookups.load()
    return queries.build_filters(
        lookups,
        country=given.get("country", []),
        department=given.get("department", []),
        include_exited=given.get("include_exited", False),
        on=given.get("on", TODAY),
        currency=given.get("currency"),
    )


def insight(name: str, **given) -> dict:
    f = filters(**given)
    return render(queries.INSIGHTS[name](f, fx.RateTable.load(f.on), queries.Lookups.load()))


def country_row(code, name, headcount, total, median, share):
    return {
        "country": {"code": code, "name": name},
        "headcount": headcount,
        "total_cost": total,
        "median_gross": median,
        "share_pct": share,
    }


def department_row(code, name, headcount, total, mean, median):
    return {
        "department": {"code": code, "name": name},
        "headcount": headcount,
        "total_cost": total,
        "mean_gross": mean,
        "median_gross": median,
    }


NOBODY_IN = [
    country_row("NL", "Netherlands", 0, None, None, None),
    country_row("SG", "Singapore", 0, None, None, None),
]


def empty(*names):
    codes = {
        "Customer Support": "customer-support",
        "Data": "data",
        "Design": "design",
        "Engineering": "engineering",
        "Finance": "finance",
        "HR": "hr",
        "IT": "it",
        "Legal": "legal",
        "Marketing": "marketing",
        "Operations": "operations",
        "Product": "product",
        "Sales": "sales",
    }
    return [department_row(codes[name], name, 0, None, None, None) for name in names]


EIGHT_EMPTY = empty("Data", "Design", "HR", "IT", "Legal", "Marketing", "Operations", "Product")


# summary


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            {},
            {
                "currency": "USD",
                "rate_month": USD_RATES,
                "headcount": 27,
                "total_cost": "2435450.00",
                "mean_gross": "80462.96",
                "median_gross": "75000.00",
                "countries": 4,
                "departments": 4,
            },
        ),
        (
            {"country": ["IN"]},
            {
                "currency": "USD",
                "rate_month": USD_RATES,
                "headcount": 12,
                "total_cost": "319200.00",
                "mean_gross": "23750.00",
                "median_gross": "23750.00",
                "countries": 1,
                "departments": 2,
            },
        ),
        (
            {"department": ["engineering"]},
            {
                "currency": "USD",
                "rate_month": USD_RATES,
                "headcount": 15,
                "total_cost": "1219200.00",
                "mean_gross": "71500.00",
                "median_gross": "87500.00",
                "countries": 3,
                "departments": 1,
            },
        ),
        (
            {"include_exited": True},
            {
                "currency": "USD",
                "rate_month": USD_RATES,
                "headcount": 29,
                "total_cost": "2574450.00",
                "mean_gross": "79267.24",
                "median_gross": "75000.00",
                "countries": 4,
                "departments": 4,
            },
        ),
        (
            {"on": NEW_YEAR},
            {
                "currency": "USD",
                "rate_month": USD_RATES,
                "headcount": 28,
                "total_cost": "2618450.00",
                "mean_gross": "83125.00",
                "median_gross": "81250.00",
                "countries": 4,
                "departments": 4,
            },
        ),
        (
            {"currency": "eur"},
            {
                "currency": "EUR",
                "rate_month": EUR_RATES,
                "headcount": 27,
                "total_cost": "1948360.00",
                "mean_gross": "64370.37",
                "median_gross": "60000.00",
                "countries": 4,
                "departments": 4,
            },
        ),
        (
            {"country": ["IN"], "currency": "local"},
            {
                "currency": "INR",
                "rate_month": {"label": "local currency (INR)", "effective_from": None},
                "headcount": 12,
                "total_cost": "25536000.00",
                "mean_gross": "1900000.00",
                "median_gross": "1900000.00",
                "countries": 1,
                "departments": 2,
            },
        ),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_summary(people, given, expected):
    assert insight("summary", **given) == expected


def test_a_small_population_shows_its_headcount_and_total_cost_only(people):
    """SPEC section 9: under five people, no mean or median, so no one's pay can be singled out."""
    assert insight("summary", country=["GB"]) == {
        "currency": "USD",
        "rate_month": USD_RATES,
        "headcount": 1,
        "total_cost": "71250.00",
        "mean_gross": None,
        "median_gross": None,
        "countries": 1,
        "departments": 1,
    }


# by-country


@pytest.mark.parametrize(
    ("given", "rows"),
    [
        (
            {},
            [
                country_row("US", "United States", 10, "1595000.00", "145000.00", "65.5"),
                country_row("DE", "Germany", 4, "450000.00", None, "18.5"),
                country_row("IN", "India", 12, "319200.00", "23750.00", "13.1"),
                country_row("GB", "United Kingdom", 1, "71250.00", None, "2.9"),
                *NOBODY_IN,
            ],
        ),
        (
            {"country": ["IN", "GB"]},
            [
                country_row("IN", "India", 12, "319200.00", "23750.00", "81.8"),
                country_row("GB", "United Kingdom", 1, "71250.00", None, "18.2"),
            ],
        ),
        (
            {"department": ["sales"]},
            [
                country_row("US", "United States", 5, "935000.00", "170000.00", "100.0"),
                country_row("DE", "Germany", 0, None, None, None),
                country_row("IN", "India", 0, None, None, None),
                *NOBODY_IN,
                country_row("GB", "United Kingdom", 0, None, None, None),
            ],
        ),
        (
            {"include_exited": True},
            [
                country_row("US", "United States", 11, "1727000.00", "140000.00", "67.1"),
                country_row("DE", "Germany", 4, "450000.00", None, "17.5"),
                country_row("IN", "India", 13, "326200.00", "22500.00", "12.7"),
                country_row("GB", "United Kingdom", 1, "71250.00", None, "2.8"),
                *NOBODY_IN,
            ],
        ),
        (
            {"on": NEW_YEAR},
            [
                country_row("US", "United States", 10, "1628000.00", "145000.00", "62.2"),
                country_row("DE", "Germany", 5, "600000.00", "100000.00", "22.9"),
                country_row("IN", "India", 12, "319200.00", "23750.00", "12.2"),
                country_row("GB", "United Kingdom", 1, "71250.00", None, "2.7"),
                *NOBODY_IN,
            ],
        ),
        (
            {"currency": "eur"},
            [
                country_row("US", "United States", 10, "1276000.00", "116000.00", "65.5"),
                country_row("DE", "Germany", 4, "360000.00", None, "18.5"),
                country_row("IN", "India", 12, "255360.00", "19000.00", "13.1"),
                country_row("GB", "United Kingdom", 1, "57000.00", None, "2.9"),
                *NOBODY_IN,
            ],
        ),
        (
            {"country": ["IN"], "currency": "local"},
            [country_row("IN", "India", 12, "25536000.00", "1900000.00", "100.0")],
        ),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_by_country(people, given, rows):
    assert insight("by-country", **given)["rows"] == rows


# by-department


@pytest.mark.parametrize(
    ("given", "rows"),
    [
        (
            {},
            [
                department_row(
                    "engineering", "Engineering", 15, "1219200.00", "71500.00", "87500.00"
                ),
                department_row("sales", "Sales", 5, "935000.00", "170000.00", "170000.00"),
                department_row(
                    "customer-support", "Customer Support", 6, "210000.00", "31250.00", "31250.00"
                ),
                department_row("finance", "Finance", 1, "71250.00", None, None),
                *EIGHT_EMPTY,
            ],
        ),
        (
            {"country": ["US"]},
            [
                department_row("sales", "Sales", 5, "935000.00", "170000.00", "170000.00"),
                department_row(
                    "engineering", "Engineering", 5, "660000.00", "120000.00", "120000.00"
                ),
                *empty("Customer Support", "Data", "Design", "Finance", "HR", "IT"),
                *empty("Legal", "Marketing", "Operations", "Product"),
            ],
        ),
        (
            {"department": ["engineering", "finance"]},
            [
                department_row(
                    "engineering", "Engineering", 15, "1219200.00", "71500.00", "87500.00"
                ),
                department_row("finance", "Finance", 1, "71250.00", None, None),
            ],
        ),
        (
            {"include_exited": True},
            [
                department_row(
                    "engineering", "Engineering", 16, "1351200.00", "74531.25", "93750.00"
                ),
                department_row("sales", "Sales", 5, "935000.00", "170000.00", "170000.00"),
                department_row(
                    "customer-support", "Customer Support", 7, "217000.00", "27678.57", "30000.00"
                ),
                department_row("finance", "Finance", 1, "71250.00", None, None),
                *EIGHT_EMPTY,
            ],
        ),
        (
            {"on": NEW_YEAR},
            [
                department_row(
                    "engineering", "Engineering", 16, "1402200.00", "76718.75", "93750.00"
                ),
                department_row("sales", "Sales", 5, "935000.00", "170000.00", "170000.00"),
                department_row(
                    "customer-support", "Customer Support", 6, "210000.00", "31250.00", "31250.00"
                ),
                department_row("finance", "Finance", 1, "71250.00", None, None),
                *EIGHT_EMPTY,
            ],
        ),
        (
            {"currency": "eur"},
            [
                department_row(
                    "engineering", "Engineering", 15, "975360.00", "57200.00", "70000.00"
                ),
                department_row("sales", "Sales", 5, "748000.00", "136000.00", "136000.00"),
                department_row(
                    "customer-support", "Customer Support", 6, "168000.00", "25000.00", "25000.00"
                ),
                department_row("finance", "Finance", 1, "57000.00", None, None),
                *EIGHT_EMPTY,
            ],
        ),
        (
            {"country": ["DE"], "currency": "local"},
            [
                department_row("engineering", "Engineering", 4, "360000.00", None, None),
                *empty("Customer Support", "Data", "Design", "Finance", "HR", "IT"),
                *empty("Legal", "Marketing", "Operations", "Product", "Sales"),
            ],
        ),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_by_department(people, given, rows):
    assert insight("by-department", **given)["rows"] == rows


def test_a_department_with_nobody_is_listed_with_nulls(people):
    """Legal has nobody: it is listed with headcount 0 and nothing else (SPEC section 9)."""
    assert insight("by-department", department=["legal"])["rows"] == empty("Legal")


# The population


def test_a_scheduled_revision_counts_from_its_date_and_not_before(people):
    """F3, the insights half (D42): U1's revision to 130,000 is scheduled for 2027-01-01, so it
    is not his record today, and is from that day."""
    u1 = people["U1"]
    today = queries.population(filters()).get(employee=u1)
    new_year = queries.population(filters(on=NEW_YEAR)).get(employee=u1)

    assert (today.gross_annual, new_year.gross_annual) == (Decimal("100000"), Decimal("130000"))
    assert (insight("summary")["headcount"], insight("summary", on=NEW_YEAR)["headcount"]) == (
        27,
        28,
    )


def test_an_exit_counts_on_its_last_date_and_is_gone_the_day_after(people):
    """F3, the insights half (D42): X1 left on 2026-06-30, so that day counts him, the next not."""
    x1 = people["X1"]
    last_day = filters(on=date(2026, 6, 30))
    day_after = filters(on=date(2026, 7, 1))

    assert queries.population(last_day).filter(employee=x1).exists()
    assert not queries.population(day_after).filter(employee=x1).exists()
    assert insight("summary", on=date(2026, 6, 30))["headcount"] == 28
    assert insight("summary", on=date(2026, 7, 1))["headcount"] == 27


def test_an_employee_with_no_live_record_is_never_counted(people):
    """D50: an exit before pay starts cancels the only record. Nothing of theirs is counted, with
    include_exited too, and not after the day the record would have started."""
    late = EmployeeFactory(country=country("US"), joining_date=date(2026, 9, 1))
    record = CompensationRecordFactory(
        employee=late, lines=us_lines(Decimal(200_000)), effective_from=date(2026, 11, 1)
    )
    employees.exit_employee(late, date(2026, 9, 30))
    record.refresh_from_db()
    assert record.cancelled_at is not None

    for on in (TODAY, date(2026, 12, 1)):
        for include_exited in (False, True):
            f = filters(on=on, include_exited=include_exited)
            assert not queries.population(f).filter(employee=late).exists()
    assert insight("summary")["headcount"] == 27
    assert insight("summary", include_exited=True)["headcount"] == 29


def test_an_unknown_country_or_department_is_refused_with_section_7s_words(people):
    with pytest.raises(Invalid) as excinfo:
        filters(country=["XX"], department=["growth"])

    assert excinfo.value.errors == {
        "country": ["Unknown country_code: XX"],
        "department": ["Unknown department: growth"],
    }
