from datetime import UTC, date, datetime
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


@pytest.fixture
def before_pay(lookups):
    """Joined 2026-09-01 with pay from 2026-12-01, so the only record has never been current."""
    employee = EmployeeFactory(joining_date=date(2026, 9, 1))
    compensation.add_first_record(employee, record_input(effective_from=date(2026, 12, 1)))
    return employee


def test_create_employee_assigns_the_code_lowercases_the_email_and_audits(lookups):
    created = services.create_employee(identity(), record_input())

    employee = created.employee
    # The database numbers the employee; an app-created one has no legacy_code (D48).
    assert employee.employee_code == f"ACME-{employee.pk}"
    assert employee.legacy_code is None
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
    assert create_entry.after["employee_code"] == f"ACME-{employee.pk}"
    assert create_entry.after["legacy_code"] is None
    assert create_entry.after["current_record"]["version"] == 1


def test_create_employee_returns_the_warnings(lookups):
    created = services.create_employee(identity(), record_input(lines={"BASE": Decimal("300000")}))

    assert [w.code for w in created.warnings] == ["gross_below_minimum"]


def test_create_employee_rolls_back_when_the_record_is_invalid(lookups):
    with pytest.raises(Invalid) as excinfo:
        services.create_employee(
            identity(), record_input(lines={"BASE": Decimal("100000"), "CPF": Decimal("1")})
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


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("employee_code", "employee_code is assigned by the system"),
        ("legacy_code", "legacy_code is set only by an import"),
    ],
)
def test_update_identity_refuses_either_code_even_unchanged(with_first, field, message):
    """Neither code is ever set through the API, whatever value is sent (D48)."""
    with pytest.raises(Invalid) as excinfo:
        services.update_identity(with_first, {field: getattr(with_first, field), "level": 4})

    assert excinfo.value.errors == {field: [message]}


def test_update_identity_refuses_a_new_country_and_accepts_the_same_one(with_first):
    with pytest.raises(Invalid) as excinfo:
        services.update_identity(with_first, {"country_code": "US"})

    assert excinfo.value.errors == {"country_code": ["country_code cannot be changed"]}
    assert (
        services.update_identity(with_first, {"country_code": "IN", "level": 4}).employee.level == 4
    )


def test_update_identity_with_nothing_new_saves_and_audits_nothing(with_first):
    stamp = with_first.updated_at
    later = datetime(2026, 10, 8, 9, tzinfo=UTC)

    services.update_identity(with_first, {}, at=later)
    services.update_identity(
        with_first,
        {"designation": with_first.designation, "email": with_first.email.upper()},
        at=later,
    )

    with_first.refresh_from_db()
    assert with_first.updated_at == stamp
    assert not AuditLog.objects.filter(action="update").exists()


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


def test_a_last_date_before_the_open_record_is_a_400_and_its_first_day_is_not(with_first):
    """The day before the open record starts is the last refused date; its first day closes it
    after one day, so no off-by-one reaches the half-open CHECK as a 500 (D44)."""
    compensation.revise(
        with_first,
        record_input(effective_from=date(2025, 4, 1), lines={**LINES, "BASE": Decimal("1600000")}),
    )

    with pytest.raises(Invalid) as excinfo:
        services.exit_employee(with_first, date(2025, 3, 31))
    services.exit_employee(with_first, date(2025, 4, 1))

    assert excinfo.value.errors == {
        "last_date": ["last_date precedes the current record (effective 2025-04-01)"]
    }
    second = CompensationRecord.objects.get(employee=with_first, version=2)
    assert (second.effective_from, second.effective_to) == (date(2025, 4, 1), date(2025, 4, 2))


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


def test_create_employee_never_takes_either_code(with_first):
    """The database numbers every employee and only an import records a legacy_code (D48)."""
    with pytest.raises(Invalid) as excinfo:
        services.create_employee(
            identity(
                employee_code=with_first.employee_code,
                legacy_code="HR-10001",
                email="someone.else@acme.example",
            ),
            record_input(),
        )

    assert excinfo.value.errors == {
        "employee_code": ["employee_code is assigned by the system"],
        "legacy_code": ["legacy_code is set only by an import"],
    }
    assert Employee.objects.count() == 1


def test_a_second_exit_through_a_stale_instance_is_a_409(with_first):
    """A double submit holds two copies of the employee; the second is read fresh and refused."""
    stale = Employee.objects.get(pk=with_first.pk)
    services.exit_employee(with_first, date(2026, 9, 30))

    with pytest.raises(Conflict, match="employee already exited on 2026-09-30"):
        services.exit_employee(stale, date(2026, 9, 30))
    assert AuditLog.objects.filter(action="exit").count() == 1


def test_update_identity_refuses_a_joining_date_past_the_first_record(with_first):
    with pytest.raises(Invalid) as excinfo:
        services.update_identity(with_first, {"joining_date": date(2024, 3, 2)})

    assert excinfo.value.errors == {
        "joining_date": ["joining_date is after the first record (effective 2024-03-01)"]
    }


