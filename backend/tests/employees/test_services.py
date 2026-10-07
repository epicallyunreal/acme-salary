from datetime import date
from decimal import Decimal

import pytest

from apps.audit.models import AuditLog
from apps.compensation import services as compensation
from apps.compensation.models import CompensationRecord
from apps.compensation.services import RecordInput
from apps.core.exceptions import Conflict, Invalid
from apps.employees import services
from apps.employees.models import Employee
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

LINES = {
    "BASE": Decimal("1450000"),
    "HRA": Decimal("580000"),
    "ALLOWANCES": Decimal("362500"),
    "TAX": Decimal("478500"),
    "EMPLOYER_CONTRIBUTION": Decimal("174000"),
}


def record_input(effective_from=None, lines=LINES) -> RecordInput:
    return RecordInput(effective_from, Decimal("0"), "", lines)


def identity(**overrides) -> dict:
    values = dict(
        full_name="Asha Rao",
        email="Asha.Rao@acme.example",
        department="engineering",
        designation="Senior Engineer",
        level=3,
        country_code="IN",
        gender="female",
        joining_date=date(2024, 3, 1),
    )
    values.update(overrides)
    return values


@pytest.fixture
def with_first(lookups):
    employee = EmployeeFactory(joining_date=date(2024, 3, 1))
    compensation.add_first_record(employee, record_input())
    return employee


def test_next_employee_code_continues_from_the_greatest_code(lookups):
    assert services.next_employee_code() == "ACME-000001"
    EmployeeFactory(employee_code="ACME-010000")
    assert services.next_employee_code() == "ACME-010001"
    EmployeeFactory(employee_code="ACME-020000")
    assert services.next_employee_code() == "ACME-020001"


def test_create_employee_assigns_the_code_lowercases_the_email_and_audits(lookups):
    created = services.create_employee(identity(), record_input())

    employee = created.employee
    assert employee.employee_code == "ACME-000001"
    assert employee.email == "asha.rao@acme.example"
    assert employee.department.code == "engineering"
    assert created.record.version == 1
    assert created.record.effective_from == date(2024, 3, 1)
    assert created.warnings == []
    actions = list(
        AuditLog.objects.filter(employee=employee)
        .order_by("id")
        .values_list("action", "entity_type")
    )
    assert sorted(actions) == [("create", "employee"), ("revise", "compensation_record")]
    create_entry = AuditLog.objects.get(action="create")
    assert create_entry.before is None
    assert create_entry.after["employee_code"] == "ACME-000001"
    assert create_entry.after["current_record"]["version"] == 1


def test_create_employee_keeps_a_given_code_and_returns_warnings(lookups):
    created = services.create_employee(
        identity(employee_code="ACME-000500"), record_input(lines={"BASE": Decimal("300000")})
    )

    assert created.employee.employee_code == "ACME-000500"
    assert [w.code for w in created.warnings] == ["gross_below_minimum"]
    assert services.next_employee_code() == "ACME-000501"


def test_create_employee_rolls_back_when_the_record_is_invalid(lookups):
    with pytest.raises(Invalid) as excinfo:
        services.create_employee(
            identity(), record_input(lines={"BASE": Decimal("1"), "CPF": Decimal("1")})
        )

    assert excinfo.value.errors == {"CPF": ["CPF is not a component for IN"]}
    assert Employee.objects.count() == 0
    assert AuditLog.objects.count() == 0


def test_create_employee_rejects_bad_identity_before_writing(lookups):
    with pytest.raises(Invalid) as excinfo:
        services.create_employee(identity(department="Growth", level=0), record_input())

    assert excinfo.value.errors == {
        "department": ["Unknown department: Growth"],
        "level": ["level must be between 1 and 6"],
    }
    assert Employee.objects.count() == 0


@pytest.mark.parametrize("field", ["employee_code", "country_code"])
def test_update_identity_refuses_to_change_code_or_country(with_first, field):
    with pytest.raises(Invalid) as excinfo:
        services.update_identity(
            with_first, {field: "ACME-999999" if field == "employee_code" else "US"}
        )

    assert excinfo.value.errors == {field: [f"{field} cannot be changed"]}


