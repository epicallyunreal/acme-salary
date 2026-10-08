"""`make_import_file --out <path> [--new N] [--raises N] [--bonus N] [--promotions N] [--exits N]
[--errors N] [--all] [--base] [--effective YYYY-MM-DD] [--share K] [--joined-after YYYY-MM-DD]`
(SPEC section 11, D72).

Writes a template-shaped .xlsx or .csv: N invented new employees, N existing employees with a
raise of 3 to 8%, N with 5 to 15% of base added to their bonus, N promoted one level, N exited
on the effective date, N planted errors, every existing employee unchanged, or with `--base` the
seed's whole organisation from the generator alone, no database read. Used by /perf-timing, the
step 5 sample and the Demo data page's files.

Rows name employees by legacy_code (D48): an existing employee's own, a fresh unused HR- code for
a new joiner. An employee created in the app has none and is never written. A revision file takes
the first N of its share by id among current employees whose latest live record is dated before
the file's effective date, so a file regenerated after its import moves on to the next people.
The joiners of two files come from one stream, the second file's after the first's, so files
made from one database never share a code or an email (D72).
"""

from __future__ import annotations

import csv
import io
import random
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, Max, OuterRef, Q
from django.db.models.functions import Mod
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from apps.compensation.models import CompensationLine, CompensationRecord
from apps.compensation.validators import IDENTITY_COLUMNS, template_columns
from apps.core.dates import today_utc
from apps.core.models import SalaryComponent
from apps.employees.models import Employee
from apps.exports.writers import XML_ILLEGAL
from seed import profiles
from seed.generator import generate, legacy_codes, ordered_entries

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
SHARES = 5  # employee id modulo this is a file's share of the directory (D72)
# In basis points, drawn whole, so no float enters the money arithmetic (rule 2).
RAISE_RANGE = (300, 800)
BONUS_RANGE = (500, 1500)
PROMOTION_RANGE = (1200, 2000)
BASIS_POINTS = Decimal(10_000)
DEPARTMENTS = {spec.code: spec for spec in profiles.DEPARTMENTS}
ONE = Decimal("1")


def next_month_first(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def whole(value: Decimal) -> Decimal:
    return value.quantize(ONE, rounding=ROUND_HALF_UP)


def proportion(rng: random.Random, low: int, high: int) -> Decimal:
    """A share of base between `low` and `high` basis points."""
    return Decimal(rng.randint(low, high)) / BASIS_POINTS


def pay_of(employees: Iterable[Employee], on: date | None) -> dict[int, tuple[Decimal, dict]]:
    """Each employee's bonus and lines: the record current on `on`, else the latest live one (an
    exited employee's last). With no `on`, the latest live record, which is what a revision
    replaces, so a raise builds on a revision already scheduled instead of undoing it."""
    employees = list(employees)
    by_employee: dict[int, CompensationRecord] = {}
    for record in CompensationRecord.objects.filter(
        employee__in=employees, cancelled_at__isnull=True
    ).order_by("effective_from"):
        by_employee[record.employee_id] = record
    if on is not None:
        current = (
            CompensationRecord.objects.filter(employee__in=employees, cancelled_at__isnull=True)
            .filter(effective_from__lte=on)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=on))
        )
        by_employee.update({record.employee_id: record for record in current})
    lines: dict[int, dict[str, Decimal]] = {}
    for record_id, code, amount in CompensationLine.objects.filter(
        record__in=by_employee.values()
    ).values_list("record_id", "component__code", "annual_amount"):
        lines.setdefault(record_id, {})[code] = amount
    return {
        employee_id: (record.bonus_annual, dict(lines.get(record.pk, {})))
        for employee_id, record in by_employee.items()
    }


