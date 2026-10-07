"""The audit trail over HTTP (SPEC F7, section 8).

Each write path writes exactly one entry per entity written, and the entry's `before` and `after`
equal what the API showed before and after the write, minus the request-dependent keys. The
employee page's list is newest first, paginated, in a pinned number of queries.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
from apps.employees import services as employees
from tests.audit.shapes import employee_shape, record_shape
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

HR = "hr@acme.example"
LINES = [
    {"component": "BASE", "annual_amount": "1450000.00"},
    {"component": "TAX", "annual_amount": "145000.00"},
]


def shown_employee(api, pk: int) -> dict:
    response = api.get(f"/api/v1/employees/{pk}/")
    assert response.status_code == 200, response.content
    return employee_shape(response.json())


def shown_record(api, employee_pk: int, record_id: int) -> dict:
    rows = api.get(f"/api/v1/employees/{employee_pk}/compensation/").json()
    return record_shape(next(row for row in rows if row["id"] == record_id))


def entries_after(last_id: int) -> list[AuditLog]:
    return list(AuditLog.objects.filter(id__gt=last_id).order_by("id"))


def last_entry_id() -> int:
    return AuditLog.objects.order_by("-id").values_list("id", flat=True).first() or 0


def by_action(entries: list[AuditLog]) -> dict[str, AuditLog]:
    """F7 names the entries a write makes, not the order it makes them in."""
    keyed = {entry.action: entry for entry in entries}
    assert len(keyed) == len(entries), [entry.action for entry in entries]
    return keyed


def who(entry: AuditLog) -> tuple[int | None, str | None]:
    """The employee the entry is filed under, which the employee page reads, and its actor."""
    return entry.employee_id, entry.actor.email if entry.actor else None


@pytest.fixture
def person(rates, hr_user):
    employee = EmployeeFactory(joining_date=date(2024, 3, 1))
    compensation.add_first_record(
        employee,
        RecordInput(None, Decimal("0"), "offer", {"BASE": Decimal("1450000")}),
        actor=hr_user,
    )
    return employee


def test_create_writes_one_entry_per_entity_matching_the_api(api, rates):
    mark = last_entry_id()

    response = api.post(
        "/api/v1/employees/",
        {
            "full_name": "Meera Iyer",
            "email": "meera@acme.example",
            "department": "engineering",
            "designation": "Engineer",
            "level": 2,
            "country_code": "IN",
            "gender": "female",
            "joining_date": "2026-03-01",
            "lines": LINES,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    employee_id = response.json()["id"]
    record_id = response.json()["current_record"]["id"]

    entries = by_action(entries_after(mark))
    assert set(entries) == {"create", "revise"}
    create_entry, revise_entry = entries["create"], entries["revise"]

    assert (create_entry.action, create_entry.entity_type, create_entry.entity_id) == (
        "create",
        "employee",
        employee_id,
    )
    assert create_entry.before is None
    assert create_entry.after == shown_employee(api, employee_id)
    assert (revise_entry.action, revise_entry.entity_type, revise_entry.entity_id) == (
        "revise",
        "compensation_record",
        record_id,
    )
    assert revise_entry.before is None
    assert revise_entry.after == shown_record(api, employee_id, record_id)
    assert who(create_entry) == who(revise_entry) == (employee_id, HR)


def test_an_identity_edit_writes_one_update_entry(api, person):
    before = shown_employee(api, person.pk)
    mark = last_entry_id()

    response = api.patch(
        f"/api/v1/employees/{person.pk}/", {"designation": "Lead Engineer"}, format="json"
    )

    assert response.status_code == 200, response.content

    (entry,) = entries_after(mark)
    assert (entry.action, entry.entity_type, who(entry)) == ("update", "employee", (person.pk, HR))
    assert entry.before == before
    assert entry.after == shown_employee(api, person.pk)
    assert entry.after["designation"] == "Lead Engineer"


def test_an_exit_writes_one_exit_entry(api, person):
    before = shown_employee(api, person.pk)
    mark = last_entry_id()

    response = api.post(
        f"/api/v1/employees/{person.pk}/exit/", {"last_date": "2026-09-30"}, format="json"
    )

    assert response.status_code == 200, response.content

    (entry,) = entries_after(mark)
    assert (entry.action, entry.entity_type, who(entry)) == ("exit", "employee", (person.pk, HR))
    assert entry.before == before
    assert entry.after == shown_employee(api, person.pk)
    assert entry.after["current_record"]["effective_to"] == "2026-10-01"


def test_a_revision_writes_one_revise_entry_with_the_previous_record_before(api, person):
    previous_id = api.get(f"/api/v1/employees/{person.pk}/").json()["current_record"]["id"]
    previous = shown_record(api, person.pk, previous_id)
    mark = last_entry_id()

    response = api.post(
        f"/api/v1/employees/{person.pk}/compensation/",
        {"effective_from": "2027-04-01", "note": "raise", "lines": LINES},
        format="json",
    )

    (entry,) = entries_after(mark)
    assert (entry.action, entry.entity_type, entry.entity_id) == (
        "revise",
        "compensation_record",
        response.json()["id"],
    )
    assert who(entry) == (person.pk, HR)
    assert entry.before == previous
    assert entry.after == shown_record(api, person.pk, response.json()["id"])


def test_a_cancel_writes_one_cancel_entry(api, person):
    scheduled = api.post(
        f"/api/v1/employees/{person.pk}/compensation/",
        {"effective_from": "2027-04-01", "lines": LINES},
        format="json",
    ).json()
    before = shown_record(api, person.pk, scheduled["id"])
    mark = last_entry_id()

    api.delete(f"/api/v1/compensation/{scheduled['id']}/")

    (entry,) = entries_after(mark)
    assert (entry.action, entry.entity_type, entry.entity_id) == (
        "cancel",
        "compensation_record",
        scheduled["id"],
    )
    assert entry.before == before
    assert who(entry) == (person.pk, HR)
    assert entry.after == shown_record(api, person.pk, scheduled["id"])
    assert entry.after["cancelled_by"] == HR


def test_an_exit_before_pay_starts_writes_exit_then_cancel_matching_the_api(api, rates, hr_user):
    """D50: the exit entry shows the employee left with no record, then the cancel entry shows
    the record as the history does, before and after."""
    employee = EmployeeFactory(joining_date=date(2026, 9, 1))
    record = compensation.add_first_record(
        employee,
        RecordInput(date(2026, 12, 1), Decimal("0"), "offer", {"BASE": Decimal("1450000")}),
        actor=hr_user,
    ).record
    employee_before = shown_employee(api, employee.pk)
    record_before = shown_record(api, employee.pk, record.pk)
    mark = last_entry_id()

    response = api.post(
        f"/api/v1/employees/{employee.pk}/exit/", {"last_date": "2026-10-31"}, format="json"
    )

    assert response.status_code == 200, response.content
    entries = by_action(entries_after(mark))
    assert set(entries) == {"exit", "cancel"}
    exit_entry, cancel_entry = entries["exit"], entries["cancel"]
    assert exit_entry.pk < cancel_entry.pk
    assert exit_entry.before == employee_before
    assert exit_entry.after == shown_employee(api, employee.pk)
    assert exit_entry.after["current_record"] is None
    assert (cancel_entry.entity_type, cancel_entry.entity_id) == ("compensation_record", record.pk)
    assert cancel_entry.before == record_before
    assert cancel_entry.after == shown_record(api, employee.pk, record.pk)
    assert who(exit_entry) == who(cancel_entry) == (employee.pk, HR)


def test_the_audit_list_is_newest_first_and_paginated(api, person):
    """Newest by timestamp, then by id: the last entry written carries the earliest time."""
    first = AuditLog.objects.get(employee=person)
    api.patch(f"/api/v1/employees/{person.pk}/", {"level": 4}, format="json")
    employees.update_identity(person, {"level": 5}, at=datetime(2026, 10, 6, 9, tzinfo=UTC))
    patched, backdated = AuditLog.objects.filter(employee=person, action="update").order_by("id")

    response = api.get(f"/api/v1/employees/{person.pk}/audit/")

    body = response.json()
    assert response.status_code == 200
    assert (body["count"], body["next"], body["previous"]) == (3, None, None)
    assert [entry["id"] for entry in body["results"]] == [patched.pk, first.pk, backdated.pk]
    newest = body["results"][0]
    assert newest["action"] == "update"
    assert newest["actor"] == HR
    assert newest["timestamp"] == "2026-10-07T09:00:00+00:00"
    assert newest["after"]["level"] == 4
    assert set(newest) == {
        "id",
        "timestamp",
        "actor",
        "action",
        "entity_type",
        "entity_id",
        "before",
        "after",
        "import_batch",
    }


def test_the_audit_list_of_an_unknown_employee_is_404(api, rates):
    assert api.get("/api/v1/employees/999999/audit/").status_code == 404


def test_audit_list_query_count(api, person, django_assert_num_queries):
    """User from the JWT, the employee, the count, the page with its actors."""
    api.patch(f"/api/v1/employees/{person.pk}/", {"level": 4}, format="json")

    with django_assert_num_queries(4):
        api.get(f"/api/v1/employees/{person.pk}/audit/")
