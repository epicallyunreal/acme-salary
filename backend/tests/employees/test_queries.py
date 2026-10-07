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


def test_directory_queryset_annotations_agree_with_the_python_rules(people, today, rates):
    from apps.core import fx
    from apps.core.money import q2
    from apps.employees.queries import directory_queryset

    table = fx.RateTable.load(today)
    rows = {row.employee_code: row for row in directory_queryset(today, "USD", table)}

    assert list(rows) == sorted(rows, key=lambda code: (rows[code].full_name, rows[code].pk))
    for employee in people.values():
        row = rows[employee.employee_code]
        shown = pick_shown(row.live_records, today)
        assert row.gross_local == shown.gross_annual
        assert q2(row.gross) == table.convert(shown.gross_annual, shown.currency_code, "USD")
        assert row.status == status_on(employee, today)
        assert all(record.cancelled_at is None for record in row.live_records)
    assert [row.employee_code for row in rows.values() if row.status == "exited"] == ["ACME-000003"]
    assert set(
        directory_queryset(today, "USD", table)
        .filter(status="upcoming")
        .values_list("employee_code", flat=True)
    ) == {"ACME-000002"}


def test_directory_queryset_without_a_record(lookups, today, rates):
    from apps.core import fx
    from apps.employees.queries import directory_queryset

    EmployeeFactory(employee_code="ACME-000009")

    row = directory_queryset(today, "USD", fx.RateTable.load(today)).get()
    assert row.gross_local is None and row.gross is None
    assert row.live_records == []


def test_gross_bound():
    from apps.employees.queries import gross_bound

    assert gross_bound(Decimal("100"), "min") == Decimal("99.995")
    assert gross_bound(Decimal("100"), "max") == Decimal("100.005")