def test_update_identity_accepts_the_unchanged_code(with_first):
    updated = services.update_identity(
        with_first, {"employee_code": with_first.employee_code, "level": 4}
    )

    assert updated.employee.level == 4


def test_update_identity_applies_the_change_and_audits(with_first):
    services.update_identity(
        with_first,
        {"department": "Sales", "designation": "Account Executive", "email": "New@acme.example"},
    )

    with_first.refresh_from_db()
    assert (with_first.department.code, with_first.designation, with_first.email) == (
        "sales",
        "Account Executive",
        "new@acme.example",
    )
    entry = AuditLog.objects.get(action="update")
    assert (entry.before["designation"], entry.after["designation"]) == (
        "Senior Engineer",
        "Account Executive",
    )
    assert entry.before["department"] == {"code": "engineering", "name": "Engineering"}
    assert entry.after["current_record"]["version"] == 1


def test_update_identity_rejects_an_email_in_use(with_first, lookups):
    other = EmployeeFactory(email="taken@acme.example")

    with pytest.raises(Invalid) as excinfo:
        services.update_identity(with_first, {"email": "TAKEN@acme.example"})

    assert excinfo.value.errors == {"email": [f"email already belongs to {other.employee_code}"]}


def test_exit_closes_the_open_record_the_day_after_and_audits(with_first):
    services.exit_employee(with_first, date(2026, 10, 31))

    with_first.refresh_from_db()
    assert with_first.last_date == date(2026, 10, 31)
    record = CompensationRecord.objects.get(employee=with_first)
    assert record.effective_to == date(2026, 11, 1)
    entry = AuditLog.objects.get(action="exit")
    assert entry.before["last_date"] is None
    assert entry.before["current_record"]["effective_to"] is None
    assert entry.after["last_date"] == "2026-10-31"
    assert entry.after["current_record"]["effective_to"] == "2026-11-01"


def test_a_future_last_date_is_a_scheduled_exit(with_first, today):
    services.exit_employee(with_first, date(2026, 12, 31))

    record = CompensationRecord.objects.get(employee=with_first)
    assert record.effective_to == date(2027, 1, 1)
    assert compensation.current_record(with_first, today) == record


@pytest.mark.parametrize("again", [date(2026, 10, 31), date(2026, 9, 30)])
def test_a_second_exit_is_a_409_even_with_the_same_date(with_first, again):
    services.exit_employee(with_first, date(2026, 9, 30))

    with pytest.raises(Conflict, match="employee already exited on 2026-09-30"):
        services.exit_employee(with_first, again)

    assert AuditLog.objects.filter(action="exit").count() == 1


def test_a_last_date_before_joining_is_a_400(with_first):
    with pytest.raises(Invalid) as excinfo:
        services.exit_employee(with_first, date(2024, 1, 1))

    assert excinfo.value.errors == {"last_date": ["last_date precedes joining_date"]}


def test_a_last_date_before_the_open_record_is_a_400(with_first):
    compensation.revise(
        with_first,
        record_input(effective_from=date(2025, 4, 1), lines={**LINES, "BASE": Decimal("1600000")}),
    )

    with pytest.raises(Invalid) as excinfo:
        services.exit_employee(with_first, date(2025, 3, 15))

    assert excinfo.value.errors == {
        "last_date": ["last_date precedes the current record (effective 2025-04-01)"]
    }


def test_exit_refuses_while_a_scheduled_revision_follows_then_works_after_cancel(with_first):
    scheduled = compensation.revise(
        with_first,
        record_input(effective_from=date(2027, 1, 1), lines={**LINES, "BASE": Decimal("1600000")}),
    ).record

    with pytest.raises(
        Conflict, match="scheduled revision on 2027-01-01 must be cancelled before exit"
    ):
        services.exit_employee(with_first, date(2026, 12, 31))

    compensation.cancel(scheduled)
    services.exit_employee(with_first, date(2026, 12, 31))

    first = CompensationRecord.objects.get(employee=with_first, version=1)
    assert first.effective_to == date(2027, 1, 1)
