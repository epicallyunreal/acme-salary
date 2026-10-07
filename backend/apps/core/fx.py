"""Read-time currency conversion (SPEC section 4 rule 4, DESIGN section 4).

A RateTable is loaded once per request for the reporting date. Rates are monthly rows; a date
before the earliest row uses the earliest rate. A pair without a direct row routes through USD.
Converted amounts are computed here and never stored.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Case, DecimalField, Value, When

from apps.core.dates import month_label as label_for_month
from apps.core.exceptions import Invalid
from apps.core.models import ExchangeRate
from apps.core.money import q2

USD = "USD"
EUR = "EUR"
ONE = Decimal("1")


@dataclass(frozen=True)
class Rate:
    from_currency: str
    to_currency: str
    rate: Decimal
    effective_from: date
    effective_to: date | None


class MissingRate(Invalid):
    def __init__(self, from_currency: str, to_currency: str):
        super().__init__({"currency": [f"no exchange rate from {from_currency} to {to_currency}"]})


class RateTable:
    def __init__(self, rates: Iterable[Rate], on: date):
        self.on = on
        self._direct: dict[tuple[str, str], Rate] = {
            (rate.from_currency, rate.to_currency): rate for rate in rates
        }

    @classmethod
    def load(cls, on: date) -> RateTable:
        """One query. Per pair: the row effective on `on`, else the earliest row."""
        exact: dict[tuple[str, str], Rate] = {}
        earliest: dict[tuple[str, str], Rate] = {}
        for row in ExchangeRate.objects.order_by("from_currency", "to_currency", "effective_from"):
            rate = Rate(
                row.from_currency, row.to_currency, row.rate, row.effective_from, row.effective_to
            )
            pair = (rate.from_currency, rate.to_currency)
            if rate.effective_from <= on and (rate.effective_to is None or rate.effective_to > on):
                exact[pair] = rate
            earliest.setdefault(pair, rate)
        return cls((earliest | exact).values(), on)

    def currencies(self) -> set[str]:
        return {ccy for pair in self._direct for ccy in pair}

    def _leg(self, from_currency: str, to_currency: str) -> Decimal | None:
        """A direct rate, or the inverse of the opposite direct rate when only that exists."""
        if from_currency == to_currency:
            return ONE
        direct = self._direct.get((from_currency, to_currency))
        if direct is not None:
            return direct.rate
        inverse = self._direct.get((to_currency, from_currency))
        if inverse is not None:
            return ONE / inverse.rate
        return None

    def rate(self, from_currency: str, to_currency: str) -> Decimal:
        if from_currency == to_currency:
            return ONE
        direct = self._direct.get((from_currency, to_currency))
        if direct is not None:
            return direct.rate
        to_usd = self._leg(from_currency, USD)
        from_usd = self._leg(USD, to_currency)
        if to_usd is None or from_usd is None:
            raise MissingRate(from_currency, to_currency)
        return to_usd * from_usd

    def effective_from(self, from_currency: str, to_currency: str) -> date | None:
        if from_currency == to_currency:
            return None
        direct = self._direct.get((from_currency, to_currency))
        if direct is not None:
            return direct.effective_from
        legs = [
            self._direct.get(pair) or self._direct.get(pair[::-1])
            for pair in ((from_currency, USD), (USD, to_currency))
        ]
        dates = [leg.effective_from for leg in legs if leg is not None]
        return max(dates) if dates else None

    def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        return q2(amount * self.rate(from_currency, to_currency))

    def case_expression(self, to_currency: str, currency_field: str) -> Case:
        """`CASE WHEN <field> = 'INR' THEN <rate> ...` for ordering and filtering in SQL only."""
        whens = [
            When(**{currency_field: ccy}, then=Value(self.rate(ccy, to_currency)))
            for ccy in sorted(self.currencies())
            if ccy != to_currency
        ]
        return Case(
            *whens,
            default=Value(ONE),
            output_field=DecimalField(max_digits=18, decimal_places=8),
        )

    def month_of(self, to_currency: str) -> date | None:
        """When the reporting currency's rates took effect: the latest `effective_from` among the
        rates into it, or None when no rate feeds it (D28)."""
        feeding = [
            rate.effective_from for pair, rate in self._direct.items() if pair[1] == to_currency
        ]
        return max(feeding) if feeding else None

    def month_label(self, to_currency: str) -> str:
        month = self.month_of(to_currency)
        if month is None:
            return f"local currency ({to_currency})"
        return f"{label_for_month(month)} rates"

    def rows(self) -> list[dict]:
        return [
            {
                "from_currency": rate.from_currency,
                "to_currency": rate.to_currency,
                "rate": rate.rate,
                "effective_from": rate.effective_from,
            }
            for _, rate in sorted(self._direct.items())
        ]


def resolve_reporting_currency(
    currency: str | None,
    country_codes: Sequence[str],
    currency_by_country: Mapping[str, str],
) -> str:
    """`usd` (default), `eur`, or `local` when exactly one country is in the filter.

    SPEC section 8.
    """
    value = (currency or "usd").strip().lower()
    if value == "usd":
        return USD
    if value == "eur":
        return EUR
    if value == "local":
        if len(country_codes) != 1:
            raise Invalid({"currency": ["currency=local needs exactly one country in the filter"]})
        code = country_codes[0]
        if code not in currency_by_country:
            raise Invalid({"country": [f"Unknown country_code: {code}"]})
        return currency_by_country[code]
    raise Invalid({"currency": [f"currency must be usd, eur or local, got {currency}"]})
