"""Directory list and detail over HTTP (SPEC F4, section 8). Rules are tested in test_queries;
these tests cover parameters, shapes, error codes and the pinned query counts."""

from datetime import date
from decimal import Decimal

import pytest

from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
from apps.employees import services
from tests.factories import EmployeeFactory, country, department

pytestmark = pytest.mark.django_db

LIST = "/api/v1/employees/"


def record_input(effective_from=None, bonus="0", **lines) -> RecordInput:
    return RecordInput(
        effective_from,
        Decimal(bonus),
        "",
        {code: Decimal(amount) for code, amount in lines.items()},
    )


def person(code, name, **fields):
    first = name.split()[0].lower()
    return EmployeeFactory(
        employee_code=code, full_name=name, email=f"{first}@acme.example", **fields
    )


@pytest.fixture
def cast(rates, hr_user):
    """Six people across three currencies, written by the HR Manager. Reporting-currency gross
    in USD on 7 Oct 2026: dev 7,200 < farah 10,800 < esha 14,400 < asha 17,400 < ben 100,000 <
    chloe 107,600."""
    asha = person("ACME-000001", "Asha Rao", joining_date=date(2020, 1, 1))
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
        "ACME-000002",
        "Ben Carter",
        country=country("US"),
        department=department("sales"),
        designation="Account Executive",
        level=4,
        joining_date=date(2018, 6, 15),
    )
    compensation.add_first_record(ben, record_input(BASE="100000"), actor=hr_user)
    chloe = person(
        "ACME-000003", "Chloe Davies", country=country("GB"), level=5, joining_date=date(2022, 3, 1)
    )
    compensation.add_first_record(chloe, record_input(BASE="80000"), actor=hr_user)
    dev = person("ACME-000004", "Dev Mehta", level=2, joining_date=date(2019, 9, 1))
    compensation.add_first_record(dev, record_input(BASE="600000"), actor=hr_user)
    services.exit_employee(dev, date(2026, 6, 30), actor=hr_user)
    esha = person(
        "ACME-000005",
        "Esha Nair",
        department=department("product"),
        designation="Product Manager",
        joining_date=date(2027, 1, 1),
    )
    compensation.add_first_record(esha, record_input(BASE="1200000"), actor=hr_user)
    farah = person("ACME-000006", "Farah Khan", joining_date=date(2021, 1, 1))
    compensation.add_first_record(farah, record_input(BASE="900000"), actor=hr_user)
    compensation.revise(farah, record_input(date(2026, 11, 1), BASE="1100000"), actor=hr_user)
    return {"asha": asha, "ben": ben, "chloe": chloe, "dev": dev, "esha": esha, "farah": farah}


def names(response) -> list[str]:
    assert response.status_code == 200, response.content
    return [row["full_name"] for row in response.json()["results"]]


def test_list_shape_and_default_order(api, cast):
    response = api.get(LIST)

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
    assert asha["employee_code"] == "ACME-000001"
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
    rows = {row["full_name"]: row for row in api.get(LIST).json()["results"]}

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
    rows = {row["full_name"]: row for row in api.get(LIST, {"on": "2026-11-15"}).json()["results"]}

    assert rows["Farah Khan"]["shown"]["version"] == 2
    assert rows["Farah Khan"]["shown"]["gross_reporting"] == "13200.00"
    assert rows["Esha Nair"]["status"] == "upcoming"
    later = api.get(LIST, {"on": "2027-02-01", "status": "active"})
    assert names(later) == ["Asha Rao", "Ben Carter", "Chloe Davies", "Esha Nair", "Farah Khan"]


def test_ordering_by_reporting_gross_crosses_currencies(api, cast):
    ascending = names(api.get(LIST, {"ordering": "gross"}))
    descending = names(api.get(LIST, {"ordering": "-gross"}))

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
    assert names(api.get(LIST, {"ordering": ordering})) == expected


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
        ({"search": "ACME-000004"}, ["Dev Mehta"]),
        ({"search": "ben@"}, ["Ben Carter"]),
    ],
)
def test_each_filter(api, cast, params, expected):
    assert names(api.get(LIST, params)) == expected


def test_filters_combine_with_and_and_survive_paging_and_sorting(api, cast):
    """SPEC F4 acceptance: filters combine with AND and survive page changes and sorting."""
    base = {"country": "IN", "department": "engineering", "level": "3"}

    assert names(api.get(LIST, base)) == ["Asha Rao", "Farah Khan"]
    page_two = api.get(LIST, {**base, "ordering": "-gross", "page_size": "1", "page": "2"})
    assert page_two.json()["count"] == 2
    assert names(page_two) == ["Farah Khan"]
    previous = page_two.json()["previous"]
    assert page_two.json()["next"] is None
    for parameter in ("country=IN", "department=engineering", "level=3", "ordering=-gross"):
        assert parameter in previous, previous


