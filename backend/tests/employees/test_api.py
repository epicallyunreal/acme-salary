"""Directory list and detail over HTTP (SPEC F4, section 8). Rules are tested in test_queries;
these tests cover parameters, shapes, error codes and the pinned query counts."""

from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from apps.audit.models import AuditLog
from apps.compensation import services as compensation
from apps.compensation.models import CompensationRecord
from apps.compensation.services import RecordInput
from apps.employees import services
from apps.employees.models import Employee
from tests.factories import EmployeeFactory, country, department

pytestmark = pytest.mark.django_db

LIST = "/api/v1/employees/"
# The directory holds its active employees unless `status` says otherwise (D64), and these tests
# read everyone.
EVERYONE = {"status": "any"}


def record_input(effective_from=None, bonus="0", **lines) -> RecordInput:
    return RecordInput(
        effective_from,
        Decimal(bonus),
        "",
        {code: Decimal(amount) for code, amount in lines.items()},
    )


def person(name, **fields):
    first = name.split()[0].lower()
    return EmployeeFactory(full_name=name, email=f"{first}@acme.example", **fields)


@pytest.fixture
def cast(rates, hr_user):
    """Six people across three currencies, written by the HR Manager. Reporting-currency gross
    in USD on 7 Oct 2026: dev 7,200 < farah 10,800 < esha 14,400 < asha 17,400 < ben 100,000 <
    chloe 107,600. Dev came from the legacy system with HR-58213; the rest were added in the app.
    The database numbers them in this order, so ACME-<id> follows it (D48)."""
    asha = person("Asha Rao", joining_date=date(2020, 1, 1))
    compensation.add_first_record(
        asha,
        record_input(
            bonus="50000",
            BASE="1000000",
            HRA="400000",
            TAX="200000",
            EMPLOYER_CONTRIBUTION="120000",
        ),
        actor=hr_user,
    )
    ben = person(
        "Ben Carter",
        country=country("US"),
        department=department("sales"),
        designation="Account Executive",
        level=4,
        joining_date=date(2018, 6, 15),
    )
    compensation.add_first_record(ben, record_input(BASE="100000"), actor=hr_user)
    chloe = person("Chloe Davies", country=country("GB"), level=5, joining_date=date(2022, 3, 1))
    compensation.add_first_record(chloe, record_input(BASE="80000"), actor=hr_user)
    dev = person("Dev Mehta", legacy_code="HR-58213", level=2, joining_date=date(2019, 9, 1))
    compensation.add_first_record(dev, record_input(BASE="600000"), actor=hr_user)
    services.exit_employee(dev, date(2026, 6, 30), actor=hr_user)
    esha = person(
        "Esha Nair",
        department=department("product"),
        designation="Product Manager",
        joining_date=date(2027, 1, 1),
    )
    compensation.add_first_record(esha, record_input(BASE="1200000"), actor=hr_user)
    farah = person("Farah Khan", joining_date=date(2021, 1, 1))
    compensation.add_first_record(farah, record_input(BASE="900000"), actor=hr_user)
    compensation.revise(farah, record_input(date(2026, 11, 1), BASE="1100000"), actor=hr_user)
    return {"asha": asha, "ben": ben, "chloe": chloe, "dev": dev, "esha": esha, "farah": farah}


def names(response) -> list[str]:
    assert response.status_code == 200, response.content
    return [row["full_name"] for row in response.json()["results"]]


def test_list_shape_and_default_order(api, cast):
    response = api.get(LIST, EVERYONE)

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 6
    assert names(response) == [
        "Asha Rao",
        "Ben Carter",
        "Chloe Davies",
        "Dev Mehta",
        "Esha Nair",
        "Farah Khan",
    ]
    asha = body["results"][0]
    assert asha["employee_code"] == f"ACME-{cast['asha'].pk}"
    assert asha["legacy_code"] is None
    assert body["results"][3]["legacy_code"] == "HR-58213"
    assert asha["department"] == {"code": "engineering", "name": "Engineering"}
    assert asha["country"] == {"code": "IN", "name": "India", "currency_code": "INR"}
    assert asha["status"] == "active"
    assert asha["shown"] == {
        "record_id": asha["shown"]["record_id"],
        "version": 1,
        "effective_from": "2020-01-01",
        "effective_to": None,
        "is_current": True,
        "label": None,
        "gross_local": "1450000.00",
        "currency_code": "INR",
        "gross_reporting": "17400.00",
        "reporting_currency": "USD",
    }
    assert isinstance(asha["shown"]["gross_reporting"], str)


