"""Staging an upload for review (SPEC F1, F2, DESIGN 1.5).

Staging reads, validates and classifies every row, then writes the batch and its rows in one short
transaction. Nothing here touches Employee or CompensationRecord: the live tables wait for approve
(CLAUDE.md rule 5).
"""

from __future__ import annotations

import math
import threading
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count, Q

from apps.compensation import validators
from apps.compensation.messages import msg
from apps.compensation.validators import NormalizedRow, ValidationContext
from apps.core import queries as core_queries
from apps.core.exceptions import Conflict, Invalid, PayloadTooLarge, clip
from apps.employees.models import LEGACY_CODE_MAX, Employee
from apps.imports import parser
from apps.imports.models import ImportBatch, ImportRow

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 1000
# A staged row keeps at most this much of a cell (D56). A longer value is an error of its own,
# so approve, which reads only accepted rows, never reads a capped one.
STORED_CELL_LIMIT = parser.CELL_KEPT
# The most employees an import may leave in the database, leavers included (D72): a demo cap
# for the 1 GB machine, checked at staging and again at approve.
ORGANISATION_CAP = 25_000
FULL_NAME_MAX = ImportRow._meta.get_field("full_name").max_length
FILE_NAME_MAX = ImportBatch._meta.get_field("file_name").max_length
_reading = threading.Lock()


# Rows


def classify(row: NormalizedRow, ctx: ValidationContext) -> str | None:
    """SPEC F1's decision table, read after the rules have set the row's flags. None when the
    row has no usable code; the rules carry the table's error messages themselves."""
    if not validators.usable_legacy_code(row):
        return None
    if ctx.employee_for(row) is None:
        return ImportRow.Action.CREATE
    if row.noop:
        return ImportRow.Action.NOOP
    if row.amounts_changed:
        return ImportRow.Action.REVISE
    return ImportRow.Action.UPDATE


def _capped(text: str | None) -> str | None:
    return None if text is None else clip(text, STORED_CELL_LIMIT)


def json_cell(value: Any) -> Any:
    """A cell as the review grid shows it: what the user typed, up to 256 characters, dates as
    ISO text, and numbers as plain decimal text, never a JSON float, since money stays text."""
    if value is None or isinstance(value, bool):
        return value
    return _capped(_cell_text(value))


def _cell_text(value: Any) -> str:
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time() else value.isoformat()
    if isinstance(value, date | time):
        return value.isoformat()
    return str(value)


def raw_cells(cells: Sequence[Any], mapping: Mapping[int, str]) -> dict[str, Any]:
    return {
        column: json_cell(cells[index] if index < len(cells) else None)
        for index, column in mapping.items()
    }


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text(value: Decimal | None) -> str | None:
    return _capped(str(value)) if value is not None else None


def normalized_json(row: NormalizedRow) -> dict[str, Any]:
    """The parsed row, read back at approve by `row_from_json`. The rows API leaves it out."""
    return {
        "legacy_code": _capped(row.legacy_code),
        "full_name": _capped(row.full_name),
        "email": _capped(row.email),
        "department": _capped(row.department),
        "designation": _capped(row.designation),
        "level": row.level,
        "country_code": _capped(row.country_code),
        "gender": _capped(row.gender),
        "joining_date": _iso(row.joining_date),
        "last_date": _iso(row.last_date),
        "effective_from": _iso(row.effective_from),
        "bonus_annual": _text(row.bonus_annual),
        "amounts": {code: _text(value) for code, value in row.amounts.items()},
        "columns": sorted(row.columns),
        "present": sorted(row.present),
    }


def row_from_json(row_number: int, data: Mapping[str, Any]) -> NormalizedRow:
    """The inverse of `normalized_json`, so approve validates the row exactly as staged."""

    def day(name: str) -> date | None:
        return date.fromisoformat(data[name]) if data.get(name) else None

    def number(value: str | None) -> Decimal | None:
        return Decimal(value) if value is not None else None

    return NormalizedRow(
        row_number=row_number,
        legacy_code=data.get("legacy_code"),
        full_name=data.get("full_name"),
        email=data.get("email"),
        department=data.get("department"),
        designation=data.get("designation"),
        level=data.get("level"),
        country_code=data.get("country_code"),
        gender=data.get("gender"),
        joining_date=day("joining_date"),
        last_date=day("last_date"),
        effective_from=day("effective_from"),
        bonus_annual=number(data.get("bonus_annual")),
        amounts={code: number(value) for code, value in data.get("amounts", {}).items()},
        columns=frozenset(data.get("columns", ())),
        present=frozenset(data.get("present", ())),
    )


# Batches


def require_review(batch: ImportBatch) -> None:
    """Skip, unskip, discard and approve act only on a batch in review (SPEC F2)."""
    if batch.status != ImportBatch.Status.REVIEW:
        raise Conflict(f"the batch is {batch.status}, not in review")


