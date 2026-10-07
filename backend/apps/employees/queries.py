"""Read-side rules for employees: which record is shown on a date (DESIGN section 1.3).

The directory queryset with the reporting-currency annotation lands in step 3.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from django.db.models import Case, IntegerField, OuterRef, Q, Value, When

from apps.compensation.models import CompensationRecord
from apps.employees.models import Employee


def is_current(record: CompensationRecord, on: date) -> bool:
    return (
        record.cancelled_at is None
        and record.effective_from <= on
        and (record.effective_to is None or record.effective_to > on)
    )


def shown_record_subquery(on: date):
    """Live records of OuterRef("pk"), the current one first, else the latest. `[:1]` picks it."""
    current = Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gt=on))
    return (
        CompensationRecord.objects.filter(employee=OuterRef("pk"), cancelled_at__isnull=True)
        .annotate(
            is_current=Case(
                When(current, then=Value(1)), default=Value(0), output_field=IntegerField()
            )
        )
        .order_by("-is_current", "-effective_from")
    )


def pick_shown(records: Sequence[CompensationRecord], on: date) -> CompensationRecord | None:
    """The Python twin of shown_record_subquery over a prefetched list."""
    live = [record for record in records if record.cancelled_at is None]
    for record in live:
        if is_current(record, on):
            return record
    if not live:
        return None
    return max(live, key=lambda record: record.effective_from)


def shown_label(employee: Employee, record: CompensationRecord | None, on: date) -> str | None:
    """None when the record is current; "exited <date>" or "from <date>" otherwise (SPEC F3)."""
    if record is None or is_current(record, on):
        return None
    if employee.last_date is not None and employee.last_date < on:
        return f"exited {employee.last_date.isoformat()}"
    if record.effective_from > on:
        return f"from {record.effective_from.isoformat()}"
    return None


def status_on(employee: Employee, on: date) -> str:
    if employee.joining_date > on:
        return "upcoming"
    if employee.last_date is not None and employee.last_date < on:
        return "exited"
    return "active"