def current_employees(
    *,
    share: int | None = None,
    revisable_on: date | None = None,
    below_level: int | None = None,
    limit: int | None = None,
) -> list[Employee]:
    """The employees on staff with no exit on file, by id, in `share` when given, with no live
    record dated on or after `revisable_on` when given, below `below_level` when given."""
    employees = (
        Employee.objects.select_related("country", "department")
        .filter(legacy_code__isnull=False, last_date__isnull=True)
        .order_by("pk")
    )
    if share is not None:
        employees = employees.annotate(share=Mod("pk", SHARES)).filter(share=share)
    if revisable_on is not None:
        dated_after = CompensationRecord.objects.filter(
            employee=OuterRef("pk"), cancelled_at__isnull=True, effective_from__gte=revisable_on
        )
        employees = employees.filter(~Exists(dated_after))
    if below_level is not None:
        employees = employees.filter(level__lt=below_level)
    if limit is not None:
        employees = employees[:limit]
    return list(employees)


def employee_row(
    employee: Employee,
    bonus: Decimal,
    amounts: dict[str, Decimal],
    *,
    effective_from: date | None = None,
    last_date: date | None = None,
    level: int | None = None,
    designation: str | None = None,
) -> dict:
    return {
        "legacy_code": employee.legacy_code,
        "full_name": employee.full_name,
        "email": employee.email,
        "department": employee.department.code,
        "designation": designation or employee.designation,
        "level": level or employee.level,
        "country_code": employee.country_id,
        "gender": employee.gender,
        "joining_date": employee.joining_date,
        "last_date": last_date or employee.last_date,
        "effective_from": effective_from,
        "bonus_annual": bonus,
        **amounts,
    }


def scaled(amounts: dict[str, Decimal], factor: Decimal) -> dict[str, Decimal]:
    return {code: whole(amount * factor) for code, amount in amounts.items()}


def all_rows(on: date) -> list[dict]:
    """Every existing employee unchanged, leavers with their `last_date` (D64)."""
    employees = list(
        Employee.objects.select_related("country", "department")
        .filter(legacy_code__isnull=False)
        .order_by("pk")
    )
    pay = pay_of(employees, on)
    return [employee_row(e, *pay.get(e.pk, (Decimal("0"), {}))) for e in employees]


def raise_rows(employees: list[Employee], effective: date, seed: int) -> list[dict]:
    """Base up 3 to 8%, every component scaled with it, effective `effective`."""
    rng = random.Random(f"raises-{seed}")
    pay = pay_of(employees, None)
    rows = []
    for employee in employees:
        bonus, amounts = pay[employee.pk]
        factor = ONE + proportion(rng, *RAISE_RANGE)
        rows.append(
            employee_row(employee, bonus, scaled(amounts, factor), effective_from=effective)
        )
    return rows


def bonus_rows(employees: list[Employee], effective: date, seed: int) -> list[dict]:
    """5 to 15% of base added to the bonus, every other amount unchanged, effective `effective`."""
    rng = random.Random(f"bonus-{seed}")
    pay = pay_of(employees, None)
    rows = []
    for employee in employees:
        bonus, amounts = pay[employee.pk]
        share = proportion(rng, *BONUS_RANGE)
        added = whole(bonus + amounts.get("BASE", Decimal("0")) * share)
        rows.append(employee_row(employee, added, amounts, effective_from=effective))
    return rows


def promotion_rows(employees: list[Employee], effective: date, seed: int) -> list[dict]:
    """One level up with the designation to match, base up 12 to 20% with every component scaled,
    effective `effective`: identity and amounts in one row."""
    rng = random.Random(f"promotions-{seed}")
    pay = pay_of(employees, None)
    rows = []
    for employee in employees:
        bonus, amounts = pay[employee.pk]
        factor = ONE + proportion(rng, *PROMOTION_RANGE)
        level = employee.level + 1
        spec = DEPARTMENTS.get(employee.department.code)
        designation = profiles.designation(spec, level) if spec else employee.designation
        rows.append(
            employee_row(
                employee,
                bonus,
                scaled(amounts, factor),
                effective_from=effective,
                level=level,
                designation=designation,
            )
        )
    return rows


