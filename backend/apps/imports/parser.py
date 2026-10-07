"""The import template's shape (SPEC F1). The row parser itself lands in step 5.

The first column is legacy_code, the code the legacy system gave the employee (D48). The old
EmployeeID headers are read as legacy_code only when a sheet has no legacy_code column; when it
has one, they are ignored with the usual "Ignored unknown column" warning.
"""

from __future__ import annotations

from collections.abc import Iterable

IDENTITY_COLUMNS = (
    "legacy_code",
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
    "legacy_code",
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
# Read as legacy_code when the sheet has no legacy_code column of its own.
ALIASES = {
    "employeecode": "legacy_code",
    "employeeid": "legacy_code",
    "empid": "legacy_code",
}


def normalize_header(name: str) -> str:
    """Case-, space-, underscore- and hyphen-insensitive header key."""
    return "".join(ch for ch in str(name).strip().lower() if ch not in " _-")


def template_columns(component_codes: Iterable[str]) -> list[str]:
    return [*IDENTITY_COLUMNS, *component_codes]