def test_shown_record_for_an_exited_and_a_future_joiner(api, cast):
    rows = {row["full_name"]: row for row in api.get(LIST, EVERYONE).json()["results"]}

    dev, esha, farah = rows["Dev Mehta"], rows["Esha Nair"], rows["Farah Khan"]
    assert dev["status"] == "exited"
    assert dev["last_date"] == "2026-06-30"
    assert dev["shown"]["label"] == "exited 2026-06-30"
    assert dev["shown"]["is_current"] is False
    assert dev["shown"]["effective_to"] == "2026-07-01"
    assert esha["status"] == "upcoming"
    assert esha["shown"]["label"] == "from 2027-01-01"
    assert esha["shown"]["gross_reporting"] == "14400.00"
    assert farah["shown"]["version"] == 1
    assert farah["shown"]["effective_to"] == "2026-11-01"
    assert farah["shown"]["label"] is None


def test_the_reporting_date_moves_the_shown_record_and_the_status(api, cast):
    rows = {
        row["full_name"]: row
        for row in api.get(LIST, {**EVERYONE, "on": "2026-11-15"}).json()["results"]
    }

    assert rows["Farah Khan"]["shown"]["version"] == 2
    assert rows["Farah Khan"]["shown"]["gross_reporting"] == "13200.00"
    assert rows["Esha Nair"]["status"] == "upcoming"
    later = api.get(LIST, {**EVERYONE, "on": "2027-02-01", "status": "active"})
    assert names(later) == ["Asha Rao", "Ben Carter", "Chloe Davies", "Esha Nair", "Farah Khan"]


def test_without_status_the_directory_holds_the_active_employees(api, cast):
    """D64: Active by default, as the grid opens, and `any` for everyone. Dev left in June and
    Esha joins in January."""
    assert names(api.get(LIST)) == ["Asha Rao", "Ben Carter", "Chloe Davies", "Farah Khan"]
    assert len(names(api.get(LIST, EVERYONE))) == 6
    assert names(api.get(LIST, {"status": "exited"})) == ["Dev Mehta"]


def test_without_ordering_the_directory_is_in_code_order(api, rates):
    """D63: the grid's default sort is Code ascending, so a request without `ordering` returns
    the order the grid shows. Hired out of name order, so name order would differ."""
    for name in ("Zara Ali", "Adam Brook", "Mia Chen"):
        person(name)

    assert names(api.get(LIST, EVERYONE)) == ["Zara Ali", "Adam Brook", "Mia Chen"]
    assert names(api.get(LIST, {**EVERYONE, "ordering": "employee_code"})) == names(
        api.get(LIST, EVERYONE)
    )


def test_ordering_by_reporting_gross_crosses_currencies(api, cast):
    ascending = names(api.get(LIST, {**EVERYONE, "ordering": "gross"}))
    descending = names(api.get(LIST, {**EVERYONE, "ordering": "-gross"}))

    assert ascending == [
        "Dev Mehta",
        "Farah Khan",
        "Esha Nair",
        "Asha Rao",
        "Ben Carter",
        "Chloe Davies",
    ]
    assert descending == ascending[::-1]


