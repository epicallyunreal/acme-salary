"""Staging an upload: every row validated and classified, nothing live touched (SPEC F1, D53,
D55). The applier and its counts are tested in test_applier."""

import csv
import io
from datetime import date
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.audit.models import AuditLog
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.core.exceptions import Invalid, PayloadTooLarge
from apps.employees.models import Employee
from apps.imports import parser
from apps.imports.models import ImportBatch
from apps.imports.services import normalized_json, row_from_json, stage_upload
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
    """SPEC F1's table over every kind of row, a promotion and an exit with a raise included
    (PLAN step 5), and the batch counts that follow."""
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
    }
    assert texts(result[2]) == ["effective_from defaulted to joining_date 2026-11-01"]
    assert texts(result[3]) == ["No changes, row will be skipped on apply"]
    assert texts(result[9]) == ["effective_from is required when amounts change"]
    assert "legacy_code is required" in texts(result[10])
    assert (result[2].matched_employee, result[3].matched_employee) == (None, s["asha"])
    assert result[6].normalized["designation"] == "Lead Engineer"
    assert result[7].normalized["last_date"] == "2026-12-31"
    counts = (batch.total_rows, batch.valid_rows, batch.warning_rows, batch.error_rows)
    assert counts == (9, 7, 0, 2)
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
    row = new_row(Remarks="joins in November")
    text = io.StringIO()
    writer = csv.writer(text)
    writer.writerow(header)
    writer.writerow([cell_text(row.get(column)) for column in HEADER] + ["joins in November", "x"])
    upload = SimpleUploadedFile("a.csv", text.getvalue().encode(), content_type="text/csv")

    batch = stage_upload(upload, actor=None)

    assert batch.warnings == ["Ignored unknown column: Remarks", "Ignored unknown column: column S"]
    assert staged(batch)[2].status == "valid"


def test_a_code_or_an_email_twice_in_the_file_is_an_error_on_both_rows(staff):
    batch = stage_upload(
        upload_of(
            new_row(),
            new_row(email="ravi@acme.example"),
            new_row(legacy_code="HR-20003", email="esha@acme.example"),
        ),
        actor=None,
    )

    rows = staged(batch)
    assert "Duplicate legacy_code in rows 2 and 3" in texts(rows[2])
    assert "Duplicate legacy_code in rows 2 and 3" in texts(rows[3])
    assert "email already belongs to " + staff["esha"].employee_code in texts(rows[4])


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


def test_a_lookup_cell_too_long_for_its_column_is_not_repeated_back(lookups):
    """D55: the length message replaces `Unknown department: <the whole cell>`."""
    batch = stage_upload(upload_of(new_row(department="d" * 65)), actor=None)

    (row,) = staged(batch).values()
    assert [m["message"] for m in row.messages if m["field"] == "department"] == [
        "department is longer than 64 characters"
    ]


def test_the_staged_row_reads_back_as_the_row_the_rules_saw():
    header = parser.check_header(HEADER, list(LINES))
    cells = [cell_text(new_row(bonus_annual="12.50", HRA=None).get(column)) for column in HEADER]
    row = parser.normalize(5, cells, header.mapping)

    again = row_from_json(5, normalized_json(row))

    assert again == row


def test_an_upload_over_ten_megabytes_is_refused_before_it_is_read(lookups):
    oversized = SimpleNamespace(size=10 * 1024 * 1024 + 1, name="big.csv")

    with pytest.raises(PayloadTooLarge):
        stage_upload(oversized, actor=None)

    assert ImportBatch.objects.count() == 0
