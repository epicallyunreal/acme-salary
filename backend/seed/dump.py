"""Canonical dump of the business tables, for the determinism test (SPEC section 11 rule 8).

Tables in a fixed order, rows by primary key, columns in model field order, Decimals at the
field's scale, dates in ISO form, JSON with sorted keys. Users are outside the scope.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from django.apps import apps

from seed import profiles


def _cell(value, field) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value.quantize(Decimal(1).scaleb(-field.decimal_places)), "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def canonical_dump() -> str:
    chunks: list[str] = []
    for label in reversed(profiles.BUSINESS_TABLES):
        model = apps.get_model(label)
        fields = [field for field in model._meta.concrete_fields]
        chunks.append("# " + label + "\n")
        chunks.append(",".join(field.name for field in fields) + "\n")
        for row in model.objects.order_by("pk").values_list(*[field.attname for field in fields]):
            chunks.append(
                ",".join(_cell(value, field) for value, field in zip(row, fields, strict=True))
                + "\n"
            )
    return "".join(chunks)


def dump_hash() -> str:
    return hashlib.sha256(canonical_dump().encode("utf-8")).hexdigest()
