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


# distribution


def bands(edges: list[str], top: str, counts: list[int]) -> list[dict]:
    """Twelve bands from their lower edges, the last band's upper edge and the counts."""
    tops = [*edges[1:], top]
    return [
        {"index": index, "from": edges[index], "to": tops[index], "count": counts[index]}
        for index in range(12)
    ]


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
            spread(
                "USD",
                USD_RATES,
                10,
                "100900.00",
                "189100.00",
                ("109000.00", "145000.00", "181000.00"),
                ["100900.00", "108250.00", "115600.00", "122950.00", "130300.00", "137650.00"]
                + ["145000.00", "152350.00", "159700.00", "167050.00", "174400.00", "181750.00"],
                [1, 1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1],
            ),
        ),
        (
            # 170,000 sits exactly on band 6's lower edge and is counted in band 6.
            {"department": ["sales"]},
            spread(
                "USD",
                USD_RATES,
                5,
                "150400.00",
                "189600.00",
                ("154000.00", "170000.00", "186000.00"),
                ["150400.00", "153666.67", "156933.33", "160200.00", "163466.67", "166733.33"]
                + ["170000.00", "173266.67", "176533.33", "179800.00", "183066.67", "186333.33"],
                [1, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 1],
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
            {"on": NEW_YEAR},
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
            spread(
                "INR",
                {"label": "local currency (INR)", "effective_from": None},
                12,
                "822000.00",
                "2978000.00",
                ("1020000.00", "1900000.00", "2780000.00"),
                ["822000.00", "1001666.67", "1181333.33", "1361000.00", "1540666.67"]
                + ["1720333.33", "1900000.00", "2079666.67", "2259333.33", "2439000.00"]
                + ["2618666.67", "2798333.33"],
                [2, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 2],
            ),
        ),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_distribution(people, given, expected):
    assert insight("distribution", **given) == expected


def test_a_distribution_whose_p1_is_its_p99_is_one_band(people):
    """SPEC section 9: five people on one salary leave no width to split into twelve."""
    for n in range(5):
        CompensationRecordFactory(
            employee=EmployeeFactory(country=country("NL"), full_name=f"N{n + 1}"),
            lines={"BASE": Decimal(70_000)},
            effective_from=date(2024, 1, 1),
        )

    result = insight("distribution", country=["NL"])

    assert (result["headcount"], result["p1"], result["p99"]) == (5, "87500.00", "87500.00")
    assert result["bands"] == [{"index": 0, "from": "87500.00", "to": "87500.00", "count": 5}]
    assert result["markers"] == {"p10": "87500.00", "p50": "87500.00", "p90": "87500.00"}


def test_a_distribution_of_under_five_people_is_its_headcount_alone(people):
    result = insight("distribution", country=["GB"])

    assert [result[key] for key in ("headcount", "p1", "p99", "bands", "markers")] == [
        1,
        None,
        None,
        None,
        None,
    ]


def test_one_value_is_every_percentile():
    assert queries.percentiles([Decimal("5.00")]) == [Decimal("5.00")] * 99


# by-level


def level(number, headcount, *figures):
    names = ("min", "p25", "median", "p75", "max")
    return {
        "level": number,
        "headcount": headcount,
        **dict(zip(names, figures or (None,) * 5, strict=True)),
    }


SAME_L2 = level(2, 6, "12500.00", "36250.00", "68750.00", "108750.00", "130000.00")
SAME_L4 = level(4, 5, "17500.00", "32500.00", "100000.00", "160000.00", "170000.00")


@pytest.mark.parametrize(
    ("given", "rows"),
    [
        (
            # Level 3 has exactly five people, the boundary of the small-group rule.
            {},
            [
                level(1, 4),
                SAME_L2,
                level(3, 5, "15000.00", "30000.00", "87500.00", "140000.00", "150000.00"),
                SAME_L4,
                level(5, 4),
                level(6, 3),
            ],
        ),
        (
            {"country": ["US"]},
            [level(1, 2), level(2, 2), level(3, 2), level(4, 2), level(5, 1), level(6, 1)],
        ),
        (
            {"department": ["engineering"]},
            [level(1, 3), level(2, 4), level(3, 3), level(4, 2), level(5, 2), level(6, 1)],
        ),
        (
            {"include_exited": True},
            [
                level(1, 5, "6250.00", "10000.00", "25000.00", "100000.00", "110000.00"),
                SAME_L2,
                level(3, 6, "15000.00", "44375.00", "103750.00", "135000.00", "150000.00"),
                SAME_L4,
                level(5, 4),
                level(6, 3),
            ],
        ),
        (
            {"on": NEW_YEAR},
            [
                level(1, 4),
                SAME_L2,
                level(3, 6, "15000.00", "44375.00", "106250.00", "136250.00", "150000.00"),
                SAME_L4,
                level(5, 4),
                level(6, 3),
            ],
        ),
        (
            {"currency": "eur"},
            [
                level(1, 4),
                level(2, 6, "10000.00", "29000.00", "55000.00", "87000.00", "104000.00"),
                level(3, 5, "12000.00", "24000.00", "70000.00", "112000.00", "120000.00"),
                level(4, 5, "14000.00", "26000.00", "80000.00", "128000.00", "136000.00"),
                level(5, 4),
                level(6, 3),
            ],
        ),
        (
            {"country": ["IN"], "currency": "local"},
            [level(number, 2) for number in range(1, 7)],
        ),
    ],
    ids=["no filter", "country", "department", "include_exited", "on", "eur", "local"],
)
def test_by_level(people, given, rows):
    assert insight("by-level", **given)["rows"] == rows


# gender-gap

SMALL = "group too small"


def gap(code, name, women, women_median, men, men_median, pct=None, other=0, undisclosed=0):
    return {
        "country": {"code": code, "name": name} if code else None,
        "female": {"headcount": women, "median_gross": women_median},
        "male": {"headcount": men, "median_gross": men_median},
        "other_count": other,
        "undisclosed_count": undisclosed,
        "gap_pct": pct,
        "reason": None if pct is not None else SMALL,
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
                gap("DE", "Germany", 2, None, 2, None),
                gap("IN", "India", 6, "25000.00", 6, "22500.00", "-11.1"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None),
                gap("US", "United States", 4, None, 6, "125000.00"),
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
                gap("DE", "Germany", 2, None, 2, None),
                gap("IN", "India", 3, None, 3, None),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 0, None, 0, None),
                gap("US", "United States", 0, None, 5, "120000.00"),
                gap(None, None, 5, "22500.00", 10, "105000.00", "78.6"),
            ],
        ),
        (
            {"include_exited": True},
            [
                gap("DE", "Germany", 2, None, 2, None),
                gap("IN", "India", 7, "22500.00", 6, "22500.00", "0.0"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None),
                gap("US", "United States", 4, None, 7, "120000.00"),
                gap(None, None, 14, "50000.00", 15, "100000.00", "50.0"),
            ],
        ),
        (
            {"on": NEW_YEAR},
            [
                gap("DE", "Germany", 2, None, 3, None),
                gap("IN", "India", 6, "25000.00", 6, "22500.00", "-11.1"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None),
                gap("US", "United States", 4, None, 6, "130000.00"),
                gap(None, None, 13, "62500.00", 15, "110000.00", "43.2"),
            ],
        ),
        (
            {"currency": "eur"},
            [
                gap("DE", "Germany", 2, None, 2, None),
                gap("IN", "India", 6, "20000.00", 6, "18000.00", "-11.1"),
                *NOBODY_ELSE,
                gap("GB", "United Kingdom", 1, None, 0, None),
                gap("US", "United States", 4, None, 6, "100000.00"),
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
