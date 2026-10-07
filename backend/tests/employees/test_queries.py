from datetime import date
from decimal import Decimal

import pytest
from django.db.models import Subquery

from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
from apps.core import fx
from apps.core.money import q2
from apps.employees import services
from apps.employees.models import Employee
from apps.employees.queries import (
    directory_queryset,
    gross_bound,
    pick_shown,
    shown_label,
    shown_record_subquery,
    status_on,
)
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

LINES = {"BASE": Decimal("1000000")}


def record_input(effective_from=None) -> RecordInput:
    return RecordInput(effective_from, Decimal("0"), "", LINES)


@pytest.fixture
def people(lookups):
    """current, future joiner, exited, cancelled revision, current plus scheduled."""
    current = EmployeeFactory(joining_date=date(2020, 1, 1))
    compensation.add_first_record(current, record_input())

    joiner = EmployeeFactory(joining_date=date(2027, 1, 1))
    compensation.add_first_record(joiner, record_input())

    exited = EmployeeFactory(joining_date=date(2020, 1, 1))
    compensation.add_first_record(exited, record_input())
    services.exit_employee(exited, date(2026, 6, 30))

    cancelled = EmployeeFactory(joining_date=date(2020, 1, 1))
    compensation.add_first_record(cancelled, record_input())
    scheduled = compensation.revise(cancelled, record_input(date(2027, 4, 1))).record
    compensation.cancel(scheduled)

    both = EmployeeFactory(joining_date=date(2020, 1, 1))
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
        ).values_list("pk", "shown_id")
    )

    for employee in people.values():
        records = list(employee.compensation_records.all())
        picked = pick_shown(records, today)
        assert picked is not None
        assert picked.pk == shown_ids[employee.pk], employee.employee_code

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
    table = fx.RateTable.load(today)
    rows = {row.pk: row for row in directory_queryset(today, "USD", table)}

    assert list(rows) == sorted(rows, key=lambda pk: (rows[pk].full_name, pk))
    for employee in people.values():
        row = rows[employee.pk]
        shown = pick_shown(row.live_records, today)
        assert row.gross_local == shown.gross_annual
        assert q2(row.gross) == table.convert(shown.gross_annual, shown.currency_code, "USD")
        assert row.status == status_on(employee, today)
        assert all(record.cancelled_at is None for record in row.live_records)
    assert [pk for pk, row in rows.items() if row.status == "exited"] == [people["exited"].pk]
    assert set(
        directory_queryset(today, "USD", table)
        .filter(status="upcoming")
        .values_list("pk", flat=True)
    ) == {people["joiner"].pk}


def test_directory_queryset_without_a_record(lookups, today, rates):
    EmployeeFactory()

    row = directory_queryset(today, "USD", fx.RateTable.load(today)).get()
    assert row.gross_local is None and row.gross is None
    assert row.live_records == []


def test_gross_bound():
    assert gross_bound(Decimal("100"), "min") == Decimal("99.995")
    assert gross_bound(Decimal("100"), "max") == Decimal("100.005")
