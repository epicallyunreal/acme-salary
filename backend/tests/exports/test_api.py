"""GET /api/v1/exports/employees/ and /exports/insights/<name>/ over HTTP (SPEC F6, D60).

The people are DESIGN section 9's thirty, and every expected figure is a literal worked out from
that table; the insight ones are the same figures tests/insights asserts on the cards.
"""

import csv
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from tests.factories import CompensationRecordFactory, EmployeeFactory, country, department
from tests.insights.fixture import build_fixture, in_lines

pytestmark = pytest.mark.django_db

EMPLOYEES = "/api/v1/exports/employees/"
INSIGHT = "/api/v1/exports/insights/{}/"
RATES = "October 2026 rates"
HEADER = [
    "Employee code",
    "Legacy code",
    "Full name",
    "Email",
    "Department",
    "Designation",
    "Level",
    "Country",
    "Currency",
    "Gross (local)",
    "Bonus (local)",
    "Gross (USD)",
    "Status",
    "Joining date",
    "Last date",
    "Effective from",
    "Version",
]


@pytest.fixture
def people(lookups):
    return build_fixture()


@pytest.fixture
def asha(people):
    """One more Indian engineer, with a legacy code and a bonus, for a row read cell by cell."""
    employee = EmployeeFactory(
        full_name="Asha Rao",
        email="asha.rao@acme.example",
        legacy_code="EMP-0042",
        department=department("engineering"),
        country=country("IN"),
        level=3,
    )
    CompensationRecordFactory(
        employee=employee,
        lines=in_lines(Decimal(1_800_000)),
        bonus_annual=Decimal(200_000),
        effective_from=date(2024, 1, 1),
    )
    return employee


def content(response) -> bytes:
    return b"".join(response.streaming_content) if response.streaming else response.content


def csv_rows(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(content(response).decode("utf-8-sig"))))


def xlsx_rows(response) -> list[list]:
    sheet = load_workbook(io.BytesIO(content(response))).active
    return [[cell.value for cell in row] for row in sheet.iter_rows()]


def json_body(response) -> dict:
    return json.loads(content(response))


# The directory


@pytest.mark.parametrize("file", ["csv", "xlsx", "json"])
def test_a_filtered_export_has_exactly_the_rows_the_pages_show(api, people, file):
    """SPEC F6: the whole filtered set in the grid's order, whatever page was asked for."""
    query = {"country": "IN,US", "level": "1,2,3", "ordering": "-gross"}
    codes = []
    for page in (1, 2, 3):
        body = api.get("/api/v1/employees/", {**query, "page": page, "page_size": 5}).json()
        codes += [row["employee_code"] for row in body["results"]]

    response = api.get(EMPLOYEES, {**query, "file": file, "page": 2, "page_size": 5})

    if file == "csv":
        exported = [row[0] for row in csv_rows(response)[1:]]
    elif file == "xlsx":
        exported = [row[0] for row in xlsx_rows(response)[1:]]
    else:
        exported = [row["employee_code"] for row in json_body(response)["rows"]]
    assert (body["count"], len(codes)) == (14, 14)
    assert exported == codes


def test_the_csv_has_seventeen_columns_in_spec_order(api, asha):
    rows = csv_rows(api.get(EMPLOYEES, {"file": "csv", "search": "asha"}))

    assert rows == [
        HEADER,
        [
            asha.employee_code,
            "EMP-0042",
            "Asha Rao",
            "asha.rao@acme.example",
            "Engineering",
            "Senior Engineer",
            "3",
            "India",
            "INR",
            "2000000.00",
            "200000.00",
            "25000.00",
            "active",
            "2020-01-01",
            "",
            "2024-01-01",
            "1",
        ],
    ]


def test_the_reporting_column_is_headed_with_its_currency(api, asha):
    rows = xlsx_rows(api.get(EMPLOYEES, {"file": "xlsx", "search": "asha", "currency": "eur"}))

    assert rows[0][11] == "Gross (EUR)"
    assert rows[1][9:12] == [2000000, 200000, 20000]


