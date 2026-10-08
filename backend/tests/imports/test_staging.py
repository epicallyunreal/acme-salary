"""Staging an upload: every row validated and classified, nothing live touched (SPEC F1, D53,
D55). The applier and its counts are tested in test_applier."""

import csv
import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.audit.models import AuditLog
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.compensation.validators import TEXT_LIMITS, check_header
from apps.core.exceptions import Conflict, Invalid, PayloadTooLarge
from apps.employees.models import LEGACY_CODE_MAX, Employee
from apps.imports import parser, services
from apps.imports.models import ImportBatch
from apps.imports.services import STORED_CELL_LIMIT, normalized_json, row_from_json, stage_upload
from tests.imports.sheets import (
    HEADER,
    LINES,
    NEXT_MONTH,
    RAISED,
    cell_text,
    new_row,
    sheet_row,
    upload_of,
)

pytestmark = pytest.mark.django_db


def staged(batch: ImportBatch) -> dict:
    return {row.row_number: row for row in batch.rows.order_by("row_number")}


def texts(row) -> list[str]:
    return [message["message"] for message in row.messages]


def live_counts() -> tuple[int, int, int, int]:
    return (
        Employee.objects.count(),
        CompensationRecord.objects.count(),
        CompensationLine.objects.count(),
        AuditLog.objects.count(),
    )


def test_staging_reads_the_decision_table_row_by_row(staff):
    """SPEC F1's table over every kind of row, a promotion, an exit with a raise and a warning
    included (PLAN step 5), and the batch counts that follow."""
    s = staff
    rows = [
        new_row(),
        sheet_row(s["asha"]),
        sheet_row(s["ben"], department="sales"),
        sheet_row(s["chloe"], effective_from=NEXT_MONTH, **RAISED),
        sheet_row(
            s["dev"], designation="Lead Engineer", level=4, effective_from=NEXT_MONTH, **RAISED
        ),
        sheet_row(s["esha"], last_date=date(2026, 12, 31), effective_from=NEXT_MONTH, **RAISED),
        sheet_row(s["farah"], last_date=date(2026, 10, 31)),
        sheet_row(s["gita"], **RAISED),
        new_row(legacy_code=None, email="nobody@acme.example"),
        sheet_row(s["hana"], effective_from=date(2024, 3, 1), **RAISED),
        sheet_row(s["ian"], country_code="US", effective_from=NEXT_MONTH, **RAISED),
        sheet_row(s["jaya"], effective_from=NEXT_MONTH, bonus_annual=Decimal("2000000"), **RAISED),
    ]
    before = live_counts()

    batch = stage_upload(upload_of(*rows), actor=None)

    result = staged(batch)
    assert {number: (row.action, row.status) for number, row in result.items()} == {
        2: ("create", "valid"),
        3: ("noop", "valid"),
        4: ("update", "valid"),
        5: ("revise", "valid"),
        6: ("revise", "valid"),
        7: ("revise", "valid"),
        8: ("update", "valid"),
        9: ("revise", "error"),
        10: (None, "error"),
        11: ("revise", "error"),
        12: ("revise", "error"),
        13: ("revise", "warning"),
    }
    assert texts(result[2]) == ["effective_from defaulted to joining_date 2026-11-01"]
    assert texts(result[3]) == ["No changes, row will be skipped on apply"]
    assert texts(result[9]) == ["effective_from is required when amounts change"]
    assert "legacy_code is required" in texts(result[10])
    assert texts(result[11]) == ["effective_from must be after 2024-03-01 (latest record)"]
    assert "country change is not supported by import" in texts(result[12])
    assert texts(result[13]) == ["bonus_annual 2,000,000.00 is above BASE 1,600,000.00"]
    assert (result[2].matched_employee, result[3].matched_employee) == (None, s["asha"])
    assert result[6].normalized["designation"] == "Lead Engineer"
    assert result[7].normalized["last_date"] == "2026-12-31"
    counts = (batch.total_rows, batch.valid_rows, batch.warning_rows, batch.error_rows)
    assert counts == (12, 7, 1, 4)
    assert (batch.skipped_rows, batch.noop_rows, batch.status) == (0, 1, "review")
    assert live_counts() == before


