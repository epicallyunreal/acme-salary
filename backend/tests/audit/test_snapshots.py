"""Snapshot shapes. Step 4 adds the equality check against the detail serializers (DESIGN 1.8)."""

from datetime import date
from decimal import Decimal

import pytest

from apps.audit import services as audit
from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
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


@pytest.fixture
def record(lookups, hr_user):
    employee = EmployeeFactory(joining_date=date(2024, 3, 1))
    return compensation.add_first_record(
        employee, RecordInput(None, Decimal("5000"), "offer", LINES), actor=hr_user
    ).record


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