@pytest.mark.parametrize(
    ("ordering", "expected"),
    [
        (
            "full_name",
            ["Asha Rao", "Ben Carter", "Chloe Davies", "Dev Mehta", "Esha Nair", "Farah Khan"],
        ),
        (
            "-full_name",
            ["Farah Khan", "Esha Nair", "Dev Mehta", "Chloe Davies", "Ben Carter", "Asha Rao"],
        ),
        (
            "designation",
            ["Ben Carter", "Esha Nair", "Asha Rao", "Chloe Davies", "Dev Mehta", "Farah Khan"],
        ),
        (
            "-level",
            ["Chloe Davies", "Ben Carter", "Asha Rao", "Esha Nair", "Farah Khan", "Dev Mehta"],
        ),
        (
            "country,-gross",
            ["Asha Rao", "Esha Nair", "Farah Khan", "Dev Mehta", "Chloe Davies", "Ben Carter"],
        ),
        (
            "joining_date",
            ["Ben Carter", "Dev Mehta", "Asha Rao", "Farah Khan", "Chloe Davies", "Esha Nair"],
        ),
        (
            "-employee_code",
            ["Farah Khan", "Esha Nair", "Dev Mehta", "Chloe Davies", "Ben Carter", "Asha Rao"],
        ),
        (
            "department",
            ["Asha Rao", "Chloe Davies", "Dev Mehta", "Farah Khan", "Esha Nair", "Ben Carter"],
        ),
    ],
)
def test_ordering_aliases(api, cast, ordering, expected):
    assert names(api.get(LIST, {**EVERYONE, "ordering": ordering})) == expected


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"country": "IN"}, ["Asha Rao", "Dev Mehta", "Esha Nair", "Farah Khan"]),
        ({"country": "US,GB"}, ["Ben Carter", "Chloe Davies"]),
        ({"department": "sales,product"}, ["Ben Carter", "Esha Nair"]),
        ({"designation": "Product Manager"}, ["Esha Nair"]),
        ({"designation": "product manager"}, ["Esha Nair"]),
        (
            {"designation": "senior engineer,ACCOUNT EXECUTIVE"},
            ["Asha Rao", "Ben Carter", "Chloe Davies", "Dev Mehta", "Farah Khan"],
        ),
        ({"level": "2,5"}, ["Chloe Davies", "Dev Mehta"]),
        ({"status": "active"}, ["Asha Rao", "Ben Carter", "Chloe Davies", "Farah Khan"]),
        ({"status": "exited"}, ["Dev Mehta"]),
        ({"status": "upcoming"}, ["Esha Nair"]),
        ({"gross_min": "100000"}, ["Ben Carter", "Chloe Davies"]),
        ({"gross_max": "10800"}, ["Dev Mehta", "Farah Khan"]),
        ({"gross_min": "17400", "gross_max": "17400"}, ["Asha Rao"]),
        ({"joined_after": "2020-01-01"}, ["Asha Rao", "Chloe Davies", "Esha Nair", "Farah Khan"]),
        ({"joined_before": "2019-12-31"}, ["Ben Carter", "Dev Mehta"]),
        ({"search": "chlo"}, ["Chloe Davies"]),
        ({"search": "ben@"}, ["Ben Carter"]),
    ],
)
def test_each_filter(api, cast, params, expected):
    assert names(api.get(LIST, {**EVERYONE, **params})) == expected


def test_search_reads_an_acme_code_as_a_number_and_a_legacy_code_in_any_case(api, cast):
    dev = cast["dev"]

    for term in (f"ACME-{dev.pk}", f"acme-{dev.pk:04d}", "hr-58213", "HR-58213"):
        assert names(api.get(LIST, {**EVERYONE, "search": term})) == ["Dev Mehta"], term
    assert names(api.get(LIST, {**EVERYONE, "search": "HR-5821"})) == []
    assert names(api.get(LIST, {**EVERYONE, "search": f"ACME-{dev.pk} dev@"})) == ["Dev Mehta"]


def test_filters_combine_with_and_and_survive_paging_and_sorting(api, cast):
    """SPEC F4 acceptance: filters combine with AND and survive page changes and sorting."""
    base = {"country": "IN", "department": "engineering", "level": "3"}

    assert names(api.get(LIST, {**EVERYONE, **base})) == ["Asha Rao", "Farah Khan"]
    page_two = api.get(
        LIST, {**EVERYONE, **base, "ordering": "-gross", "page_size": "1", "page": "2"}
    )
    assert page_two.json()["count"] == 2
    assert names(page_two) == ["Farah Khan"]
    previous = page_two.json()["previous"]
    assert page_two.json()["next"] is None
    for parameter in ("country=IN", "department=engineering", "level=3", "ordering=-gross"):
        assert parameter in previous, previous


def test_page_size_defaults_to_25_and_is_a_parameter(api, cast):
    default = api.get(LIST, EVERYONE).json()
    small = api.get(LIST, {**EVERYONE, "page_size": "5"}).json()

    assert default["next"] is None and len(default["results"]) == 6
    assert len(small["results"]) == 5
    assert "page=2" in small["next"] and "page_size=5" in small["next"]


def test_currency_eur(api, cast):
    rows = api.get(LIST, {**EVERYONE, "currency": "eur", "ordering": "gross"}).json()["results"]

    assert [row["full_name"] for row in rows] == [
        "Dev Mehta",
        "Farah Khan",
        "Esha Nair",
        "Asha Rao",
        "Ben Carter",
        "Chloe Davies",
    ]
    asha = next(row for row in rows if row["full_name"] == "Asha Rao")
    assert asha["shown"]["gross_reporting"] == "14804.50"
    assert asha["shown"]["reporting_currency"] == "EUR"


def test_currency_local_with_one_country(api, cast):
    response = api.get(LIST, {**EVERYONE, "currency": "local", "country": "IN"})

    rows = response.json()["results"]
    assert [row["full_name"] for row in rows] == [
        "Asha Rao",
        "Dev Mehta",
        "Esha Nair",
        "Farah Khan",
    ]
    assert rows[0]["shown"]["gross_reporting"] == "1450000.00"
    assert rows[0]["shown"]["reporting_currency"] == "INR"


