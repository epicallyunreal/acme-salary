"""Compensation rules (SPEC section 4 rules 2, 3 and 6; DESIGN sections 1.4 and 3).

Every write to a record goes through here, single or bulk, and every write is audited.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from apps.audit import services as audit
from apps.compensation import validators
from apps.compensation.models import CompensationLine, CompensationRecord, Source
from apps.core.dates import today_utc
from apps.core.exceptions import Conflict, Invalid
from apps.core.models import SalaryComponent
from apps.core.money import q2
from apps.employees.models import Employee

ZERO = Decimal("0")
BATCH = 1000
CHUNK = 500
ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class RecordInput:
    effective_from: date | None
    bonus_annual: Decimal
    note: str
    lines: Mapping[str, Decimal]


@dataclass(frozen=True)
class Totals:
    gross: Decimal
    net: Decimal
    total_cost: Decimal


@dataclass(frozen=True)
class Written:
    record: CompensationRecord
    warnings: list[validators.Message]


def compute_totals(
    lines: Mapping[str, Decimal],
    bonus_annual: Decimal,
    components: Mapping[str, SalaryComponent],
) -> Totals:
    """SPEC section 4 rule 2 (DESIGN section 3):

    gross = earning lines + bonus, net = gross - deduction lines,
    total cost = gross + employer contribution lines. Pure, Decimal in and out.
    """
    earnings = ZERO
    deductions = ZERO
    employer = ZERO
    for code, amount in lines.items():
        component = components.get(code)
        if component is None:
            raise ValueError(f"unknown component {code}")
        if component.kind == SalaryComponent.Kind.EARNING:
            earnings += amount
        elif component.kind == SalaryComponent.Kind.DEDUCTION:
            deductions += amount
        else:
            employer += amount
    gross = q2(earnings + (bonus_annual or ZERO))
    return Totals(gross=gross, net=q2(gross - deductions), total_cost=q2(gross + employer))


# Reads over live records (cancelled rows never count).


def live_records(employee: Employee):
    return CompensationRecord.objects.filter(employee=employee, cancelled_at__isnull=True)


def latest_record(employee: Employee) -> CompensationRecord | None:
    return live_records(employee).order_by("-effective_from").first()


def open_record(employee: Employee) -> CompensationRecord | None:
    return live_records(employee).filter(effective_to__isnull=True).first()


def current_record(employee: Employee, on: date) -> CompensationRecord | None:
    return (
        live_records(employee)
        .filter(effective_from__lte=on)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gt=on))
        .first()
    )


def shown_record(employee: Employee, on: date) -> CompensationRecord | None:
    """Current on the date, else the latest live record (what the detail page shows)."""
    return current_record(employee, on) or latest_record(employee)


def next_version(employee: Employee) -> int:
    """Previous maximum plus one, cancelled rows included, so a number is never reused."""
    current_max = CompensationRecord.objects.filter(employee=employee).aggregate(m=Max("version"))
    return (current_max["m"] or 0) + 1


def _build_record(
    employee: Employee,
    record: RecordInput,
    *,
    version: int,
    effective_from: date,
    effective_to: date | None,
    components: Mapping[str, SalaryComponent],
    actor,
    source: str,
    batch,
    at: datetime,
) -> tuple[CompensationRecord, list[CompensationLine]]:
    totals = compute_totals(record.lines, record.bonus_annual, components)
    row = CompensationRecord(
        employee=employee,
        version=version,
        currency_code=employee.country.currency_code,
        bonus_annual=q2(record.bonus_annual or ZERO),
        effective_from=effective_from,
        effective_to=effective_to,
        gross_annual=totals.gross,
        net_annual=totals.net,
        total_cost_annual=totals.total_cost,
        source=source,
        import_batch=batch,
        note=record.note or "",
        created_by=actor,
        created_at=at,
    )
    lines = [
        CompensationLine(record=row, component=components[code], annual_amount=q2(amount))
        for code, amount in record.lines.items()
    ]
    return row, lines


def add_first_record(
    employee: Employee,
    record: RecordInput,
    *,
    actor=None,
    source: str = Source.UI,
    batch=None,
    at: datetime | None = None,
    ctx: validators.ValidationContext | None = None,
) -> Written:
    """Version 1, effective from joining_date unless given. Audited as `revise` with no before."""
    at = at or timezone.now()
    ctx = ctx or validators.build_context(employees=[employee])
    warnings = validators.validate_record(
        ctx,
        employee=None,
        country_code=employee.country_id,
        joining_date=employee.joining_date,
        effective_from=record.effective_from,
        bonus_annual=record.bonus_annual,
        lines=record.lines,
    )
    components = ctx.components_for(employee.country_id)
    with transaction.atomic():
        row, lines = _build_record(
            employee,
            record,
            version=1,
            effective_from=record.effective_from or employee.joining_date,
            effective_to=None,
            components=components,
            actor=actor,
            source=source,
            batch=batch,
            at=at,
        )
        row.save()
        CompensationLine.objects.bulk_create(lines)
        audit.record(
            "revise",
            entity=row,
            actor=actor,
            before=None,
            after=audit.snapshot_record(row, lines),
            employee=employee,
            import_batch=batch,
            at=at,
        )
    return Written(row, warnings)


def revise(
    employee: Employee,
    record: RecordInput,
    *,
    actor=None,
    source: str = Source.UI,
    batch=None,
    at: datetime | None = None,
    ctx: validators.ValidationContext | None = None,
) -> Written:
    """A new record dated after the latest; the previous open record closes at that date."""
    at = at or timezone.now()
    if employee.last_date is not None:
        raise Conflict(
            f"employee exited on {employee.last_date.isoformat()}, no revision after an exit"
        )
    ctx = ctx or validators.build_context(employees=[employee])
    warnings = validators.validate_record(
        ctx,
        employee=employee,
        country_code=employee.country_id,
        joining_date=employee.joining_date,
        effective_from=record.effective_from,
        bonus_annual=record.bonus_annual,
        lines=record.lines,
    )
    components = ctx.components_for(employee.country_id)
    with transaction.atomic():
        previous = latest_record(employee)
        before = audit.snapshot_record(previous) if previous is not None else None
        if previous is not None:
            previous.effective_to = record.effective_from
            previous.save(update_fields=["effective_to"])
        row, lines = _build_record(
            employee,
            record,
            version=next_version(employee),
            effective_from=record.effective_from,
            effective_to=None,
            components=components,
            actor=actor,
            source=source,
            batch=batch,
            at=at,
        )
        row.save()
        CompensationLine.objects.bulk_create(lines)
        audit.record(
            "revise",
            entity=row,
            actor=actor,
            before=before,
            after=audit.snapshot_record(row, lines),
            employee=employee,
            import_batch=batch,
            at=at,
        )
    return Written(row, warnings)


def cancel(
    record: CompensationRecord,
    *,
    actor=None,
    today: date | None = None,
    at: datetime | None = None,
) -> CompensationRecord:
    """Mark a scheduled revision cancelled and re-chain its neighbours. Nothing is deleted (D20)."""
    today = today or today_utc()
    at = at or timezone.now()
    if record.cancelled_at is not None or record.effective_from <= today:
        raise Conflict("only a scheduled revision can be cancelled")
    employee = record.employee
    with transaction.atomic():
        previous = (
            live_records(employee)
            .filter(effective_from__lt=record.effective_from)
            .order_by("-effective_from")
            .first()
        )
        if previous is None:
            raise Conflict("the first record cannot be cancelled")
        before = audit.snapshot_record(record)
        record.cancelled_at = at
        record.cancelled_by = actor
        record.save(update_fields=["cancelled_at", "cancelled_by"])
        following = (
            live_records(employee)
            .filter(effective_from__gt=record.effective_from)
            .order_by("effective_from")
            .first()
        )
        previous.effective_to = following.effective_from if following is not None else None
        previous.save(update_fields=["effective_to"])
        audit.record(
            "cancel",
            entity=record,
            actor=actor,
            before=before,
            after=audit.snapshot_record(record),
            employee=employee,
            at=at,
        )
    return record


def close_open_record(employee: Employee, *, at: date) -> CompensationRecord | None:
    """Exit support: the open live record ends at `at` (last_date + 1). Audited by the caller."""
    record = open_record(employee)
    if record is None:
        return None
    record.effective_to = at
    record.save(update_fields=["effective_to"])
    return record


# The bulk entry point shared by the seed and the import applier (DESIGN section 1.4).


@dataclass
class BulkEntry:
    ref: Any = None
    employee: Employee | None = None
    identity: dict[str, Any] | None = None
    identity_changes: dict[str, Any] | None = None
    last_date: date | None = None
    records: list[RecordInput] = field(default_factory=list)


@dataclass
class BulkResult:
    created: list[Employee] = field(default_factory=list)
    updated: list[Employee] = field(default_factory=list)
    exited: list[Employee] = field(default_factory=list)
    revised: list[CompensationRecord] = field(default_factory=list)
    by_ref: dict[Any, dict[str, Any]] = field(default_factory=dict)
    audit_entries: int = 0


class BulkInvalid(Exception):
    def __init__(self, ref: Any, errors: Mapping[str, Any]):
        self.ref = ref
        self.errors = dict(errors)
        super().__init__(f"entry {ref!r}: {self.errors}")


@dataclass(frozen=True)
class Chained:
    record: RecordInput
    effective_from: date
    effective_to: date | None


def chain_records(
    records: Sequence[RecordInput], *, joining_date: date, close_at: date | None
) -> list[Chained]:
    """Half-open chaining: each record ends where the next begins, the last at close_at or open."""
    starts: list[date] = []
    for index, record in enumerate(records):
        start = record.effective_from
        if start is None:
            if index != 0:
                raise ValueError("only the first record may omit effective_from")
            start = joining_date
        if starts and start <= starts[-1]:
            raise ValueError(f"records must be dated in strictly increasing order, got {start}")
        starts.append(start)
    chained = []
    for index, record in enumerate(records):
        end = starts[index + 1] if index + 1 < len(starts) else close_at
        if end is not None and end <= starts[index]:
            raise ValueError(f"record from {starts[index]} cannot end at {end}")
        chained.append(Chained(record, starts[index], end))
    return chained


def _validate_entries(entries: list[BulkEntry], ctx: validators.ValidationContext) -> None:
    for entry in entries:
        try:
            if entry.employee is None:
                identity = entry.identity or {}
                validators.validate_identity(identity, ctx)
                if not entry.records:
                    raise Invalid({"records": ["a new employee needs a first record"]})
                last_date = identity.get("last_date")
                if last_date is not None and last_date < identity["joining_date"]:
                    raise Invalid({"last_date": ["last_date precedes joining_date"]})
                for record in entry.records:
                    validators.validate_record(
                        ctx,
                        employee=None,
                        country_code=identity["country_code"],
                        joining_date=identity["joining_date"],
                        effective_from=record.effective_from,
                        bonus_annual=record.bonus_annual,
                        lines=record.lines,
                    )
            else:
                employee = entry.employee
                if entry.identity_changes:
                    validators.validate_identity(entry.identity_changes, ctx, employee=employee)
                if entry.last_date is not None:
                    validators.validate_exit(employee, entry.last_date, ctx)
                for record in entry.records:
                    validators.validate_record(
                        ctx,
                        employee=employee,
                        country_code=employee.country_id,
                        joining_date=employee.joining_date,
                        effective_from=record.effective_from,
                        bonus_annual=record.bonus_annual,
                        lines=record.lines,
                    )
        except Invalid as exc:
            raise BulkInvalid(entry.ref, exc.errors) from exc
        except Conflict as exc:
            raise BulkInvalid(entry.ref, {"detail": [exc.detail]}) from exc


def _next_code_number() -> int:
    last = (
        Employee.objects.order_by("-employee_code").values_list("employee_code", flat=True).first()
    )
    return int(last.split("-")[1]) + 1 if last else 1


def _apply_identity(employee: Employee, values: Mapping[str, Any], ctx) -> None:
    for name, value in values.items():
        if name == "department":
            employee.department = ctx.department_for(value)
        elif name == "email":
            employee.email = value.lower()
        elif name in validators.IDENTITY_FIELDS and name != "last_date":
            setattr(employee, name, value)


def _record_for_snapshot(employee: Employee, ctx) -> CompensationRecord | None:
    """The record the employee's detail shows: current today, else the latest live one."""
    latest = ctx.latest_by_employee.get(employee.pk)
    for record in (ctx.open_by_employee.get(employee.pk), latest):
        if (
            record is not None
            and record.effective_from <= ctx.today
            and (record.effective_to is None or record.effective_to > ctx.today)
        ):
            return record
    return latest


