"""Approving a batch: every accepted row in one transaction, or none (SPEC F1, F2, D24, D26,
D50). Skip, unskip and discard are here too, since approve reads what they leave."""

from datetime import date
from decimal import Decimal

import pytest

from apps.audit import services as audit_services
from apps.audit.models import AuditLog
from apps.compensation import services as compensation
from apps.compensation.models import CompensationRecord
from apps.compensation.services import RecordInput
from apps.core.exceptions import ApplyFailed, Conflict
from apps.employees import services as employees_services
from apps.employees.models import Employee
from apps.imports import services as services_module
from apps.imports.applier import approve
from apps.imports.models import ImportBatch
from apps.imports.services import discard, skip_row, stage_upload, unskip_row
from tests.factories import EmployeeFactory
from tests.imports.sheets import LINES, NEXT_MONTH, RAISED, new_row, sheet_row, upload_of

pytestmark = pytest.mark.django_db


def last_entry_id() -> int:
    return AuditLog.objects.order_by("-id").values_list("id", flat=True).first() or 0


def row_at(batch: ImportBatch, number: int):
    return batch.rows.get(row_number=number)


def test_errors_refuse_the_approve_then_skipped_it_applies_with_f2s_count(staff, hr_user):
    """SPEC F2 acceptance 1 and 2, over the decision table with a promotion row, an exit with a
    raise and a warning row, so every term of the audit count is exercised."""
    s = staff
    batch = stage_upload(
        upload_of(
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
            new_row(legacy_code="HR-20002", email="ravi@acme.example", BASE=-5000),
            sheet_row(
                s["jaya"], effective_from=NEXT_MONTH, bonus_annual=Decimal("2000000"), **RAISED
            ),
        ),
        actor=hr_user,
    )

    with pytest.raises(Conflict) as refused:
        approve(batch, actor=hr_user)
    for staged in batch.rows.filter(status="error"):
        skip_row(batch, staged)
    mark = last_entry_id()
    approve(batch, actor=hr_user)

    assert (refused.value.detail, refused.value.extra) == ("3 rows have errors", {"error_rows": 3})
    batch.refresh_from_db()
    assert (batch.status, batch.approved_at is not None) == ("approved", True)
    counts = (batch.created_rows, batch.updated_rows, batch.revised_rows, batch.applied_rows)
    assert counts == (1, 2, 4, 7)
    assert batch.applied_rows == batch.total_rows - batch.skipped_rows - batch.noop_rows
    entries = AuditLog.objects.filter(id__gt=mark)
    # 2 x created + updated + revised + revised rows that changed identity or set last_date
    # (the promotion and the exit with a raise) + exit-before-pay cancels (none) + 1.
    assert entries.count() == 2 * 1 + 2 + 4 + 2 + 0 + 1
    assert set(entries.values_list("import_batch", flat=True)) == {batch.pk}
    applied = entries.get(action="import_apply")
    assert (applied.entity_type, applied.entity_id, applied.after["applied_rows"]) == (
        "import_batch",
        batch.pk,
        7,
    )
    dev = Employee.objects.get(pk=s["dev"].pk)
    assert (dev.designation, dev.level) == ("Lead Engineer", 4)
    assert [entry.action for entry in entries.filter(employee=dev).order_by("id")] == [
        "update",
        "revise",
    ]
    # SPEC F2's order for a row that sets last_date as well as amounts: exit, then revise.
    esha = s["esha"]
    assert [entry.action for entry in entries.filter(employee=esha).order_by("id")] == [
        "exit",
        "revise",
    ]
    raised = CompensationRecord.objects.get(employee=esha, version=2)
    assert (raised.effective_from, raised.effective_to) == (NEXT_MONTH, date(2027, 1, 1))
    # The warning row is applied like a valid one (SPEC F2).
    jaya = CompensationRecord.objects.get(employee=s["jaya"], version=2)
    assert jaya.bonus_annual == Decimal("2000000.00")


def test_a_new_department_alone_is_an_update_and_adds_no_record(staff, hr_user):
    """SPEC F1 acceptance."""
    ben = staff["ben"]
    batch = stage_upload(upload_of(sheet_row(ben, department="sales")), actor=hr_user)

    approve(batch, actor=hr_user)

    ben.refresh_from_db()
    assert ben.department.code == "sales"
    assert CompensationRecord.objects.filter(employee=ben).count() == 1
    assert row_at(batch, 2).action == "update"


