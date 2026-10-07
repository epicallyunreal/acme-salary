"""Reporting-date helpers. The reporting date is today in UTC unless the request passes `on`."""

from datetime import UTC, date, datetime

from apps.core.exceptions import Invalid, clip


def today_utc() -> date:
    return datetime.now(UTC).date()


def parse_on(value: str | None) -> date:
    if value in (None, ""):
        return today_utc()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise Invalid({"on": [f"on must be a date in YYYY-MM-DD form, got {clip(value)}"]}) from exc


def month_label(day: date) -> str:
    return day.strftime("%B %Y")
