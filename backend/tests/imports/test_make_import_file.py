import csv
from datetime import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from openpyxl import load_workbook

from apps.compensation.services import bulk_apply
from apps.imports.parser import IDENTITY_COLUMNS
from seed import profiles
from seed.generator import generate
from seed.lookups import ensure_lookups

pytestmark = pytest.mark.django_db

COMPONENT_COLUMNS = {
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
    assert set(header[len(IDENTITY_COLUMNS) :]) == COMPONENT_COLUMNS
    assert "wrote 34 rows" in out
    assert len(rows) == 34
    # Planted errors: negative BASE, bad email, unknown department, in turn.
    assert rows[0]["BASE"] == -5000
    assert rows[1]["email"] == "not-an-email"
    assert rows[2]["department"] == "Growth"
    # Raises: the first five existing rows are dated the first of next month, as date cells.
    assert rows[3]["effective_from"] == datetime(2026, 11, 1)
    assert rows[5]["effective_from"] is None
    # Row 3 is ACME-000004, whose current base at seed 42 is 1,381,400, raised 5 percent.
    assert rows[3]["BASE"] == 1450470
    assert rows[5]["EmployeeID"] == "ACME-000006"
    # New rows continue the code sequence.
    assert rows[30]["EmployeeID"] == "ACME-000031"
    assert rows[33]["EmployeeID"] == "ACME-000034"


def test_every_planted_error_kind_is_written(thirty, tmp_path):
    path = tmp_path / "errors.xlsx"

    run(path, all=True, errors=8)

    _, rows = rows_of_xlsx(path)
    assert rows[0]["BASE"] == -5000
    assert rows[1]["email"] == "not-an-email"
    assert rows[2]["department"] == "Growth"
    assert rows[3]["level"] == 9
    assert rows[4]["joining_date"] == "31/02/2024"
    assert rows[5]["EmployeeID"] == rows[6]["EmployeeID"]
    assert rows[6]["BASE"] == "1.200.000,50"
    assert rows[7]["HRA"] is not None and rows[7]["country_code"] != "IN"


def test_new_alone_invents_employees_after_the_last_code(thirty, tmp_path):
    path = tmp_path / "new.xlsx"

    out = run(path, new=3)

    _, rows = rows_of_xlsx(path)
    assert "wrote 3 rows" in out
    assert [row["EmployeeID"] for row in rows] == ["ACME-000031", "ACME-000032", "ACME-000033"]
    assert all(row["effective_from"] is None for row in rows)


def test_csv_output_matches_the_template(thirty, tmp_path):
    path = tmp_path / "import.csv"

    run(path, all=True)

    with path.open(encoding="utf-8") as handle:
        reader = list(csv.reader(handle))
    assert reader[0][: len(IDENTITY_COLUMNS)] == list(IDENTITY_COLUMNS)
    assert len(reader) == 31
    first = dict(zip(reader[0], reader[1], strict=True))
    assert first["EmployeeID"] == "ACME-000001"
    assert first["full_name"] == "Margaret Johnson"
    # The current record, not the joining one: three April raises since 2017.
    assert first["BASE"] == "220500.00"
    assert first["joining_date"] == "2017-04-19"
    assert first["effective_from"] == ""
    assert Decimal(first["BASE"]) == Decimal("220500")


def test_raises_alone_writes_only_the_raised_employees(thirty, tmp_path):
    path = tmp_path / "raises.csv"

    out = run(path, raises=7)

    assert "wrote 7 rows" in out


def test_the_output_extension_must_be_xlsx_or_csv(thirty, tmp_path):
    with pytest.raises(CommandError, match="must end in .xlsx or .csv"):
        run(tmp_path / "import.txt", all=True)
