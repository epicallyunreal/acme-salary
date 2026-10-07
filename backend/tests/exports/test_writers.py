"""The CSV, XLSX and JSON writers (SPEC F6, DESIGN 1.7), without HTTP."""

import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from apps.exports import writers

HEADER = ("Full name", "Level", "Gross", "Gap %", "Joining date", "Last date")
ROW = ('=HYPERLINK("http://x")', 3, Decimal("1595000.00"), Decimal("-11.1"), date(2020, 1, 1), None)


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_text_that_starts_like_a_formula_gets_a_single_quote(start):
    assert writers.escape_cell(f"{start}SUM(A1:A9)") == f"'{start}SUM(A1:A9)"


@pytest.mark.parametrize(
    "value", ["Asha Rao", "a=b", "", None, 3, Decimal("-5000.00"), date(2026, 10, 7)]
)
def test_anything_else_is_left_as_it_is(value):
    assert writers.escape_cell(value) == value


def csv_text(header, rows):
    return b"".join(writers.csv_stream(header, rows)).decode()


def test_csv_starts_with_a_byte_order_mark_then_the_header():
    text = csv_text(HEADER, [])

    assert text == "﻿Full name,Level,Gross,Gap %,Joining date,Last date\r\n"


def test_csv_escapes_formulas_and_writes_numbers_dates_and_blanks_plainly():
    text = csv_text(HEADER, [ROW])

    assert text.splitlines()[1] == '"\'=HYPERLINK(""http://x"")",3,1595000.00,-11.1,2020-01-01,'


def test_csv_streams_a_hundred_rows_at_a_time():
    chunks = list(writers.csv_stream(("n",), [(n,) for n in range(250)]))

    assert len(chunks) == 4
    assert b"".join(chunks).decode().splitlines()[1:] == [str(n) for n in range(250)]


def sheet_of(content: bytes):
    return load_workbook(io.BytesIO(content)).active


def test_xlsx_writes_one_named_sheet_with_the_header_first():
    worksheet = sheet_of(writers.xlsx_bytes(HEADER, [ROW], sheet="employees"))

    assert worksheet.title == "employees"
    assert [cell.value for cell in worksheet[1]] == list(HEADER)


def test_xlsx_keeps_a_formula_as_text_and_numbers_and_dates_typed():
    name, level, gross, gap, joined, left = sheet_of(
        writers.xlsx_bytes(HEADER, [ROW], sheet="employees")
    )[2]

    assert (name.value, name.data_type) == ('\'=HYPERLINK("http://x")', "s")
    assert (level.value, level.data_type) == (3, "n")
    assert (gross.value, gross.data_type) == (1595000, "n")
    assert (gap.value, gap.data_type) == (-11.1, "n")
    assert (joined.value, joined.is_date) == (datetime(2020, 1, 1), True)
    assert left.value is None


def test_xlsx_replaces_a_control_character_it_cannot_hold():
    """openpyxl refuses a whole workbook over one such character."""
    (cell,) = sheet_of(writers.xlsx_bytes(("Full name",), [("Asha\x0bRao",)], sheet="employees"))[2]

    assert cell.value == "Asha�Rao"


def test_json_holds_the_stamp_the_filters_and_one_object_per_row():
    content = writers.json_bytes(
        ("full_name", "level", "gross", "gap_pct", "joining_date", "last_date"),
        [ROW],
        generated_at=datetime(2026, 10, 7, 9, 0, tzinfo=UTC),
        filters={"country": "IN", "currency": "USD", "on": date(2026, 10, 7)},
    )

    assert json.loads(content) == {
        "generated_at": "2026-10-07T09:00:00+00:00",
        "filters": {"country": "IN", "currency": "USD", "on": "2026-10-07"},
        "rows": [
            {
                "full_name": '=HYPERLINK("http://x")',
                "level": 3,
                "gross": "1595000.00",
                "gap_pct": "-11.1",
                "joining_date": "2020-01-01",
                "last_date": None,
            }
        ],
    }
