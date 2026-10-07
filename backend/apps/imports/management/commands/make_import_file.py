"""`make_import_file --out <path> [--new N] [--raises N] [--errors N] [--all]` (SPEC section 11).

Writes a template-shaped .xlsx or .csv: N invented new employees, N existing employees with a
5 percent raise dated the first of the month after the reference date, N planted errors, or every
existing employee unchanged. Used by /perf-timing and to build the sample file in step 5.

Rows name employees by legacy_code (D48): an existing employee's own, a fresh unused HR- code for
a new joiner. An employee created in the app has none and is never written.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Q
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from apps.compensation.models import CompensationLine, CompensationRecord
from apps.compensation.validators import IDENTITY_COLUMNS, template_columns
from apps.core.models import SalaryComponent
from apps.employees.models import Employee
from seed import profiles
from seed.generator import generate, legacy_codes

ERROR_KINDS = (
    "negative_base",
    "bad_email",
    "unknown_department",
    "bad_level",
    "bad_date",
    "duplicate_legacy_code",
    "comma_decimal",
    "wrong_component",
)


def next_month_first(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def existing_rows(limit: int | None, raise_count: int, raise_date: date) -> list[dict]:
    """Every existing employee with the amounts the validators compare a row against: the
    record current on the reference date, else the latest live one (an exited employee's last).
    The raises go to the first employees still employed on the raise date, so every raise is a
    revision the rules accept."""
    employees = (
        Employee.objects.select_related("country", "department")
        .filter(legacy_code__isnull=False)
        .order_by("pk")
    )
    if limit is not None:
        employees = employees[:limit]
    employees = list(employees)
    on = profiles.REFERENCE_DATE
    current = (
        CompensationRecord.objects.filter(employee__in=employees, cancelled_at__isnull=True)
        .filter(effective_from__lte=on)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=on))
    )
    by_employee: dict[int, CompensationRecord] = {}
    for record in CompensationRecord.objects.filter(
        employee__in=employees, cancelled_at__isnull=True
    ).order_by("effective_from"):
        by_employee[record.employee_id] = record
    by_employee.update({record.employee_id: record for record in current})
    lines: dict[int, dict[str, Decimal]] = {}
    for record_id, code, amount in CompensationLine.objects.filter(
        record__in=by_employee.values()
    ).values_list("record_id", "component__code", "annual_amount"):
        lines.setdefault(record_id, {})[code] = amount

    rows = []
    raised = 0
    for employee in employees:
        record = by_employee.get(employee.pk)
        amounts = dict(lines.get(record.pk, {})) if record else {}
        bonus = record.bonus_annual if record else Decimal("0")
        effective_from = None
        employed = employee.last_date is None or employee.last_date >= raise_date
        if raised < raise_count and record is not None and employed:
            raised += 1
            amounts = {
                code: (amount * Decimal("1.05")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                for code, amount in amounts.items()
            }
            effective_from = raise_date
        rows.append(
            {
                "legacy_code": employee.legacy_code,
                "full_name": employee.full_name,
                "email": employee.email,
                "department": employee.department.code,
                "designation": employee.designation,
                "level": employee.level,
                "country_code": employee.country_id,
                "gender": employee.gender,
                "joining_date": employee.joining_date,
                "last_date": employee.last_date,
                "effective_from": effective_from,
                "bonus_annual": bonus,
                **amounts,
            }
        )
    return rows


def new_rows(count: int, seed: int, start_number: int, taken: set[str]) -> list[dict]:
    rows = []
    codes = legacy_codes(count, f"import-{seed}", taken)
    for entry, code in zip(generate(count, seed, start_number=start_number), codes, strict=True):
        identity = entry.identity
        first = entry.records[0]
        rows.append(
            {
                "legacy_code": code,
                "full_name": identity["full_name"],
                "email": identity["email"],
                "department": identity["department"],
                "designation": identity["designation"],
                "level": identity["level"],
                "country_code": identity["country_code"],
                "gender": identity["gender"],
                "joining_date": identity["joining_date"],
                "last_date": identity["last_date"],
                "effective_from": None,
                "bonus_annual": first.bonus_annual,
                **first.lines,
            }
        )
    return rows


def plant_errors(rows: list[dict], count: int) -> None:
    """Each planted error is one of ERROR_KINDS in turn, applied to successive rows."""
    for index in range(min(count, len(rows))):
        row = rows[index]
        kind = ERROR_KINDS[index % len(ERROR_KINDS)]
        if kind == "negative_base":
            row["BASE"] = Decimal("-5000")
        elif kind == "bad_email":
            row["email"] = "not-an-email"
        elif kind == "unknown_department":
            row["department"] = "Growth"
        elif kind == "bad_level":
            row["level"] = 9
        elif kind == "bad_date":
            row["joining_date"] = "31/02/2024"
        elif kind == "duplicate_legacy_code" and index + 1 < len(rows):
            row["legacy_code"] = rows[index + 1]["legacy_code"]
        elif kind == "comma_decimal":
            row["BASE"] = "1.200.000,50"
        elif kind == "wrong_component":
            row["HRA"] = row.get("HRA") or Decimal("1000")
            if row["country_code"] == "IN":
                row["country_code"] = "US"


def write_file(path: Path, columns: list[str], rows: list[dict]) -> None:
    if path.suffix.lower() == ".xlsx":
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("employees")
        sheet.append(columns)
        for row in rows:
            sheet.append([_xlsx_cell(sheet, row.get(column)) for column in columns])
        workbook.save(path)
    elif path.suffix.lower() == ".csv":
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(["" if row.get(c) is None else _text(row.get(c)) for c in columns])
    else:
        raise CommandError("--out must end in .xlsx or .csv")


def _xlsx_cell(sheet, value):
    """Numbers and dates as typed cells; every string as text, so a value that begins with `=`
    is never written as a formula."""
    if isinstance(value, str):
        cell = WriteOnlyCell(sheet, value=value)
        cell.data_type = "s"
        return cell
    return value


def _text(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class Command(BaseCommand):
    help = "Write a template-shaped import file from the live tables."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True)
        parser.add_argument("--new", type=int, default=0)
        parser.add_argument("--raises", type=int, default=0)
        parser.add_argument("--errors", type=int, default=0)
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        raise_date = next_month_first(profiles.REFERENCE_DATE)
        rows: list[dict] = []
        if options["all"]:
            rows += existing_rows(None, options["raises"], raise_date)
        elif options["raises"]:
            rows += existing_rows(options["raises"], options["raises"], raise_date)
        if options["new"]:
            taken = set(
                Employee.objects.exclude(legacy_code=None).values_list("legacy_code", flat=True)
            )
            start = (Employee.objects.aggregate(last=Max("pk"))["last"] or 0) + 1
            rows += new_rows(options["new"], options["seed"], start, taken)
        plant_errors(rows, options["errors"])
        codes = list(
            SalaryComponent.objects.filter(is_active=True)
            .order_by("sort_order", "code")
            .values_list("code", flat=True)
        )
        path = Path(options["out"])
        write_file(path, template_columns(codes), rows)
        self.stdout.write(
            f"wrote {len(rows)} rows to {path} ({len(IDENTITY_COLUMNS) + len(codes)} columns)"
        )
