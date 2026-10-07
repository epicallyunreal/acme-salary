"""Snapshot shapes, and their equality with the detail serializers (DESIGN 1.8, D34, SPEC F7).

An audit entry's `before` and `after` must match what the API shows, so the snapshots and the
serializers are held equal here, minus the request-dependent keys.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.audit import services as audit
from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
from apps.core.fx import RateTable
from apps.core.money import render
from apps.employees import queries
from apps.employees import services as employees
from apps.employees.serializers import CompensationRecordSerializer, EmployeeDetailSerializer
from tests.conftest import TODAY
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

LINES = {"BASE": Decimal("1000000"), "TAX": Decimal("100000")}

RECORD_KEYS = {
    "id",
    "employee",
    "version",
    "effective_from",
    "effective_to",
    "cancelled_at",
    "cancelled_by",
    "currency_code",
    "bonus_annual",
    "gross_annual",
    "net_annual",
    "total_cost_annual",
    "source",
    "note",
    "created_at",
    "created_by",
    "lines",
}
EMPLOYEE_KEYS = {
    "id",
    "employee_code",
    "full_name",
    "email",
    "gender",
    "department",
    "designation",
    "level",
    "country",
    "joining_date",
    "last_date",
    "created_at",
    "updated_at",
    "current_record",
}
RECORD_REQUEST_KEYS = {"converted", "is_current", "is_scheduled"}
EMPLOYEE_REQUEST_KEYS = {"status", "shown_label"}


@pytest.fixture
def record(lookups, hr_user):
    employee = EmployeeFactory(joining_date=date(2024, 3, 1))
    return compensation.add_first_record(
        employee, RecordInput(None, Decimal("5000"), "offer", LINES), actor=hr_user
    ).record


@pytest.fixture
def context(rates):
    return {"on": TODAY, "reporting_currency": "USD", "rates": RateTable.load(TODAY)}


def record_shape(data: dict) -> dict:
    return {key: value for key, value in data.items() if key not in RECORD_REQUEST_KEYS}


def employee_shape(data: dict) -> dict:
    shape = {key: value for key, value in data.items() if key not in EMPLOYEE_REQUEST_KEYS}
    if shape["current_record"] is not None:
        shape["current_record"] = record_shape(shape["current_record"])
    return shape


def test_snapshot_record_reads_lines_in_component_order(record, hr_user):
    snapshot = audit.snapshot_record(record)

    assert set(snapshot) == RECORD_KEYS
    assert snapshot["lines"] == [
        {"component": "BASE", "annual_amount": Decimal("1000000.00")},
        {"component": "TAX", "annual_amount": Decimal("100000.00")},
    ]
    assert snapshot["created_by"] == hr_user.email
    assert snapshot["cancelled_by"] is None
    assert snapshot["bonus_annual"] == Decimal("5000.00")


def test_snapshot_employee_shape(record):
    employee = record.employee

    bare = audit.snapshot_employee(employee)
    with_record = audit.snapshot_employee(employee, record=record)

    assert set(bare) == EMPLOYEE_KEYS
    assert bare["current_record"] is None
    assert bare["department"] == {"code": "engineering", "name": "Engineering"}
    assert bare["country"] == {"code": "IN", "name": "India", "currency_code": "INR"}
    assert with_record["current_record"]["version"] == 1


def test_build_renders_a_snapshot_to_json_safe_values(record):
    entry = audit.build("revise", entity=record, before=None, after=audit.snapshot_record(record))

    assert entry.after["gross_annual"] == "1005000.00"
    assert entry.after["effective_from"] == "2024-03-01"
    assert entry.after["lines"][0]["annual_amount"] == "1000000.00"


def test_snapshot_record_equals_the_serializer(record, context, hr_user):
    """A current record, then the same employee's cancelled scheduled revision."""
    scheduled = compensation.revise(
        record.employee,
        RecordInput(date(2027, 1, 1), Decimal("0"), "raise", LINES),
        actor=hr_user,
    ).record
    compensation.cancel(scheduled, actor=hr_user)

    for pk in (record.pk, scheduled.pk):
        shown = queries.history_queryset(record.employee_id).get(pk=pk)
        data = CompensationRecordSerializer(shown, context=context).data

        assert render(audit.snapshot_record(shown)) == record_shape(data)


def test_snapshot_employee_equals_the_serializer(record, context, hr_user):
    """With the shown record, then after an exit, which sets last_date and closes the record."""
    employee = record.employee
    employees.exit_employee(employee, date(2026, 9, 30), actor=hr_user)

    shown = queries.detail_queryset().get(pk=employee.pk)
    data = EmployeeDetailSerializer(shown, context=context).data
    snapshot = audit.snapshot_employee(shown, record=compensation.shown_record(shown, TODAY))

    assert render(snapshot) == employee_shape(data)
    assert data["last_date"] == "2026-09-30"
    assert data["current_record"]["effective_to"] == "2026-10-01"
