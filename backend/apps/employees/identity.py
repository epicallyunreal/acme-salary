"""Applying validated identity values to an Employee, shared by the single and bulk paths."""

from collections.abc import Mapping
from typing import Any

from apps.employees.models import Employee

IDENTITY_FIELDS = (
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "gender",
    "joining_date",
)


def apply_identity(employee: Employee, values: Mapping[str, Any], ctx) -> None:
    """Set the identity fields in `values`. last_date, employee_code and country stay put."""
    for name, value in values.items():
        if name == "department":
            employee.department = ctx.department_for(value)
        elif name == "email":
            employee.email = value.lower()
        elif name in IDENTITY_FIELDS:
            setattr(employee, name, value)
