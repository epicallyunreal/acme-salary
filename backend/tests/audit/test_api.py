"""The audit trail over HTTP (SPEC F7, section 8).

Each write path writes exactly one entry per entity written, and the entry's `before` and `after`
equal what the API showed before and after the write, minus the request-dependent keys. The
employee page's list is newest first, paginated, in a pinned number of queries.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

RECORD_REQUEST_KEYS = {"converted", "is_current", "is_scheduled"}
EMPLOYEE_REQUEST_KEYS = {"status", "shown_label"}
LINES = [
    {"component": "BASE", "annual_amount": "1450000.00"},
    {"component": "TAX", "annual_amount": "145000.00"},
]


def record_shape(data: dict) -> dict:
    return {key: value for key, value in data.items() if key not in RECORD_REQUEST_KEYS}


def employee_shape(data: dict) -> dict:
    shape = {key: value for key, value in data.items() if key not in EMPLOYEE_REQUEST_KEYS}
    if shape["current_record"] is not None:
        shape["current_record"] = record_shape(shape["current_record"])
    return shape


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

    revise_entry, create_entry = entries_after(mark)

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
    assert {create_entry.actor.email, revise_entry.actor.email} == {"hr@acme.example"}


def test_an_identity_edit_writes_one_update_entry(api, person):
    before = shown_employee(api, person.pk)
    mark = last_entry_id()

    api.patch(f"/api/v1/employees/{person.pk}/", {"designation": "Lead Engineer"}, format="json")

    (entry,) = entries_after(mark)
    assert (entry.action, entry.entity_type, entry.employee_id) == ("update", "employee", person.pk)
    assert entry.before == before
    assert entry.after == shown_employee(api, person.pk)
    assert entry.after["designation"] == "Lead Engineer"


def test_an_exit_writes_one_exit_entry(api, person):
    before = shown_employee(api, person.pk)
    mark = last_entry_id()

    api.post(f"/api/v1/employees/{person.pk}/exit/", {"last_date": "2026-09-30"}, format="json")

    (entry,) = entries_after(mark)
    assert (entry.action, entry.entity_type) == ("exit", "employee")
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
    assert entry.after == shown_record(api, person.pk, scheduled["id"])
    assert entry.after["cancelled_by"] == "hr@acme.example"


def test_the_audit_list_is_newest_first_and_paginated(api, person):
    api.patch(f"/api/v1/employees/{person.pk}/", {"level": 4}, format="json")

    response = api.get(f"/api/v1/employees/{person.pk}/audit/")

    body = response.json()
    assert response.status_code == 200
    assert (body["count"], body["next"], body["previous"]) == (2, None, None)
    newest, oldest = body["results"]
    assert (newest["action"], oldest["action"]) == ("update", "revise")
    assert newest["actor"] == "hr@acme.example"
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
