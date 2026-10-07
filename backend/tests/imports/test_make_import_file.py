import csv
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from openpyxl import load_workbook

from apps.compensation.services import bulk_apply
from apps.imports.parser import IDENTITY_COLUMNS
from seed import profiles
from seed.generator import generate
from seed.lookups import ensure_lookups

pytestmark = pytest.mark.django_db


@pytest.fixture
def thirty(db):
    ensure_lookups()
    bulk_apply(
        generate(30, 42),
        source="seed",
        at=profiles.REFERENCE_DATETIME,
        today=profiles.REFERENCE_DATE,
    )


def run(path, **options) -> str:
    out = StringIO()
    call_command("make_import_file", out=str(path), stdout=out, **options)
    return out.getvalue()


def rows_of_xlsx(path) -> tuple[list[str], list[dict]]:
    sheet = load_workbook(path, read_only=True).worksheets[0]
    values = list(sheet.iter_rows(values_only=True))
    header = list(values[0])
    return header, [dict(zip(header, row, strict=True)) for row in values[1:]]


def test_all_writes_every_employee_with_raises_errors_and_new_rows(thirty, tmp_path):
    path = tmp_path / "import.xlsx"

    out = run(path, all=True, raises=5, errors=3, new=4)

    header, rows = rows_of_xlsx(path)
    assert header[: len(IDENTITY_COLUMNS)] == list(IDENTITY_COLUMNS)
    assert set(header[len(IDENTITY_COLUMNS) :]) == {
        "BASE",
        "HRA",
        "ALLOWANCES",
        "HOLIDAY_ALLOWANCE",
        "AWS",
        "TAX",
        "NATIONAL_INSURANCE",
        "SOCIAL_INSURANCE",
        "CPF",
        "EMPLOYER_CONTRIBUTION",
    }
    assert "wrote 34 rows" in out
    assert len(rows) == 34
    # Planted errors: negative BASE, bad email, unknown department, in turn.
    assert rows[0]["BASE"] == -5000
    assert rows[1]["email"] == "not-an-email"
    assert rows[2]["department"] == "Growth"
    # Raises: the first five existing rows are dated the first of next month (a date cell).
    raised = rows[3]["effective_from"]
    assert (raised.date() if hasattr(raised, "date") else raised) == date(2026, 11, 1)
    assert rows[5]["effective_from"] in (None, "")
    # New rows continue the code sequence.
    assert rows[30]["EmployeeID"] == "ACME-000031"
    assert rows[33]["EmployeeID"] == "ACME-000034"


def test_csv_output_matches_the_template(thirty, tmp_path):
    path = tmp_path / "import.csv"

    run(path, all=True)

    with path.open(encoding="utf-8") as handle:
        reader = list(csv.reader(handle))
    assert reader[0][: len(IDENTITY_COLUMNS)] == list(IDENTITY_COLUMNS)
    assert len(reader) == 31
    first = dict(zip(reader[0], reader[1], strict=True))
    assert first["EmployeeID"] == "ACME-000001"
    assert Decimal(first["BASE"]) > 0
    assert first["effective_from"] == ""


def test_raises_alone_writes_only_the_raised_employees(thirty, tmp_path):
    path = tmp_path / "raises.csv"

    out = run(path, raises=7)

    assert "wrote 7 rows" in out