def test_the_json_names_each_value_and_the_filters_applied(api, asha):
    body = json_body(
        api.get(EMPLOYEES, {"file": "json", "search": "asha", "country": "IN", "page": 2})
    )

    assert body == {
        "generated_at": "2026-10-07T09:00:00+00:00",
        "filters": {"search": "asha", "country": "IN", "on": "2026-10-07", "currency": "USD"},
        "rows": [
            {
                "employee_code": asha.employee_code,
                "legacy_code": "EMP-0042",
                "full_name": "Asha Rao",
                "email": "asha.rao@acme.example",
                "department": "Engineering",
                "designation": "Senior Engineer",
                "level": 3,
                "country": "India",
                "currency": "INR",
                "gross_local": "2000000.00",
                "bonus_local": "200000.00",
                "gross_reporting": "25000.00",
                "status": "active",
                "joining_date": "2020-01-01",
                "last_date": None,
                "effective_from": "2024-01-01",
                "version": 1,
            }
        ],
    }


def test_a_name_starting_with_equals_is_escaped_in_csv_and_xlsx(api, people):
    """SPEC F6: a spreadsheet shows the text instead of running it. JSON keeps it as it is."""
    EmployeeFactory(full_name="=cmd|' /C calc'!A0", email="calc@acme.example")
    query = {"search": "calc"}

    (_, csv_row) = csv_rows(api.get(EMPLOYEES, {**query, "file": "csv"}))
    sheet = load_workbook(io.BytesIO(content(api.get(EMPLOYEES, {**query, "file": "xlsx"}))))
    xlsx_cell = sheet.active["C2"]
    (json_row,) = json_body(api.get(EMPLOYEES, {**query, "file": "json"}))["rows"]

    assert csv_row[2] == "'=cmd|' /C calc'!A0"
    assert (xlsx_cell.value, xlsx_cell.data_type) == ("'=cmd|' /C calc'!A0", "s")
    assert json_row["full_name"] == "=cmd|' /C calc'!A0"


def test_an_employee_with_no_live_record_is_exported_without_amounts(api, people):
    """D50: an exit before pay started leaves the only record cancelled."""
    employee = EmployeeFactory(full_name="Never Paid", email="never@acme.example")
    CompensationRecordFactory(employee=employee, cancelled_at=datetime(2026, 9, 1, tzinfo=UTC))

    (_, row) = csv_rows(api.get(EMPLOYEES, {"file": "csv", "search": "never"}))

    assert row[8:12] == ["INR", "", "", ""]
    assert row[15:] == ["", ""]


def test_the_directory_export_reads_in_a_fixed_number_of_queries(
    api, people, django_assert_num_queries
):
    """The user, the rates, the employees and their records: one prefetch a chunk of 1,000."""
    with django_assert_num_queries(4):
        rows = csv_rows(api.get(EMPLOYEES, {"file": "csv"}))

    assert len(rows) == 31


