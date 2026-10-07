"""make_import_file writes template-shaped sheets that name employees by legacy_code (D48)."""

import csv
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from openpyxl import load_workbook

from apps.compensation import services as compensation
from apps.compensation.services import RecordInput, bulk_apply
from apps.employees import services as employees
from apps.employees.models import Employee
from apps.imports.parser import IDENTITY_COLUMNS
from seed import profiles
from seed.generator import ordered_entries
from seed.lookups import ensure_lookups
from tests.factories import EmployeeFactory

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
        ordered_entries(30, 42),
        source="seed",
        at=profiles.REFERENCE_DATETIME,
        today=profiles.REFERENCE_DATE,
    )


def run(path, **options) -> str:
    out = StringIO()
    call_command("make_import_file", out=str(path), stdout=out, **options)
    return out.getvalue()


def current_base(employee: Employee) -> Decimal:
    on = profiles.REFERENCE_DATE
    record = compensation.current_record(employee, on) or compensation.latest_record(employee)
    return record.lines.get(component__code="BASE").annual_amount


def taken_codes() -> set[str]:
    return set(Employee.objects.exclude(legacy_code=None).values_list("legacy_code", flat=True))


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
    # Existing rows run in id order and carry each employee's own legacy_code.
    employees = list(Employee.objects.order_by("pk"))
    assert [row["legacy_code"] for row in rows[3:30]] == [e.legacy_code for e in employees[3:30]]
    raised = (current_base(employees[3]) * Decimal("1.05")).quantize(1, rounding=ROUND_HALF_UP)
    assert rows[3]["BASE"] == raised
    # Seed 42 is fixed, so the raised row is known by name too.
    assert (rows[3]["legacy_code"], rows[3]["full_name"], rows[3]["BASE"]) == (
        "HR-90977",
        "Abdul Hopkins",
        122955,
    )
    # New joiners get fresh HR- codes that no employee holds.
    fresh = [row["legacy_code"] for row in rows[30:]]
    assert all(re.fullmatch(r"HR-\d{5}", code) for code in fresh)
    assert len(set(fresh)) == 4 and not set(fresh) & taken_codes()


def test_every_planted_error_kind_is_written(thirty, tmp_path):
    path = tmp_path / "errors.xlsx"

    run(path, all=True, errors=8)

    _, rows = rows_of_xlsx(path)
    assert rows[0]["BASE"] == -5000
    assert rows[1]["email"] == "not-an-email"
    assert rows[2]["department"] == "Growth"
    assert rows[3]["level"] == 9
    assert rows[4]["joining_date"] == "31/02/2024"
    assert rows[5]["legacy_code"] == rows[6]["legacy_code"]
    assert rows[6]["BASE"] == "1.200.000,50"
    assert rows[7]["HRA"] is not None and rows[7]["country_code"] != "IN"


def test_new_alone_invents_employees_with_unused_legacy_codes(thirty, tmp_path):
    path = tmp_path / "new.xlsx"

    out = run(path, new=3)

    _, rows = rows_of_xlsx(path)
    assert "wrote 3 rows" in out
    codes = [row["legacy_code"] for row in rows]
    assert len(set(codes)) == 3 and not set(codes) & taken_codes()
    assert all(row["effective_from"] is None for row in rows)


def test_an_employee_created_in_the_app_is_never_written(thirty, tmp_path):
    """The import serves the legacy system's employees only (D48)."""
    added = EmployeeFactory(joining_date=date(2024, 1, 1))
    compensation.add_first_record(
        added, RecordInput(None, Decimal("0"), "", {"BASE": Decimal("900000")})
    )
    path = tmp_path / "all.xlsx"

    out = run(path, all=True)

    _, rows = rows_of_xlsx(path)
    assert "wrote 30 rows" in out
    assert added.email not in {row["email"] for row in rows}


def test_csv_output_matches_the_template(thirty, tmp_path):
    path = tmp_path / "import.csv"

    run(path, all=True)

    with path.open(encoding="utf-8") as handle:
        reader = list(csv.reader(handle))
    assert reader[0][: len(IDENTITY_COLUMNS)] == list(IDENTITY_COLUMNS)
    assert len(reader) == 31
    first = dict(zip(reader[0], reader[1], strict=True))
    # ACME-1 is the longest-serving employee (D48), and the row carries the current record.
    earliest = Employee.objects.order_by("pk").first()
    assert earliest.joining_date == min(Employee.objects.values_list("joining_date", flat=True))
    assert first["legacy_code"] == earliest.legacy_code
    assert first["full_name"] == earliest.full_name
    assert first["joining_date"] == earliest.joining_date.isoformat()
    assert first["effective_from"] == ""
    assert Decimal(first["BASE"]) == current_base(earliest)
    assert (first["legacy_code"], first["full_name"], first["joining_date"], first["BASE"]) == (
        "HR-62905",
        "Sian Cox",
        "2015-08-09",
        "326200.00",
    )


def test_an_exited_employee_carries_their_last_record_and_gets_no_raise(thirty, tmp_path):
    """The rules compare a row with the current record, else the latest live one, and refuse a
    raise after the exit, so the file writes the latest amounts and raises the next employee."""
    first, second = Employee.objects.order_by("pk")[:2]
    assert compensation.live_records(first).count() > 1
    employees.exit_employee(first, date(2026, 6, 30))
    path = tmp_path / "raises.xlsx"

    run(path, all=True, raises=1)

    _, rows = rows_of_xlsx(path)
    latest = compensation.latest_record(first)
    assert rows[0]["BASE"] == latest.lines.get(component__code="BASE").annual_amount
    assert (rows[0]["effective_from"], rows[1]["effective_from"]) == (None, datetime(2026, 11, 1))
    assert rows[1]["legacy_code"] == second.legacy_code


def test_raises_alone_writes_only_the_raised_employees(thirty, tmp_path):
    path = tmp_path / "raises.csv"

    out = run(path, raises=7)

    assert "wrote 7 rows" in out


def test_the_output_extension_must_be_xlsx_or_csv(thirty, tmp_path):
    with pytest.raises(CommandError, match="must end in .xlsx or .csv"):
        run(tmp_path / "import.txt", all=True)