@pytest.mark.parametrize(
    ("params", "field", "message"),
    [
        (
            {"currency": "local", "country": "IN,US"},
            "currency",
            "currency=local needs exactly one country in the filter",
        ),
        (
            {"currency": "local"},
            "currency",
            "currency=local needs exactly one country in the filter",
        ),
        ({"currency": "local", "country": "XX"}, "country", "Unknown country_code: XX"),
        ({"currency": "gbp"}, "currency", "currency must be usd, eur or local, got gbp"),
        ({"on": "yesterday"}, "on", "on must be a date in YYYY-MM-DD form, got yesterday"),
    ],
)
def test_bad_reporting_parameters_are_400(api, cast, params, field, message):
    response = api.get(LIST, {**EVERYONE, **params})

    assert response.status_code == 400
    assert response.json() == {field: [message]}


CHOICE = "Select a valid choice. {} is not one of the available choices."


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"ordering": "salary"}, CHOICE.format("salary")),
        ({"status": "gone"}, CHOICE.format("gone")),
        ({"level": "x"}, CHOICE.format("x")),
        ({"level": "7"}, CHOICE.format("7")),
        ({"level": "99999999999999999999999"}, CHOICE.format("99999999999999999999999")),
        ({"search": " ".join(["a"] * 11)}, "search accepts at most 10 words"),
        ({"designation": ",".join(["Engineer"] * 21)}, "designation accepts at most 20 titles"),
    ],
)
def test_bad_filter_values_are_400_per_field(api, cast, params, message):
    response = api.get(LIST, {**EVERYONE, **params})

    assert response.status_code == 400
    assert response.json() == {next(iter(params)): [message]}


def test_twenty_titles_are_one_filter(api, cast):
    """D61: each title is one more OR, and past a thousand SQLite answers with a 500."""
    response = api.get(LIST, {**EVERYONE, "designation": ",".join(["Engineer"] * 20)})

    assert response.status_code == 200


def test_gross_range_includes_a_figure_that_rounds_onto_the_bound(api, rates):
    """SPEC F4's 0.005 tolerance: the SQL product keeps more decimals than the shown figure."""
    lata = person("Lata Iyer", joining_date=date(2020, 1, 1))
    compensation.add_first_record(lata, record_input(BASE="1234567.89"))  # USD 14,814.81468
    meera = person("Meera Pillai", joining_date=date(2020, 1, 1))
    compensation.add_first_record(meera, record_input(BASE="1234568.00"))  # USD 14,814.816

    rows = {
        row["full_name"]: row["shown"]["gross_reporting"]
        for row in api.get(LIST, EVERYONE).json()["results"]
    }

    assert rows == {"Lata Iyer": "14814.81", "Meera Pillai": "14814.82"}
    assert names(api.get(LIST, {**EVERYONE, "gross_max": "14814.81"})) == ["Lata Iyer"]
    assert names(api.get(LIST, {**EVERYONE, "gross_min": "14814.82"})) == ["Meera Pillai"]


def test_an_employee_without_records_has_no_shown_block(api, lookups):
    EmployeeFactory(full_name="Gina Lopez")

    row = api.get(LIST, EVERYONE).json()["results"][0]
    assert row["shown"] is None
    assert row["status"] == "active"


def test_list_query_count(api, cast, django_assert_num_queries):
    """User from the JWT, rates, count, page, prefetch of the page's live records."""
    with django_assert_num_queries(5):
        api.get(LIST, EVERYONE)
    with django_assert_num_queries(5):
        api.get(
            LIST,
            {**EVERYONE, "country": "IN", "ordering": "-gross", "search": "a", "page_size": "2"},
        )
    with django_assert_num_queries(6):
        api.get(LIST, {**EVERYONE, "currency": "local", "country": "IN"})


def test_detail_shape(api, cast):
    asha = cast["asha"]

    response = api.get(f"/api/v1/employees/{asha.pk}/")

    body = response.json()
    assert response.status_code == 200
    assert body["employee_code"] == f"ACME-{asha.pk}"
    assert body["legacy_code"] is None
    assert body["gender"] == "female"
    assert body["department"] == {"code": "engineering", "name": "Engineering"}
    assert body["country"] == {"code": "IN", "name": "India", "currency_code": "INR"}
    assert body["status"] == "active"
    assert body["shown_label"] is None
    assert body["created_at"].startswith("2026-10-07T09:00:00")
    record = body["current_record"]
    assert record["version"] == 1
    assert record["is_current"] is True
    assert record["is_scheduled"] is False
    assert record["cancelled_at"] is None and record["cancelled_by"] is None
    assert record["created_by"] == "hr@acme.example"
    assert record["currency_code"] == "INR"
    assert record["bonus_annual"] == "50000.00"
    assert record["gross_annual"] == "1450000.00"
    assert record["net_annual"] == "1250000.00"
    assert record["total_cost_annual"] == "1570000.00"
    assert record["source"] == "ui"
    assert record["employee"] == asha.pk
    # Codes, as the audit snapshot writes them; names and kinds come from /meta/components/ (D34).
    assert record["lines"] == [
        {"component": "BASE", "annual_amount": "1000000.00"},
        {"component": "HRA", "annual_amount": "400000.00"},
        {"component": "TAX", "annual_amount": "200000.00"},
        {"component": "EMPLOYER_CONTRIBUTION", "annual_amount": "120000.00"},
    ]
    assert record["converted"] == {
        "currency": "USD",
        "rate": "0.01200000",
        "rate_effective_from": "2026-10-01",
        "bonus_annual": "600.00",
        "gross_annual": "17400.00",
        "net_annual": "15000.00",
        "total_cost_annual": "18840.00",
    }