def test_a_new_last_date_closes_the_open_record_the_day_after(staff, hr_user):
    """SPEC F1 acceptance; the exit writes one `exit` entry and counts as updated (D26)."""
    farah = staff["farah"]
    batch = stage_upload(upload_of(sheet_row(farah, last_date=date(2026, 10, 31))), actor=hr_user)

    approve(batch, actor=hr_user)

    farah.refresh_from_db()
    assert farah.last_date == date(2026, 10, 31)
    record = CompensationRecord.objects.get(employee=farah)
    assert record.effective_to == date(2026, 11, 1)
    batch.refresh_from_db()
    assert (batch.updated_rows, batch.revised_rows) == (1, 0)
    assert AuditLog.objects.filter(import_batch=batch, action="exit", employee=farah).count() == 1


def test_a_created_employee_carries_the_sheets_code_and_the_row_points_at_them(lookups, hr_user):
    batch = stage_upload(upload_of(new_row()), actor=hr_user)

    approve(batch, actor=hr_user)

    employee = Employee.objects.get(legacy_code="HR-20001")
    assert row_at(batch, 2).matched_employee == employee
    assert employee.employee_code == f"ACME-{employee.pk}"
    record = CompensationRecord.objects.get(employee=employee)
    assert (record.effective_from, record.bonus_annual, record.source) == (
        NEXT_MONTH,
        Decimal("0.00"),
        "import",
    )


def test_a_sheet_uploaded_again_after_approve_matches_its_own_codes(lookups, hr_user):
    """SPEC F1: the second upload updates or no-ops, never duplicates."""
    first = stage_upload(upload_of(new_row()), actor=hr_user)
    approve(first, actor=hr_user)

    again = stage_upload(upload_of(new_row()), actor=hr_user)

    assert (row_at(again, 2).action, row_at(again, 2).status) == ("noop", "valid")
    assert Employee.objects.filter(legacy_code="HR-20001").count() == 1


def test_an_exit_before_pay_starts_writes_exit_and_cancel_in_the_count(lookups, hr_user):
    """D50 through an import: F2's count gains the cancel."""
    employee = EmployeeFactory(legacy_code="HR-10009", joining_date=date(2026, 9, 1))
    compensation.add_first_record(employee, RecordInput(date(2026, 12, 1), Decimal("0"), "", LINES))
    batch = stage_upload(
        upload_of(sheet_row(employee, last_date=date(2026, 10, 31))), actor=hr_user
    )
    mark = last_entry_id()

    approve(batch, actor=hr_user)

    entries = AuditLog.objects.filter(id__gt=mark)
    assert sorted(entries.values_list("action", flat=True)) == ["cancel", "exit", "import_apply"]
    assert CompensationRecord.objects.get(employee=employee).cancelled_at is not None


def test_a_simulated_failure_leaves_nothing_and_marks_the_batch_failed(
    staff, hr_user, monkeypatch, caplog
):
    """SPEC F2 acceptance 3: zero partial employees or records, the rows kept. The failure comes
    after the closing update and the identity update, so their rollback is proven too."""
    chloe, ben = staff["chloe"], staff["ben"]
    batch = stage_upload(
        upload_of(
            new_row(),
            sheet_row(chloe, effective_from=NEXT_MONTH, **RAISED),
            sheet_row(ben, department="sales"),
        ),
        actor=hr_user,
    )
    before = (
        Employee.objects.count(),
        CompensationRecord.objects.count(),
        AuditLog.objects.count(),
    )

    def disk_full(entries):
        raise OSError("disk full")

    monkeypatch.setattr(audit_services, "bulk_record", disk_full)

    with pytest.raises(ApplyFailed) as excinfo:
        approve(batch, actor=hr_user)

    batch.refresh_from_db()
    assert (batch.status, batch.error_summary) == ("failed", "OSError: disk full")
    assert excinfo.value.detail["error_summary"] == "OSError: disk full"
    assert (
        Employee.objects.count(),
        CompensationRecord.objects.count(),
        AuditLog.objects.count(),
    ) == before
    assert CompensationRecord.objects.get(employee=chloe).effective_to is None
    ben.refresh_from_db()
    assert ben.department.code == "engineering"
    assert batch.rows.count() == 3
    (logged,) = [record for record in caplog.records if record.name == "apps.imports.applier"]
    assert (logged.levelname, logged.getMessage(), type(logged.exc_info[1])) == (
        "ERROR",
        f"approve of import batch {batch.pk} failed",
        OSError,
    )


