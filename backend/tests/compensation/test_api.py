"""Revisions, scheduling and cancellation over HTTP (SPEC F3, section 8).

The dating rules are tested without HTTP in test_services. These tests cover F3's criteria
through the API, the shapes, every 400 and 409 with its field and message, and the pinned query
count. The insights half of the scheduled-revision criterion closes in step 6 (D42).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.compensation import services
from apps.compensation.services import RecordInput
from apps.employees import services as employees
from tests.factories import EmployeeFactory, country

pytestmark = pytest.mark.django_db

LINES = {
    "BASE": "1450000.00",
    "HRA": "580000.00",
    "ALLOWANCES": "362500.00",
    "TAX": "478500.00",
    "EMPLOYER_CONTRIBUTION": "174000.00",
}


def lines(**amounts) -> list[dict]:
    return [
        {"component": code, "annual_amount": amount}
        for code, amount in {**LINES, **amounts}.items()
    ]


def first_record(employee, effective_from, actor, amounts=LINES):
    return services.add_first_record(
        employee,
        RecordInput(
            effective_from,
            Decimal("0"),
            "offer",
            {code: Decimal(amount) for code, amount in amounts.items()},
        ),
        actor=actor,
    ).record


@pytest.fixture
def asha(rates, hr_user):
    """Joined 2024-03-01; her current record runs from 2025-04-01."""
    employee = EmployeeFactory(
        employee_code="ACME-000001",
        full_name="Asha Rao",
        email="asha@acme.example",
        joining_date=date(2024, 3, 1),
    )
    first_record(employee, date(2025, 4, 1), hr_user)
    return employee


def history_url(employee_id: int) -> str:
    return f"/api/v1/employees/{employee_id}/compensation/"


def revise(api, employee, effective_from, **body):
    payload = {
        "effective_from": effective_from,
        "bonus_annual": "0",
        "note": "annual raise",
        "lines": lines(BASE="1600000.00"),
        **body,
    }
    return api.post(history_url(employee.pk), payload, format="json")


def cancel(api, record_id: int):
    return api.delete(f"/api/v1/compensation/{record_id}/")


def history(api, employee) -> list[dict]:
    response = api.get(history_url(employee.pk))
    assert response.status_code == 200, response.content
    return response.json()


def test_history_is_every_record_newest_first_with_lines_as_codes(api, asha):
    scheduled = revise(api, asha, "2027-04-01").json()

    rows = history(api, asha)

    assert [(row["version"], row["is_current"], row["is_scheduled"]) for row in rows] == [
        (2, False, True),
        (1, True, False),
    ]
    assert rows[0]["id"] == scheduled["id"]
    assert rows[0]["employee"] == asha.pk
    assert rows[0]["note"] == "annual raise"
    assert rows[0]["created_by"] == "hr@acme.example"
    assert rows[1]["lines"][0] == {"component": "BASE", "annual_amount": "1450000.00"}
    assert rows[1]["converted"]["currency"] == "USD"


def test_a_revision_on_or_before_the_latest_record_is_a_400(api, asha):
    for day in ("2025-04-01", "2025-03-31"):
        response = revise(api, asha, day)

        assert response.status_code == 400
        assert response.json() == {
            "effective_from": ["effective_from must be after 2025-04-01 (latest record)"]
        }


def test_a_revision_the_day_after_the_current_record_chains_half_open(api, asha):
    response = revise(api, asha, "2025-04-02")

    assert response.status_code == 201, response.content
    second, first = history(api, asha)
    assert first["effective_to"] == second["effective_from"] == "2025-04-02"
    assert second["effective_to"] is None
    assert [row["effective_to"] for row in (second, first)].count(None) == 1


def test_a_revision_next_year_is_scheduled_until_its_date(api, asha):
    body = revise(api, asha, "2027-04-01").json()

    assert (body["version"], body["is_scheduled"], body["is_current"]) == (2, True, False)
    today_row = api.get("/api/v1/employees/").json()["results"][0]
    later_row = api.get("/api/v1/employees/", {"on": "2027-04-01"}).json()["results"][0]
    assert (today_row["shown"]["version"], today_row["shown"]["is_current"]) == (1, True)
    assert (later_row["shown"]["version"], later_row["shown"]["is_current"]) == (2, True)
    detail = f"/api/v1/employees/{asha.pk}/"
    assert api.get(detail).json()["current_record"]["version"] == 1
    assert api.get(detail, {"on": "2027-04-01"}).json()["current_record"]["version"] == 2


def test_cancelling_a_scheduled_revision_keeps_the_row_and_reopens_the_previous(api, asha):
    scheduled = revise(api, asha, "2027-04-01").json()

    response = cancel(api, scheduled["id"])

    assert response.status_code == 200, response.content
    assert response.json()["cancelled_at"] == "2026-10-07T09:00:00+00:00"
    assert response.json()["cancelled_by"] == "hr@acme.example"
    cancelled, first = history(api, asha)
    assert (cancelled["id"], cancelled["is_scheduled"]) == (scheduled["id"], False)
    assert cancelled["cancelled_at"] is not None
    assert first["effective_to"] is None


def test_cancelling_a_current_or_cancelled_record_is_a_409(api, asha):
    scheduled = revise(api, asha, "2027-04-01").json()
    current = history(api, asha)[1]
    cancel(api, scheduled["id"])

    for record_id in (current["id"], scheduled["id"]):
        response = cancel(api, record_id)

        assert response.status_code == 409
        assert response.json() == {"detail": "only a scheduled revision can be cancelled"}


def test_cancel_and_re_enter_the_same_date_twice(api, asha):
    """Cancel and re-enter is how a scheduled revision is corrected in v1 (D43)."""
    second = revise(api, asha, "2027-04-01")
    assert second.status_code == 201
    assert cancel(api, second.json()["id"]).status_code == 200
    third = revise(api, asha, "2027-04-01", lines=lines(BASE="1650000.00"))
    assert third.status_code == 201, third.content
    assert cancel(api, third.json()["id"]).status_code == 200

    fourth = revise(api, asha, "2027-04-01", lines=lines(BASE="1700000.00"))

    assert fourth.status_code == 201, fourth.content
    assert fourth.json()["version"] == 4
    rows = history(api, asha)
    assert [
        (row["version"], row["effective_from"], row["cancelled_at"] is not None) for row in rows
    ] == [
        (4, "2027-04-01", False),
        (3, "2027-04-01", True),
        (2, "2027-04-01", True),
        (1, "2025-04-01", False),
    ]
    assert rows[3]["effective_to"] == "2027-04-01"


def test_totals_in_a_body_are_ignored_and_recomputed(api, asha):
    response = revise(
        api,
        asha,
        "2026-11-01",
        bonus_annual="100000.00",
        gross_annual="1.00",
        net_annual="1.00",
        total_cost_annual="1.00",
    )

    body = response.json()
    assert response.status_code == 201, response.content
    # Earnings 1,600,000 + 580,000 + 362,500, plus the bonus; TAX out; employer cost in.
    assert body["gross_annual"] == "2642500.00"
    assert body["net_annual"] == "2164000.00"
    assert body["total_cost_annual"] == "2816500.00"


def test_version_increments_per_employee(api, asha, hr_user):
    ben = EmployeeFactory(country=country("US"), joining_date=date(2022, 1, 1))
    first_record(ben, None, hr_user, {"BASE": "100000.00"})

    versions = [
        revise(api, asha, "2026-11-01").json()["version"],
        revise(api, asha, "2027-01-01").json()["version"],
        api.post(
            history_url(ben.pk),
            {
                "effective_from": "2026-11-01",
                "lines": [{"component": "BASE", "annual_amount": "110000"}],
            },
            format="json",
        ).json()["version"],
    ]

    assert versions == [2, 3, 2]


def test_a_revision_after_the_exit_is_a_409(api, asha, hr_user):
    employees.exit_employee(asha, date(2026, 9, 30), actor=hr_user)

    response = revise(api, asha, "2026-10-01")

    assert response.status_code == 409
    assert response.json() == {"detail": "no revision after the exit on 2026-09-30"}


def test_a_revision_needs_an_effective_from(api, asha):
    response = api.post(history_url(asha.pk), {"lines": lines()}, format="json")

    assert response.status_code == 400
    assert response.json() == {"effective_from": ["effective_from is required when amounts change"]}


def test_rule_errors_are_keyed_by_the_component(api, asha):
    response = revise(api, asha, "2026-11-01", lines=lines(BASE="0.00", HRA="-5.00"))

    assert response.status_code == 400
    assert response.json() == {
        "BASE": ["BASE is required"],
        "HRA": ["HRA must be a non-negative number, got -5.00"],
    }


def test_a_component_listed_twice_is_a_400(api, asha):
    twice = [*lines(), {"component": "BASE", "annual_amount": "1.00"}]

    response = revise(api, asha, "2026-11-01", lines=twice)

    assert response.status_code == 400
    assert response.json() == {"lines": ["BASE appears twice in lines"]}


def test_a_malformed_amount_is_keyed_by_its_index_in_lines(api, asha):
    """DRF 3.18 reports a bad item of a list as an object keyed by the item's index."""
    bad = [
        {"component": "BASE", "annual_amount": "1450000.00"},
        {"component": "HRA", "annual_amount": "1.234"},
    ]

    response = revise(api, asha, "2026-11-01", lines=bad)

    assert response.status_code == 400
    assert response.json() == {
        "lines": {"1": {"annual_amount": ["Ensure that there are no more than 2 decimal places."]}}
    }


