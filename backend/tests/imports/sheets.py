"""Template-shaped rows and uploads for the import tests."""

import csv
import io
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.compensation.validators import IDENTITY_COLUMNS
from apps.employees.models import Employee

LINES = {
    "BASE": Decimal("1450000"),
    "HRA": Decimal("580000"),
    "ALLOWANCES": Decimal("362500"),
    "TAX": Decimal("478500"),
    "EMPLOYER_CONTRIBUTION": Decimal("174000"),
}
RAISED = {**LINES, "BASE": Decimal("1600000")}
HEADER = [*IDENTITY_COLUMNS, *LINES]
NEXT_MONTH = date(2026, 11, 1)


def sheet_row(employee: Employee, **cells) -> dict:
    """The row a sheet carries for `employee` as stored, with `cells` changed."""
    row = {
        "legacy_code": employee.legacy_code,
        "full_name": employee.full_name,
        "email": employee.email,
        "department": employee.department.code,
        "designation": employee.designation,
        "level": employee.level,
        "country_code": employee.country_id,
        "gender": employee.gender,
        "joining_date": employee.joining_date,
        **LINES,
    }
    row.update(cells)
    return row


def new_row(**cells) -> dict:
    row = {
        "legacy_code": "HR-20001",
        "full_name": "Meera Iyer",
        "email": "meera@acme.example",
        "department": "engineering",
        "designation": "Engineer",
        "level": 2,
        "country_code": "IN",
        "gender": "female",
        "joining_date": NEXT_MONTH,
        **LINES,
    }
    row.update(cells)
    return row


def cell_text(value) -> str:
    if value is None:
        return ""
    return value.isoformat() if isinstance(value, date) else str(value)


def upload_of(*rows, header=HEADER, name="october.csv") -> SimpleUploadedFile:
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(header)
    for row in rows:
        writer.writerow([cell_text(row.get(column)) for column in header])
    return SimpleUploadedFile(name, text.getvalue().encode(), content_type="text/csv")
