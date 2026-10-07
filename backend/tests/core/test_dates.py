from datetime import date

import pytest

from apps.core.dates import month_label, parse_on, today_utc
from apps.core.exceptions import Invalid


def test_today_is_the_frozen_date(today):
    assert today_utc() == today == date(2026, 10, 7)


def test_parse_on_defaults_to_today(today):
    assert parse_on(None) == today
    assert parse_on("") == today


def test_parse_on_reads_an_iso_date():
    assert parse_on("2027-01-01") == date(2027, 1, 1)


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
