"""The insights against DESIGN section 9's fixture. Every figure below was worked out by hand from
that table and is written as a literal; none is computed by the code under test."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.core import fx
from apps.core import services as core_services
from apps.core.dates import parse_period
from apps.core.exceptions import Invalid
from apps.core.money import render
from apps.employees import services as employees
from apps.insights import queries
from tests.factories import CompensationRecordFactory, EmployeeFactory, country, department
from tests.insights.fixture import build_fixture, us_lines
from tests.insights.history import build_history, hire

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 7)
NEW_YEAR = date(2027, 1, 1)
USD_RATES = {"label": "October 2026 rates", "effective_from": "2026-10-01"}
EUR_RATES = {"label": "October 2026 rates", "effective_from": "2026-10-01"}
FEWER_THAN_5 = "fewer than 5 people"


@pytest.fixture
def people(lookups):
    return build_fixture()


def filters(**given) -> queries.InsightFilters:
    """The filters a request names, its period read as the API reads `from` and `to`, today and
    the same day a year before when not given (D64)."""
    lookups = queries.Lookups.load()
    start, end = given.get("from"), given.get("to", TODAY)
    return queries.build_filters(
        lookups,
        country=given.get("country", []),
        department=given.get("department", []),
        include_exited=given.get("include_exited", False),
        period=parse_period(start and start.isoformat(), end.isoformat()),
        currency=given.get("currency"),
    )


def insight(name: str, control: dict | None = None, **given) -> dict:
    """An insight for the given filters and, where the card has one, its control (D62)."""
    f = filters(**given)
    rates, lookups = fx.RateTable.load(f.end), queries.Lookups.load()
    return render(queries.INSIGHTS[name](f, rates, lookups, **(control or {})))


def figures(payload: dict) -> dict:
    """A payload without the period every insight names, which
    test_every_insight_names_its_period holds, and without the summary's spend, which the spend
    tests hold (D64)."""
    return {key: value for key, value in payload.items() if key not in ("from", "to", "spent")}


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


FINANCE = department_row("finance", "Finance", 1, None, None, None)
# After the groups that show a total: the withheld and the empty, in name order.
THE_REST = [
    *empty("Data", "Design"),
    FINANCE,
    *empty("HR", "IT", "Legal", "Marketing", "Operations", "Product"),
]


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
            {"to": NEW_YEAR},
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
    assert figures(insight("summary", **given)) == expected


def test_a_population_under_five_shows_its_headcount_alone(people):
    """D59: a one-person total is that person's cost, read straight off the card."""
    assert figures(insight("summary", country=["GB"])) == {
        "currency": "USD",
        "rate_month": USD_RATES,
        "headcount": 1,
        "total_cost": None,
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
                country_row("IN", "India", 12, "319200.00", "23750.00", "13.1"),
                country_row("DE", "Germany", 4, None, None, None),
                *NOBODY_IN,
                country_row("GB", "United Kingdom", 1, None, None, None),
            ],
        ),
        (
            {"country": ["IN", "GB"]},
            [
                country_row("IN", "India", 12, "319200.00", "23750.00", "81.8"),
                country_row("GB", "United Kingdom", 1, None, None, None),
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
                country_row("IN", "India", 13, "326200.00", "22500.00", "12.7"),
                country_row("DE", "Germany", 4, None, None, None),
                *NOBODY_IN,
                country_row("GB", "United Kingdom", 1, None, None, None),
            ],
        ),
        (
            {"to": NEW_YEAR},
            [
                country_row("US", "United States", 10, "1628000.00", "145000.00", "62.2"),
                country_row("DE", "Germany", 5, "600000.00", "100000.00", "22.9"),
                country_row("IN", "India", 12, "319200.00", "23750.00", "12.2"),
                *NOBODY_IN,
                country_row("GB", "United Kingdom", 1, None, None, None),
            ],
        ),
        (
            {"currency": "eur"},
            [
                country_row("US", "United States", 10, "1276000.00", "116000.00", "65.5"),
                country_row("IN", "India", 12, "255360.00", "19000.00", "13.1"),
                country_row("DE", "Germany", 4, None, None, None),
                *NOBODY_IN,
                country_row("GB", "United Kingdom", 1, None, None, None),
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
                *THE_REST,
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
                FINANCE,
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
                *THE_REST,
            ],
        ),
        (
            {"to": NEW_YEAR},
            [
                department_row(
                    "engineering", "Engineering", 16, "1402200.00", "76718.75", "93750.00"
                ),
                department_row("sales", "Sales", 5, "935000.00", "170000.00", "170000.00"),
                department_row(
                    "customer-support", "Customer Support", 6, "210000.00", "31250.00", "31250.00"
                ),
                *THE_REST,
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
                *THE_REST,
            ],
        ),
        (
            # Germany's four engineers show their headcount alone, so nothing is ranked by cost.
            {"country": ["DE"], "currency": "local"},
            [
                *empty("Customer Support", "Data", "Design"),
                department_row("engineering", "Engineering", 4, None, None, None),
                *empty("Finance", "HR", "IT", "Legal", "Marketing", "Operations", "Product"),
                *empty("Sales"),
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
    grosses = [
        queries.population(filters(to=on)).get(employee=u1).gross_annual
        for on in (TODAY, date(2026, 12, 31), NEW_YEAR)
    ]

    assert grosses == [Decimal("100000"), Decimal("100000"), Decimal("130000")]


def test_an_exit_counts_on_its_last_date_and_is_gone_the_day_after(people):
    """F3, the insights half (D42): X1 left on 2026-06-30, so that day counts him, the next not."""
    x1 = people["X1"]
    last_day = filters(to=date(2026, 6, 30))
    day_after = filters(to=date(2026, 7, 1))

    assert queries.population(last_day).filter(employee=x1).exists()
    assert not queries.population(day_after).filter(employee=x1).exists()
    assert insight("summary", to=date(2026, 6, 30))["headcount"] == 28
    assert insight("summary", to=date(2026, 7, 1))["headcount"] == 27


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
            f = filters(to=on, include_exited=include_exited)
            assert not queries.population(f).filter(employee=late).exists()
    assert insight("summary")["headcount"] == 27
    assert insight("summary", include_exited=True)["headcount"] == 29


def test_include_exited_counts_someone_who_left_once_at_their_last_record(people):
    """SPEC section 9: a leaver counts at the last record, not once per record they ever had."""
    z1 = EmployeeFactory(country=country("US"), last_date=date(2026, 3, 31))
    for gross, starts, ends in (
        (100_000, date(2024, 1, 1), date(2025, 4, 1)),
        (110_000, date(2025, 4, 1), date(2026, 4, 1)),
    ):
        CompensationRecordFactory(
            employee=z1, lines=us_lines(Decimal(gross)), effective_from=starts, effective_to=ends
        )

    counted = queries.population(filters(include_exited=True)).filter(employee=z1)

    assert [record.gross_annual for record in counted] == [Decimal("110000")]
    assert insight("summary", include_exited=True)["headcount"] == 30


def test_nobody_in_the_filters_is_headcount_zero_and_nothing_else(people):
    """The dashboard's empty state reads this: Legal has nobody."""
    assert figures(insight("summary", department=["legal"])) == {
        "currency": "USD",
        "rate_month": USD_RATES,
        "headcount": 0,
        "total_cost": None,
        "mean_gross": None,
        "median_gross": None,
        "countries": 0,
        "departments": 0,
    }
    assert figures(insight("distribution", department=["legal"])) == headcount_only(
        "USD", USD_RATES, 0
    )
    assert insight("by-level", department=["legal"])["rows"] == [
        level(number, 0) for number in range(1, 7)
    ]


def test_local_currency_is_labelled_local_even_when_the_toggle_offers_it_too(people):
    """D58: US figures in local currency use no rate, so the label says local, not a rate month."""
    assert figures(insight("summary", country=["US"], currency="local")) == {
        "currency": "USD",
        "rate_month": {"label": "local currency (USD)", "effective_from": None},
        "headcount": 10,
        "total_cost": "1595000.00",
        "mean_gross": "145000.00",
        "median_gross": "145000.00",
        "countries": 1,
        "departments": 2,
    }


def test_the_rates_are_those_of_the_reporting_date(people):
    """INR to USD becomes 0.015 on 2027-01-01: India's figures and the rate month follow `on`."""
    core_services.set_exchange_rate("INR", "USD", Decimal("0.015"), NEW_YEAR)

    today = insight("summary", country=["IN"])
    new_year = insight("summary", country=["IN"], to=NEW_YEAR)

    assert (today["total_cost"], today["rate_month"]) == ("319200.00", USD_RATES)
    assert new_year["rate_month"] == {"label": "January 2027 rates", "effective_from": "2027-01-01"}
    assert (new_year["total_cost"], new_year["mean_gross"], new_year["median_gross"]) == (
        "383040.00",
        "28500.00",
        "28500.00",
    )


def test_a_code_given_twice_is_one_group(people):
    by_department = insight("by-department", department=["sales", "sales"])["rows"]

    assert insight("by-country", country=["IN", "IN"])["rows"] == [
        country_row("IN", "India", 12, "319200.00", "23750.00", "100.0")
    ]
    assert [row["department"]["code"] for row in by_department] == ["sales"]


def test_sums_are_converted_once_per_currency_then_quantised_once(people):
    """SPEC section 9: amounts are summed per currency in SQL, converted at the Decimal rate and
    quantised once. Five Dutch and five British salaries of 1,000.01: 5,000.05 EUR and 5,000.05
    GBP at 1.25 are 6,250.0625 each and 12,500.125 together, so 12,500.13. Quantised per row the
    total would be 12,500.10, and per currency 12,500.12."""
    for code in ("NL", "GB"):
        for _ in range(5):
            CompensationRecordFactory(
                employee=EmployeeFactory(country=country(code), department=department("design")),
                lines={"BASE": Decimal("1000.01")},
                effective_from=date(2024, 1, 1),
            )

    (row,) = insight("by-department", department=["design"])["rows"]

    assert (row["headcount"], row["total_cost"], row["mean_gross"], row["median_gross"]) == (
        10,
        "12500.13",
        "1250.01",
        "1250.01",
    )


def test_an_unknown_country_or_department_is_refused_with_section_7s_words(people):
    with pytest.raises(Invalid) as excinfo:
        filters(country=["XX"], department=["growth"])

    assert excinfo.value.errors == {
        "country": ["Unknown country_code: XX"],
        "department": ["Unknown department: growth"],
    }


# distribution


def bands(edges: list[str], top: str, counts: list[int]) -> list[dict]:
    """Twelve bands from their lower edges, the last band's upper edge and the counts."""
    tops = [*edges[1:], top]
    return [
        {"index": index, "from": edges[index], "to": tops[index], "count": counts[index]}
        for index in range(12)
    ]


def headcount_only(currency, rates, headcount):
    return {
        "currency": currency,
        "rate_month": rates,
        "headcount": headcount,
        "p1": None,
        "p99": None,
        "bands": None,
        "markers": None,
    }


def spread(currency, rates, headcount, p1, p99, markers, edges, counts):
    return {
        "currency": currency,
        "rate_month": rates,
        "headcount": headcount,
        "p1": p1,
        "p99": p99,
        "bands": bands(edges, p99, counts),
        "markers": dict(zip(("p10", "p50", "p90"), markers, strict=True)),
    }


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            {},
            spread(
                "USD",
                USD_RATES,
                27,
                "10650.00",
                "187400.00",
                ("16500.00", "75000.00", "164000.00"),
                ["10650.00", "25379.17", "40108.33", "54837.50", "69566.67", "84295.83"]
                + ["99025.00", "113754.17", "128483.33", "143212.50", "157941.67", "172670.83"],
                [7, 5, 0, 1, 1, 1, 4, 1, 2, 1, 2, 2],
            ),
        ),
        (
            {"country": ["US"]},
            headcount_only("USD", USD_RATES, 10),
        ),
        (
            {"department": ["engineering", "sales"]},
            spread(
                "USD",
                USD_RATES,
                20,
                "10475.00",
                "188100.00",
                ("14750.00", "105000.00", "171000.00"),
                ["10475.00", "25277.08", "40079.17", "54881.25", "69683.33", "84485.42"]
                + ["99287.50", "114089.58", "128891.67", "143693.75", "158495.83", "173297.92"],
                [6, 0, 0, 0, 1, 1, 4, 1, 2, 1, 2, 2],
            ),
        ),
        (
            {"include_exited": True},
            spread(
                "USD",
                USD_RATES,
                29,
                "7300.00",
                "187200.00",
                ("14500.00", "75000.00", "162000.00"),
                ["7300.00", "22291.67", "37283.33", "52275.00", "67266.67", "82258.33"]
                + ["97250.00", "112241.67", "127233.33", "142225.00", "157216.67", "172208.33"],
                [6, 6, 1, 1, 1, 1, 3, 3, 2, 1, 2, 2],
            ),
        ),
        (
            {"to": NEW_YEAR},
            spread(
                "USD",
                USD_RATES,
                28,
                "10675.00",
                "187300.00",
                ("16750.00", "81250.00", "163000.00"),
                ["10675.00", "25393.75", "40112.50", "54831.25", "69550.00", "84268.75"]
                + ["98987.50", "113706.25", "128425.00", "143143.75", "157862.50", "172581.25"],
                [7, 5, 0, 1, 1, 1, 3, 2, 3, 1, 2, 2],
            ),
        ),
        (
            {"currency": "eur"},
            spread(
                "EUR",
                EUR_RATES,
                27,
                "8520.00",
                "149920.00",
                ("13200.00", "60000.00", "131200.00"),
                ["8520.00", "20303.33", "32086.67", "43870.00", "55653.33", "67436.67"]
                + ["79220.00", "91003.33", "102786.67", "114570.00", "126353.33", "138136.67"],
                [7, 5, 0, 1, 1, 1, 4, 1, 2, 1, 2, 2],
            ),
        ),
        (
            {"country": ["IN"], "currency": "local"},
            headcount_only("INR", {"label": "local currency (INR)", "effective_from": None}, 12),
        ),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_distribution(people, given, expected):
    assert figures(insight("distribution", **given)) == expected


def test_a_distribution_needs_twenty_people_and_one_salary_is_one_band(people):
    """D59: under twenty, the headcount alone. Twenty people on one salary leave no width to
    split into twelve, so one band holds them all (SPEC section 9)."""

    def hire(count):
        for _ in range(count):
            CompensationRecordFactory(
                employee=EmployeeFactory(country=country("NL")),
                lines={"BASE": Decimal(70_000)},
                effective_from=date(2024, 1, 1),
            )

    hire(queries.SPREAD_GROUP - 1)
    assert figures(insight("distribution", country=["NL"])) == headcount_only("USD", USD_RATES, 19)

    hire(1)
    result = insight("distribution", country=["NL"])

    assert (result["headcount"], result["p1"], result["p99"]) == (20, "87500.00", "87500.00")
    assert result["bands"] == [{"index": 0, "from": "87500.00", "to": "87500.00", "count": 20}]
    assert result["markers"] == {"p10": "87500.00", "p50": "87500.00", "p90": "87500.00"}


def test_a_value_on_a_band_edge_lands_in_that_band():
    """170,000 between p1 150,400 and p99 189,600 is exactly band 6's lower edge."""
    low, high = Decimal("150400.00"), Decimal("189600.00")

    assert queries.band_of(Decimal("170000.00"), low, high) == 6
    assert queries.band_of(Decimal("169999.99"), low, high) == 5
    assert queries.band_of(Decimal("100.00"), low, high) == 0
    assert queries.band_of(Decimal("999999.00"), low, high) == 11


def test_one_value_is_every_percentile():
    assert queries.percentiles([Decimal("5.00")]) == [Decimal("5.00")] * 99


# by-level


def level(number, headcount, *figures):
    names = ("p10", "p25", "median", "p75", "p90")
    return {
        "level": number,
        "headcount": headcount,
        **dict(zip(names, figures or (None,) * 5, strict=True)),
    }


@pytest.mark.parametrize(
    ("given", "headcounts"),
    [
        ({}, [4, 6, 5, 5, 4, 3]),
        ({"country": ["US"]}, [2, 2, 2, 2, 1, 1]),
        ({"department": ["engineering"]}, [3, 4, 3, 2, 2, 1]),
        ({"include_exited": True}, [5, 6, 6, 5, 4, 3]),
        ({"to": NEW_YEAR}, [4, 6, 6, 5, 4, 3]),
        ({"currency": "eur"}, [4, 6, 5, 5, 4, 3]),
        ({"country": ["IN"], "currency": "local"}, [2, 2, 2, 2, 2, 2]),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_by_level_shows_headcount_alone_under_twenty(people, given, headcounts):
    """No level of DESIGN section 9's fixture reaches twenty, level 3's five included: at five,
    the five figures were every salary in the level (D59)."""
    rows = insight("by-level", **given)["rows"]

    assert rows == [level(number, count) for number, count in enumerate(headcounts, start=1)]


def test_a_level_of_twenty_shows_p10_to_p90_and_one_of_nineteen_its_headcount(people):
    """D59, by the inclusive method: twenty Dutch salaries of 50,000 to 97,500 USD in steps of
    2,500, so p10 sits at position 1.9, p25 at 4.75, the median at 9.5, p75 at 14.25, p90 at
    17.1. Never min or max, each of which is one person's pay."""
    assert (queries.SMALL_GROUP, queries.SPREAD_GROUP) == (5, 20)
    for step in range(queries.SPREAD_GROUP):
        CompensationRecordFactory(
            employee=EmployeeFactory(country=country("NL"), level=1),
            lines={"BASE": Decimal(40_000 + 2_000 * step)},
            effective_from=date(2024, 1, 1),
        )
    for _ in range(queries.SPREAD_GROUP - 1):
        CompensationRecordFactory(
            employee=EmployeeFactory(country=country("NL"), level=2),
            lines={"BASE": Decimal(60_000)},
            effective_from=date(2024, 1, 1),
        )

    assert insight("by-level", country=["NL"])["rows"] == [
        level(1, 20, "54750.00", "61875.00", "73750.00", "85625.00", "92750.00"),
        level(2, 19),
        level(3, 0),
        level(4, 0),
        level(5, 0),
        level(6, 0),
    ]


# gender-gap

WOMEN = "fewer than 5 women"
MEN = "fewer than 5 men"
BOTH = "fewer than 5 women and fewer than 5 men"


def gap(
    code, name, women, women_median, men, men_median, pct=None, other=0, undisclosed=0, reason=None
):
    return {
        "country": {"code": code, "name": name} if code else None,
        "female": {"headcount": women, "median_gross": women_median},
        "male": {"headcount": men, "median_gross": men_median},
        "other_count": other,
        "undisclosed_count": undisclosed,
        "gap_pct": pct,
        "reason": reason,
    }


NOBODY_ELSE = [
    gap("NL", "Netherlands", 0, None, 0, None),
    gap("SG", "Singapore", 0, None, 0, None),
]


@pytest.mark.parametrize(
    ("given", "rows"),
    [
        (
            {},
            [
                gap("DE", "Germany", 2, None, 2, None, reason=BOTH),
                gap("IN", "India", 6, "25000.00", 6, "22500.00", "-11.1"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None, reason=BOTH),
                gap("US", "United States", 4, None, 6, "125000.00", reason=WOMEN),
                gap(None, None, 13, "62500.00", 14, "100000.00", "37.5"),
            ],
        ),
        (
            {"country": ["IN"]},
            [
                gap("IN", "India", 6, "25000.00", 6, "22500.00", "-11.1"),
                gap(None, None, 6, "25000.00", 6, "22500.00", "-11.1"),
            ],
        ),
        (
            {"department": ["engineering"]},
            [
                gap("DE", "Germany", 2, None, 2, None, reason=BOTH),
                gap("IN", "India", 3, None, 3, None, reason=BOTH),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 0, None, 0, None),
                gap("US", "United States", 0, None, 5, "120000.00", reason=WOMEN),
                gap(None, None, 5, "22500.00", 10, "105000.00", "78.6"),
            ],
        ),
        (
            {"include_exited": True},
            [
                gap("DE", "Germany", 2, None, 2, None, reason=BOTH),
                gap("IN", "India", 7, "22500.00", 6, "22500.00", "0.0"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None, reason=BOTH),
                gap("US", "United States", 4, None, 7, "120000.00", reason=WOMEN),
                gap(None, None, 14, "50000.00", 15, "100000.00", "50.0"),
            ],
        ),
        (
            {"to": NEW_YEAR},
            [
                gap("DE", "Germany", 2, None, 3, None, reason=BOTH),
                gap("IN", "India", 6, "25000.00", 6, "22500.00", "-11.1"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None, reason=BOTH),
                gap("US", "United States", 4, None, 6, "130000.00", reason=WOMEN),
                gap(None, None, 13, "62500.00", 15, "110000.00", "43.2"),
            ],
        ),
        (
            {"currency": "eur"},
            [
                gap("DE", "Germany", 2, None, 2, None, reason=BOTH),
                gap("IN", "India", 6, "20000.00", 6, "18000.00", "-11.1"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None, reason=BOTH),
                gap("US", "United States", 4, None, 6, "100000.00", reason=WOMEN),
                gap(None, None, 13, "50000.00", 14, "80000.00", "37.5"),
            ],
        ),
        (
            {"country": ["IN"], "currency": "local"},
            [
                gap("IN", "India", 6, "2000000.00", 6, "1800000.00", "-11.1"),
                gap(None, None, 6, "2000000.00", 6, "1800000.00", "-11.1"),
            ],
        ),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_gender_gap(people, given, rows):
    assert insight("gender-gap", **given)["rows"] == rows


def test_a_gap_needs_five_of_each_gender(people):
    """Seven women and four men in Sales and Customer Support: the men's median and the gap are
    withheld, and the reason names the men (SPEC section 9, D62)."""
    rows = insight("gender-gap", department=["sales", "customer-support"])["rows"]

    assert rows[-1] == gap(None, None, 7, "160000.00", 4, None, reason=MEN)


def test_other_and_undisclosed_are_counted_never_given_a_median(people):
    """SPEC section 9: they count in headcount and show as a count beside the two medians."""
    for name, code, gender, lines in (
        ("O1", "US", "other", us_lines(Decimal(105_000))),
        ("Q1", "IN", "undisclosed", {"BASE": Decimal(1_500_000)}),
    ):
        CompensationRecordFactory(
            employee=EmployeeFactory(country=country(code), gender=gender, full_name=name),
            lines=lines,
            effective_from=date(2024, 1, 1),
        )

    rows = {
        row["country"]["code"] if row["country"] else "all": row
        for row in insight("gender-gap")["rows"]
    }

    assert (rows["US"]["other_count"], rows["IN"]["undisclosed_count"]) == (1, 1)
    assert (rows["all"]["other_count"], rows["all"]["undisclosed_count"]) == (1, 1)
    assert rows["all"]["female"] == {"headcount": 13, "median_gross": "62500.00"}
    assert rows["all"]["male"] == {"headcount": 14, "median_gross": "100000.00"}
    assert insight("summary")["headcount"] == 29


# trend (D62), over tests/insights/history.py


@pytest.fixture
def history(lookups):
    return build_history()


def point(day, headcount, total_cost):
    return {"date": day, "headcount": headcount, "total_cost": total_cost}


def test_a_period_reads_its_first_day_each_month_end_between_and_its_last():
    """D64: 7 October 2025 to 7 October 2026 is 14 dates."""
    dates = queries.period_dates(date(2025, 10, 7), TODAY)

    assert (len(dates), dates[:2], dates[-2:]) == (
        14,
        [date(2025, 10, 7), date(2025, 10, 31)],
        [date(2026, 9, 30), TODAY],
    )


def test_a_month_end_first_or_last_day_is_read_once():
    dates = queries.period_dates(date(2024, 10, 31), date(2026, 9, 30))

    assert (len(dates), dates[0], dates[-1]) == (24, date(2024, 10, 31), date(2026, 9, 30))
    assert queries.period_dates(TODAY, TODAY) == [TODAY]


def test_a_leap_year_keeps_its_29_february():
    assert queries.period_dates(date(2024, 1, 15), date(2024, 3, 15)) == [
        date(2024, 1, 15),
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 15),
    ]


def test_trend_counts_the_people_employed_on_each_date_at_one_rate(history):
    """From 31 October 2024 to 7 October 2026. A4 and A5 are EUR, at 1.25 on every date although
    1.10 was in effect until October 2026. X1's last day is 31 March 2025, a month-end, so he
    counts on it and is gone by 30 April. B1 joins in January 2025, J1 to J4 through 2026, J4 on
    30 September, a month-end that counts him. Three raises land on 1 April 2026, and J5 joins on
    1 October, so the last date, `to`, has 11 people and 733,000, the bridge's end."""
    result = insight("trend", **{"from": date(2024, 10, 31)})

    assert result["measure"] == "total_cost"
    assert result["points"] == [
        point("2024-10-31", 6, "405000.00"),
        point("2024-11-30", 6, "405000.00"),
        point("2024-12-31", 6, "405000.00"),
        point("2025-01-31", 7, "470000.00"),
        point("2025-02-28", 7, "470000.00"),
        point("2025-03-31", 7, "470000.00"),
        point("2025-04-30", 6, "415000.00"),
        point("2025-05-31", 6, "415000.00"),
        point("2025-06-30", 6, "415000.00"),
        point("2025-07-31", 6, "415000.00"),
        point("2025-08-31", 6, "415000.00"),
        point("2025-09-30", 6, "415000.00"),
        point("2025-10-31", 6, "415000.00"),
        point("2025-11-30", 7, "485000.00"),
        point("2025-12-31", 7, "485000.00"),
        point("2026-01-31", 7, "485000.00"),
        point("2026-02-28", 8, "535000.00"),
        point("2026-03-31", 8, "535000.00"),
        point("2026-04-30", 8, "558000.00"),
        point("2026-05-31", 8, "558000.00"),
        point("2026-06-30", 9, "598000.00"),
        point("2026-07-31", 9, "598000.00"),
        point("2026-08-31", 9, "598000.00"),
        point("2026-09-30", 10, "688000.00"),
        point("2026-10-07", 11, "733000.00"),
    ]


def test_trend_starts_on_the_first_day_whatever_it_is(history):
    """15 June 2026 is J3's first day, so she counts on it: 9 people and 598,000, as on 30 June."""
    points = insight("trend", **{"from": date(2026, 6, 15)})["points"]

    assert points == [
        point("2026-06-15", 9, "598000.00"),
        point("2026-06-30", 9, "598000.00"),
        point("2026-07-31", 9, "598000.00"),
        point("2026-08-31", 9, "598000.00"),
        point("2026-09-30", 10, "688000.00"),
        point("2026-10-07", 11, "733000.00"),
    ]


def test_the_bridge_starts_and_ends_at_trends_first_and_last_points(history):
    """D64: one period, so the bridge's start and end are trend's first and last points."""
    period = {"from": date(2026, 6, 15)}
    points = insight("trend", **period)["points"]
    parts = {part["part"]: part for part in insight("cost-bridge", **period)["parts"]}

    assert (parts["start"]["people"], parts["start"]["amount"]) == (
        points[0]["headcount"],
        points[0]["total_cost"],
    )
    assert (parts["end"]["people"], parts["end"]["amount"]) == (
        points[-1]["headcount"],
        points[-1]["total_cost"],
    )


def test_a_trend_point_under_five_people_shows_its_headcount_alone(history):
    """Germany is A4 and A5, and J3 from 15 June 2026, over the default 12 months: the first day,
    eight month-ends to May, four from June and the last day."""
    points = insight("trend", country=["DE"])["points"]

    assert [(p["headcount"], p["total_cost"]) for p in points] == [(2, None)] * 9 + [(3, None)] * 5


def test_trend_reads_the_country_and_department_filters(history):
    """US engineering: A1 to A3 and X1 are four, then B1 makes five in January 2025, 100,000 +
    80,000 + 60,000 + 55,000 + 65,000 = 360,000. X1 leaves in March, and J1 makes five again in
    November, 375,000 with J1's 70,000. J2 makes six from February 2026, 425,000, the raises
    443,000 from April, J4 seven in September, 533,000, and J5 eight on the last day, 578,000.
    A sales hire is left out."""
    hire("S1", "US", 1_000_000, dept="sales")

    points = insight(
        "trend", country=["US"], department=["engineering"], **{"from": date(2024, 10, 31)}
    )["points"]

    assert [(p["headcount"], p["total_cost"]) for p in points] == (
        [(4, None)] * 3
        + [(5, "360000.00")] * 3
        + [(4, None)] * 7
        + [(5, "375000.00")] * 3
        + [(6, "425000.00")] * 2
        + [(6, "443000.00")] * 5
        + [(7, "533000.00")]
        + [(8, "578000.00")]
    )


def test_include_exited_does_not_apply_to_trend(history):
    """D62: trend counts the people employed on each date, so X1 is gone after March 2025."""
    assert insight("trend", include_exited=True) == insight("trend")


# cost-bridge (D62), over tests/insights/history.py


def part(name, people, amount, reason=None):
    return {"part": name, "people": people, "amount": amount, "reason": reason}


def test_a_year_back_is_the_same_day_or_the_months_last():
    assert queries.months_before(TODAY, 12) == date(2025, 10, 7)
    assert queries.months_before(date(2024, 2, 29), 12) == date(2023, 2, 28)


def test_the_bridge_adds_up_exactly_and_no_leavers_shows_every_amount(history):
    """From 7 Oct 2025 to 7 Oct 2026 at 1.25 for EUR. Start: A1 100,000, A2 80,000, A3 60,000,
    A4 50,000, A5 60,000 and B1 65,000, 415,000. Nobody left, so leavers is 0 and triggers
    nothing. Joiners J1 to J5: 70,000 + 50,000 + 40,000 + 90,000 + 45,000 = 295,000. Pay changes:
    A1 +10,000, A2 +8,000, A4 +5,000 = 23,000. End: 415,000 - 0 + 295,000 + 23,000 = 733,000."""
    result = insight("cost-bridge")

    assert (result["start_date"], result["end_date"]) == ("2025-10-07", "2026-10-07")
    assert result["parts"] == [
        part("start", 6, "415000.00"),
        part("leavers", 0, "0.00"),
        part("joiners", 5, "295000.00"),
        part("pay_changes", 6, "23000.00"),
        part("end", 11, "733000.00"),
    ]


def test_three_leavers_withhold_leavers_joiners_and_pay_changes(lookups):
    """D62: L1, L2 and L3 leave during the year. Any one of the three changes could be worked
    out from the other two and the totals, so all three show their people alone. Start gains
    30,000 + 36,000 + 30,000 (24,000 EUR) and stays shown, as does the end."""
    build_history(with_leavers=True)

    assert insight("cost-bridge")["parts"] == [
        part("start", 9, "511000.00"),
        part("leavers", 3, None, FEWER_THAN_5),
        part("joiners", 5, None, "withheld with the leavers"),
        part("pay_changes", 6, None, "withheld with the leavers"),
        part("end", 11, "733000.00"),
    ]


def test_pay_changes_summed_from_the_stayers_match_the_balancing_figure(lookups):
    """Fifteen salaries of 1,000.01 EUR at 1.25, five raised to 1,000.03, convert with half
    cents. Start 10,000.10 EUR is 12,500.13, end 10,000.20 is 12,500.25, leavers and joiners
    5,000.05 each are 6,250.06, so the balancing pay change is 0.12. Summed from the stayers,
    0.10 EUR is 0.13. They may differ by 3 cents per currency in the filter (D62)."""
    core_services.set_exchange_rate("EUR", "USD", Decimal("1.25"), date(2024, 1, 1))
    pay, raised = Decimal("1000.01"), Decimal("1000.03")
    for n in range(5):
        hire(f"S{n}", "DE", pay, raised_to=raised)
        hire(f"J{n}", "DE", pay, joined=date(2026, 1, 15))
        hire(f"L{n}", "DE", pay, left=date(2026, 2, 28))

    b = queries.bridge(filters(), fx.RateTable.load(TODAY))

    assert (b.pay_changes, b.summed_pay_changes) == (Decimal("0.12"), Decimal("0.13"))
    assert abs(b.pay_changes - b.summed_pay_changes) <= Decimal("0.03")
    parts = [p["amount"] for p in insight("cost-bridge")["parts"]]
    assert parts == ["12500.13", "-6250.06", "6250.06", "0.12", "12500.25"]


def test_include_exited_does_not_apply_to_the_bridge(lookups):
    """D62: with the box ticked, the three who left are still leavers, not stayers."""
    build_history(with_leavers=True)

    assert insight("cost-bridge", include_exited=True) == insight("cost-bridge")


def test_a_start_or_end_under_five_shows_its_people_alone(lookups):
    """Engineering: three stay on 10,000 and five join on 20,000, so the start has three people
    and the end eight, 30,000 + 100,000 = 130,000. Sales is the mirror: three stay and five
    leave. Each time the stayers are too few, so the other change goes with them."""
    for n in range(3):
        hire(f"E{n}", "US", 10_000)
        hire(f"S{n}", "US", 10_000, dept="sales")
    for n in range(5):
        hire(f"J{n}", "US", 20_000, joined=date(2026, 1, 15))
        hire(f"L{n}", "US", 20_000, left=date(2026, 1, 31), dept="sales")

    assert insight("cost-bridge", department=["engineering"])["parts"] == [
        part("start", 3, None, FEWER_THAN_5),
        part("leavers", 0, "0.00"),
        part("joiners", 5, None, "withheld with the pay changes"),
        part("pay_changes", 3, None, FEWER_THAN_5),
        part("end", 8, "130000.00"),
    ]
    assert insight("cost-bridge", department=["sales"])["parts"] == [
        part("start", 8, "130000.00"),
        part("leavers", 5, None, "withheld with the pay changes"),
        part("joiners", 0, "0.00"),
        part("pay_changes", 3, None, FEWER_THAN_5),
        part("end", 3, None, FEWER_THAN_5),
    ]


def test_four_leavers_are_withheld_and_five_are_shown(lookups):
    """Five stay on 10,000 and four leave on 20,000: start 130,000, end 50,000, the leavers too
    few and the pay changes with them. A fifth leaver shows every part: start 150,000, leavers
    -100,000, no pay change, end 50,000."""
    for n in range(5):
        hire(f"S{n}", "US", 10_000)
    for n in range(4):
        hire(f"L{n}", "US", 20_000, left=date(2026, 1, 31))

    assert insight("cost-bridge")["parts"] == [
        part("start", 9, "130000.00"),
        part("leavers", 4, None, FEWER_THAN_5),
        part("joiners", 0, "0.00"),
        part("pay_changes", 5, None, "withheld with the leavers"),
        part("end", 5, "50000.00"),
    ]

    hire("L4", "US", 20_000, left=date(2026, 1, 31))

    assert insight("cost-bridge")["parts"] == [
        part("start", 10, "150000.00"),
        part("leavers", 5, "-100000.00"),
        part("joiners", 0, "0.00"),
        part("pay_changes", 5, "0.00"),
        part("end", 5, "50000.00"),
    ]


def test_two_short_changes_each_say_so_and_the_third_names_the_first(lookups):
    """Five stay on 10,000, three leave on 20,000 and two join on 30,000: start and end are both
    50,000 + 60,000 = 110,000."""
    for n in range(5):
        hire(f"S{n}", "US", 10_000)
    for n in range(3):
        hire(f"L{n}", "US", 20_000, left=date(2026, 1, 31))
    for n in range(2):
        hire(f"J{n}", "US", 30_000, joined=date(2026, 1, 15))

    assert insight("cost-bridge")["parts"] == [
        part("start", 8, "110000.00"),
        part("leavers", 3, None, FEWER_THAN_5),
        part("joiners", 2, None, FEWER_THAN_5),
        part("pay_changes", 5, None, "withheld with the leavers"),
        part("end", 7, "110000.00"),
    ]


def test_the_bridge_counts_who_is_employed_on_its_two_dates(lookups):
    """The start is 7 October 2025. A last day of 6 October is in neither date, a last day of
    the 7th makes a leaver, and joining on `on` makes a joiner."""
    for n in range(5):
        hire(f"S{n}", "US", 10_000)
    hire("Gone", "US", 20_000, left=date(2025, 10, 6))
    hire("Left", "US", 30_000, left=date(2025, 10, 7))
    hire("New", "US", 40_000, joined=TODAY)

    people = [p["people"] for p in insight("cost-bridge")["parts"]]

    assert people == [6, 1, 1, 5, 6]


# The period and what it cost (D64)


@pytest.mark.parametrize("name", sorted(queries.INSIGHTS))
def test_every_insight_names_its_period(people, name):
    """`to` today and `from` a year before it when not given, else as given."""
    assert (insight(name)["from"], insight(name)["to"]) == ("2025-10-07", "2026-10-07")
    given = insight(name, **{"from": date(2026, 4, 1), "to": NEW_YEAR})
    assert (given["from"], given["to"]) == ("2026-04-01", "2027-01-01")


def test_a_year_fraction_counts_each_day_against_its_own_year():
    assert queries.year_fraction(date(2024, 1, 1), date(2024, 12, 31)) == 1
    assert queries.year_fraction(date(2025, 1, 1), date(2025, 12, 31)) == 1
    assert queries.year_fraction(date(2023, 12, 1), date(2024, 1, 31)) == (
        Decimal(31) / 365 + Decimal(31) / 366
    )


def pay_all_year(name, base, *, raised=None, left=None):
    """A US employee since 2020 on one BASE line, raised on 1 July 2024 or gone after `left`."""
    employee = EmployeeFactory(
        full_name=name, country=country("US"), joining_date=date(2020, 1, 1), last_date=left
    )
    first_ends = date(2024, 7, 1) if raised else (left + timedelta(days=1) if left else None)
    CompensationRecordFactory(
        employee=employee,
        lines={"BASE": Decimal(base)},
        effective_from=date(2020, 1, 1),
        effective_to=first_ends,
    )
    if raised:
        CompensationRecordFactory(
            employee=employee, lines={"BASE": Decimal(raised)}, effective_from=date(2024, 7, 1)
        )


YEAR_2024 = {"from": date(2024, 1, 1), "to": date(2024, 12, 31)}


def test_spent_in_period_counts_each_day_a_record_was_current(lookups):
    """2024 has 366 days, so 36,600 a year is 100 a day. Four on 36,600 all year are 146,400.
    A fifth is raised to 73,200 on 1 July: 182 days at 100 and 184 at 200 are 55,000. A sixth
    leaves on 31 March, after 91 days, 9,100. 146,400 + 55,000 + 9,100 = 210,500, six people."""
    for n in range(4):
        pay_all_year(f"P{n}", 36_600)
    pay_all_year("Raised", 36_600, raised=73_200)
    pay_all_year("Left", 36_600, left=date(2024, 3, 31))

    result = insight("summary", **YEAR_2024)

    assert result["spent"] == {"headcount": 6, "total_cost": "210500.00"}
    assert (result["headcount"], result["total_cost"]) == (5, "219600.00")


def test_spent_in_period_is_withheld_under_five_and_ignores_include_exited(lookups):
    """Four people, one of whom left: the period counts the people employed in it, as trend
    does, whatever Include exited says (D59, D64)."""
    for n in range(3):
        pay_all_year(f"P{n}", 36_600)
    pay_all_year("Left", 36_600, left=date(2024, 3, 31))

    spent = insight("summary", **YEAR_2024)["spent"]

    assert spent == {"headcount": 4, "total_cost": None}
    assert insight("summary", include_exited=True, **YEAR_2024)["spent"] == spent


# by-tenure (D62)


def tenure(*headcounts_and_medians):
    keys = ("under_1", "1_to_3", "3_to_5", "5_to_10", "10_plus")
    labels = ("Under 1 year", "1 to 3 years", "3 to 5 years", "5 to 10 years", "10 years or more")
    return [
        {"band": key, "label": label, "headcount": headcount, "median_gross": median}
        for key, label, (headcount, median) in zip(
            keys, labels, headcounts_and_medians, strict=True
        )
    ]


@pytest.mark.parametrize(
    ("level", "rows"),
    [
        ("all", tenure((0, None), (0, None), (0, None), (27, "75000.00"), (0, None))),
        ("1", tenure((0, None), (0, None), (0, None), (4, None), (0, None))),
        ("3", tenure((0, None), (0, None), (0, None), (5, "87500.00"), (0, None))),
        ("6", tenure((0, None), (0, None), (0, None), (3, None), (0, None))),
    ],
)
def test_by_tenure_within_a_level(people, level, rows):
    """DESIGN 9's people joined on 1 January 2020, six years before `on`. Level 3 is U5, U6, I3,
    I9 and D2, whose median is D2's 87,500. Level 1 has four, U1, U2, I1 and I7, and level 6
    three, under five (D59)."""
    result = insight("by-tenure", control={"level": level})

    assert (result["level"], result["rows"]) == (level, rows)


def test_completed_years_count_whole_years_to_the_anniversary():
    """A day short of an anniversary is a year fewer. Someone who joined on 29 February has their
    anniversary on 28 February in a year without one."""
    years = queries.completed_years

    assert years(date(2020, 10, 8), TODAY) == 5
    assert years(date(2020, 10, 7), TODAY) == 6
    assert years(date(2020, 2, 29), date(2026, 2, 27)) == 5
    assert years(date(2020, 2, 29), date(2026, 2, 28)) == 6
    assert years(date(2020, 2, 29), date(2024, 2, 28)) == 3
    assert years(date(2020, 2, 29), date(2024, 2, 29)) == 4


def test_each_tenure_band_starts_on_its_anniversary(lookups):
    """On 7 October 2026: a day short of a year is under 1, exactly 1 year is 1 to 3, exactly 3
    is 3 to 5, exactly 5 is 5 to 10, a day short of 10 years is 5 to 10, and exactly 10 is 10 or
    more."""
    for joined in (
        date(2025, 10, 8),
        date(2025, 10, 7),
        date(2023, 10, 7),
        date(2021, 10, 7),
        date(2016, 10, 8),
        date(2016, 10, 7),
    ):
        CompensationRecordFactory(
            employee=EmployeeFactory(country=country("US"), joining_date=joined),
            lines={"BASE": Decimal(100_000)},
        )

    rows = insight("by-tenure")["rows"]

    assert [row["headcount"] for row in rows] == [1, 1, 1, 2, 1]


def test_a_leavers_tenure_is_counted_to_their_last_date(lookups):
    """Joined 1 March 2016 and left 31 January 2026: 9 years at the last date, though 10 by
    `on`, so 5 to 10 with Include exited."""
    employee = EmployeeFactory(
        country=country("US"), joining_date=date(2016, 3, 1), last_date=date(2026, 1, 31)
    )
    CompensationRecordFactory(
        employee=employee,
        lines={"BASE": Decimal(100_000)},
        effective_to=date(2026, 2, 1),
    )

    rows = insight("by-tenure", include_exited=True)["rows"]

    assert [row["headcount"] for row in rows] == [0, 0, 0, 1, 0]


# The Netherlands in its own currency, so no rate is needed

NL_LOCAL = {"country": ["NL"], "currency": "local"}


def hire_nl(gender="female", gross=50_000, *, level=1, bonus=0, lines=None):
    CompensationRecordFactory(
        employee=EmployeeFactory(country=country("NL"), gender=gender, level=level),
        lines=lines or {"BASE": Decimal(gross)},
        bonus_annual=Decimal(bonus),
        effective_from=date(2024, 1, 1),
    )


# cost-mix (D62)


def segment(code, name, share):
    return {"code": code, "name": name, "share_pct": share}


def mix(code, name, headcount, segments=None, reason=None):
    return {
        "country": {"code": code, "name": name},
        "headcount": headcount,
        "segments": segments,
        "reason": reason,
    }


def test_cost_mix_gives_each_country_its_shares_of_total_cost(people):
    """DESIGN 9's lines are fixed shares of gross. India: base 0.6, HRA 0.25, allowances 0.15
    and employer 0.12, of a total cost of 1.12. The US: base 1, employer 0.1, of 1.1. Nobody has
    a bonus. Germany has four people and the UK one, so they show their headcount alone. The
    segments come once, in the order the card stacks them."""
    result = insight("cost-mix")

    assert result["view"] == "cost"
    assert result["segments"] == [
        {"code": "BASE", "name": "Base salary"},
        {"code": "HRA", "name": "House rent allowance"},
        {"code": "ALLOWANCES", "name": "Allowances"},
        {"code": "BONUS", "name": "Bonus"},
        {"code": "EMPLOYER_CONTRIBUTION", "name": "Employer contribution"},
    ]
    assert result["rows"] == [
        mix("DE", "Germany", 4, reason=FEWER_THAN_5),
        mix(
            "IN",
            "India",
            12,
            [
                segment("BASE", "Base salary", "53.6"),
                segment("HRA", "House rent allowance", "22.3"),
                segment("ALLOWANCES", "Allowances", "13.4"),
                segment("BONUS", "Bonus", "0.0"),
                segment("EMPLOYER_CONTRIBUTION", "Employer contribution", "10.7"),
            ],
        ),
        mix("NL", "Netherlands", 0),
        mix("SG", "Singapore", 0),
        mix("GB", "United Kingdom", 1, reason=FEWER_THAN_5),
        mix(
            "US",
            "United States",
            10,
            [
                segment("BASE", "Base salary", "90.9"),
                segment("BONUS", "Bonus", "0.0"),
                segment("EMPLOYER_CONTRIBUTION", "Employer contribution", "9.1"),
            ],
        ),
    ]


def test_cost_mix_take_home_splits_gross_into_net_and_each_deduction(people):
    """India's tax is 0.1 of gross and the US's 0.2."""
    result = insight("cost-mix", control={"view": "take_home"}, country=["IN", "US"])

    assert result["segments"] == [
        {"code": "NET", "name": "Net pay"},
        {"code": "TAX", "name": "Income tax"},
    ]
    assert result["rows"] == [
        mix(
            "IN",
            "India",
            12,
            [segment("NET", "Net pay", "90.0"), segment("TAX", "Income tax", "10.0")],
        ),
        mix(
            "US",
            "United States",
            10,
            [segment("NET", "Net pay", "80.0"), segment("TAX", "Income tax", "20.0")],
        ),
    ]


def test_five_people_show_a_bar_and_four_their_headcount_alone(people):
    """US engineering is U1 to U5, German engineering D1 to D4."""
    rows = insight("cost-mix", country=["DE", "US"], department=["engineering"])["rows"]

    assert [(row["headcount"], row["reason"]) for row in rows] == [(4, FEWER_THAN_5), (5, None)]
    assert rows[1]["segments"] is not None


def test_a_bonus_held_by_four_hides_the_bar_and_by_five_shows_it(lookups):
    """Six on 50,000, four with a bonus of 5,000: the bonus share would give back what those four
    are paid. A seventh with a bonus makes five: base 350,000 and bonus 25,000 of 375,000, so
    93.3% and 6.7%."""
    for bonus in (5000, 5000, 5000, 5000, 0, 0):
        hire_nl(bonus=bonus)

    (row,) = insight("cost-mix", **NL_LOCAL)["rows"]

    assert row == mix("NL", "Netherlands", 6, reason="Bonus held by fewer than 5 people")

    hire_nl(bonus=5000)
    result = insight("cost-mix", **NL_LOCAL)

    assert result["rows"] == [
        mix(
            "NL",
            "Netherlands",
            7,
            [segment("BASE", "Base salary", "93.3"), segment("BONUS", "Bonus", "6.7")],
        )
    ]


def test_a_deduction_held_by_four_hides_the_take_home_bar(lookups):
    """Six people, four of them with a tax line: net pay and tax would give back their pay."""
    for taxed in (True, True, True, True, False, False):
        tax = {"TAX": Decimal(10_000)} if taxed else {}
        hire_nl(lines={"BASE": Decimal(50_000), **tax})

    result = insight("cost-mix", control={"view": "take_home"}, **NL_LOCAL)

    assert result["rows"] == [
        mix("NL", "Netherlands", 6, reason="Income tax held by fewer than 5 people")
    ]
    assert result["segments"] == []


# gender-gap's views (D62)


NETHERLANDS = {"code": "NL", "name": "Netherlands"}


def bonus_side(headcount, receiving, pct, median_bonus):
    return {
        "headcount": headcount,
        "receiving": receiving,
        "receiving_pct": pct,
        "median_bonus": median_bonus,
    }


def bonus_view() -> dict:
    """The Netherlands' row; overall is the same group."""
    (row, overall) = insight("gender-gap", control={"view": "bonus"}, **NL_LOCAL)["rows"]
    assert overall == {**row, "country": None}
    return row


def test_the_bonus_view_compares_who_receives_one_and_how_much(lookups):
    """Five of six women receive 1,000 to 5,000, mean and median 3,000. All six men receive
    2,000 to 6,000 and 10,000, mean 5,000 and median (4,000 + 5,000) / 2 = 4,500. The mean gap
    is (5,000 - 3,000) / 5,000 = 40.0% of men's bonus and the median gap (4,500 - 3,000) / 4,500
    = 33.3%. No mean amount is published (D62). The other and the undisclosed employee are
    counted beside and change nothing."""
    for bonus in (1000, 2000, 3000, 4000, 5000, 0):
        hire_nl("female", bonus=bonus)
    for bonus in (2000, 3000, 4000, 5000, 6000, 10_000):
        hire_nl("male", bonus=bonus)
    hire_nl("other", bonus=9000)
    hire_nl("undisclosed")

    result = insight("gender-gap", control={"view": "bonus"}, **NL_LOCAL)

    assert result["view"] == "bonus"
    assert bonus_view() == {
        "country": NETHERLANDS,
        "female": bonus_side(6, 5, "83.3", "3000.00"),
        "male": bonus_side(6, 6, "100.0", "4500.00"),
        "other_count": 1,
        "undisclosed_count": 1,
        "mean_gap_pct": "40.0",
        "median_gap_pct": "33.3",
        "reason": None,
    }


def test_a_bonus_gap_needs_five_of_each_with_a_bonus(lookups):
    """Four of six women receive a bonus: the shares show, the medians and gaps do not. A fifth
    woman with one shows them: 1,000 to 5,000 against 2,000 to 7,000, means and medians 3,000
    and 4,500, so both gaps are 33.3%."""
    for bonus in (1000, 2000, 3000, 4000, 0, 0):
        hire_nl("female", bonus=bonus)
    for bonus in (2000, 3000, 4000, 5000, 6000, 7000):
        hire_nl("male", bonus=bonus)

    row = bonus_view()

    assert (row["female"], row["male"]) == (
        bonus_side(6, 4, "66.7", None),
        bonus_side(6, 6, "100.0", None),
    )
    assert (row["mean_gap_pct"], row["median_gap_pct"], row["reason"]) == (
        None,
        None,
        "fewer than 5 women with a bonus",
    )

    hire_nl("female", bonus=5000)
    row = bonus_view()

    assert row["female"] == bonus_side(7, 5, "71.4", "3000.00")
    assert (row["mean_gap_pct"], row["median_gap_pct"], row["reason"]) == ("33.3", "33.3", None)


def test_a_bonus_reason_names_both_sides_when_both_are_short(lookups):
    for bonus in (1000, 2000, 3000, 4000, 0):
        hire_nl("female", bonus=bonus)
    for bonus in (1000, 2000, 3000, 0, 0):
        hire_nl("male", bonus=bonus)

    assert bonus_view()["reason"] == "fewer than 5 women and fewer than 5 men with a bonus"


def test_bonus_shares_need_five_women_and_five_men(lookups):
    for _ in range(4):
        hire_nl("female", bonus=1000)
    for _ in range(5):
        hire_nl("male", bonus=1000)

    row = bonus_view()

    assert (row["female"], row["male"], row["reason"]) == (
        bonus_side(4, None, None, None),
        bonus_side(5, None, None, None),
        WOMEN,
    )


def quartile(number, women, men, women_pct, men_pct):
    return {
        "quartile": number,
        "headcount": women + men,
        "female": women,
        "male": men,
        "female_pct": women_pct,
        "male_pct": men_pct,
    }


def test_the_quartiles_rank_women_and_men_and_break_a_tie_by_employee_id(lookups):
    """Ten women and ten men cut at 5, 10 and 15. The fifth and sixth both earn 54,000: the man,
    hired first, closes the lowest quartile and the woman opens the next, where ranking women
    first would swap them. Other and undisclosed are counted beside and never ranked: on 30,000
    the one who is other would be lowest (D62)."""
    first_six = [
        (50_000, "female"),
        (51_000, "male"),
        (52_000, "female"),
        (53_000, "male"),
        (54_000, "male"),
        (54_000, "female"),
    ]
    rest = [(56_000 + 1000 * n, ("female", "male")[n % 2]) for n in range(14)]
    for gross, gender in first_six + rest:
        hire_nl(gender, gross)
    hire_nl("other", 30_000)
    hire_nl("undisclosed", 200_000)

    result = insight("gender-gap", control={"view": "quartiles"}, **NL_LOCAL)

    assert (
        result["headcount"],
        result["other_count"],
        result["undisclosed_count"],
        result["reason"],
    ) == (20, 1, 1, None)
    assert result["quartiles"] == [
        quartile(1, 2, 3, "40.0", "60.0"),
        quartile(2, 3, 2, "60.0", "40.0"),
        quartile(3, 3, 2, "60.0", "40.0"),
        quartile(4, 2, 3, "40.0", "60.0"),
    ]


def test_quartiles_need_twenty_women_and_men_five_of_each(lookups):
    """Four women and fifteen men are 19, and the undisclosed one is not ranked. A sixteenth man
    makes 20, with four women. A fifth woman makes 21, cut at 5, 10 and 15."""
    for _ in range(4):
        hire_nl("female")
    for _ in range(15):
        hire_nl("male")
    hire_nl("undisclosed")

    def quartiles():
        result = insight("gender-gap", control={"view": "quartiles"}, **NL_LOCAL)
        sizes = [q["headcount"] for q in result["quartiles"]] if result["quartiles"] else None
        return (result["headcount"], sizes, result["reason"])

    assert quartiles() == (19, None, "fewer than 20 people")
    hire_nl("male")
    assert quartiles() == (20, None, WOMEN)
    hire_nl("female")
    assert quartiles() == (21, [5, 5, 5, 6], None)


def test_the_by_level_view_flags_a_mean_gap_of_five_percent_either_way(lookups):
    """Level 1: women's mean 46,000 and median 44,000, men's 50,000 and 48,000, gaps of 8.0% and
    8.3%, flagged. Level 2: 95,000 against 100,000, exactly 5.0%, flagged. Level 3: 95,001
    against 100,000 is 4.999%, shown as 5.0 and not flagged, since the flag reads the gap before
    rounding. Level 4: women 60,000, men 55,000, -9.1%, flagged as well. Level 5 has four women,
    and level 6 nobody. The other and the undisclosed employee are counted per country."""
    for women, men, level in (
        ((40_000, 42_000, 44_000, 46_000, 58_000), (44_000, 46_000, 48_000, 50_000, 62_000), 1),
        ((95_000,) * 5, (100_000,) * 5, 2),
        ((95_001,) * 5, (100_000,) * 5, 3),
        ((60_000,) * 5, (55_000,) * 5, 4),
        ((50_000,) * 4, (50_000,) * 5, 5),
    ):
        for gross in women:
            hire_nl("female", gross, level=level)
        for gross in men:
            hire_nl("male", gross, level=level)
    hire_nl("other", 70_000, level=1)
    hire_nl("undisclosed", 70_000, level=4)

    result = insight("gender-gap", control={"view": "by_level"}, **NL_LOCAL)

    def level_row(level, women, men, mean_gap=None, median_gap=None, flagged=False, reason=None):
        return {
            "country": NETHERLANDS,
            "level": level,
            "female": {"headcount": women[0], "median_gross": women[1]},
            "male": {"headcount": men[0], "median_gross": men[1]},
            "mean_gap_pct": mean_gap,
            "median_gap_pct": median_gap,
            "flagged": flagged,
            "reason": reason,
        }

    assert result["rows"] == [
        level_row(1, (5, "44000.00"), (5, "48000.00"), "8.0", "8.3", True),
        level_row(2, (5, "95000.00"), (5, "100000.00"), "5.0", "5.0", True),
        level_row(3, (5, "95001.00"), (5, "100000.00"), "5.0", "5.0", False),
        level_row(4, (5, "60000.00"), (5, "55000.00"), "-9.1", "-9.1", True),
        level_row(5, (4, None), (5, None), reason=WOMEN),
        level_row(6, (0, None), (0, None)),
    ]
    assert result["others"] == [{"country": NETHERLANDS, "other_count": 1, "undisclosed_count": 1}]
