"""Reporting-date helpers. The reporting date is today in UTC unless the request passes `on`, and
the insights read a period, `from` and `to`, instead (D64)."""

import calendar
import re
from datetime import UTC, date, datetime, timedelta

from apps.core.exceptions import Invalid, clip

# The reporting cut-off, 1 April 2020, the start of FY 2020-21 (D70): the first day a period may
# cover, and the earliest last_date Include exited adds. Pay history before it stays, and a
# record running into it counts for the days it covers.
REPORTING_START = date(2020, 4, 1)
# The last day a period may cover, the last date the data allows (D53).
PERIOD_LAST = date(2100, 12, 31)
# A period without `from` is the dashboard's Last 12 months (D64).
PERIOD_MONTHS = 12
# `fromisoformat` reads week dates and compact forms as well, which the messages do not offer.
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def today_utc() -> date:
    return datetime.now(UTC).date()


EARLIEST_ON = date(1900, 1, 1)


def parse_on(value: str | None) -> date:
    """`on`, or today in UTC when it is not given. Before 1900 is a 400 (D62)."""
    on = parse_date("on", value) or today_utc()
    if on < EARLIEST_ON:
        raise Invalid({"on": [f"on must be on or after 1900-01-01, got {clip(value)}"]})
    return on


def parse_date(name: str, value: str | None) -> date | None:
    """`value` as a `YYYY-MM-DD` date, or None when not given. Any other shape is a 400 naming
    `name`."""
    if value in (None, ""):
        return None
    message = f"{name} must be a date in YYYY-MM-DD form, got {clip(value)}"
    if not ISO_DATE.fullmatch(value):
        raise Invalid({name: [message]})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise Invalid({name: [message]}) from exc


def parse_period(start: str | None, end: str | None) -> tuple[date, date]:
    """An insight's `from` and `to` (D64, D70). `to` is today in UTC when not given, and `from` the
    first day of the 12 months ending on it, never before the reporting cut-off. Each must lie
    from 2020-04-01 to 2100-12-31, and `from` on or before `to`."""
    last = parse_date("to", end) or today_utc()
    first = parse_date("from", start)
    if first is None:
        # Worked out only from a `to` inside the bounds, so a far-off one never leaves them.
        within = REPORTING_START < last <= PERIOD_LAST
        first = REPORTING_START
        if within:
            first = max(period_start(last, PERIOD_MONTHS), REPORTING_START)
    errors = {}
    for name, value in (("from", first), ("to", last)):
        if value < REPORTING_START:
            bound = REPORTING_START.isoformat()
            errors[name] = [f"{name} must be on or after {bound}, got {value.isoformat()}"]
        elif value > PERIOD_LAST:
            bound = PERIOD_LAST.isoformat()
            errors[name] = [f"{name} must be on or before {bound}, got {value.isoformat()}"]
    if errors:
        raise Invalid(errors)
    if first > last:
        raise Invalid({"from": ["from must be on or before to"]})
    return first, last


def last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def period_start(last: date, months: int) -> date:
    """The first day of the `months` months ending on `last`: the day after the same day that many
    months before, or after that month's last day when it is shorter. 12 months ending 8 October
    2026 start on 9 October 2025, and 6 ending 31 October start on 1 May (D69)."""
    return months_before(last, months) + timedelta(days=1)


def months_before(day: date, months: int) -> date:
    """The same day `months` months earlier, or that month's last day when it is shorter, so 31
    October six months back is 30 April and 29 February a year back is 28 February."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def month_label(day: date) -> str:
    return day.strftime("%B %Y")