def test_page_size_defaults_to_25_and_is_a_parameter(api, cast):
    default = api.get(LIST).json()
    small = api.get(LIST, {"page_size": "5"}).json()

    assert default["next"] is None and len(default["results"]) == 6
    assert len(small["results"]) == 5
    assert "page=2" in small["next"] and "page_size=5" in small["next"]


def test_currency_eur(api, cast):
    rows = api.get(LIST, {"currency": "eur", "ordering": "gross"}).json()["results"]

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
    response = api.get(LIST, {"currency": "local", "country": "IN"})

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
    response = api.get(LIST, params)

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
    ],
)
def test_bad_filter_values_are_400_per_field(api, cast, params, message):
    response = api.get(LIST, params)

    assert response.status_code == 400
    assert response.json() == {next(iter(params)): [message]}


def test_gross_range_includes_a_figure_that_rounds_onto_the_bound(api, rates):
    """SPEC F4's 0.005 tolerance: the SQL product keeps more decimals than the shown figure."""
    lata = person("ACME-000011", "Lata Iyer", joining_date=date(2020, 1, 1))
    compensation.add_first_record(lata, record_input(BASE="1234567.89"))  # USD 14,814.81468
    meera = person("ACME-000012", "Meera Pillai", joining_date=date(2020, 1, 1))
    compensation.add_first_record(meera, record_input(BASE="1234568.00"))  # USD 14,814.816

    rows = {
        row["full_name"]: row["shown"]["gross_reporting"] for row in api.get(LIST).json()["results"]
    }

    assert rows == {"Lata Iyer": "14814.81", "Meera Pillai": "14814.82"}
    assert names(api.get(LIST, {"gross_max": "14814.81"})) == ["Lata Iyer"]
    assert names(api.get(LIST, {"gross_min": "14814.82"})) == ["Meera Pillai"]


def test_an_employee_without_records_has_no_shown_block(api, lookups):
    EmployeeFactory(full_name="Gina Lopez")

    row = api.get(LIST).json()["results"][0]
    assert row["shown"] is None
    assert row["status"] == "active"


def test_list_query_count(api, cast, django_assert_num_queries):
    """User from the JWT, rates, count, page, prefetch of the page's live records."""
    with django_assert_num_queries(5):
        api.get(LIST)
    with django_assert_num_queries(5):
        api.get(LIST, {"country": "IN", "ordering": "-gross", "search": "a", "page_size": "2"})
    with django_assert_num_queries(6):
        api.get(LIST, {"currency": "local", "country": "IN"})


def test_detail_shape(api, cast):
    asha = cast["asha"]

    response = api.get(f"/api/v1/employees/{asha.pk}/")

    body = response.json()
    assert response.status_code == 200
    assert body["employee_code"] == "ACME-000001"
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
    assert body["employee_code"] == "ACME-000001"
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


def test_create_with_a_code_in_use_is_a_400(api, cast):
    """A client may name a code, but not one in use (D44)."""
    response = api.post(LIST, new_employee(employee_code="ACME-000001"), format="json")

    assert response.status_code == 400
    assert response.json() == {
        "employee_code": [
            "employee_code ACME-000001 already exists; omit employee_code to have one assigned"
        ]
    }
    assert api.get(LIST).json()["count"] == 6


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
        {"email": ["email already belongs to ACME-000001"]},
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
    ("field", "value"), [("employee_code", "ACME-000099"), ("country_code", "US")]
)
def test_patch_cannot_change_the_code_or_the_country(api, cast, field, value):
    response = api.patch(f"/api/v1/employees/{cast['asha'].pk}/", {field: value}, format="json")

    assert response.status_code == 400
    assert response.json() == {field: [f"{field} cannot be changed"]}


def test_patch_cannot_move_joining_date_past_the_first_record(api, cast):
    response = api.patch(
        f"/api/v1/employees/{cast['asha'].pk}/", {"joining_date": "2020-01-02"}, format="json"
    )

    assert response.status_code == 400
    assert response.json() == {
        "joining_date": ["joining_date is after the first record (effective 2020-01-01)"]
    }


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


def test_exit_errors_name_the_field_or_the_conflict(api, cast, hr_user):
    chloe = cast["chloe"]
    compensation.revise(chloe, record_input(date(2025, 4, 1), BASE="85000"), actor=hr_user)

    def exit_on(person, day):
        return api.post(f"/api/v1/employees/{person.pk}/exit/", {"last_date": day}, format="json")

    before_joining = exit_on(cast["ben"], "2018-06-14")
    before_record = exit_on(chloe, "2025-03-15")
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
