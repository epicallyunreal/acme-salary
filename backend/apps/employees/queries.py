"""Read-side rules for employees: which record is shown on a date, and the directory query.

The directory queryset is the one query the 300 ms target depends on (SPEC F4, DESIGN 1.3).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Literal

from django.db.models import (
    Case,
    CharField,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)

from apps.audit.models import AuditLog
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.core import fx
from apps.employees.models import Employee

TOLERANCE = Decimal("0.005")
STATUSES = ("active", "exited", "upcoming")


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


ACME_CODE = re.compile(r"^acme-(\d{1,18})$", re.IGNORECASE)


def parse_employee_code(text: str) -> int | None:
    """The id an ACME code names, read as a number for people typing a search: ACME-0017 and
    acme-17 both give 17 (D48). Anything else gives None."""
    match = ACME_CODE.match(text.strip())
    return int(match.group(1)) if match else None


def status_on(employee: Employee, on: date) -> str:
    if employee.joining_date > on:
        return "upcoming"
    if employee.last_date is not None and employee.last_date < on:
        return "exited"
    return "active"


def status_expression(on: date) -> Case:
    """`active`, `exited` or `upcoming` on the reporting date, in SQL, so `status=` is a WHERE."""
    return Case(
        When(joining_date__gt=on, then=Value("upcoming")),
        When(last_date__lt=on, then=Value("exited")),
        default=Value("active"),
        output_field=CharField(),
    )


def gross_bound(value: Decimal, side: Literal["min", "max"]) -> Decimal:
    """SPEC F4: range filters on the reporting-currency gross use a tolerance of 0.005."""
    return value - TOLERANCE if side == "min" else value + TOLERANCE


def lines_in_order() -> Prefetch:
    """A record's lines with their components, in the order the audit snapshot writes them."""
    lines = CompensationLine.objects.select_related("component").order_by(
        "component__sort_order", "component__code"
    )
    return Prefetch("lines", queryset=lines)


def live_records(*, with_lines: bool = False) -> QuerySet[CompensationRecord]:
    """Non-cancelled records newest first, with their authors; `with_lines` adds the lines in
    component order for the detail view."""
    queryset = (
        CompensationRecord.objects.filter(cancelled_at__isnull=True)
        .select_related("created_by", "cancelled_by")
        .order_by("-effective_from")
    )
    if with_lines:
        queryset = queryset.prefetch_related(lines_in_order())
    return queryset


def history_queryset(employee_id: int) -> QuerySet[CompensationRecord]:
    """Every record of one employee, cancelled ones included, newest first. A cancelled row may
    share its date with a live one (D43), so the tie goes to the higher version."""
    return (
        CompensationRecord.objects.filter(employee_id=employee_id)
        .select_related("created_by", "cancelled_by")
        .prefetch_related(lines_in_order())
        .order_by("-effective_from", "-version")
    )


def audit_queryset(employee_id: int) -> QuerySet[AuditLog]:
    """One employee's audit entries newest first, through the indexed AuditLog.employee (F7)."""
    return (
        AuditLog.objects.filter(employee_id=employee_id)
        .select_related("actor")
        .order_by("-timestamp", "-id")
    )


def live_records_prefetch(*, with_lines: bool = False) -> Prefetch:
    """The page's live records as `employee.live_records`, for pick_shown in the serializers."""
    return Prefetch(
        "compensation_records", queryset=live_records(with_lines=with_lines), to_attr="live_records"
    )


def detail_queryset() -> QuerySet[Employee]:
    """One employee with its lookups, its live records with their authors, and their lines:
    user, employee, records, lines and rates make the five queries of the detail endpoint."""
    return Employee.objects.select_related("country", "department").prefetch_related(
        live_records_prefetch(with_lines=True)
    )


def directory_queryset(
    on: date, reporting_currency: str, rates: fx.RateTable
) -> QuerySet[Employee]:
    """Employees annotated with the shown record's local gross, its reporting-currency value and
    the status on `on`. One correlated subquery per row and a CASE expression for the rate, so
    SQLite sorts and range-filters 10,000 rows in one pass; the shown records themselves come
    from a prefetch of the page. In code order, ascending, unless `ordering` asks otherwise: the
    grid's default sort, so the list and its export match what the grid shows (D63)."""
    shown = shown_record_subquery(on)
    return (
        Employee.objects.select_related("country", "department")
        .annotate(
            gross_local=Subquery(
                shown.values("gross_annual")[:1],
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            gross=ExpressionWrapper(
                F("gross_local")
                * rates.case_expression(reporting_currency, "country__currency_code"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            status=status_expression(on),
        )
        .prefetch_related(live_records_prefetch())
        .order_by("id")
    )
