"""Revision dating, cancellation and the one-open-record invariant (SPEC F3, DESIGN section 3)."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditLog
from apps.compensation import services
from apps.compensation.models import CompensationRecord
from apps.compensation.services import RecordInput
from apps.core.exceptions import Conflict, Invalid
from apps.employees import services as employees
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

LINES = {
    "BASE": Decimal("1450000"),
    "HRA": Decimal("580000"),
    "ALLOWANCES": Decimal("362500"),
    "TAX": Decimal("478500"),
    "EMPLOYER_CONTRIBUTION": Decimal("174000"),
}
RAISED = {**LINES, "BASE": Decimal("1600000")}


def record_input(effective_from=None, bonus="0", note="", lines=LINES) -> RecordInput:
    return RecordInput(effective_from, Decimal(bonus), note, lines)


@pytest.fixture
def employee(lookups):
    return EmployeeFactory(joining_date=date(2024, 3, 1))


@pytest.fixture
def with_first(employee):
    services.add_first_record(employee, record_input())
    return employee


def test_add_first_record_defaults_to_the_joining_date_and_audits(employee):
    written = services.add_first_record(employee, record_input(bonus="100000", note="offer"))

    record = written.record
    assert (record.version, record.effective_from, record.effective_to) == (
        1,
        date(2024, 3, 1),
        None,
    )
    assert record.currency_code == "INR"
    assert (record.gross_annual, record.net_annual, record.total_cost_annual) == (
        Decimal("2492500.00"),
        Decimal("2014000.00"),
        Decimal("2666500.00"),
    )
    assert record.lines.count() == 5
    assert written.warnings == []
    entry = AuditLog.objects.get()
    assert (entry.action, entry.entity_type, entry.employee) == (
        "revise",
        "compensation_record",
        employee,
    )
    assert entry.before is None
    assert entry.after["version"] == 1
    assert entry.after["note"] == "offer"
    assert entry.after["lines"][0] == {"component": "BASE", "annual_amount": "1450000.00"}


def test_add_first_record_rejects_a_component_from_another_country(employee):
    with pytest.raises(Invalid) as excinfo:
        services.add_first_record(
            employee, record_input(lines={**LINES, "NATIONAL_INSURANCE": Decimal("1")})
        )

    assert excinfo.value.errors == {
        "NATIONAL_INSURANCE": ["NATIONAL_INSURANCE is not a component for IN"]
    }
    assert CompensationRecord.objects.count() == 0


def test_revise_the_next_day_chains_half_open(with_first):
    written = services.revise(
        with_first, record_input(effective_from=date(2024, 3, 2), lines=RAISED)
    )

    first = CompensationRecord.objects.get(employee=with_first, version=1)
    assert first.effective_to == date(2024, 3, 2)
    assert (written.record.version, written.record.effective_to) == (2, None)
    assert (
        CompensationRecord.objects.filter(employee=with_first, effective_to__isnull=True).count()
        == 1
    )
    entry = AuditLog.objects.filter(action="revise").order_by("-id").first()
    assert (entry.before["version"], entry.before["effective_to"]) == (1, None)
    assert entry.after["version"] == 2
    assert entry.after["gross_annual"] == "2542500.00"


@pytest.mark.parametrize("day", [date(2024, 3, 1), date(2024, 2, 1)])
def test_revise_on_or_before_the_latest_record_is_a_400(with_first, day):
    with pytest.raises(Invalid) as excinfo:
        services.revise(with_first, record_input(effective_from=day, lines=RAISED))

    assert (
        "effective_from must be after 2024-03-01 (latest record)"
        in excinfo.value.errors["effective_from"]
    )


def test_revise_needs_an_effective_from(with_first):
    with pytest.raises(Invalid) as excinfo:
        services.revise(with_first, record_input(lines=RAISED))

    assert excinfo.value.errors == {
        "effective_from": ["effective_from is required when amounts change"]
    }


def test_revise_next_year_is_scheduled(with_first, today):
    written = services.revise(
        with_first, record_input(effective_from=date(2027, 1, 1), lines=RAISED)
    )

    assert services.current_record(with_first, today).version == 1
    assert services.current_record(with_first, date(2027, 1, 1)) == written.record
    assert services.latest_record(with_first) == written.record
    assert services.open_record(with_first) == written.record
    assert services.shown_record(with_first, today).version == 1


def test_cancel_a_scheduled_revision_keeps_the_row_and_reopens_the_previous(with_first, today):
    scheduled = services.revise(
        with_first, record_input(effective_from=date(2027, 1, 1), lines=RAISED)
    ).record

    cancelled = services.cancel(scheduled)

    assert cancelled.cancelled_at is not None
    assert CompensationRecord.objects.filter(employee=with_first).count() == 2
    first = CompensationRecord.objects.get(employee=with_first, version=1)
    assert first.effective_to is None
    assert services.latest_record(with_first) == first
    entry = AuditLog.objects.filter(action="cancel").get()
    assert entry.before["cancelled_at"] is None
    assert entry.after["cancelled_at"].startswith("2026-10-07T09:00")
    assert entry.employee == with_first


def test_cancel_the_current_record_is_a_409(with_first):
    current = CompensationRecord.objects.get(employee=with_first)

    with pytest.raises(Conflict, match="only a scheduled revision can be cancelled"):
        services.cancel(current)


def test_cancel_twice_is_a_409(with_first):
    scheduled = services.revise(
        with_first, record_input(effective_from=date(2027, 1, 1), lines=RAISED)
    ).record
    services.cancel(scheduled)

    with pytest.raises(Conflict, match="only a scheduled revision can be cancelled"):
        services.cancel(scheduled)


def test_cancel_a_future_joiners_only_record_is_a_409(lookups):
    joiner = EmployeeFactory(joining_date=date(2027, 1, 1))
    first = services.add_first_record(joiner, record_input()).record

    with pytest.raises(Conflict, match="the first record cannot be cancelled"):
        services.cancel(first)


def test_cancel_the_middle_of_two_scheduled_revisions_rechains(with_first):
    second = services.revise(
        with_first, record_input(effective_from=date(2027, 1, 1), lines=RAISED)
    ).record
    third = services.revise(
        with_first, record_input(effective_from=date(2027, 6, 1), lines=RAISED)
    ).record

    services.cancel(second)

    first = CompensationRecord.objects.get(employee=with_first, version=1)
    third.refresh_from_db()
    assert first.effective_to == date(2027, 6, 1)
    assert third.effective_to is None
    assert services.latest_record(with_first) == third


def test_versions_are_never_reused_after_a_cancel(with_first):
    second = services.revise(
        with_first, record_input(effective_from=date(2027, 1, 1), lines=RAISED)
    ).record
    services.cancel(second)

    again = services.revise(
        with_first, record_input(effective_from=date(2027, 2, 1), lines=RAISED)
    ).record

    assert again.version == 3
    assert services.next_version(with_first) == 4


def test_only_one_open_live_record_per_employee(with_first):
    with pytest.raises(IntegrityError), transaction.atomic():
        CompensationRecord.objects.create(
            employee=with_first,
            version=9,
            currency_code="INR",
            effective_from=date(2025, 1, 1),
            effective_to=None,
            gross_annual=1,
            net_annual=1,
            total_cost_annual=1,
            source="ui",
        )


def test_a_record_cannot_end_where_it_starts(with_first):
    with pytest.raises(IntegrityError), transaction.atomic():
        CompensationRecord.objects.create(
            employee=with_first,
            version=9,
            currency_code="INR",
            effective_from=date(2025, 1, 1),
            effective_to=date(2025, 1, 1),
            gross_annual=1,
            net_annual=1,
            total_cost_annual=1,
            source="ui",
        )


def test_no_revision_after_an_exit(with_first):
    employees.exit_employee(with_first, date(2026, 9, 30))

    with pytest.raises(Conflict, match="employee exited on 2026-09-30"):
        services.revise(with_first, record_input(effective_from=date(2026, 11, 1), lines=RAISED))