def test_a_negative_base_is_an_error_on_its_row_alone(staff):
    """SPEC F1 acceptance: the message names the field and the value; other rows are fine."""
    batch = stage_upload(
        upload_of(new_row(BASE=-5000), new_row(legacy_code="HR-20002", email="ravi@acme.example")),
        actor=None,
    )

    first, second = staged(batch).values()
    assert first.status == "error"
    assert [m for m in first.messages if m["severity"] == "error"] == [
        {
            "field": "BASE",
            "severity": "error",
            "message": "BASE must be a non-negative number, got -5000",
        }
    ]
    assert second.status == "valid"


def test_an_unchanged_row_is_a_noop_and_its_dates_are_not_checked(staff):
    """SPEC F1 acceptance: an effective_from before joining would be an error on a row that
    changes something; on a no-op row the date rules do not run."""
    batch = stage_upload(
        upload_of(sheet_row(staff["asha"], effective_from=date(2020, 1, 1))), actor=None
    )

    (row,) = staged(batch).values()
    assert (row.action, row.status, texts(row)) == (
        "noop",
        "valid",
        ["No changes, row will be skipped on apply"],
    )


def test_a_header_that_cannot_be_mapped_refuses_the_upload_with_no_batch(lookups):
    """SPEC F1 acceptance: the missing column is named and no batch exists."""
    header = [column for column in HEADER if column != "country_code"]

    with pytest.raises(Invalid) as excinfo:
        stage_upload(upload_of(new_row(), header=header), actor=None)

    assert excinfo.value.errors == {
        "missing_columns": ["Missing required column: country_code"],
        "unknown_columns": [],
    }
    assert ImportBatch.objects.count() == 0


def test_unknown_and_headerless_columns_are_batch_warnings(lookups):
    header = [*HEADER, "Remarks", ""]
    row = new_row()
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(header)
    writer.writerow([cell_text(row.get(column)) for column in HEADER] + ["joins in November", "x"])
    upload = SimpleUploadedFile("a.csv", text.getvalue().encode(), content_type="text/csv")

    batch = stage_upload(upload, actor=None)

    assert batch.warnings == ["Ignored unknown column: Remarks", "Ignored unknown column: column S"]
    assert staged(batch)[2].status == "valid"


def test_a_code_twice_in_the_file_is_an_error_on_both_rows(staff):
    batch = stage_upload(upload_of(new_row(), new_row(email="ravi@acme.example")), actor=None)

    rows = staged(batch)
    assert "Duplicate legacy_code in rows 2 and 3" in texts(rows[2])
    assert "Duplicate legacy_code in rows 2 and 3" in texts(rows[3])


def test_an_email_twice_in_the_file_is_an_error_on_both_rows(lookups):
    batch = stage_upload(upload_of(new_row(), new_row(legacy_code="HR-20004")), actor=None)

    rows = staged(batch)
    assert "Duplicate email in rows 2 and 3" in texts(rows[2])
    assert "Duplicate email in rows 2 and 3" in texts(rows[3])


def test_an_email_another_employee_holds_is_an_error(staff):
    batch = stage_upload(
        upload_of(new_row(legacy_code="HR-20003", email="esha@acme.example")), actor=None
    )

    assert texts(staged(batch)[2]) == [
        f"email already belongs to {staff['esha'].employee_code}",
        "effective_from defaulted to joining_date 2026-11-01",
    ]


def test_a_legacy_code_matches_exactly_after_trimming(staff):
    """SPEC F1: trimmed, then exact and case-sensitive. A code in another case is a different
    code, and the email check catches the person it would duplicate."""
    asha = staff["asha"]
    batch = stage_upload(
        upload_of(
            sheet_row(asha, legacy_code="  HR-10001 "), sheet_row(asha, legacy_code="hr-10001")
        ),
        actor=None,
    )

    trimmed, other_case = staged(batch).values()
    assert (trimmed.action, trimmed.matched_employee) == ("noop", asha)
    assert other_case.action == "create"
    assert f"email already belongs to {asha.employee_code}" in texts(other_case)


def test_a_date_past_2100_and_an_overlong_cell_are_row_errors_through_an_upload(lookups):
    """The add-validation-rule recipe: D53 and D55 reach a staged row."""
    batch = stage_upload(
        upload_of(
            new_row(joining_date=date(2101, 1, 1)),
            new_row(legacy_code="HR-20002", email="ravi@acme.example", full_name="x" * 121),
        ),
        actor=None,
    )

    late, long_name = staged(batch).values()
    assert late.status == long_name.status == "error"
    assert "joining_date must be on or before 2100-12-31, got 2101-01-01" in texts(late)
    assert "full_name is longer than 120 characters" in texts(long_name)
    assert long_name.full_name == "x" * 120
    assert long_name.raw["full_name"] == "x" * 121