def test_warnings_come_back_with_the_new_record(api, asha):
    response = revise(
        api, asha, "2026-11-01", lines=[{"component": "BASE", "annual_amount": "300000.00"}]
    )

    assert response.status_code == 201, response.content
    assert response.json()["warnings"] == [
        {
            "field": "gross",
            "severity": "warning",
            "message": "gross 300,000 INR is below the India minimum 400,000",
        }
    ]


def test_a_future_joiners_only_record_cannot_be_cancelled(api, rates, hr_user):
    joiner = EmployeeFactory(joining_date=date(2027, 1, 1))
    record = first_record(joiner, None, hr_user)

    response = cancel(api, record.pk)

    assert response.status_code == 409
    assert response.json() == {"detail": "the first record cannot be cancelled"}


def test_unknown_ids_are_404(api, asha):
    assert api.get(history_url(999999)).status_code == 404
    assert api.post(history_url(999999), {"lines": lines()}, format="json").status_code == 404
    assert cancel(api, 999999).status_code == 404


def test_history_query_count(api, asha, django_assert_num_queries):
    """User from the JWT, the employee, rates, the records with their authors, their lines."""
    scheduled = revise(api, asha, "2027-04-01").json()
    cancel(api, scheduled["id"])

    with django_assert_num_queries(5):
        api.get(history_url(asha.pk))
