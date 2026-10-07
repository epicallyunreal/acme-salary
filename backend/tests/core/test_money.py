from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.core.money import format_amount, q1, q2, render, to_str


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2.345", "2.35"), ("2.344", "2.34"), ("-2.345", "-2.35"), ("1", "1.00"), ("0.005", "0.01")],
)
def test_q2_rounds_half_up_to_two_places(value, expected):
    assert q2(Decimal(value)) == Decimal(expected)
    assert str(q2(Decimal(value))) == expected


def test_q1_rounds_half_up_to_one_place():
    assert str(q1(Decimal("65.45"))) == "65.5"
    assert str(q1(Decimal("-11.11"))) == "-11.1"


def test_to_str_never_uses_scientific_notation():
    assert to_str(Decimal("1E+2")) == "100"
    assert to_str(Decimal("0.01200000")) == "0.01200000"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("300000.00", "300,000"), ("12.5", "12.50"), ("1450000", "1,450,000"), ("0", "0")],
)
def test_format_amount_for_messages(value, expected):
    assert format_amount(Decimal(value)) == expected


def test_render_turns_decimals_and_dates_into_text_recursively():
    payload = {
        "gross": Decimal("17400.00"),
        "lines": [{"amount": Decimal("1"), "on": date(2026, 10, 7)}],
        "at": datetime(2026, 10, 6, tzinfo=UTC),
        "n": 3,
        "label": "x",
        "none": None,
    }

    assert render(payload) == {
        "gross": "17400.00",
        "lines": [{"amount": "1", "on": "2026-10-07"}],
        "at": "2026-10-06T00:00:00+00:00",
        "n": 3,
        "label": "x",
        "none": None,
    }
