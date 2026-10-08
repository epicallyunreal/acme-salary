"""Reporting-date helpers. The reporting date is today in UTC unless the request passes `on`, and
the insights read a period, `from` and `to`, instead (D64)."""

import calendar
from datetime import UTC, date, datetime

from apps.core.exceptions import Invalid, clip

# The period the insights read (D64): from the seed's first day to the last date the data allows
# (D53), the dashboard's Last 12 months when not given.
PERIOD_FIRST = date(2015, 1, 1)
PERIOD_LAST = date(2100, 12, 31)
PERIOD_MONTHS = 12


def today_utc() -> date:
    return datetime.now(UTC).date()


EARLIEST_ON = date(1900, 1, 1)


def parse_on(value: str | None) -> date:
    """`on`, or today in UTC when it is not given. Before 1900 is a 400, since the trend and the
    bridge reach two years back from it (D62)."""
    if value in (None, ""):
        return today_utc()
    try:
        on = date.fromisoformat(value)
    except ValueError as exc:
        raise Invalid({"on": [f"on must be a date in YYYY-MM-DD form, got {clip(value)}"]}) from exc
    if on < EARLIEST_ON:
        raise Invalid({"on": [f"on must be on or after 1900-01-01, got {clip(value)}"]})
    return on


def parse_date(name: str, value: str | None) -> date | None:
    """`value` as a date, or None when not given. Any other shape is a 400 naming `name`."""
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        message = f"{name} must be a date in YYYY-MM-DD form, got {clip(value)}"
        raise Invalid({name: [message]}) from exc


def parse_period(start: str | None, end: str | None) -> tuple[date, date]:
    """An insight's `from` and `to` (D64). `to` is today in UTC when not given, and `from` the same
    day 12 months before it, no earlier than 1 January 2015. Each must lie from 2015-01-01 to
    2100-12-31, and `from` on or before `to`."""
    last = parse_date("to", end) or today_utc()
    first = parse_date("from", start) or max(months_before(last, PERIOD_MONTHS), PERIOD_FIRST)
    errors = {}
    for name, value in (("from", first), ("to", last)):
        if value < PERIOD_FIRST:
            errors[name] = [f"{name} must be on or after 2015-01-01, got {value.isoformat()}"]
        elif value > PERIOD_LAST:
            errors[name] = [f"{name} must be on or before 2100-12-31, got {value.isoformat()}"]
    if errors:
        raise Invalid(errors)
    if first > last:
        raise Invalid({"from": ["from must be on or before to"]})
    return first, last


def last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def months_before(day: date, months: int) -> date:
    """The same day `months` months earlier, or that month's last day when it is shorter, so 31
    October six months back is 30 April and 29 February a year back is 28 February."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def month_label(day: date) -> str:
    return day.strftime("%B %Y")
