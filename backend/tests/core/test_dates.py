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


def test_month_label():
    assert month_label(date(2026, 10, 1)) == "October 2026"
