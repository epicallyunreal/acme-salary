"""Approving a staged batch (SPEC F2, DESIGN 1.5): every accepted row applied in one
transaction through the bulk service, or none of them.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from django.db import transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.compensation import services as compensation
from apps.compensation import validators
from apps.compensation.messages import msg
from apps.compensation.services import ZERO, BulkEntry, RecordInput
from apps.compensation.validators import NormalizedRow, ValidationContext
from apps.core.dates import today_utc
from apps.core.exceptions import ApplyFailed, Conflict
from apps.imports.models import ImportBatch, ImportRow
from apps.imports.services import (
    CHUNK_SIZE,
    classify,
    organisation_cap_breach,
    recount,
    require_review,
    row_from_json,
    waited_out_the_lock,
)

logger = logging.getLogger(__name__)

ACCEPTED_STATUSES = (ImportRow.Status.VALID, ImportRow.Status.WARNING)
APPLIED_ACTIONS = (ImportRow.Action.CREATE, ImportRow.Action.UPDATE, ImportRow.Action.REVISE)


class ReValidationFailed(Exception):
    """Rows that no longer pass against the live tables, by ImportRow id."""

    def __init__(self, failures: dict[int, list[validators.Message]]):
        self.failures = failures
        super().__init__(f"{len(failures)} rows failed re-validation")


def rows_have_errors(count: int) -> str:
    return "1 row has errors" if count == 1 else f"{count} rows have errors"


def _record_of(row: NormalizedRow) -> RecordInput:
    return RecordInput(
        effective_from=row.effective_from,
        bonus_annual=row.bonus_annual if row.bonus_annual is not None else ZERO,
        note="",
        lines={code: amount for code, amount in row.amounts.items() if amount is not None},
    )


def build_entries(
    accepted: list[ImportRow], rows: list[NormalizedRow], ctx: ValidationContext
) -> list[BulkEntry]:
    """One BulkEntry per accepted row, referenced by the ImportRow id (DESIGN 1.5). The rows have
    been through the rules again, which recorded the identity changes each one makes."""
    entries = []
    for staged, row in zip(accepted, rows, strict=True):
        if staged.action == ImportRow.Action.CREATE:
            identity = {
                "legacy_code": row.legacy_code,
                "full_name": row.full_name,
                "email": row.email,
                "department": row.department,
                "designation": row.designation,
                "level": row.level,
                "country_code": row.country_code,
                "gender": row.gender,
                "joining_date": row.joining_date,
                "last_date": row.last_date,
            }
            entries.append(BulkEntry(ref=staged.pk, identity=identity, records=[_record_of(row)]))
            continue
        employee = ctx.employee_for(row)
        exits = row.last_date is not None and row.last_date != employee.last_date
        entries.append(
            BulkEntry(
                ref=staged.pk,
                employee=employee,
                identity_changes=row.identity_changes or None,
                last_date=row.last_date if exits else None,
                records=[_record_of(row)] if staged.action == ImportRow.Action.REVISE else [],
            )
        )
    return entries


def approve(
    batch: ImportBatch,
    *,
    actor,
    at: datetime | None = None,
    today: date | None = None,
) -> ImportBatch:
    """Apply every valid and warning row that is not skipped and not a no-op, or none of them.

    The batch's state and its error rows are read under the write lock, the rows are checked
    again against the live tables, and the bulk service writes them with the import's audit
    entries. A row that fails the check is re-marked and the batch stays in review; any other
    failure marks the batch failed with the rows kept (SPEC F2).
    """
    at = at or timezone.now()
    today = today or today_utc()
    try:
        with transaction.atomic():
            batch.refresh_from_db()
            require_review(batch)
            errors = batch.rows.filter(status=ImportRow.Status.ERROR).count()
            if errors:
                raise Conflict(rows_have_errors(errors), error_rows=errors)
            accepted = list(
                batch.rows.filter(
                    status__in=ACCEPTED_STATUSES, action__in=APPLIED_ACTIONS
                ).order_by("row_number")
            )
            rows = [row_from_json(staged.row_number, staged.normalized) for staged in accepted]
            ctx = validators.build_context(rows=rows, today=today)
            failures = {
                staged.pk: found
                for staged, row in zip(accepted, rows, strict=True)
                if (found := validators.recheck_for_apply(row, ctx, staged.action))
            }
            # The live tables may have moved since staging. A row the UI has made a no-op since
            # is left out. A row that would now apply as another action than the one reviewed
            # is refused, as the re-check refuses (SPEC F2, D57).
            noops = []
            for staged, row in zip(accepted, rows, strict=True):
                if staged.pk in failures:
                    continue
                action = classify(row, ctx)
                if action == ImportRow.Action.NOOP:
                    staged.action = action
                    noops.append(staged)
                elif action != staged.action:
                    employee = ctx.employee_for(row).employee_code
                    failures[staged.pk] = [
                        validators.error("legacy_code", "action_changed", employee=employee)
                    ]
            if failures:
                raise ReValidationFailed(failures)
            ImportRow.objects.bulk_update(noops, ["action"], batch_size=CHUNK_SIZE)
            applying = [
                (staged, row)
                for staged, row in zip(accepted, rows, strict=True)
                if staged.action != ImportRow.Action.NOOP
            ]
            applied = [staged for staged, _ in applying]
            rows = [row for _, row in applying]
            # The cap again, with what the database holds now, so two batches staged under it
            # cannot pass it together (D72).
            creates = sum(staged.action == ImportRow.Action.CREATE for staged in applied)
            if (message := organisation_cap_breach(creates)) is not None:
                raise Conflict(message)
            result = compensation.bulk_apply(
                build_entries(applied, rows, ctx),
                actor=actor,
                source="import",
                batch=batch,
                at=at,
                today=today,
                ctx=ctx,
            )
            created = [staged for staged in applied if staged.action == ImportRow.Action.CREATE]
            for staged in created:
                staged.matched_employee = result.by_ref[staged.pk]["employee"]
            ImportRow.objects.bulk_update(created, ["matched_employee"], batch_size=CHUNK_SIZE)
            batch.created_rows = len(created)
            batch.updated_rows = sum(row.action == ImportRow.Action.UPDATE for row in applied)
            batch.revised_rows = sum(row.action == ImportRow.Action.REVISE for row in applied)
            batch.applied_rows = len(applied)
            recount(batch)  # noop_rows takes in the rows left out above
            batch.status = ImportBatch.Status.APPROVED
            batch.approved_at = at
            batch.save()
            audit.record(
                "import_apply",
                entity=batch,
                actor=actor,
                before=None,
                after={
                    "file_name": batch.file_name,
                    "total_rows": batch.total_rows,
                    "skipped_rows": batch.skipped_rows,
                    "noop_rows": batch.noop_rows,
                    "created_rows": batch.created_rows,
                    "updated_rows": batch.updated_rows,
                    "revised_rows": batch.revised_rows,
                    "applied_rows": batch.applied_rows,
                    "audit_entries": result.audit_entries,
                },
                import_batch=batch,
                at=at,
            )
    except ReValidationFailed as exc:
        # The rollback is complete; the rows keep what they were found to be, in one write.
        with transaction.atomic():
            stale = list(ImportRow.objects.filter(pk__in=exc.failures))
            for staged in stale:
                staged.status = staged.validation_status = ImportRow.Status.ERROR
                staged.messages = [message.as_dict() for message in exc.failures[staged.pk]]
            ImportRow.objects.bulk_update(stale, ["status", "validation_status", "messages"])
            recount(batch)
        count = len(exc.failures)
        raise Conflict(
            f"{count} {'row' if count == 1 else 'rows'} failed re-validation against current data",
            rows=sorted(staged.row_number for staged in stale),
        ) from exc
    except Conflict:
        raise
    except Exception as exc:
        if waited_out_the_lock(exc):
            # Another approve, a cut one still running on the server, holds SQLite's lock for
            # its whole transaction. This one wrote nothing and the batch waits in review (D72).
            raise Conflict(msg("apply_busy")) from exc
        logger.exception("approve of import batch %s failed", batch.pk)
        summary = f"{type(exc).__name__}: {exc}"[:2000]
        # Only a batch still in review is marked, so an approve that finished meanwhile stands.
        ImportBatch.objects.filter(pk=batch.pk, status=ImportBatch.Status.REVIEW).update(
            status=ImportBatch.Status.FAILED, error_summary=summary
        )
        batch.refresh_from_db(fields=["status", "error_summary"])
        raise ApplyFailed(error_summary=summary) from exc
    return batch