def test_a_lookup_cell_too_long_for_its_column_is_not_repeated_back(lookups):
    """D55: the length message replaces `Unknown department: <the whole cell>`."""
    batch = stage_upload(upload_of(new_row(department="d" * 65)), actor=None)

    (row,) = staged(batch).values()
    assert [m["message"] for m in row.messages if m["field"] == "department"] == [
        "department is longer than 64 characters"
    ]


def test_the_staged_row_reads_back_as_the_row_the_rules_saw():
    header = check_header(HEADER, list(LINES))
    cells = [cell_text(new_row(bonus_annual="12.50", HRA=None).get(column)) for column in HEADER]
    row = parser.normalize(5, cells, header.mapping)

    again = row_from_json(5, normalized_json(row))

    assert again == row


def test_an_upload_over_ten_megabytes_is_refused_before_it_is_read(lookups):
    oversized = SimpleNamespace(size=10 * 1024 * 1024 + 1, name="big.csv")

    with pytest.raises(PayloadTooLarge):
        stage_upload(oversized, actor=None)

    assert ImportBatch.objects.count() == 0


def test_amounts_no_column_could_hold_are_row_errors_not_a_crash(staff):
    """A 29-digit BASE once reached a quantise that raised; it is its own rule's error now, on a
    new row and on a matched one."""
    huge = "1" + "0" * 28
    batch = stage_upload(
        upload_of(
            new_row(BASE=huge),
            sheet_row(staff["asha"], effective_from=NEXT_MONTH, BASE=huge),
        ),
        actor=None,
    )

    new, matched = staged(batch).values()
    too_large = (
        "BASE must be at most 9,999,999,999.99, got 10,000,000,000,000,000,000,000,000,000.00"
    )
    assert (new.status, matched.status) == ("error", "error")
    assert too_large in texts(new)
    assert too_large in texts(matched)


def test_no_above_base_warning_is_measured_against_a_bad_base(lookups):
    batch = stage_upload(upload_of(new_row(BASE=-5000, bonus_annual="100")), actor=None)

    (row,) = staged(batch).values()
    assert [m["message"] for m in row.messages if m["severity"] == "warning"] == []


def test_a_new_country_alone_is_a_change_that_is_refused_never_a_no_op(staff):
    ian = staff["ian"]
    batch = stage_upload(
        upload_of(sheet_row(ian, country_code="US", HRA=None, ALLOWANCES=None)), actor=None
    )

    (row,) = staged(batch).values()
    assert row.status == "error"
    assert "country change is not supported by import" in texts(row)
    assert "No changes, row will be skipped on apply" not in texts(row)


