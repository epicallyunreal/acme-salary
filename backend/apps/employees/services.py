"""Employee writes: create with a first record, edit identity, exit (SPEC F3, DESIGN 1.3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.compensation import services as compensation
from apps.compensation import validators
from apps.compensation.models import Source
from apps.core.dates import today_utc
from apps.core.exceptions import Invalid
from apps.employees.identity import apply_identity
from apps.employees.models import Employee

ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class Created:
    employee: Employee
    record: Any
    warnings: list[validators.Message]


@dataclass(frozen=True)
class Updated:
    employee: Employee
    warnings: list[validators.Message]


def create_employee(
    identity: Mapping[str, Any],
    record: compensation.RecordInput,
    *,
    actor=None,
    at: datetime | None = None,
) -> Created:
    """Identity plus the first record in one transaction, audited as `create` and `revise`.

    The database numbers the employee, ACME-<id>, and an API create never sets either code (D48).
    """
    at = at or timezone.now()
    validators.refuse_codes(identity)
    with transaction.atomic():
        # Validated under the write lock (IMMEDIATE mode), so a double submit is a 400 rather
        # than a unique-constraint error on the email (D44).
        ctx = validators.build_context(emails=[identity.get("email")])
        warnings = validators.validate_identity(identity, ctx)
        employee = Employee(
            full_name=identity["full_name"],
            email=identity["email"].lower(),
            gender=identity["gender"],
            department=ctx.department_for(identity["department"]),
            designation=identity["designation"],
            level=identity["level"],
            country=ctx.countries[identity["country_code"]],
            joining_date=identity["joining_date"],
            created_at=at,
            updated_at=at,
        )
        employee.save()
        written = compensation.add_first_record(
            employee, record, actor=actor, source=Source.UI, at=at, ctx=ctx
        )
        audit.record(
            "create",
            entity=employee,
            actor=actor,
            before=None,
            after=audit.snapshot_employee(employee, record=written.record),
            employee=employee,
            at=at,
        )
    return Created(employee, written.record, warnings + written.warnings)


def update_identity(
    employee: Employee,
    changes: Mapping[str, Any],
    *,
    actor=None,
    at: datetime | None = None,
) -> Updated:
    """Edit identity fields. Neither code is ever set through the API (D48), and country_code
    cannot change (SPEC F3)."""
    at = at or timezone.now()
    validators.refuse_codes(changes)
    if "country_code" in changes and changes["country_code"] != employee.country_id:
        raise Invalid({"country_code": ["country_code cannot be changed"]})
    with transaction.atomic():
        # Read and validated under the write lock (D44).
        employee.refresh_from_db()
        ctx = validators.build_context(employees=[employee], emails=[changes.get("email")])
        warnings = validators.validate_identity(changes, ctx, employee=employee)
        shown = compensation.shown_record(employee, ctx.today)
        before = audit.snapshot_employee(employee, record=shown)
        apply_identity(employee, changes, ctx)
        employee.updated_at = at
        employee.save()
        audit.record(
            "update",
            entity=employee,
            actor=actor,
            before=before,
            after=audit.snapshot_employee(employee, record=shown),
            employee=employee,
            at=at,
        )
    return Updated(employee, warnings)


def exit_employee(
    employee: Employee,
    last_date: date,
    *,
    actor=None,
    at: datetime | None = None,
    today: date | None = None,
) -> Employee:
    """Set last_date and close the open record at last_date + 1 (SPEC F3). One `exit` entry."""
    at = at or timezone.now()
    today = today or today_utc()
    with transaction.atomic():
        # Read and validated under the write lock, so a second exit is a 409 (D44).
        employee.refresh_from_db()
        ctx = validators.build_context(employees=[employee], today=today)
        validators.validate_exit(employee, last_date, ctx)
        shown = compensation.shown_record(employee, today)
        before = audit.snapshot_employee(employee, record=shown)
        employee.last_date = last_date
        employee.updated_at = at
        employee.save(update_fields=["last_date", "updated_at"])
        closed = compensation.close_open_record(employee, at=last_date + ONE_DAY)
        audit.record(
            "exit",
            entity=employee,
            actor=actor,
            before=before,
            after=audit.snapshot_employee(employee, record=closed or shown),
            employee=employee,
            at=at,
        )
    return employee
