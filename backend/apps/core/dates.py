"""Reporting-date helpers. The reporting date is today in UTC unless the request passes `on`."""

from datetime import UTC, date, datetime

from apps.core.exceptions import Invalid, clip


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


def month_label(day: date) -> str:
    return day.strftime("%B %Y")
