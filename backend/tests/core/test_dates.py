from datetime import date

import pytest

from apps.core.dates import (
    month_label,
    months_before,
    parse_on,
    parse_period,
    period_start,
    today_utc,
)
from apps.core.exceptions import Invalid


def test_today_is_the_frozen_date(today):
    assert today_utc() == today == date(2026, 10, 7)


def test_parse_on_defaults_to_today(today):
    assert parse_on(None) == today
    assert parse_on("") == today


def test_parse_on_reads_an_iso_date():
    assert parse_on("2027-01-01") == date(2027, 1, 1)


def test_parse_on_starts_in_1900():
    """D62: the trend and the bridge reach two years back from `on`, so year 1 would be a 500."""
    assert parse_on("1900-01-01") == date(1900, 1, 1)
    with pytest.raises(Invalid) as excinfo:
        parse_on("1899-12-31")

    assert excinfo.value.errors == {"on": ["on must be on or after 1900-01-01, got 1899-12-31"]}


def test_parse_on_rejects_other_shapes():
    with pytest.raises(Invalid) as excinfo:
        parse_on("31/02/2024")

    assert excinfo.value.errors == {"on": ["on must be a date in YYYY-MM-DD form, got 31/02/2024"]}


def test_parse_on_repeats_at_most_64_characters_of_what_it_refused():
    """D56: the 400 names the value, cut, however long the query string was."""
    with pytest.raises(Invalid) as excinfo:
        parse_on("9" * 4000)

    assert excinfo.value.errors == {
        "on": [f"on must be a date in YYYY-MM-DD form, got {'9' * 63}\u2026"]
    }


def test_month_label():
    assert month_label(date(2026, 10, 1)) == "October 2026"


def test_a_period_defaults_to_the_twelve_months_ending_today(today):
    """D64 and D69: `to` today in UTC and `from` the day after the same day a year before, 365
    days, the dashboard's default, never before the reporting cut-off, 1 April 2020 (D70)."""
    assert parse_period(None, None) == (date(2025, 10, 8), date(2026, 10, 7))
    assert parse_period("2026-04-01", "2027-01-01") == (date(2026, 4, 1), date(2027, 1, 1))
    assert parse_period(None, "2020-06-30") == (date(2020, 4, 1), date(2020, 6, 30))
    assert parse_period(None, "2021-03-31") == (date(2020, 4, 1), date(2021, 3, 31))
    assert parse_period(None, "2021-04-30") == (date(2020, 5, 1), date(2021, 4, 30))


def test_a_period_may_end_on_the_last_day_allowed_and_be_one_day_long(today):
    assert parse_period("2100-12-01", "2100-12-31") == (date(2100, 12, 1), date(2100, 12, 31))
    assert parse_period(None, "2100-12-31") == (date(2100, 1, 1), date(2100, 12, 31))
    assert parse_period("2026-10-07", "2026-10-07") == (date(2026, 10, 7), date(2026, 10, 7))
    assert parse_period(None, "2020-04-01") == (date(2020, 4, 1), date(2020, 4, 1))


def test_a_period_of_n_months_starts_the_day_after_the_date_n_months_back():
    """D69: 12 months ending 8 October 2026 start on 9 October 2025. Where the day does not exist
    the date back is that month's last day, so 6 months ending 31 October start on 1 May, and one
    ending 31 March starts on 1 March."""
    assert period_start(date(2026, 10, 8), 12) == date(2025, 10, 9)
    assert period_start(date(2026, 10, 31), 6) == date(2026, 5, 1)
    assert period_start(date(2026, 3, 31), 1) == date(2026, 3, 1)
    assert period_start(date(2028, 2, 29), 12) == date(2027, 3, 1)


def test_a_month_back_lands_on_the_months_last_day_when_the_day_is_not_there():
    """D64: 31 October six months back is 30 April, 31 March a month back 28 or 29 February."""
    assert months_before(date(2026, 10, 31), 6) == date(2026, 4, 30)
    assert months_before(date(2025, 3, 31), 1) == date(2025, 2, 28)
    assert months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)
    assert months_before(date(2026, 10, 7), 12) == date(2025, 10, 7)


@pytest.mark.parametrize(
    ("start", "end", "errors"),
    [
        ("01/04/2026", None, {"from": ["from must be a date in YYYY-MM-DD form, got 01/04/2026"]}),
        ("20260101", None, {"from": ["from must be a date in YYYY-MM-DD form, got 20260101"]}),
        (None, "2026-W41-3", {"to": ["to must be a date in YYYY-MM-DD form, got 2026-W41-3"]}),
        (None, "0001-06-15", {"to": ["to must be on or after 2020-04-01, got 0001-06-15"]}),
        (None, "9999-12-31", {"to": ["to must be on or before 2100-12-31, got 9999-12-31"]}),
        ("2020-03-31", None, {"from": ["from must be on or after 2020-04-01, got 2020-03-31"]}),
        (None, "2020-03-31", {"to": ["to must be on or after 2020-04-01, got 2020-03-31"]}),
        (None, "2101-01-01", {"to": ["to must be on or before 2100-12-31, got 2101-01-01"]}),
        ("2026-10-08", "2026-10-07", {"from": ["from must be on or before to"]}),
    ],
)
def test_a_period_out_of_bounds_or_backwards_is_refused(today, start, end, errors):
    with pytest.raises(Invalid) as excinfo:
        parse_period(start, end)

    assert excinfo.value.errors == errors