def test_detail_in_eur_and_in_the_local_currency(api, cast):
    url = f"/api/v1/employees/{cast['asha'].pk}/"

    eur = api.get(url, {"currency": "eur"}).json()["current_record"]["converted"]
    local = api.get(url, {"currency": "local"}).json()["current_record"]["converted"]

    assert eur["currency"] == "EUR"
    assert eur["rate"] == "0.01021000"
    assert eur["gross_annual"] == "14804.50"
    assert local == {
        "currency": "INR",
        "rate": "1.00000000",
        "rate_effective_from": None,
        "bonus_annual": "50000.00",
        "gross_annual": "1450000.00",
        "net_annual": "1250000.00",
        "total_cost_annual": "1570000.00",
    }


def test_detail_labels_for_exited_and_scheduled_records(api, cast):
    dev = api.get(f"/api/v1/employees/{cast['dev'].pk}/").json()
    esha = api.get(f"/api/v1/employees/{cast['esha'].pk}/").json()
    farah_later = api.get(f"/api/v1/employees/{cast['farah'].pk}/", {"on": "2026-11-15"}).json()

    assert dev["status"] == "exited"
    assert dev["shown_label"] == "exited 2026-06-30"
    assert dev["current_record"]["effective_to"] == "2026-07-01"
    assert dev["current_record"]["is_current"] is False
    assert esha["status"] == "upcoming"
    assert esha["shown_label"] == "from 2027-01-01"
    assert esha["current_record"]["is_scheduled"] is True
    assert farah_later["current_record"]["version"] == 2
    assert farah_later["current_record"]["converted"]["gross_annual"] == "13200.00"


def test_detail_without_records_and_unknown_id(api, lookups):
    bare = EmployeeFactory()

    assert api.get(f"/api/v1/employees/{bare.pk}/").json()["current_record"] is None
    assert api.get("/api/v1/employees/999999/").status_code == 404


def test_detail_query_count(api, cast, django_assert_num_queries):
    """User from the JWT, the employee with its lookups, its live records with their authors,
    their lines, rates. The fixture's records carry an author, so the pin covers a real one."""
    with django_assert_num_queries(5):
        api.get(f"/api/v1/employees/{cast['asha'].pk}/")


# Writes: create, edit identity, exit (SPEC F3, section 8)


def new_employee(**overrides) -> dict:
    body = {
        "full_name": "Meera Iyer",
        "email": "Meera.Iyer@acme.example",
        "department": "engineering",
        "designation": "Engineer",
        "level": 2,
        "country_code": "IN",
        "gender": "female",
        "joining_date": "2026-11-01",
        "bonus_annual": "0",
        "note": "offer",
        "lines": [
            {"component": "BASE", "annual_amount": "900000.00"},
            {"component": "HRA", "annual_amount": "360000.00"},
            {"component": "TAX", "annual_amount": "90000.00"},
        ],
    }
    body.update(overrides)
    return body


def test_create_assigns_the_code_and_answers_with_the_detail(api, rates):
    response = api.post(LIST, new_employee(gross_annual="1.00"), format="json")

    body = response.json()
    assert response.status_code == 201, response.content
    assert body["employee_code"] == f"ACME-{body['id']}"
    assert body["legacy_code"] is None
    assert body["email"] == "meera.iyer@acme.example"
    assert (body["status"], body["shown_label"]) == ("upcoming", "from 2026-11-01")
    record = body["current_record"]
    assert (record["version"], record["effective_from"], record["is_scheduled"]) == (
        1,
        "2026-11-01",
        True,
    )
    # gross_annual in the body is ignored: totals come from the lines (SPEC F3).
    assert (record["gross_annual"], record["net_annual"]) == ("1260000.00", "1170000.00")
    assert [line["component"] for line in record["lines"]] == ["BASE", "HRA", "TAX"]
    assert record["note"] == "offer"
    assert body["warnings"] == []