@pytest.mark.parametrize(
    ("file", "content_type"),
    [
        ("csv", "text/csv; charset=utf-8"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("json", "application/json"),
        ("CSV", "text/csv; charset=utf-8"),
    ],
)
def test_the_file_is_an_attachment_stamped_in_utc(api, people, file, content_type):
    response = api.get(EMPLOYEES, {"file": file})

    assert response.status_code == 200
    assert response["Content-Type"] == content_type
    assert response["Content-Disposition"] == (
        f'attachment; filename="acme-employees-20261007-0900.{file.lower()}"'
    )
    assert response["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("params", "errors"),
    [
        ({}, {"file": ["file must be csv, xlsx or json"]}),
        ({"file": "pdf"}, {"file": ["file must be csv, xlsx or json, got pdf"]}),
        (
            {"file": "csv", "currency": "local", "country": "IN,US"},
            {"currency": ["currency=local needs exactly one country in the filter"]},
        ),
        (
            {"file": "csv", "level": "9"},
            {"level": ["Select a valid choice. 9 is not one of the available choices."]},
        ),
    ],
)
def test_a_bad_parameter_is_the_directorys_400(api, people, params, errors):
    response = api.get(EMPLOYEES, params)

    assert (response.status_code, response.json()) == (400, errors)


# The insights


def test_the_summary_is_one_row_with_its_currency_and_rates(api, people):
    body = json_body(api.get(INSIGHT.format("summary"), {"file": "json"}))

    assert body["filters"] == {"on": "2026-10-07", "currency": "USD"}
    assert body["rows"] == [
        {
            "currency": "USD",
            "rates": RATES,
            "headcount": 27,
            "total_cost": "2435450.00",
            "mean_gross": "80462.96",
            "median_gross": "75000.00",
            "countries": 4,
            "departments": 4,
            "reason": None,
        }
    ]


def test_a_summary_under_five_says_why_its_figures_are_missing(api, people):
    """D59 and D60: Finance is G1 alone."""
    rows = csv_rows(api.get(INSIGHT.format("summary"), {"file": "csv", "department": "finance"}))

    assert rows == [
        [
            "Currency",
            "Rates",
            "Headcount",
            "Total cost",
            "Mean gross",
            "Median gross",
            "Countries",
            "Departments",
            "Reason",
        ],
        ["USD", RATES, "1", "", "", "", "1", "1", "fewer than 5 people"],
    ]


def test_by_country_lists_every_country_with_the_withheld_ones_saying_why(api, people):
    rows = csv_rows(api.get(INSIGHT.format("by-country"), {"file": "csv"}))

    assert rows == [
        [
            "Country code",
            "Country",
            "Headcount",
            "Total cost",
            "Median gross",
            "Share %",
            "Reason",
            "Currency",
            "Rates",
        ],
        ["US", "United States", "10", "1595000.00", "145000.00", "65.5", "", "USD", RATES],
        ["IN", "India", "12", "319200.00", "23750.00", "13.1", "", "USD", RATES],
        ["DE", "Germany", "4", "", "", "", "fewer than 5 people", "USD", RATES],
        ["NL", "Netherlands", "0", "", "", "", "", "USD", RATES],
        ["SG", "Singapore", "0", "", "", "", "", "USD", RATES],
        ["GB", "United Kingdom", "1", "", "", "", "fewer than 5 people", "USD", RATES],
    ]


def test_by_department_says_why_and_leaves_nobody_without_a_reason(api, people):
    body = json_body(
        api.get(INSIGHT.format("by-department"), {"file": "json", "department": "finance,legal"})
    )

    assert body["rows"] == [
        {
            "department_code": "finance",
            "department": "Finance",
            "headcount": 1,
            "total_cost": None,
            "mean_gross": None,
            "median_gross": None,
            "reason": "fewer than 5 people",
            "currency": "USD",
            "rates": RATES,
        },
        {
            "department_code": "legal",
            "department": "Legal",
            "headcount": 0,
            "total_cost": None,
            "mean_gross": None,
            "median_gross": None,
            "reason": None,
            "currency": "USD",
            "rates": RATES,
        },
    ]


def test_the_distribution_is_one_row_per_band_numbered_from_one(api, people):
    """The 27 people of tests/insights: p1 10,650.00, p99 187,400.00, twelve bands."""
    rows = csv_rows(api.get(INSIGHT.format("distribution"), {"file": "csv"}))
    edges = ["10650.00", "25379.17", "40108.33", "54837.50", "69566.67", "84295.83"]
    edges += ["99025.00", "113754.17", "128483.33", "143212.50", "157941.67", "172670.83"]
    counts = ["7", "5", "0", "1", "1", "1", "4", "1", "2", "1", "2", "2"]

    assert rows[0] == ["Band", "From", "To", "People", "Reason", "Currency", "Rates"]
    assert rows[1:] == [
        [
            str(band),
            edges[band - 1],
            (edges + ["187400.00"])[band],
            counts[band - 1],
            "",
            "USD",
            RATES,
        ]
        for band in range(1, 13)
    ]


@pytest.mark.parametrize(
    ("query", "people_count", "reason"),
    [({"country": "US"}, 10, "fewer than 20 people"), ({"department": "legal"}, 0, None)],
    ids=["under twenty", "nobody"],
)
def test_a_distribution_without_bands_is_one_row_of_its_headcount(
    api, people, query, people_count, reason
):
    """D60: the file still says how many people the filters matched."""
    body = json_body(api.get(INSIGHT.format("distribution"), {**query, "file": "json"}))

    assert body["rows"] == [
        {
            "band": None,
            "from": None,
            "to": None,
            "people": people_count,
            "reason": reason,
            "currency": "USD",
            "rates": RATES,
        }
    ]


@pytest.mark.parametrize("file", ["csv", "json"])
def test_a_level_under_twenty_carries_its_headcount_and_empty_figures(api, people, file):
    """D59: no level of the fixture reaches twenty, so every level is its headcount alone, as the
    card shows it."""
    response = api.get(INSIGHT.format("by-level"), {"file": file})
    headcounts = [4, 6, 5, 5, 4, 3]

    if file == "csv":
        rows = csv_rows(response)
        assert rows[0] == [
            "Level",
            "Headcount",
            "p10",
            "p25",
            "Median",
            "p75",
            "p90",
            "Reason",
            "Currency",
            "Rates",
        ]
        assert rows[1:] == [
            [str(level), str(count), "", "", "", "", "", "fewer than 20 people", "USD", RATES]
            for level, count in enumerate(headcounts, start=1)
        ]
    else:
        assert json_body(response)["rows"][0] == {
            "level": 1,
            "headcount": 4,
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "reason": "fewer than 20 people",
            "currency": "USD",
            "rates": RATES,
        }


def test_the_gender_gap_is_one_row_per_group_and_gender(api, people):
    """India: six women at a median of 2.0M INR, six men at 1.8M, a gap of -11.1. Overall is the
    same group when the filter is India alone."""
    rows = csv_rows(api.get(INSIGHT.format("gender-gap"), {"file": "csv", "country": "IN"}))

    def group(code, name):
        return [
            [code, name, "female", "6", "25000.00", "-11.1", "", "USD", RATES],
            [code, name, "male", "6", "22500.00", "-11.1", "", "USD", RATES],
            [code, name, "other", "0", "", "-11.1", "", "USD", RATES],
            [code, name, "undisclosed", "0", "", "-11.1", "", "USD", RATES],
        ]

    assert rows[0] == [
        "Country code",
        "Country",
        "Gender",
        "Headcount",
        "Median gross",
        "Gap %",
        "Reason",
        "Currency",
        "Rates",
    ]
    assert rows[1:] == group("IN", "India") + group("", "Overall")


def test_a_small_gender_group_repeats_the_cards_reason(api, people):
    """The US has four women: no gap, `group too small` on each of its rows."""
    rows = csv_rows(api.get(INSIGHT.format("gender-gap"), {"file": "csv", "country": "US"}))

    assert [row[2:7] for row in rows[1:5]] == [
        ["female", "4", "", "", "group too small"],
        ["male", "6", "125000.00", "", "group too small"],
        ["other", "0", "", "", "group too small"],
        ["undisclosed", "0", "", "", "group too small"],
    ]


def test_local_currency_names_the_currency_and_no_rate_month(api, people):
    body = json_body(
        api.get(INSIGHT.format("summary"), {"file": "json", "country": "IN", "currency": "local"})
    )

    assert body["filters"] == {"country": "IN", "on": "2026-10-07", "currency": "INR"}
    assert (body["rows"][0]["currency"], body["rows"][0]["rates"]) == (
        "INR",
        "local currency (INR)",
    )


def test_every_insight_filter_reaches_the_export(api, people):
    body = json_body(api.get(INSIGHT.format("summary"), {"file": "json", "include_exited": "true"}))

    assert body["rows"][0]["headcount"] == 29


def test_an_insight_file_is_named_after_the_insight(api, people):
    response = api.get(INSIGHT.format("by-level"), {"file": "xlsx"})

    assert (
        response["Content-Disposition"] == 'attachment; filename="acme-by-level-20261007-0900.xlsx"'
    )
    assert load_workbook(io.BytesIO(response.content)).active.title == "by-level"


@pytest.mark.parametrize("file", ["csv", "pdf"])
def test_an_unknown_insight_is_a_404_before_anything_else(api, people, file):
    response = api.get(INSIGHT.format("top-earners"), {"file": file})

    assert (response.status_code, response.json()) == (404, {"detail": "Not found."})


def test_a_bad_insight_filter_is_the_insights_400(api, people):
    response = api.get(INSIGHT.format("summary"), {"file": "csv", "country": "XX"})

    assert (response.status_code, response.json()) == (
        400,
        {"country": ["Unknown country_code: XX"]},
    )


def test_an_insight_export_reads_what_the_insight_reads(api, people, django_assert_num_queries):
    """The user, the countries, the departments, the rates, one aggregate, one list of values."""
    with django_assert_num_queries(6):
        response = api.get(INSIGHT.format("by-country"), {"file": "csv"})

    assert response.status_code == 200