def exit_rows(employees: list[Employee], on: date, last_date: date) -> list[dict]:
    """`last_date` on the day given, nothing else changed."""
    pay = pay_of(employees, on)
    return [employee_row(e, *pay[e.pk], last_date=last_date) for e in employees]


def new_rows(
    count: int,
    seed: int,
    start_number: int,
    taken: set[str],
    *,
    stream: str = "import",
    offset: int = 0,
    joined_after: date | None = None,
    end: date | None = None,
) -> list[dict]:
    """`count` invented employees with fresh legacy codes, joined after `joined_after` when given,
    their careers ending at `end`, today when given, else the seed's reference date. The codes
    come from `stream`, `offset` of them passed over, and the email numbers start that far past
    `start_number`: fix-me's joiners follow newhires' 500, so the two files made from one database
    share no code and no email (D72)."""
    rows = []
    codes = legacy_codes(offset + count, f"{stream}-{seed}", taken)[offset:]
    people = generate(
        count,
        f"{stream}-{seed}-{offset}",
        start_number=start_number + offset,
        joined_after=joined_after,
        end=end,
    )
    for entry, code in zip(people, codes, strict=True):
        identity = entry.identity
        # Today's pay beside today's level: the seed's history starts at the joining pay, years
        # and levels below it (D64).
        latest = entry.records[-1]
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
                "bonus_annual": latest.bonus_annual,
                **latest.lines,
            }
        )
    return rows


def base_rows(active: int, exited: int, seed: int) -> list[dict]:
    """The seed's organisation from the generator alone (D72): in joining order with the seed's
    legacy codes, each row the current or last pay with `effective_from` at joining, leavers with
    their `last_date`. Into an empty database it creates everyone; into the seeded one every row
    is a no-op."""
    rows = []
    for entry in ordered_entries(active, seed, exited=exited):
        identity = entry.identity
        latest = entry.records[-1]
        rows.append(
            {
                "legacy_code": identity["legacy_code"],
                "full_name": identity["full_name"],
                "email": identity["email"],
                "department": identity["department"],
                "designation": identity["designation"],
                "level": identity["level"],
                "country_code": identity["country_code"],
                "gender": identity["gender"],
                "joining_date": identity["joining_date"],
                "last_date": identity["last_date"],
                "effective_from": identity["joining_date"],
                "bonus_annual": latest.bonus_annual,
                **latest.lines,
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


def profile_codes() -> list[str]:
    """The template's component columns from the seed's profiles, for a run with no database."""
    return [spec.code for spec in sorted(profiles.COMPONENTS, key=lambda s: (s.sort_order, s.code))]


def database_codes() -> list[str]:
    return list(
        SalaryComponent.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values_list("code", flat=True)
    )


def file_bytes(columns: list[str], rows: list[dict], kind: str) -> bytes:
    """The sheet as `.xlsx` or `.csv` bytes, numbers and dates as typed cells, every string as
    text so a value that begins with `=` is never written as a formula."""
    if kind == ".xlsx":
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("employees")
        sheet.append(columns)
        for row in rows:
            sheet.append([_xlsx_cell(sheet, row.get(column)) for column in columns])
        stream = io.BytesIO()
        workbook.save(stream)
        return stream.getvalue()
    if kind == ".csv":
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if row.get(c) is None else _text(row.get(c)) for c in columns])
        return text.getvalue().encode("utf-8")
    raise CommandError("--out must end in .xlsx or .csv")