@pytest.mark.parametrize(
    ("extra", "errors"),
    [
        (
            {"employee_code": "ACME-1"},
            {"employee_code": ["employee_code is assigned by the system"]},
        ),
        ({"legacy_code": "HR-1"}, {"legacy_code": ["legacy_code is set only by an import"]}),
        (
            {"employee_code": None, "legacy_code": ""},
            {
                "employee_code": ["employee_code is assigned by the system"],
                "legacy_code": ["legacy_code is set only by an import"],
            },
        ),
    ],
)
def test_create_never_takes_either_code(api, cast, extra, errors):
    """The database numbers every employee and only an import records a legacy_code (D48)."""
    response = api.post(LIST, new_employee(**extra), format="json")

    assert (response.status_code, response.json()) == (400, errors)
    assert api.get(LIST, EVERYONE).json()["count"] == 6


def test_create_reports_shape_and_rule_errors_per_field(api, cast):
    missing = new_employee()
    del missing["full_name"]

    shape = api.post(LIST, missing, format="json")
    rules = api.post(LIST, new_employee(department="Growth", level=9, gender="x"), format="json")
    email = api.post(LIST, new_employee(email="ASHA@acme.example"), format="json")

    assert (shape.status_code, shape.json()) == (400, {"full_name": ["This field is required."]})
    assert (rules.status_code, rules.json()) == (
        400,
        {
            "department": ["Unknown department: Growth"],
            "level": ["level must be between 1 and 6"],
            "gender": ["gender must be one of female, male, other, undisclosed"],
        },
    )
    assert (email.status_code, email.json()) == (
        400,
        {"email": [f"email already belongs to ACME-{cast['asha'].pk}"]},
    )


def test_patch_edits_identity_and_answers_with_the_detail(api, cast):
    url = f"/api/v1/employees/{cast['asha'].pk}/"

    response = api.patch(
        url, {"designation": "Staff Engineer", "level": 4, "department": "product"}, format="json"
    )

    body = response.json()
    assert response.status_code == 200, response.content
    assert (body["designation"], body["level"]) == ("Staff Engineer", 4)
    assert body["department"] == {"code": "product", "name": "Product"}
    assert body["current_record"]["version"] == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("employee_code", "own", "employee_code is assigned by the system"),
        ("legacy_code", "HR-1", "legacy_code is set only by an import"),
        ("country_code", "US", "country_code cannot be changed"),
    ],
)
def test_patch_refuses_the_codes_and_a_new_country(api, cast, field, value, message):
    """Either code is refused even when it repeats the current one (D48)."""
    asha = cast["asha"]
    sent = asha.employee_code if value == "own" else value

    response = api.patch(f"/api/v1/employees/{asha.pk}/", {field: sent}, format="json")

    assert (response.status_code, response.json()) == (400, {field: [message]})


def test_patch_cannot_move_joining_date_past_the_first_record(api, cast):
    response = api.patch(
        f"/api/v1/employees/{cast['asha'].pk}/", {"joining_date": "2020-01-02"}, format="json"
    )

    assert response.status_code == 400
    assert response.json() == {
        "joining_date": ["joining_date is after the first record (effective 2020-01-01)"]
    }


def written() -> tuple[int, ...]:
    """Counts every write moves: it adds a row or marks one, and is audited (rules 6 and 7)."""
    return (
        Employee.objects.count(),
        Employee.objects.exclude(last_date=None).count(),
        CompensationRecord.objects.count(),
        CompensationRecord.objects.exclude(cancelled_at=None).count(),
        AuditLog.objects.count(),
    )


@pytest.mark.parametrize(
    ("query", "errors"),
    [
        ("on=yesterday", {"on": ["on must be a date in YYYY-MM-DD form, got yesterday"]}),
        ("currency=gbp", {"currency": ["currency must be usd, eur or local, got gbp"]}),
    ],
)
@pytest.mark.parametrize("write", ["create", "edit", "exit", "revise", "cancel"])
def test_a_bad_reporting_parameter_refuses_a_write_before_it_lands(api, cast, write, query, errors):
    """A write answers 400 only when nothing was written: the response's `on` and `currency`
    are checked before the service runs."""
    asha = cast["asha"]
    scheduled = CompensationRecord.objects.get(employee=cast["farah"], version=2)
    revision = {
        "effective_from": "2027-01-01",
        "lines": [{"component": "BASE", "annual_amount": "1100000.00"}],
    }
    method, path, body = {
        "create": ("post", LIST, new_employee()),
        "edit": ("patch", f"{LIST}{asha.pk}/", {"designation": "Staff Engineer"}),
        "exit": ("post", f"{LIST}{asha.pk}/exit/", {"last_date": "2026-10-31"}),
        "revise": ("post", f"{LIST}{asha.pk}/compensation/", revision),
        "cancel": ("delete", f"/api/v1/compensation/{scheduled.pk}/", None),
    }[write]
    before = written()

    response = getattr(api, method)(f"{path}?{query}", body, format="json")

    assert (response.status_code, response.json()) == (400, errors)
    assert written() == before
    asha.refresh_from_db()
    assert asha.designation == "Senior Engineer"