def test_numeric_cells_are_kept_as_text_in_raw(lookups):
    """Money stays text end to end: an xlsx number cell is shown as the user typed it."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    sheet.append([new_row(BASE=1450000.5, HRA=360000).get(column) for column in HEADER])
    stream = io.BytesIO()
    workbook.save(stream)
    xlsx_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    batch = stage_upload(SimpleUploadedFile("a.xlsx", stream.getvalue(), xlsx_type), actor=None)

    raw = staged(batch)[2].raw
    assert (raw["BASE"], raw["HRA"], raw["level"], raw["joining_date"]) == (
        "1450000.5",
        "360000",
        "2",
        "2026-11-01",
    )


@pytest.mark.parametrize(
    "column",
    [
        "full_name",
        "email",
        "department",
        "designation",
        "level",
        "country_code",
        "gender",
        "joining_date",
    ],
)
def test_a_blank_required_cell_is_an_error_on_a_new_row_and_a_matched_one(staff, column):
    """A blank full_name used to stage as valid and fail the whole approve on a NOT NULL
    constraint (D56)."""
    batch = stage_upload(
        upload_of(new_row(**{column: ""}), sheet_row(staff["asha"], **{column: ""})), actor=None
    )

    rows = staged(batch)
    for number in (2, 3):
        assert rows[number].status == "error"
        assert [m["message"] for m in rows[number].messages if m["field"] == column] == [
            f"{column} is required"
        ]


def test_a_long_cell_is_kept_as_a_256_character_prefix_and_echoed_as_64(lookups):
    """A cell can hold 100,000 characters. The row keeps enough to show what it was, and is an
    error, so approve never reads the cut value (D56)."""
    long = {
        column: column[0] * 10_000
        for column in ("full_name", "email", "department", "designation", "country_code", "gender")
    }
    batch = stage_upload(
        upload_of(new_row(**long, BASE="9" * 300 + "x", HRA="9" * 300)), actor=None
    )

    row = staged(batch)[2]
    assert row.status == "error"
    assert row.raw["full_name"] == row.normalized["full_name"] == "f" * 255 + "\u2026"
    assert row.raw["BASE"] == "9" * 255 + "\u2026"
    kept = [value for value in row.normalized.values() if isinstance(value, str)]
    kept += [value for value in row.normalized["amounts"].values() if value]
    assert max(len(value) for value in kept) == STORED_CELL_LIMIT
    assert "full_name is longer than 120 characters" in texts(row)
    assert f"BASE must be a non-negative number, got {'9' * 63}\u2026" in texts(row)


def test_every_value_a_row_applies_fits_inside_the_stored_cap():
    """The cap cuts only values that are errors already, so nothing applied is ever cut (D56)."""
    assert max(*TEXT_LIMITS.values(), LEGACY_CODE_MAX) < STORED_CELL_LIMIT


def test_one_long_shared_string_in_every_cell_is_cut_once_and_errs_in_every_column(lookups):
    """A crafted sheet points every cell at one 10,000-character shared string. Each cell is cut
    to 256 characters as it is read, one copy for them all, and errs in its column, never a
    shorter value that passes (D68)."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for _ in range(3):
        sheet.append(["9" * 10_000] * len(HEADER))
    stream = io.BytesIO()
    workbook.save(stream)
    xlsx_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    upload = SimpleUploadedFile("a.xlsx", stream.getvalue(), xlsx_type)

    cells = [cell for _, row in parser.read(upload, upload.name, xlsx_type).rows for cell in row]
    upload.seek(0)
    batch = stage_upload(upload, actor=None)

    assert len(cells) == 3 * len(HEADER)
    assert all(cell is cells[0] for cell in cells)
    assert cells[0] == "9" * 255 + "\u2026"
    for row in staged(batch).values():
        assert row.status == "error"
        assert {m["field"] for m in row.messages if m["severity"] == "error"} >= set(HEADER)


def test_a_cell_of_nothing_but_spaces_past_the_cap_stays_blank(lookups):
    """Cutting keeps a blank cell blank: 10,000 spaces in an optional column change nothing."""
    batch = stage_upload(upload_of(new_row(bonus_annual=" " * 10_000)), actor=None)

    row = staged(batch)[2]
    assert row.status != "error"
    assert not [m for m in row.messages if m["field"] == "bonus_annual"]


def test_a_number_padded_past_the_cap_is_an_error_never_a_shorter_number(lookups):
    """`1`, 300 spaces and an x is no number. Cut to 256 characters it is still none, so the row
    errs rather than staging BASE as 1 (D68)."""
    batch = stage_upload(upload_of(new_row(BASE="1" + " " * 300 + "x")), actor=None)

    row = staged(batch)[2]
    assert row.status == "error"
    assert any(
        m["field"] == "BASE"
        and m["message"].startswith("BASE must be a non-negative number, got 1")
        for m in row.messages
    )


def test_a_level_thousands_of_digits_long_is_a_row_error_not_a_crash(lookups):
    """Python will not write an int past 4,300 digits back as text, so none is ever kept."""
    batch = stage_upload(upload_of(new_row(level="9" * 5000)), actor=None)

    row = staged(batch)[2]
    assert (row.status, row.normalized["level"]) == ("error", None)
    assert "level must be between 1 and 6" in texts(row)


def test_a_second_upload_while_one_is_being_read_is_refused(lookups):
    """One upload is read at a time, so two of the worst files the limits allow cannot add up
    past the 1 GB machine across gunicorn's threads (D56)."""
    with services._one_upload_at_a_time(), pytest.raises(Conflict) as excinfo:
        stage_upload(upload_of(new_row()), actor=None)

    assert excinfo.value.detail == "another file is being read; try again in a moment"
    assert ImportBatch.objects.count() == 0
    assert stage_upload(upload_of(new_row()), actor=None).total_rows == 1
