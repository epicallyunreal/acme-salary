"""Lookup rows and seeded rates, idempotent. seed_data and the test fixtures both call these.

The lookups are data, not a migration (DESIGN section 1.0): migrations stay schema-only and
reset_demo can rebuild everything in the determinism scope.
"""

from datetime import datetime

from apps.core.models import Country, Department, ExchangeRate, SalaryComponent
from apps.core.services import set_exchange_rate
from seed import profiles


def ensure_lookups() -> None:
    for spec in profiles.COUNTRIES:
        Country.objects.update_or_create(
            code=spec.code,
            defaults={
                "name": spec.name,
                "currency_code": spec.currency,
                "min_gross_annual": spec.min_gross,
            },
        )
    for spec in profiles.DEPARTMENTS:
        Department.objects.update_or_create(code=spec.code, defaults={"name": spec.name})
    for spec in profiles.COMPONENTS:
        SalaryComponent.objects.update_or_create(
            code=spec.code,
            defaults={
                "name": spec.name,
                "kind": spec.kind,
                "country_id": spec.country,
                "sort_order": spec.sort_order,
                "is_active": True,
            },
        )


def ensure_rates(at: datetime | None = None) -> None:
    """The sixteen rows through the service, September before October, skipping rows that exist."""
    existing = set(
        ExchangeRate.objects.values_list("from_currency", "to_currency", "effective_from")
    )
    for from_currency, to_currency, effective_from, rate in profiles.RATES:
        if (from_currency, to_currency, effective_from) in existing:
            continue
        set_exchange_rate(from_currency, to_currency, rate, effective_from, at=at)
