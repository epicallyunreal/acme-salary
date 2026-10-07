"""Decimal helpers: money is Decimal in Python, quantised half-up to two places once at the edge."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

TWO_PLACES = Decimal("0.01")
ONE_PLACE = Decimal("0.1")
EIGHT_PLACES = Decimal("0.00000001")


def q2(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def q8(value: Decimal) -> Decimal:
    """FX rates are stored with eight places; snapshots use the stored shape."""
    return value.quantize(EIGHT_PLACES, rounding=ROUND_HALF_UP)


def q1(value: Decimal) -> Decimal:
    return value.quantize(ONE_PLACE, rounding=ROUND_HALF_UP)


def to_str(value: Decimal) -> str:
    """A Decimal as plain text, never in scientific notation."""
    return format(value, "f")


def format_cents(value: Decimal) -> str:
    """For messages about a limit: thousands separators and always two decimals
    (`9,999,999,999.99`, `5.00`)."""
    return f"{value:,.2f}"


def format_amount(value: Decimal) -> str:
    """For messages: thousands separators, decimals only when there are any (`300,000`, `12.50`)."""
    if value == value.to_integral_value():
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def render(payload: Any) -> Any:
    """Walk a payload turning Decimal into text and dates into ISO text, so DRF's encoder never
    sees a Decimal (it would make a float) and audit JSON is reproducible."""
    if isinstance(payload, Decimal):
        return to_str(payload)
    if isinstance(payload, datetime):
        return payload.isoformat()
    if isinstance(payload, date):
        return payload.isoformat()
    if isinstance(payload, dict):
        return {key: render(value) for key, value in payload.items()}
    if isinstance(payload, list | tuple):
        return [render(value) for value in payload]
    return payload