def recount(batch: ImportBatch) -> ImportBatch:
    """The summary counts in one aggregate (SPEC section 5). A no-op row counts as valid too;
    a skipped one only as skipped."""
    counts = batch.rows.aggregate(
        total_rows=Count("id"),
        valid_rows=Count("id", filter=Q(status=ImportRow.Status.VALID)),
        warning_rows=Count("id", filter=Q(status=ImportRow.Status.WARNING)),
        error_rows=Count("id", filter=Q(status=ImportRow.Status.ERROR)),
        skipped_rows=Count("id", filter=Q(status=ImportRow.Status.SKIPPED)),
        noop_rows=Count(
            "id", filter=Q(action=ImportRow.Action.NOOP) & ~Q(status=ImportRow.Status.SKIPPED)
        ),
    )
    for name, value in counts.items():
        setattr(batch, name, value)
    batch.save(update_fields=list(counts))
    return batch


@contextmanager
def _one_upload_at_a_time():
    """One upload is read at a time (D56). The worst file the limits allow peaks near 400 MB,
    and gunicorn runs one worker with eight threads on a 1 GB machine. More workers would need a
    lock across processes."""
    if not _reading.acquire(blocking=False):
        raise Conflict(msg("upload_busy"))
    try:
        yield
    finally:
        _reading.release()


def stage_upload(upload, *, actor, today: date | None = None) -> ImportBatch:
    """Read, validate and classify every row of an upload, then write the batch and its rows.

    The size is checked before anything is read, and a second upload while one is being read
    is refused. A header that cannot be mapped refuses the upload with no batch (SPEC F1). The
    reading and the rules run outside any transaction, so the write lock is held only for the
    inserts.
    """
    if upload.size > MAX_UPLOAD_BYTES:
        raise PayloadTooLarge()
    with _one_upload_at_a_time():
        return _stage(upload, actor=actor, today=today)


def organisation_cap_message(now: int, adds: int) -> str:
    return msg("org_cap", cap=f"{ORGANISATION_CAP:,}", now=f"{now:,}", adds=f"{adds:,}")


def organisation_cap_breach(creates: int) -> str | None:
    """The cap's message when `creates` new employees would take the employees in the database,
    leavers included, past it, else None. Updates and revisions do not count (D72)."""
    now = Employee.objects.count()
    if now + creates > ORGANISATION_CAP:
        return organisation_cap_message(now, creates)
    return None


def check_organisation_cap(creates: int) -> None:
    """At staging: a file past the cap is refused with no batch (D72)."""
    if (message := organisation_cap_breach(creates)) is not None:
        raise Invalid({"rows": [message]})


def _stage(upload, *, actor, today: date | None) -> ImportBatch:
    parsed = parser.read(upload, upload.name, getattr(upload, "content_type", None))
    component_codes = [component.code for component in core_queries.active_components()]
    header = validators.check_header(parsed.header, component_codes)
    if header.rejected:
        raise Invalid(header.errors())
    warnings = header.warnings + [
        msg("unknown_column", column=f"column {letter}") for letter in parsed.unnamed
    ]
    rows = [parser.normalize(number, cells, header.mapping) for number, cells in parsed.rows]
    ctx = validators.build_context(rows=rows, today=today)
    staged = []
    for row, (_, cells) in zip(rows, parsed.rows, strict=True):
        messages = validators.validate_row(row, ctx)
        severity = validators.worst_severity(messages)
        staged.append(
            ImportRow(
                row_number=row.row_number,
                # Denormalised for search; a value too long for the column is an error anyway.
                legacy_code=(row.legacy_code or "")[:LEGACY_CODE_MAX],
                full_name=(row.full_name or "")[:FULL_NAME_MAX],
                raw=raw_cells(cells, header.mapping),
                normalized=normalized_json(row),
                status=severity,
                validation_status=severity,
                messages=[message.as_dict() for message in messages],
                action=classify(row, ctx),
                matched_employee=ctx.employee_for(row),
            )
        )
    check_organisation_cap(
        sum(
            item.action == ImportRow.Action.CREATE and item.status != ImportRow.Status.ERROR
            for item in staged
        )
    )
    with transaction.atomic():
        batch = ImportBatch.objects.create(
            file_name=upload.name[:FILE_NAME_MAX],
            file_size=upload.size,
            uploaded_by=actor,
            warnings=warnings,
        )
        for item in staged:
            item.batch = batch
        ImportRow.objects.bulk_create(staged, batch_size=CHUNK_SIZE)
        recount(batch)
    return batch


def skip_row(batch: ImportBatch, row: ImportRow) -> ImportRow:
    """Leave a row out of the approve. Skipping a skipped row changes nothing."""
    with transaction.atomic():
        batch.refresh_from_db()
        require_review(batch)
        row.refresh_from_db()
        if row.status != ImportRow.Status.SKIPPED:
            row.status = ImportRow.Status.SKIPPED
            row.save(update_fields=["status"])
        recount(batch)
    return row


def unskip_row(batch: ImportBatch, row: ImportRow) -> ImportRow:
    """Put a skipped row back as the rules found it (SPEC section 5)."""
    with transaction.atomic():
        batch.refresh_from_db()
        require_review(batch)
        row.refresh_from_db()
        if row.status != row.validation_status:
            row.status = row.validation_status
            row.save(update_fields=["status"])
        recount(batch)
    return row


def discard(batch: ImportBatch) -> ImportBatch:
    """Set a batch aside unapplied. Not audited: no pay data changes (DESIGN 1.5)."""
    with transaction.atomic():
        batch.refresh_from_db()
        require_review(batch)
        batch.status = ImportBatch.Status.DISCARDED
        batch.save(update_fields=["status"])
    return batch
