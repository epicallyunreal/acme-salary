"""Exchange-rate writes (DESIGN section 4). The table is the single source of truth for rates."""

from datetime import date, datetime
from decimal import Decimal

from django.db import transaction

from apps.audit import services as audit
from apps.core.dates import month_label
from apps.core.exceptions import Invalid
from apps.core.models import ExchangeRate


def set_exchange_rate(
    from_currency: str,
    to_currency: str,
    rate: Decimal,
    effective_from: date,
    *,
    actor=None,
    replace: bool = False,
    at: datetime | None = None,
) -> ExchangeRate:
    """Insert the month's row and close the previous one, in one audited transaction.

    Rules (SPEC section 15 step 2, D22): the date is the first of a month; it is after the pair's
    latest row, or equal to it with `replace`, which updates that row's rate instead.
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    errors: dict[str, list[str]] = {}
    if from_currency == to_currency:
        errors["to_currency"] = ["to_currency must differ from from_currency"]
    if rate <= 0:
        errors["rate"] = ["rate must be greater than 0"]
    if effective_from.day != 1:
        errors["effective_from"] = ["must be the first day of a month"]
    if errors:
        raise Invalid(errors)

    with transaction.atomic():
        latest = (
            ExchangeRate.objects.filter(from_currency=from_currency, to_currency=to_currency)
            .order_by("-effective_from")
            .first()
        )
        if latest is not None and effective_from < latest.effective_from:
            raise Invalid(
                {"effective_from": [f"on or before the latest row {latest.effective_from}"]}
            )
        if latest is not None and effective_from == latest.effective_from:
            if not replace:
                raise Invalid(
                    {
                        "effective_from": [
                            f"a rate for {month_label(effective_from)} exists, pass --replace"
                        ]
                    }
                )
            before = audit.snapshot_rate(latest)
            latest.rate = rate
            latest.save(update_fields=["rate"])
            audit.record(
                "set_rate",
                entity=latest,
                actor=actor,
                before=before,
                after=audit.snapshot_rate(latest),
                at=at,
            )
            return latest

        before = None
        if latest is not None:
            before = audit.snapshot_rate(latest)
            latest.effective_to = effective_from
            latest.save(update_fields=["effective_to"])
        row = ExchangeRate.objects.create(
            from_currency=from_currency,
            to_currency=to_currency,
            rate=rate,
            effective_from=effective_from,
            effective_to=None,
            created_by=actor,
            **({"created_at": at} if at is not None else {}),
        )
        audit.record(
            "set_rate",
            entity=row,
            actor=actor,
            before=before,
            after=audit.snapshot_rate(row),
            at=at,
        )
        return row
