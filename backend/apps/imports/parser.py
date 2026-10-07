"""The import template's shape (SPEC F1). The row parser itself lands in step 5."""

from __future__ import annotations

from collections.abc import Iterable

IDENTITY_COLUMNS = (
    "EmployeeID",
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "country_code",
    "gender",
    "joining_date",
    "last_date",
    "effective_from",
    "bonus_annual",
)
REQUIRED_COLUMNS = (
    "EmployeeID",
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "country_code",
    "gender",
    "joining_date",
    "BASE",
)
ALIASES = {
    "employeecode": "EmployeeID",
    "employeeid": "EmployeeID",
    "empid": "EmployeeID",
    "id": "EmployeeID",
}


def normalize_header(name: str) -> str:
    """Case-, space-, underscore- and hyphen-insensitive header key."""
    return "".join(ch for ch in str(name).strip().lower() if ch not in " _-")


def template_columns(component_codes: Iterable[str]) -> list[str]:
    return [*IDENTITY_COLUMNS, *component_codes]