def test_a_patch_that_changes_nothing_writes_nothing(api, cast):
    asha = cast["asha"]
    url = f"{LIST}{asha.pk}/"
    before = written()

    # Ten minutes on, inside the access token's life, so a save would move updated_at.
    with freeze_time("2026-10-07T09:10:00Z"):
        empty = api.patch(url, {}, format="json")
        same = api.patch(
            url, {"designation": asha.designation, "email": asha.email.upper()}, format="json"
        )

    assert (empty.status_code, same.status_code) == (200, 200)
    assert written() == before
    assert {empty.json()["updated_at"], same.json()["updated_at"]} == {"2026-10-07T09:00:00+00:00"}


def test_a_date_after_2100_is_a_400_on_every_write_and_writes_nothing(api, cast):
    """D53: an exit on the last representable date used to overflow last_date + 1 into a 500."""
    asha = cast["asha"]
    before = written()
    late = "on or before 2100-12-31, got"
    revision = {
        "effective_from": "2101-01-01",
        "lines": [{"component": "BASE", "annual_amount": "1100000.00"}],
    }

    exit_ = api.post(f"{LIST}{asha.pk}/exit/", {"last_date": "9999-12-31"}, format="json")
    revise = api.post(f"{LIST}{asha.pk}/compensation/", revision, format="json")
    create = api.post(LIST, new_employee(joining_date="2101-01-01"), format="json")
    edit = api.patch(f"{LIST}{asha.pk}/", {"joining_date": "2101-01-01"}, format="json")

    assert (exit_.status_code, exit_.json()) == (
        400,
        {"last_date": [f"last_date must be {late} 9999-12-31"]},
    )
    assert (revise.status_code, revise.json()) == (
        400,
        {"effective_from": [f"effective_from must be {late} 2101-01-01"]},
    )
    assert (create.status_code, create.json()) == (
        400,
        {"joining_date": [f"joining_date must be {late} 2101-01-01"]},
    )
    assert (edit.status_code, edit.json()) == (
        400,
        {
            "joining_date": [
                f"joining_date must be {late} 2101-01-01",
                "joining_date is after the first record (effective 2020-01-01)",
            ]
        },
    )
    assert written() == before


def test_a_patch_with_a_code_and_a_new_country_refuses_both_at_once(api, cast):
    response = api.patch(
        f"{LIST}{cast['asha'].pk}/",
        {"employee_code": "ACME-1", "country_code": "US", "designation": "Lead"},
        format="json",
    )

    assert (response.status_code, response.json()) == (
        400,
        {
            "employee_code": ["employee_code is assigned by the system"],
            "country_code": ["country_code cannot be changed"],
        },
    )


def test_a_create_without_bonus_or_note_has_none(api, rates):
    """D51: both are optional; the totals come from the lines alone."""
    body = new_employee()
    del body["bonus_annual"], body["note"]

    response = api.post(LIST, body, format="json")

    record = response.json()["current_record"]
    assert response.status_code == 201, response.content
    assert (record["bonus_annual"], record["note"], record["gross_annual"]) == (
        "0.00",
        "",
        "1260000.00",
    )


def test_the_note_and_the_lookup_strings_are_capped(api, cast):
    """Nothing unbounded is stored or echoed back in a 400 (D51)."""
    too_long = "Ensure this field has no more than {} characters."

    response = api.post(
        LIST,
        new_employee(
            department="x" * 65,
            country_code="I" * 65,
            gender="g" * 65,
            note="n" * 1001,
            lines=[{"component": "C" * 65, "annual_amount": "900000.00"}],
        ),
        format="json",
    )
    edit = api.patch(f"{LIST}{cast['asha'].pk}/", {"department": "x" * 65}, format="json")
    longest = api.post(LIST, new_employee(note="n" * 1000), format="json")

    assert response.status_code == 400
    assert response.json() == {
        "department": [too_long.format(64)],
        "country_code": [too_long.format(64)],
        "gender": [too_long.format(64)],
        "note": [too_long.format(1000)],
        "lines": {"0": {"component": [too_long.format(64)]}},
    }
    assert (edit.status_code, edit.json()) == (400, {"department": [too_long.format(64)]})
    assert longest.status_code == 201, longest.content