def test_an_exit_before_pay_starts_cancels_the_only_record(before_pay, hr_user, today):
    """D50: the record would never be current, so the exit cancels it instead of closing it."""
    services.exit_employee(before_pay, date(2026, 10, 31), actor=hr_user)

    before_pay.refresh_from_db()
    assert before_pay.last_date == date(2026, 10, 31)
    record = CompensationRecord.objects.get(employee=before_pay)
    assert (record.effective_to, record.cancelled_by) == (None, hr_user)
    assert record.cancelled_at is not None
    assert not compensation.live_records(before_pay).exists()
    assert compensation.shown_record(before_pay, today) is None
    exit_entry, cancel_entry = AuditLog.objects.filter(
        employee=before_pay, action__in=["exit", "cancel"]
    ).order_by("pk")
    assert (exit_entry.action, cancel_entry.action) == ("exit", "cancel")
    assert exit_entry.before["current_record"]["version"] == 1
    assert exit_entry.after["last_date"] == "2026-10-31"
    assert exit_entry.after["current_record"] is None
    assert (cancel_entry.entity_type, cancel_entry.entity_id) == ("compensation_record", record.pk)
    assert (cancel_entry.actor, cancel_entry.employee) == (hr_user, before_pay)
    assert cancel_entry.before["cancelled_at"] is None
    assert cancel_entry.after["cancelled_by"] == hr_user.email


def test_an_exit_on_or_after_the_start_closes_the_unstarted_record(before_pay):
    services.exit_employee(before_pay, date(2026, 12, 1))

    record = CompensationRecord.objects.get(employee=before_pay)
    assert (record.cancelled_at, record.effective_to) == (None, date(2026, 12, 2))
    assert not AuditLog.objects.filter(action="cancel").exists()


def test_an_exit_before_pay_starts_names_a_later_revision_to_cancel_first(before_pay):
    """The 409 names the revision that can be cancelled, not version 1, which cannot (D26)."""
    later = compensation.revise(
        before_pay,
        record_input(effective_from=date(2027, 4, 1), lines={**LINES, "BASE": Decimal("1600000")}),
    ).record

    with pytest.raises(
        Conflict, match="scheduled revision on 2027-04-01 must be cancelled before exit"
    ):
        services.exit_employee(before_pay, date(2026, 10, 31))

    compensation.cancel(later)
    services.exit_employee(before_pay, date(2026, 10, 31))

    assert not compensation.live_records(before_pay).exists()


def test_a_first_record_that_has_been_current_keeps_the_400(lookups):
    """D50 is narrow: pay that has started is history, so last_date cannot precede it."""
    employee = EmployeeFactory(joining_date=date(2024, 1, 1))
    compensation.add_first_record(employee, record_input(effective_from=date(2024, 3, 1)))

    with pytest.raises(Invalid) as excinfo:
        services.exit_employee(employee, date(2024, 2, 15))

    assert excinfo.value.errors == {
        "last_date": ["last_date precedes the current record (effective 2024-03-01)"]
    }
    assert CompensationRecord.objects.get(employee=employee).cancelled_at is None


@pytest.mark.parametrize(
    ("starts", "last_date"),
    [(date(2026, 10, 8), date(2026, 10, 7)), (date(2026, 12, 1), date(2026, 11, 30))],
    ids=["pay-starts-tomorrow", "exit-the-day-before-pay"],
)
def test_the_edges_of_an_exit_before_pay_starts_cancel(lookups, starts, last_date):
    """Pay starting tomorrow has not started today; the last day before pay is still before it."""
    employee = EmployeeFactory(joining_date=date(2026, 9, 1))
    compensation.add_first_record(employee, record_input(effective_from=starts))

    services.exit_employee(employee, last_date)

    record = CompensationRecord.objects.get(employee=employee)
    assert (record.cancelled_at is not None, record.effective_to) == (True, None)


def test_pay_that_starts_today_has_started(lookups):
    employee = EmployeeFactory(joining_date=date(2026, 9, 1))
    compensation.add_first_record(employee, record_input(effective_from=date(2026, 10, 7)))

    with pytest.raises(Invalid) as excinfo:
        services.exit_employee(employee, date(2026, 10, 6))

    assert excinfo.value.errors == {
        "last_date": ["last_date precedes the current record (effective 2026-10-07)"]
    }


def test_after_an_exit_before_pay_a_record_up_to_the_exit_is_still_possible(before_pay):
    """The way back when the employee did work for a while: a record dated on or before the exit
    ends the day after it, and one after the exit is a 409 like any other (D36)."""
    services.exit_employee(before_pay, date(2026, 10, 31))

    worked = compensation.revise(before_pay, record_input(effective_from=date(2026, 10, 1)))
    with pytest.raises(Conflict, match="no revision after the exit on 2026-10-31"):
        compensation.revise(before_pay, record_input(effective_from=date(2026, 11, 15)))

    assert (worked.record.version, worked.record.effective_to) == (2, date(2026, 11, 1))
    assert compensation.live_records(before_pay).get() == worked.record