def write_file(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.write_bytes(file_bytes(columns, rows, path.suffix.lower()))


def _xlsx_cell(sheet, value):
    if isinstance(value, str):
        # A control character openpyxl cannot write, as the exports replace it.
        cell = WriteOnlyCell(sheet, value=XML_ILLEGAL.sub("\ufffd", value))
        cell.data_type = "s"
        return cell
    return value


def _text(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def generated_rows(
    *,
    today: date,
    effective: date,
    seed: int,
    share: int | None = None,
    raises: int = 0,
    bonus: int = 0,
    promotions: int = 0,
    exits: int = 0,
    new: int = 0,
    errors: int = 0,
    everyone: bool = False,
    joined_after: date | None = None,
    stream: str = "import",
    offset: int = 0,
) -> list[dict]:
    """The rows of one generated file, in the order the options are listed (D72)."""
    rows: list[dict] = []
    if everyone:
        rows += all_rows(today)
        raised = current_employees(share=share, revisable_on=effective, limit=raises)
        replacement = {row["legacy_code"]: row for row in raise_rows(raised, effective, seed)}
        rows = [replacement.get(row["legacy_code"], row) for row in rows]
    elif raises:
        picked = current_employees(share=share, revisable_on=effective, limit=raises)
        rows += raise_rows(picked, effective, seed)
    if bonus:
        picked = current_employees(share=share, revisable_on=effective, limit=bonus)
        rows += bonus_rows(picked, effective, seed)
    if promotions:
        picked = current_employees(
            share=share, revisable_on=effective, below_level=profiles.LEVELS[-1], limit=promotions
        )
        rows += promotion_rows(picked, effective, seed)
    if exits:
        # Nobody with a record dated after the last day: a scheduled revision would have to be
        # cancelled first, and a future joiner cannot leave before joining.
        picked = current_employees(
            share=share, revisable_on=effective + timedelta(days=1), limit=exits
        )
        rows += exit_rows(picked, today, effective)
    if new:
        taken = set(
            Employee.objects.exclude(legacy_code=None).values_list("legacy_code", flat=True)
        )
        start = (Employee.objects.aggregate(last=Max("pk"))["last"] or 0) + 1
        rows += new_rows(
            new,
            seed,
            start,
            taken,
            stream=stream,
            offset=offset,
            joined_after=joined_after,
            end=today,
        )
    plant_errors(rows, errors)
    return rows


class Command(BaseCommand):
    help = "Write a template-shaped import file from the live tables, or the seed's base file."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True)
        parser.add_argument("--new", type=int, default=0)
        parser.add_argument("--raises", type=int, default=0)
        parser.add_argument("--bonus", type=int, default=0)
        parser.add_argument("--promotions", type=int, default=0)
        parser.add_argument("--exits", type=int, default=0)
        parser.add_argument("--errors", type=int, default=0)
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--base", action="store_true")
        parser.add_argument("--effective", type=date.fromisoformat, default=None)
        parser.add_argument("--share", type=int, choices=range(SHARES), default=None)
        parser.add_argument("--joined-after", type=date.fromisoformat, default=None)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--stream", default="import", help="the joiners' stream, by name")
        parser.add_argument("--offset", type=int, default=0, help="joiners of the stream to skip")

    def handle(self, *args, **options):
        path = Path(options["out"])
        # call_command passes a date option as given, a string or a date.
        for name in ("effective", "joined_after"):
            if isinstance(options[name], str):
                options[name] = date.fromisoformat(options[name])
        if options["base"]:
            rows = base_rows(profiles.ACTIVE_EMPLOYEES, profiles.EXITED_EMPLOYEES, options["seed"])
            codes = profile_codes()
        else:
            today = today_utc()
            try:
                rows = generated_rows(
                    today=today,
                    effective=options["effective"] or next_month_first(today),
                    seed=options["seed"],
                    share=options["share"],
                    raises=options["raises"],
                    bonus=options["bonus"],
                    promotions=options["promotions"],
                    exits=options["exits"],
                    new=options["new"],
                    errors=options["errors"],
                    everyone=options["all"],
                    joined_after=options["joined_after"],
                    stream=options["stream"],
                    offset=options["offset"],
                )
            except ValueError as exc:  # a joining window that ends before it starts
                raise CommandError(str(exc)) from exc
            codes = database_codes()
        write_file(path, template_columns(codes), rows)
        self.stdout.write(
            f"wrote {len(rows)} rows to {path} ({len(IDENTITY_COLUMNS) + len(codes)} columns)"
        )