def test_put_is_not_offered(api, cast):
    response = api.put(f"/api/v1/employees/{cast['asha'].pk}/", new_employee(), format="json")

    assert response.status_code == 405


def test_exit_closes_the_open_record_and_a_second_exit_is_a_409(api, cast):
    url = f"/api/v1/employees/{cast['asha'].pk}/exit/"

    response = api.post(url, {"last_date": "2026-09-30"}, format="json")
    again = api.post(url, {"last_date": "2026-09-30"}, format="json")

    body = response.json()
    assert response.status_code == 200, response.content
    assert (body["last_date"], body["status"], body["shown_label"]) == (
        "2026-09-30",
        "exited",
        "exited 2026-09-30",
    )
    assert body["current_record"]["effective_to"] == "2026-10-01"
    assert (again.status_code, again.json()) == (
        409,
        {"detail": "employee already exited on 2026-09-30"},
    )


def test_an_exit_before_pay_starts_leaves_an_employee_who_still_shows(api, cast, hr_user):
    """D50: the exit cancels the only record. With no live record the employee still renders in
    the directory, the detail, the history and the audit list."""
    gita = person("Gita Rao", joining_date=date(2026, 9, 1))
    compensation.add_first_record(
        gita, record_input(date(2026, 12, 1), BASE="900000"), actor=hr_user
    )

    response = api.post(
        f"/api/v1/employees/{gita.pk}/exit/", {"last_date": "2026-09-30"}, format="json"
    )

    body = response.json()
    assert response.status_code == 200, response.content
    assert (body["last_date"], body["status"], body["current_record"]) == (
        "2026-09-30",
        "exited",
        None,
    )
    rows = api.get(LIST, {**EVERYONE, "search": "Gita"}).json()["results"]
    assert [(row["full_name"], row["status"], row["shown"]) for row in rows] == [
        ("Gita Rao", "exited", None)
    ]
    detail = api.get(f"/api/v1/employees/{gita.pk}/")
    assert (detail.status_code, detail.json()["current_record"]) == (200, None)
    history = api.get(f"/api/v1/employees/{gita.pk}/compensation/").json()
    assert [(row["version"], row["cancelled_at"] is not None) for row in history] == [(1, True)]
    audit = api.get(f"/api/v1/employees/{gita.pk}/audit/").json()["results"]
    assert [entry["action"] for entry in audit] == ["cancel", "exit", "revise"]


def test_an_exit_before_a_first_record_that_has_been_current_is_a_400(api, cast, hr_user):
    """D50 is narrow: pay that has started stays history, so the exit cannot precede it."""
    hana = person("Hana Sato", joining_date=date(2024, 1, 1))
    compensation.add_first_record(
        hana, record_input(date(2024, 3, 1), BASE="900000"), actor=hr_user
    )

    response = api.post(
        f"/api/v1/employees/{hana.pk}/exit/", {"last_date": "2024-02-15"}, format="json"
    )

    assert (response.status_code, response.json()) == (
        400,
        {"last_date": ["last_date precedes the current record (effective 2024-03-01)"]},
    )
    assert not CompensationRecord.objects.filter(employee=hana).exclude(cancelled_at=None).exists()


def test_exit_errors_name_the_field_or_the_conflict(api, cast, hr_user):
    chloe = cast["chloe"]
    compensation.revise(chloe, record_input(date(2025, 4, 1), BASE="85000"), actor=hr_user)

    def exit_on(person, day):
        return api.post(f"/api/v1/employees/{person.pk}/exit/", {"last_date": day}, format="json")

    before_joining = exit_on(cast["ben"], "2018-06-14")
    before_record = exit_on(chloe, "2025-03-31")
    scheduled = exit_on(cast["farah"], "2026-10-15")
    missing = api.post(f"/api/v1/employees/{chloe.pk}/exit/", {}, format="json")

    assert (before_joining.status_code, before_joining.json()) == (
        400,
        {"last_date": ["last_date precedes joining_date"]},
    )
    assert (before_record.status_code, before_record.json()) == (
        400,
        {"last_date": ["last_date precedes the current record (effective 2025-04-01)"]},
    )
    assert (scheduled.status_code, scheduled.json()) == (
        409,
        {"detail": "scheduled revision on 2026-11-01 must be cancelled before exit"},
    )
    assert (missing.status_code, missing.json()) == (
        400,
        {"last_date": ["This field is required."]},
    )
    assert exit_on(EmployeeFactory.build(pk=999999), "2026-09-30").status_code == 404
