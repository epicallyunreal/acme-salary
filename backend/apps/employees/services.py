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


def next_employee_code() -> str:
    """The greatest existing code plus one. Codes are fixed-width, so text order is numeric."""
    last = (
        Employee.objects.order_by("-employee_code").values_list("employee_code", flat=True).first()
    )
    number = int(last.split("-")[1]) + 1 if last else 1
    return f"ACME-{number:06d}"


def create_employee(
    identity: Mapping[str, Any],
    record: compensation.RecordInput,
    *,
    actor=None,
    at: datetime | None = None,
) -> Created:
    """Identity plus the first record in one transaction, audited as `create` and `revise`."""
    at = at or timezone.now()
    ctx = validators.build_context(
        emails=[identity.get("email")], codes=[identity.get("employee_code")]
    )
    warnings = validators.validate_identity(identity, ctx)
    with transaction.atomic():
        employee = Employee(
            employee_code=identity.get("employee_code") or next_employee_code(),
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
    """Edit identity fields. employee_code and country_code cannot change (SPEC F3)."""
    at = at or timezone.now()
    frozen = {
        name: [f"{name} cannot be changed"]
        for name, current in (
            ("employee_code", employee.employee_code),
            ("country_code", employee.country_id),
        )
        if name in changes and changes[name] != current
    }
    if frozen:
        raise Invalid(frozen)
    ctx = validators.build_context(employees=[employee], emails=[changes.get("email")])
    warnings = validators.validate_identity(changes, ctx, employee=employee)
    with transaction.atomic():
        shown = compensation.current_record(employee, ctx.today) or compensation.latest_record(
            employee
        )
        before = audit.snapshot_employee(employee, record=shown)
        for name, value in changes.items():
            if name == "department":
                employee.department = ctx.department_for(value)
            elif name == "email":
                employee.email = value.lower()
            elif name in validators.IDENTITY_FIELDS and name != "last_date":
                setattr(employee, name, value)
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
    ctx = validators.build_context(employees=[employee], today=today)
    validators.validate_exit(employee, last_date, ctx)
    with transaction.atomic():
        shown = compensation.current_record(employee, today) or compensation.latest_record(employee)
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
