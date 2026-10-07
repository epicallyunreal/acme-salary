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


def snapshot_rate(rate) -> dict[str, Any]:
    return {
        "id": rate.pk,
        "from_currency": rate.from_currency,
        "to_currency": rate.to_currency,
        "rate": q8(rate.rate),
        "effective_from": rate.effective_from,
        "effective_to": rate.effective_to,
    }
