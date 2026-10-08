"""make_import_file writes template-shaped sheets that name employees by legacy_code (D48)."""

import csv
import random
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from openpyxl import load_workbook

from apps.compensation import services as compensation
from apps.compensation.services import RecordInput, bulk_apply
from apps.compensation.validators import IDENTITY_COLUMNS, template_columns
from apps.employees import services as employees
from apps.employees.models import Employee
from apps.imports.applier import approve
from apps.imports.management.commands.make_import_file import (
    EXIT_SPREAD,
    HIRE_SPREAD,
    base_rows,
    new_rows,
    profile_codes,
    spread_day,
    write_file,
)
from apps.imports.parser import XLSX_TYPE
from apps.imports.services import stage_upload
from seed import profiles
from seed.generator import draw_career, generate, ordered_entries
from seed.lookups import ensure_lookups
from tests.factories import EmployeeFactory

TODAY = date(2026, 10, 7)

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


def current_pay(employee: Employee) -> tuple[Decimal, dict[str, Decimal]]:
    on = profiles.REFERENCE_DATE
    record = compensation.current_record(employee, on) or compensation.latest_record(employee)
    lines = {
        line.component.code: line.annual_amount for line in record.lines.select_related("component")
    }
    return record.bonus_annual, lines


def current_base(employee: Employee) -> Decimal:
    return current_pay(employee)[1]["BASE"]


def by_code(row: dict) -> Employee:
    return Employee.objects.get(legacy_code=row["legacy_code"])