def test_a_blank_required_cell_refuses_the_approve_and_never_fails_it(staff, hr_user):
    """It used to stage as valid, then fail the whole batch on a NOT NULL constraint (D56)."""
    batch = stage_upload(
        upload_of(sheet_row(staff["asha"], designation=""), new_row(full_name="")),
        actor=hr_user,
    )

    with pytest.raises(Conflict, match="2 rows have errors"):
        approve(batch, actor=hr_user)

    batch.refresh_from_db()
    assert (batch.status, batch.error_rows) == ("review", 2)


def test_the_organisation_cap_is_checked_again_at_approve(lookups, hr_user, monkeypatch):
    """D72: two batches each staged under the cap cannot pass it together. The second approve is
    a 409 with the same wording, nothing is written and the batch stays in review."""
    monkeypatch.setattr(services_module, "ORGANISATION_CAP", 3)
    first = stage_upload(
        upload_of(new_row(), new_row(legacy_code="HR-20002", email="two@acme.example")),
        actor=hr_user,
    )
    second = stage_upload(
        upload_of(
            new_row(legacy_code="HR-20003", email="three@acme.example"),
            new_row(legacy_code="HR-20004", email="four@acme.example"),
        ),
        actor=hr_user,
    )

    approve(first, actor=hr_user)
    with pytest.raises(Conflict) as refused:
        approve(second, actor=hr_user)

    second.refresh_from_db()
    assert refused.value.detail == (
        "No more data can be imported: this file would take ACME past 3 employees "
        "(now 2, this file adds 2)"
    )
    assert (second.status, Employee.objects.count()) == ("review", 2)


def test_approving_an_approved_batch_is_a_409(lookups, hr_user):
    """SPEC F2 acceptance 4."""
    batch = stage_upload(upload_of(new_row()), actor=hr_user)
    approve(batch, actor=hr_user)

    with pytest.raises(Conflict, match="the batch is approved, not in review"):
        approve(batch, actor=hr_user)


def test_a_revision_made_since_staging_fails_the_recheck_and_the_batch_waits(staff, hr_user):
    """DESIGN 1.5: the rules run again against the live tables inside the transaction."""
    chloe = staff["chloe"]
    batch = stage_upload(
        upload_of(new_row(), sheet_row(chloe, effective_from=NEXT_MONTH, **RAISED)),
        actor=hr_user,
    )
    compensation.revise(chloe, RecordInput(date(2026, 12, 1), Decimal("0"), "", RAISED))
    created_before = Employee.objects.count()

    with pytest.raises(Conflict) as excinfo:
        approve(batch, actor=hr_user)

    assert (excinfo.value.detail, excinfo.value.extra) == (
        "1 row failed re-validation against current data",
        {"rows": [3]},
    )
    stale = row_at(batch, 3)
    assert (stale.status, stale.validation_status) == ("error", "error")
    assert [m["message"] for m in stale.messages] == [
        "effective_from must be after 2026-12-01 (latest record)"
    ]
    batch.refresh_from_db()
    assert (batch.status, batch.error_rows) == ("review", 1)
    assert Employee.objects.count() == created_before


def test_a_row_that_would_now_apply_as_another_action_is_refused(staff, hr_user):
    """D57: Ben's row was reviewed as an update. His scheduled raise became current before the
    approve, so the sheet's old amounts would now write a revise over it. The row is refused and
    re-marked, and nothing is applied."""
    ben = staff["ben"]
    compensation.revise(ben, RecordInput(NEXT_MONTH, Decimal("0"), "", RAISED))
    batch = stage_upload(
        upload_of(sheet_row(ben, designation="Lead Engineer", effective_from=date(2026, 12, 1))),
        actor=hr_user,
    )
    assert row_at(batch, 2).action == "update"

    with pytest.raises(Conflict) as excinfo:
        approve(batch, actor=hr_user, today=date(2026, 11, 5))

    assert (excinfo.value.detail, excinfo.value.extra) == (
        "1 row failed re-validation against current data",
        {"rows": [2]},
    )
    stale = row_at(batch, 2)
    assert (stale.status, stale.action) == ("error", "update")
    assert [m["message"] for m in stale.messages] == [
        f"{ben.employee_code} changed since this sheet was uploaded; upload the sheet again"
    ]
    ben.refresh_from_db()
    assert ben.designation != "Lead Engineer"
    batch.refresh_from_db()
    assert batch.status == "review"