def _max_versions(employee_ids: list[int]) -> dict[int, int]:
    versions: dict[int, int] = {}
    for start in range(0, len(employee_ids), CHUNK):
        rows = (
            CompensationRecord.objects.filter(employee_id__in=employee_ids[start : start + CHUNK])
            .values("employee_id")
            .annotate(m=Max("version"))
        )
        for row in rows:
            versions[row["employee_id"]] = row["m"]
    return versions


def _lines_by_record(record_ids: Iterable[int]) -> dict[int, list[CompensationLine]]:
    found: dict[int, list[CompensationLine]] = {}
    ids = list(dict.fromkeys(record_ids))
    for start in range(0, len(ids), CHUNK):
        lines = CompensationLine.objects.filter(
            record_id__in=ids[start : start + CHUNK]
        ).select_related("component")
        for line in lines:
            found.setdefault(line.record_id, []).append(line)
    return found


def bulk_apply(
    entries: Iterable[BulkEntry],
    *,
    actor=None,
    source: str,
    batch=None,
    at: datetime | None = None,
    today: date | None = None,
    ctx: validators.ValidationContext | None = None,
) -> BulkResult:
    """Apply creates, identity updates, exits and revisions with bulk writes of 1,000 rows.

    Shares compute_totals, the validators, chain_records, the version rule and the snapshots with
    the single-row functions, so a seeded or imported row is exactly what the UI would have written.
    Runs inside the caller's transaction (its own atomic block is a savepoint).
    """
    entries = list(entries)
    at = at or timezone.now()
    today = today or today_utc()
    if ctx is None:
        ctx = validators.build_context(
            today=today,
            employees=[entry.employee for entry in entries if entry.employee is not None],
            emails=[
                (entry.identity or entry.identity_changes or {}).get("email")
                for entry in entries
                if (entry.identity or entry.identity_changes or {}).get("email")
            ],
            codes=[
                entry.identity["employee_code"]
                for entry in entries
                if entry.identity and entry.identity.get("employee_code")
            ],
        )
    _validate_entries(entries, ctx)
    result = BulkResult()

    with transaction.atomic():
        # 1. New employees.
        next_number = _next_code_number()
        new_employees: list[tuple[BulkEntry, Employee]] = []
        for entry in entries:
            if entry.employee is not None:
                continue
            identity = entry.identity or {}
            code = identity.get("employee_code")
            if not code:
                code = f"ACME-{next_number:06d}"
                next_number += 1
            employee = Employee(
                employee_code=code,
                full_name=identity["full_name"],
                email=identity["email"].lower(),
                gender=identity["gender"],
                department=ctx.department_for(identity["department"]),
                designation=identity["designation"],
                level=identity["level"],
                country=ctx.countries[identity["country_code"]],
                joining_date=identity["joining_date"],
                last_date=identity.get("last_date"),
                created_at=at,
                updated_at=at,
            )
            new_employees.append((entry, employee))
        Employee.objects.bulk_create([e for _, e in new_employees], batch_size=BATCH)
        created_ids: set[int] = set()
        for entry, employee in new_employees:
            entry.employee = employee
            created_ids.add(employee.pk)
            result.created.append(employee)
            result.by_ref[entry.ref] = {"employee": employee, "record": None, "action": "create"}

        # 2. Identity changes and exits on existing employees (before snapshots taken first).
        changed: list[Employee] = []
        employee_entries: list[tuple[BulkEntry, dict[str, Any], str]] = []
        for entry in entries:
            employee = entry.employee
            if employee.pk in created_ids:
                continue
            if not entry.identity_changes and entry.last_date is None:
                continue
            before = audit.snapshot_employee(employee)
            before_record = _record_for_snapshot(employee, ctx)
            if entry.identity_changes:
                _apply_identity(employee, entry.identity_changes, ctx)
            employee.updated_at = at
            changed.append(employee)
            item = {"before": before, "record": before_record}
            if entry.last_date is not None:
                employee.last_date = entry.last_date
                result.exited.append(employee)
                employee_entries.append((entry, item, "exit"))
                result.by_ref.setdefault(
                    entry.ref, {"employee": employee, "record": None, "action": "exit"}
                )
            elif not entry.records:
                # An identity-only row writes one `update` entry. A row that also revises writes
                # only its `revise` entry (SPEC F2); the identity change rides in the same
                # transaction.
                result.updated.append(employee)
                employee_entries.append((entry, item, "update"))
                result.by_ref.setdefault(
                    entry.ref, {"employee": employee, "record": None, "action": "update"}
                )
        Employee.objects.bulk_update(
            changed,
            [
                "full_name",
                "email",
                "gender",
                "department",
                "designation",
                "level",
                "joining_date",
                "last_date",
                "updated_at",
            ],
            batch_size=BATCH,
        )

        # 3. Records: close what the new ones supersede, then insert the new ones.
        max_versions = _max_versions([entry.employee.pk for entry in entries])
        to_close: list[CompensationRecord] = []
        closed_for_exit: dict[int, CompensationRecord] = {}
        new_rows: list[
            tuple[BulkEntry, CompensationRecord, list[CompensationLine], CompensationRecord | None]
        ] = []
        for entry in entries:
            employee = entry.employee
            is_new = employee.pk in created_ids
            last = entry.last_date or employee.last_date
            close_at = last + ONE_DAY if last is not None else None
            if not entry.records:
                if entry.last_date is not None:
                    open_row = ctx.open_by_employee.get(employee.pk)
                    if open_row is not None:
                        open_row.effective_to = close_at
                        to_close.append(open_row)
                        closed_for_exit[employee.pk] = open_row
                continue
            try:
                chained = chain_records(
                    entry.records, joining_date=employee.joining_date, close_at=close_at
                )
            except ValueError as exc:
                raise BulkInvalid(entry.ref, {"effective_from": [str(exc)]}) from exc
            previous = None if is_new else ctx.latest_by_employee.get(employee.pk)
            if previous is not None:
                previous.effective_to = chained[0].effective_from
                to_close.append(previous)
            components = ctx.components_for(employee.country_id)
            version = max_versions.get(employee.pk, 0)
            # What each new record supersedes: the stored previous record for the first one, the
            # in-memory prior record for the rest of a chain. Lines come with the in-memory one.
            superseded = (previous, None) if previous is not None else None
            for item in chained:
                version += 1
                row, lines = _build_record(
                    employee,
                    item.record,
                    version=version,
                    effective_from=item.effective_from,
                    effective_to=item.effective_to,
                    components=components,
                    actor=actor,
                    source=source,
                    batch=batch,
                    at=at,
                )
                new_rows.append((entry, row, lines, superseded))
                superseded = (row, lines)
        CompensationRecord.objects.bulk_update(to_close, ["effective_to"], batch_size=BATCH)
        CompensationRecord.objects.bulk_create([row for _, row, _, _ in new_rows], batch_size=BATCH)
        all_lines: list[CompensationLine] = []
        for _, row, lines, _ in new_rows:
            for line in lines:
                line.record = row
            all_lines.extend(lines)
        CompensationLine.objects.bulk_create(all_lines, batch_size=BATCH)

        # 4. Audit, one entry per entity written, lines fetched in one query.
        wanted_lines = [
            superseded[0].pk
            for _, _, _, superseded in new_rows
            if superseded is not None and superseded[1] is None
        ]
        wanted_lines += [row.pk for row in closed_for_exit.values()]
        wanted_lines += [
            item["record"].pk for _, item, _ in employee_entries if item["record"] is not None
        ]
        stored_lines = _lines_by_record(wanted_lines)
        first_rows = {}
        for entry, row, lines, _ in new_rows:
            first_rows.setdefault(id(entry), (row, lines))
        to_log: list = []
        for entry, employee in new_employees:
            first, first_lines = first_rows.get(id(entry), (None, None))
            to_log.append(
                audit.build(
                    "create",
                    entity=employee,
                    actor=actor,
                    before=None,
                    after=audit.snapshot_employee(employee, record=first, lines=first_lines),
                    employee=employee,
                    import_batch=batch,
                    at=at,
                )
            )
        for entry, item, action in employee_entries:
            employee = entry.employee
            before = item["before"]
            before_record = item["record"]
            if before_record is not None:
                before["current_record"] = audit.snapshot_record(
                    before_record, stored_lines.get(before_record.pk)
                )
                if before_record in to_close:
                    # The before snapshot shows the record as it was, still open-ended.
                    before["current_record"]["effective_to"] = None
            after_record = closed_for_exit.get(employee.pk) or before_record
            after_lines = stored_lines.get(after_record.pk) if after_record is not None else None
            to_log.append(
                audit.build(
                    action,
                    entity=employee,
                    actor=actor,
                    before=before,
                    after=audit.snapshot_employee(employee, record=after_record, lines=after_lines),
                    employee=employee,
                    import_batch=batch,
                    at=at,
                )
            )
        for entry, row, lines, superseded in new_rows:
            before = None
            if superseded is not None:
                prior, prior_lines = superseded
                if prior_lines is None:
                    prior_lines = stored_lines.get(prior.pk)
                before = audit.snapshot_record(prior, prior_lines)
                # As the single path snapshots it: before the new record closed it.
                before["effective_to"] = None
            to_log.append(
                audit.build(
                    "revise",
                    entity=row,
                    actor=actor,
                    before=before,
                    after=audit.snapshot_record(row, lines),
                    employee=entry.employee,
                    import_batch=batch,
                    at=at,
                )
            )
            result.revised.append(row)
            slot = result.by_ref.setdefault(
                entry.ref, {"employee": entry.employee, "record": None, "action": "revise"}
            )
            if slot["record"] is None:
                slot["record"] = row
                if slot["action"] == "update":
                    slot["action"] = "revise"
        result.audit_entries = audit.bulk_record(to_log)
    return result
