from datetime import date
from decimal import Decimal

import pytest
from django.db.models import Subquery

from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
from apps.employees import services
from apps.employees.models import Employee
from apps.employees.queries import pick_shown, shown_label, shown_record_subquery, status_on
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

LINES = {"BASE": Decimal("1000000")}


def record_input(effective_from=None) -> RecordInput:
    return RecordInput(effective_from, Decimal("0"), "", LINES)


@pytest.fixture
def people(lookups):
    """current, future joiner, exited, cancelled revision, current plus scheduled."""
    current = EmployeeFactory(employee_code="ACME-000001", joining_date=date(2020, 1, 1))
    compensation.add_first_record(current, record_input())

    joiner = EmployeeFactory(employee_code="ACME-000002", joining_date=date(2027, 1, 1))
    compensation.add_first_record(joiner, record_input())

    exited = EmployeeFactory(employee_code="ACME-000003", joining_date=date(2020, 1, 1))
    compensation.add_first_record(exited, record_input())
    services.exit_employee(exited, date(2026, 6, 30))

    cancelled = EmployeeFactory(employee_code="ACME-000004", joining_date=date(2020, 1, 1))
    compensation.add_first_record(cancelled, record_input())
    scheduled = compensation.revise(cancelled, record_input(date(2027, 4, 1))).record
    compensation.cancel(scheduled)

    both = EmployeeFactory(employee_code="ACME-000005", joining_date=date(2020, 1, 1))
    compensation.add_first_record(both, record_input())
    compensation.revise(both, record_input(date(2027, 4, 1)))

    return {
        "current": current,
        "joiner": joiner,
        "exited": exited,
        "cancelled": cancelled,
        "both": both,
    }


def test_pick_shown_agrees_with_the_subquery(people, today):
    shown_ids = dict(
        Employee.objects.annotate(
            shown_id=Subquery(shown_record_subquery(today).values("id")[:1])
        ).values_list("employee_code", "shown_id")
    )

    for employee in people.values():
        records = list(employee.compensation_records.all())
        picked = pick_shown(records, today)
        assert picked is not None
        assert picked.pk == shown_ids[employee.employee_code], employee.employee_code

    assert pick_shown(list(people["both"].compensation_records.all()), today).version == 1
    assert pick_shown(list(people["cancelled"].compensation_records.all()), today).version == 1
    assert pick_shown(list(people["joiner"].compensation_records.all()), today).version == 1
    assert pick_shown([], today) is None


def test_shown_label(people, today):
    def label(key):
        employee = people[key]
        return shown_label(
            employee, pick_shown(list(employee.compensation_records.all()), today), today
        )

    assert label("current") is None
    assert label("joiner") == "from 2027-01-01"
    assert label("exited") == "exited 2026-06-30"
    assert label("cancelled") is None
    assert label("both") is None


def test_status_on(people, today):
    assert status_on(people["current"], today) == "active"
    assert status_on(people["joiner"], today) == "upcoming"
    assert status_on(people["joiner"], date(2027, 2, 1)) == "active"
    assert status_on(people["exited"], today) == "exited"
    assert status_on(people["exited"], date(2026, 6, 30)) == "active"
