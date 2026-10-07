"""audit.record(): the one way a write to employee or compensation data is logged (rule 7).

Snapshots mirror the detail serializers field for field, minus the request-dependent keys, and are
plain functions so the seed can produce tens of thousands of them inside its time budget.
"""

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from django.db import models

from apps.audit.models import AuditLog
from apps.core.money import q8, render

ENTITY_TYPES = {
    "employee": "employee",
    "compensationrecord": "compensation_record",
    "importbatch": "import_batch",
    "exchangerate": "exchange_rate",
}

BULK_SIZE = 1000


def entity_type_of(entity: models.Model) -> str:
    return ENTITY_TYPES[entity._meta.model_name]


def build(
    action: str,
    *,
    entity: models.Model,
    actor=None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    employee=None,
    import_batch=None,
    at: datetime | None = None,
) -> AuditLog:
    """An unsaved entry, for record() and for bulk_record()."""
    entry = AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type_of(entity),
        entity_id=entity.pk,
        employee=employee,
        before=render(before) if before is not None else None,
        after=render(after) if after is not None else None,
        import_batch=import_batch,
    )
    if at is not None:
        entry.timestamp = at
    return entry


def record(action: str, **kwargs) -> AuditLog:
    entry = build(action, **kwargs)
    entry.save()
    return entry


def bulk_record(entries: Iterable[AuditLog]) -> int:
    rows = list(entries)
    AuditLog.objects.bulk_create(rows, batch_size=BULK_SIZE)
    return len(rows)


def snapshot_record(record, lines: Iterable | None = None) -> dict[str, Any]:
    """The record as the detail serializer shows it, minus the request-dependent keys.

    `lines` are CompensationLine objects (saved or not, component loaded); when omitted they are
    read from the database.
    """
    if lines is None:
        lines = list(record.lines.select_related("component").order_by("component__sort_order"))
    line_items = [
        {"component": line.component.code, "annual_amount": line.annual_amount}
        for line in sorted(lines, key=lambda line: (line.component.sort_order, line.component.code))
    ]
    return {
        "id": record.pk,
        "employee": record.employee_id,
        "version": record.version,
        "effective_from": record.effective_from,
        "effective_to": record.effective_to,
        "cancelled_at": record.cancelled_at,
        "cancelled_by": record.cancelled_by.email if record.cancelled_by_id else None,
        "currency_code": record.currency_code,
        "bonus_annual": record.bonus_annual,
        "gross_annual": record.gross_annual,
        "net_annual": record.net_annual,
        "total_cost_annual": record.total_cost_annual,
        "source": record.source,
        "note": record.note,
        "created_at": record.created_at,
        "created_by": record.created_by.email if record.created_by_id else None,
        "lines": line_items,
    }


def snapshot_employee(employee, record=None, lines=None) -> dict[str, Any]:
    """Identity as the detail serializer shows it, plus the shown record when one is given."""
    return {
        "id": employee.pk,
        "employee_code": employee.employee_code,
        "legacy_code": employee.legacy_code,
        "full_name": employee.full_name,
        "email": employee.email,
        "gender": employee.gender,
        "department": {"code": employee.department.code, "name": employee.department.name},
        "designation": employee.designation,
        "level": employee.level,
        "country": {
            "code": employee.country.code,
            "name": employee.country.name,
            "currency_code": employee.country.currency_code,
        },
        "joining_date": employee.joining_date,
        "last_date": employee.last_date,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
        "current_record": snapshot_record(record, lines) if record is not None else None,
    }


def snapshot_rate(rate) -> dict[str, Any]:
    return {
        "id": rate.pk,
        "from_currency": rate.from_currency,
        "to_currency": rate.to_currency,
        "rate": q8(rate.rate),
        "effective_from": rate.effective_from,
        "effective_to": rate.effective_to,
    }