def factor_of(row: dict, lines: dict[str, Decimal]) -> Decimal:
    """The raise a row carries, read from BASE, with every other component scaled the same way
    up to rounding to whole units."""
    factor = Decimal(row["BASE"]) / lines["BASE"]
    for code, amount in lines.items():
        assert abs(Decimal(row[code]) - amount * factor) <= 1, code
    return factor


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
    # A raise is 3 to 8% drawn from the seed, rounded to whole units (D72).
    factor = Decimal(rows[3]["BASE"]) / current_base(employees[3])
    assert Decimal("1.03") <= factor <= Decimal("1.0801")
    # Seed 42 is fixed, so the raised row is known by name and amount too.
    assert (rows[3]["legacy_code"], rows[3]["full_name"], rows[3]["BASE"]) == (
        "HR-90977",
        "Charan Chahal",
        1568352,
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
    assert all(row["effective_from"] == row["joining_date"] for row in rows)


def test_a_new_row_is_paid_as_today_beside_todays_level():
    """The seed's history starts at the joining pay, levels below the one written beside it, so a
    new row carries the latest record's pay (D64). The people come from the file's own stream,
    `import` at offset 0 by default."""
    entries = list(generate(5, "import-42-0", start_number=1))

    rows = new_rows(5, 42, 1, set())

    assert any(len(entry.records) > 1 for entry in entries)
    assert [(row["level"], row["BASE"]) for row in rows] == [
        (entry.identity["level"], entry.records[-1].lines["BASE"]) for entry in entries
    ]


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
    # ACME-1 is the earliest joiner (D48), and the row carries the current record.
    earliest = Employee.objects.order_by("pk").first()
    assert earliest.joining_date == min(Employee.objects.values_list("joining_date", flat=True))
    assert first["legacy_code"] == earliest.legacy_code
    assert first["full_name"] == earliest.full_name
    assert first["joining_date"] == earliest.joining_date.isoformat()
    assert first["effective_from"] == ""
    assert Decimal(first["BASE"]) == current_base(earliest)
    assert (first["legacy_code"], first["full_name"], first["joining_date"], first["BASE"]) == (
        "HR-62905",
        "Amruta Chander",
        "2017-03-13",
        "2567700.00",
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


def test_raises_alone_pass_over_the_leavers(thirty, tmp_path):
    """The seed's earliest joiners include leavers (D64): `--raises 2` still writes two raises,
    to the first two still employed."""
    first, second, third = Employee.objects.order_by("pk")[:3]
    employees.exit_employee(first, date(2026, 6, 30))
    path = tmp_path / "raises.xlsx"

    run(path, raises=2)

    _, rows = rows_of_xlsx(path)
    assert [row["legacy_code"] for row in rows] == [second.legacy_code, third.legacy_code]
    assert [row["effective_from"] for row in rows] == [datetime(2026, 11, 1)] * 2


def test_the_whole_organisation_leavers_included_stages_with_no_errors(db, tmp_path):
    """The seed's leavers are written with their last_date, and `--all` reads back as the
    database holds it: every row a no-op, none an error (D64)."""
    ensure_lookups()
    bulk_apply(
        ordered_entries(20, 42, exited=10),
        source="seed",
        at=profiles.REFERENCE_DATETIME,
        today=profiles.REFERENCE_DATE,
    )
    path = tmp_path / "everyone.csv"

    run(path, all=True)

    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    leavers = Employee.objects.exclude(last_date=None)
    assert leavers.count() == 10
    assert {row["legacy_code"]: row["last_date"] for row in rows if row["last_date"]} == {
        employee.legacy_code: employee.last_date.isoformat() for employee in leavers
    }
    upload = SimpleUploadedFile(path.name, path.read_bytes(), content_type="text/csv")
    batch = stage_upload(upload, actor=None, today=profiles.REFERENCE_DATE)
    assert (batch.total_rows, batch.error_rows, batch.noop_rows) == (30, 0, 30)


def test_the_output_extension_must_be_xlsx_or_csv(thirty, tmp_path):
    with pytest.raises(CommandError, match="must end in .xlsx or .csv"):
        run(tmp_path / "import.txt", all=True)


# The Demo data page's files (D72)


def test_raises_are_3_to_8_percent_with_every_component_scaled_and_dated_effective(
    thirty, tmp_path
):
    path = tmp_path / "raises.xlsx"

    run(path, raises=5, effective=date(2027, 4, 1))

    _, rows = rows_of_xlsx(path)
    factors = set()
    for row in rows:
        bonus, lines = current_pay(by_code(row))
        factor = factor_of(row, lines)
        assert Decimal("1.03") - 1 / lines["BASE"] <= factor <= Decimal("1.08") + 1 / lines["BASE"]
        assert (row["effective_from"], row["bonus_annual"]) == (datetime(2027, 4, 1), bonus)
        factors.add(factor)
    assert len(rows) == 5 and len(factors) > 1


def test_bonus_rows_add_5_to_15_percent_of_base_to_the_bonus_and_nothing_else(thirty, tmp_path):
    path = tmp_path / "bonus.xlsx"

    run(path, bonus=5, effective=date(2026, 10, 7))

    _, rows = rows_of_xlsx(path)
    assert len(rows) == 5
    for row in rows:
        bonus, lines = current_pay(by_code(row))
        added = Decimal(row["bonus_annual"]) - bonus
        assert lines["BASE"] * Decimal("0.05") - 1 <= added <= lines["BASE"] * Decimal("0.15") + 1
        assert {code: Decimal(row[code]) for code in lines} == lines
        assert row["effective_from"] == datetime(2026, 10, 7)


def test_promotions_move_one_level_with_the_designation_and_12_to_20_percent(thirty, tmp_path):
    """Identity and amounts in one row, and nobody at L6, who has nowhere to go (D72): the one L6
    among the thirty, id 22, is passed over by a file that reaches past it."""
    path = tmp_path / "promotions.xlsx"
    specs = {spec.code: spec for spec in profiles.DEPARTMENTS}
    assert [e.pk for e in Employee.objects.filter(level=6)] == [22]

    run(path, promotions=25, effective=date(2026, 10, 7))

    _, rows = rows_of_xlsx(path)
    assert len(rows) == 25
    assert 22 not in {by_code(row).pk for row in rows}
    for row in rows:
        employee = by_code(row)
        _, lines = current_pay(employee)
        factor = factor_of(row, lines)
        assert employee.level < 6 and row["level"] == employee.level + 1
        assert row["designation"] == profiles.designation(
            specs[employee.department.code], row["level"]
        )
        assert Decimal("1.12") - 1 / lines["BASE"] <= factor <= Decimal("1.20") + 1 / lines["BASE"]
        assert row["effective_from"] == datetime(2026, 10, 7)
    Employee.objects.update(level=6)
    run(path, promotions=5, effective=date(2026, 10, 7))
    assert rows_of_xlsx(path)[1] == []


def test_exits_spread_the_last_day_around_today_and_change_nothing_else(thirty, tmp_path):
    """D72: each last day is drawn from 14 days before today to 60 days after, on or after the
    person's joining date and their open record's start, so every row passes the exit rules.
    Past ones leave the counts at once, future ones are scheduled exits."""
    path = tmp_path / "exits.xlsx"

    run(path, exits=20)

    _, rows = rows_of_xlsx(path)
    assert len(rows) == 20
    last_days = [row["last_date"].date() for row in rows]
    assert all(TODAY - timedelta(days=14) <= day <= TODAY + timedelta(days=60) for day in last_days)
    assert min(last_days) < TODAY < max(last_days)
    for row, last_day in zip(rows, last_days, strict=True):
        employee = by_code(row)
        bonus, lines = current_pay(employee)
        assert employee.last_date is None and employee.joining_date <= last_day
        assert compensation.current_record(employee, TODAY).effective_from <= last_day
        assert row["effective_from"] is None and row["bonus_annual"] == bonus
        assert {code: Decimal(row[code]) for code in lines} == lines
    batch = stage_upload(
        SimpleUploadedFile(path.name, path.read_bytes(), content_type=XLSX_TYPE), actor=None
    )
    assert (batch.total_rows, batch.error_rows) == (20, 0)


def test_the_spreads_reach_both_ends(thirty):
    """The exits' draw and the generator's joining date each include the end days (D72)."""
    rng = random.Random("ends")
    exits = {spread_day(rng, TODAY, EXIT_SPREAD) for _ in range(5000)}
    after = TODAY + timedelta(days=HIRE_SPREAD[0] - 1)
    until = TODAY + timedelta(days=HIRE_SPREAD[1])
    hires = {
        draw_career(rng, 1, None, joined_after=after, end=until).joining_date for _ in range(5000)
    }

    assert (min(exits), max(exits)) == (TODAY - timedelta(days=14), TODAY + timedelta(days=60))
    assert (min(hires), max(hires)) == (TODAY - timedelta(days=60), TODAY + timedelta(days=14))


def test_a_share_keeps_to_its_ids_and_passes_over_anyone_revised_on_or_after_the_date(
    thirty, tmp_path
):
    """D72: employee id modulo 5 is the share, and a file regenerated after its import moves on
    to the next people instead of erroring on those just revised."""
    share = [e for e in Employee.objects.order_by("pk") if e.pk % 5 == 2]
    bonus, lines = current_pay(share[0])
    doubled = {code: amount * 2 for code, amount in lines.items()}
    compensation.revise(share[0], RecordInput(date(2027, 4, 1), bonus, "", doubled))
    path = tmp_path / "share.xlsx"

    run(path, raises=10, share=2, effective=date(2027, 4, 1))

    _, rows = rows_of_xlsx(path)
    picked = [by_code(row).pk for row in rows]
    assert picked == [e.pk for e in share[1:]]
    assert len(picked) == 5


def test_new_hires_join_within_the_window_with_their_record_at_joining(thirty, tmp_path):
    """Today is 7 October 2026: joined after 7 August, the day after the bound (D69), and by 21
    October, the future ones Upcoming until they join, and every row passes the create rules
    (D72)."""
    path = tmp_path / "newhires.xlsx"

    run(path, new=30, joined_after=date(2026, 8, 7), joined_until=date(2026, 10, 21))

    _, rows = rows_of_xlsx(path)
    assert len(rows) == 30
    joined = [row["joining_date"].date() for row in rows]
    assert all(date(2026, 8, 8) <= day <= date(2026, 10, 21) for day in joined)
    assert min(joined) < TODAY < max(joined)
    for row in rows:
        assert row["effective_from"] == row["joining_date"] and row["last_date"] is None
        assert re.fullmatch(r"HR-\d{5}", row["legacy_code"])
        assert row["legacy_code"] not in taken_codes()
    batch = stage_upload(
        SimpleUploadedFile(path.name, path.read_bytes(), content_type=XLSX_TYPE), actor=None
    )
    assert (batch.total_rows, batch.error_rows) == (30, 0)
    approve(batch, actor=None)
    assert Employee.objects.filter(joining_date__gt=TODAY).exists()


def test_the_same_database_seed_and_options_give_the_same_file(thirty, tmp_path):
    first, again = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    options = dict(raises=3, bonus=3, promotions=3, exits=3, new=3, effective=date(2026, 10, 7))

    run(first, **options)
    run(again, **options)

    assert rows_of_xlsx(first) == rows_of_xlsx(again)
    assert len(rows_of_xlsx(first)[1]) == 15


def test_base_rows_are_the_seed_in_joining_order_and_build_an_empty_database(db, tmp_path):
    """D72 at small scale: each row the seed's own code, current or last pay and effective_from
    at joining. Into an empty database every row creates, the leavers exited; staged again, every
    row is a no-op."""
    ensure_lookups()
    rows = base_rows(20, 10, 42)
    entries = ordered_entries(20, 42, exited=10)
    for row, entry in zip(rows, entries, strict=True):
        assert row["legacy_code"] == entry.identity["legacy_code"]
        assert row["effective_from"] == row["joining_date"] == entry.identity["joining_date"]
        assert row["last_date"] == entry.identity["last_date"]
        assert {code: row[code] for code in entry.records[-1].lines} == entry.records[-1].lines
    assert sum(row["last_date"] is not None for row in rows) == 10
    path = tmp_path / "base.xlsx"
    write_file(path, template_columns(profile_codes()), rows)

    batch = stage_upload(
        SimpleUploadedFile(path.name, path.read_bytes(), content_type=XLSX_TYPE), actor=None
    )
    assert (batch.total_rows, batch.error_rows, batch.created_rows) == (30, 0, 0)
    approve(batch, actor=None)
    again = stage_upload(
        SimpleUploadedFile(path.name, path.read_bytes(), content_type=XLSX_TYPE), actor=None
    )

    assert Employee.objects.count() == 30
    assert Employee.objects.exclude(last_date=None).count() == 10
    for employee in Employee.objects.all():
        (record,) = employee.compensation_records.all()
        assert record.effective_from == employee.joining_date
        if employee.last_date is not None:
            assert record.effective_to == employee.last_date + timedelta(days=1)
    assert (again.total_rows, again.noop_rows, again.error_rows) == (30, 30, 0)


def test_a_generated_file_imported_twice_is_a_no_op_scheduled_raises_included(thirty, tmp_path):
    """D72: the second import of a bonus file repeats the current record, and of a raises file
    dated 1 April next repeats the scheduled revision the first made."""
    bonus, raises = tmp_path / "bonus.xlsx", tmp_path / "raises.xlsx"
    run(bonus, bonus=4, share=0, effective=date(2026, 10, 7))
    run(raises, raises=4, share=1, effective=date(2027, 4, 1))

    for path in (bonus, raises):
        first = stage_upload(
            SimpleUploadedFile(path.name, path.read_bytes(), content_type=XLSX_TYPE), actor=None
        )
        assert (first.total_rows, first.error_rows, first.noop_rows) == (4, 0, 0)
        approve(first, actor=None)
        again = stage_upload(
            SimpleUploadedFile(path.name, path.read_bytes(), content_type=XLSX_TYPE), actor=None
        )
        assert (again.total_rows, again.noop_rows) == (4, 4)


def test_a_control_character_in_a_name_is_replaced_so_the_file_still_builds(thirty, tmp_path):
    """openpyxl refuses XML-illegal characters; a generated file replaces them as the exports do."""
    employee = Employee.objects.order_by("pk").first()
    employee.designation = "Lead\x07Engineer"
    employee.save()
    path = tmp_path / "all.xlsx"

    run(path, all=True)

    _, rows = rows_of_xlsx(path)
    assert rows[0]["designation"] == "Lead\ufffdEngineer"


def test_a_joining_window_that_ends_before_it_starts_is_a_command_error(thirty, tmp_path):
    with pytest.raises(CommandError, match="nobody can join after 2027-01-01"):
        run(tmp_path / "late.xlsx", new=1, joined_after=date(2027, 1, 1))


def test_exits_pass_over_a_scheduled_revision_and_a_record_newer_than_the_last_day(
    thirty, tmp_path
):
    """A scheduled revision must be cancelled before an exit, so the file never names them, and
    someone whose open record started after their drawn last day waits for another draw."""
    first, second = Employee.objects.order_by("pk")[:2]
    bonus, lines = current_pay(first)
    compensation.revise(first, RecordInput(date(2026, 11, 1), bonus, "", lines))
    bonus, lines = current_pay(second)
    compensation.revise(second, RecordInput(TODAY, bonus, "", lines))
    path = tmp_path / "exits.xlsx"

    run(path, exits=10)

    _, rows = rows_of_xlsx(path)
    picked = {by_code(row).pk: row["last_date"].date() for row in rows}
    assert first.pk not in picked
    assert second.pk not in picked or picked[second.pk] >= TODAY


def test_a_raise_builds_on_a_revision_already_scheduled(thirty, tmp_path):
    """The latest live record is what a revision replaces: a raise dated after a scheduled one
    scales that one, instead of undoing it or warning that gross falls."""
    first = Employee.objects.order_by("pk").first()
    bonus, lines = current_pay(first)
    doubled = {code: amount * 2 for code, amount in lines.items()}
    compensation.revise(first, RecordInput(date(2026, 12, 1), bonus, "", doubled))
    path = tmp_path / "raises.xlsx"

    run(path, raises=1, effective=date(2027, 4, 1))

    _, rows = rows_of_xlsx(path)
    assert by_code(rows[0]).pk == first.pk
    assert Decimal("1.03") <= Decimal(rows[0]["BASE"]) / doubled["BASE"] <= Decimal("1.0801")
    batch = stage_upload(
        SimpleUploadedFile(path.name, path.read_bytes(), content_type=XLSX_TYPE), actor=None
    )
    assert (batch.error_rows, batch.warning_rows) == (0, 0)


def test_two_files_from_one_stream_share_no_code_and_no_email(thirty):
    """D72: fix-me's joiners follow newhires' 500 in codes and email numbers, so the two files
    made from one database collide nowhere, whichever is imported first."""
    hires = new_rows(500, 42, 31, set(), stream="newhires")
    fixes = new_rows(20, 42, 31, set(), stream="newhires", offset=500)

    assert not {r["legacy_code"] for r in hires} & {r["legacy_code"] for r in fixes}
    assert not {r["email"] for r in hires} & {r["email"] for r in fixes}
    assert [r["email"].split("@")[0].rsplit(".", 1)[1] for r in fixes] == [
        str(n) for n in range(531, 551)
    ]