def test_a_code_taken_by_another_batch_is_never_matched_to_that_employee(lookups, hr_user):
    """D24: the row staged as new is re-marked, and the approve is refused."""
    first = stage_upload(upload_of(new_row()), actor=hr_user)
    other = stage_upload(upload_of(new_row(email="meera.iyer@acme.example")), actor=hr_user)
    approve(other, actor=hr_user)
    taken = Employee.objects.get(legacy_code="HR-20001")

    with pytest.raises(Conflict, match="1 row failed re-validation"):
        approve(first, actor=hr_user)

    assert [m["message"] for m in row_at(first, 2).messages] == [
        f"legacy_code HR-20001 now belongs to {taken.employee_code}; upload the sheet again"
    ]
    assert Employee.objects.filter(legacy_code="HR-20001").count() == 1


def test_skip_and_unskip_restore_the_status_and_the_counts(staff, hr_user):
    batch = stage_upload(
        upload_of(sheet_row(staff["gita"], **RAISED), sheet_row(staff["asha"])), actor=hr_user
    )
    error_row, noop_row = row_at(batch, 2), row_at(batch, 3)

    skip_row(batch, error_row)
    skip_row(batch, error_row)
    skipped = (batch.error_rows, batch.skipped_rows)
    skip_row(batch, noop_row)
    noops_while_skipped = batch.noop_rows
    unskip_row(batch, error_row)
    unskip_row(batch, noop_row)

    assert skipped == (0, 1)
    assert noops_while_skipped == 0
    error_row.refresh_from_db()
    noop_row.refresh_from_db()
    assert (error_row.status, noop_row.status) == ("error", "valid")
    assert (batch.error_rows, batch.skipped_rows, batch.noop_rows) == (1, 0, 1)


def test_only_a_batch_in_review_takes_skip_unskip_discard_or_approve(staff, hr_user):
    batch = stage_upload(upload_of(new_row()), actor=hr_user)
    row = row_at(batch, 2)

    discard(batch)

    for act in (
        lambda: skip_row(batch, row),
        lambda: unskip_row(batch, row),
        lambda: discard(batch),
        lambda: approve(batch, actor=hr_user),
    ):
        with pytest.raises(Conflict, match="the batch is discarded, not in review"):
            act()
    assert Employee.objects.filter(legacy_code="HR-20001").exists() is False


def test_an_email_taken_since_staging_refuses_the_new_employee(lookups, hr_user):
    """F2: the duplicate rules run again inside the approve."""
    batch = stage_upload(upload_of(new_row()), actor=hr_user)
    taken = EmployeeFactory(email="meera@acme.example")

    with pytest.raises(Conflict, match="1 row failed re-validation"):
        approve(batch, actor=hr_user)

    assert [m["message"] for m in row_at(batch, 2).messages] == [
        f"email already belongs to {taken.employee_code}"
    ]
    assert not Employee.objects.filter(legacy_code="HR-20001").exists()


def test_a_change_made_in_the_ui_since_staging_is_neither_applied_nor_counted(staff, hr_user):
    """The re-check classifies again: a staged update the UI has already made is a no-op now,
    so the counts and the audit entries agree with what was written (SPEC F2)."""
    ben = staff["ben"]
    batch = stage_upload(upload_of(sheet_row(ben, department="sales"), new_row()), actor=hr_user)
    employees_services.update_identity(ben, {"department": "sales"})
    mark = last_entry_id()

    approve(batch, actor=hr_user)

    batch.refresh_from_db()
    assert (batch.updated_rows, batch.created_rows, batch.applied_rows, batch.noop_rows) == (
        0,
        1,
        1,
        1,
    )
    assert row_at(batch, 2).action == "noop"
    entries = AuditLog.objects.filter(id__gt=mark)
    assert sorted(entries.values_list("action", flat=True)) == ["create", "import_apply", "revise"]
