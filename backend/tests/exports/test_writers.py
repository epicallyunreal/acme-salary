"""The CSV, XLSX and JSON writers (SPEC F6, DESIGN 1.7), without HTTP."""

import csv
import io
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from apps.exports import writers

# Spelt by code point, so no invisible character sits in this file.
REPLACEMENT = chr(0xFFFD)
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


def test_csv_starts_with_a_byte_order_mark_then_the_quoted_header():
    text = csv_text(HEADER, [])

    assert writers.BOM == chr(0xFEFF)
    assert (
        text == writers.BOM + '"Full name","Level","Gross","Gap %","Joining date","Last date"\r\n'
    )


def test_csv_escapes_formulas_quotes_every_field_and_writes_numbers_and_dates_plainly():
    text = csv_text(HEADER, [ROW])

    assert text.splitlines()[1] == (
        '"\'=HYPERLINK(""http://x"")","3","1595000.00","-11.1","2020-01-01",""'
    )


@pytest.mark.parametrize("start", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_puts_a_single_quote_after_a_semicolon_a_formula_start_follows(start):
    """Excel set to split on semicolons would read `=1+1` as a cell of its own (D76)."""
    text = csv_text(("Full name",), [(f"Ann;{start}1+1;x",)])

    assert text.split("\r\n")[1] == f'"Ann;\'{start}1+1;x"'


def test_csv_puts_a_single_quote_after_a_semicolon_and_one_double_quote_a_formula_start_follows():
    """That reader takes the doubled quote after the semicolon as an empty quoted start and reads
    the formula as the rest of the cell. After two quotes the cell starts with a quote, as text."""
    text = csv_text(("Full name",), [('Ann;"=1+1',), ('Ann;""=1+1',)])

    assert text.splitlines()[1:] == ['"Ann;\'""=1+1"', '"Ann;""""=1+1"']


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("Ann\n=1+1", "Ann\n'=1+1"),
        ("Ann\r\n=1+1", "Ann\r\n'=1+1"),
        ("Ann\r=1+1", "Ann\r'=1+1"),
        ('Ann\n"@x', "Ann\n'\"@x"),
        ("Ann\nRao", "Ann\nRao"),
    ],
    ids=["newline", "crlf", "lone_cr", "after_a_quote", "no_formula"],
)
def test_csv_puts_a_single_quote_after_a_line_break_a_formula_start_follows(written, read):
    """A reader that ignores quotes starts a record at a line break as readily as a cell at a
    semicolon, so the formula after it would begin a cell (D76)."""
    rows = list(csv.reader(io.StringIO(csv_text(("x",), [(written,)]).removeprefix(writers.BOM))))

    (cell,) = rows[1]
    assert cell == read


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("Ann;=1+1;x", "Ann;'=1+1;x"),
        ("=1;+2;-3", "'=1;'+2;'-3"),
        ('Ann;"@x', "Ann;'\"@x"),
        ("R&D;Sales", "R&D;Sales"),
        ("a; =1", "a; =1"),
        ("a;'=1", "a;'=1"),
        ("Ann;Rao;", "Ann;Rao;"),
    ],
)
def test_csv_text_reads_back_as_written_apart_from_the_added_quote_mark(written, read):
    rows = list(csv.reader(io.StringIO(csv_text(("x",), [(written,)]).removeprefix(writers.BOM))))

    (cell,) = rows[1]
    assert cell == read
    assert cell.replace("'", "") == written.replace("'", "")


def test_csv_streams_a_hundred_rows_at_a_time():
    chunks = list(writers.csv_stream(("n",), [(n,) for n in range(250)]))

    assert len(chunks) == 4
    rows = list(csv.reader(io.StringIO(b"".join(chunks).decode().removeprefix(writers.BOM))))
    assert rows[1:] == [[str(n)] for n in range(250)]


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


@pytest.mark.parametrize("bad", [chr(0x0B), chr(0x01), chr(0xFFFE), chr(0xFFFF)])
def test_xlsx_replaces_a_character_xml_cannot_hold(bad):
    """openpyxl refuses a workbook over a control character, and writes U+FFFE and U+FFFF into
    one that will not open."""
    (cell,) = sheet_of(writers.xlsx_bytes(("Full name",), [(f"Asha{bad}Rao",)], sheet="x"))[2]

    assert cell.value == f"Asha{REPLACEMENT}Rao"


def test_xlsx_keeps_tabs_and_line_breaks():
    (cell,) = sheet_of(writers.xlsx_bytes(("Note",), [("a\tb\nc",)], sheet="x"))[2]

    assert cell.value == "a\tb\nc"


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


def test_only_the_csv_escapes_after_a_semicolon():
    (cell,) = sheet_of(writers.xlsx_bytes(("Full name",), [("Ann;=1+1;x",)], sheet="x"))[2]
    content = writers.json_bytes(
        ("full_name",),
        [("Ann;=1+1;x",)],
        generated_at=datetime(2026, 10, 9, 9, 0, tzinfo=UTC),
        filters={},
    )

    assert cell.value == "Ann;=1+1;x"
    assert json.loads(content)["rows"] == [{"full_name": "Ann;=1+1;x"}]
