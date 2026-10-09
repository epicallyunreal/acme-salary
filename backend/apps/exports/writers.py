"""The three export formats (SPEC F6, DESIGN 1.7). Each takes a header, or the keys, and rows of
plain values: text, int, Decimal, date or None.

A CSV or XLSX cell whose text starts like a formula gets a leading single quote, so a spreadsheet
shows it instead of running it. In a CSV a formula start after a semicolon inside the text takes
one too, after the semicolon (D76). Numbers are written as numbers and never escaped, so a
negative amount stays a number. JSON holds values, not cells, and is written as it is (D60).
"""

import csv
import io
import json
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from itertools import batched
from typing import Any

from openpyxl import Workbook

from apps.core.money import render, to_str

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
# Excel reads a CSV as UTF-8 only when it starts with a byte order mark.
BOM = "\ufeff"
# Rows per chunk of a streamed CSV, as Django's own streaming example batches them.
BATCH = 100
# What XML 1.0 cannot hold: the C0 controls but tab, newline and carriage return, and U+FFFE and
# U+FFFF. openpyxl refuses the first and writes the last two into a file that will not open.
XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
# A semicolon that a formula start follows, directly or after one double quote. A reader whose list
# separator is ';', as Excel's is in Germany and the Netherlands, starts a cell there and reads the
# doubled quote as an empty quoted start, so the formula would begin that cell (D76).
SEMICOLON_FORMULA = re.compile(r';(?="?[=+\-@\t\r])')


def escape_cell(value: Any) -> Any:
    """Text that starts like a formula, with a single quote in front. Anything else as it is."""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return f"'{value}"
    return value


class _Echo:
    """The one method of a file csv.writer needs: each written line is handed straight back."""

    def write(self, line: str) -> str:
        return line


def _csv_cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        return to_str(value)
    value = escape_cell(value)
    return SEMICOLON_FORMULA.sub(";'", value) if isinstance(value, str) else value


def csv_stream(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Iterator[bytes]:
    """The header, then the rows a hundred at a time, so a whole directory never sits in memory.
    Dates are ISO text and an empty value an empty cell. Every field is quoted, and a formula
    start after a semicolon takes a single quote, so a spreadsheet that splits on semicolons
    finds no cell that starts a formula."""
    writer = csv.writer(_Echo(), quoting=csv.QUOTE_ALL)
    yield (BOM + writer.writerow(header)).encode()
    for batch in batched(rows, BATCH, strict=False):  # the last batch may be short
        yield "".join(
            writer.writerow([_csv_cell(value) for value in row]) for row in batch
        ).encode()


def _xlsx_cell(value: Any) -> Any:
    """Each character XML cannot hold becomes U+FFFD, which shows where something was."""
    if isinstance(value, str):
        return XML_ILLEGAL.sub("\ufffd", escape_cell(value))
    return value


def xlsx_bytes(header: Sequence[str], rows: Iterable[Sequence[Any]], *, sheet: str) -> bytes:
    """A one-sheet workbook in openpyxl's write-only mode, amounts and levels as numbers and dates
    as dates. The mode spools the sheet to a temporary file it removes on save, so the rows are
    read first: a row that fails then fails before any file holds pay."""
    rows = list(rows)
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title=sheet)
    worksheet.append(list(header))
    for row in rows:
        worksheet.append([_xlsx_cell(value) for value in row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def json_bytes(
    keys: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    generated_at: datetime,
    filters: Mapping[str, Any],
) -> bytes:
    """`{generated_at, filters, rows}` with one object per row under snake_case keys, money as
    two-decimal text as everywhere in the API (D27)."""
    payload = {
        "generated_at": generated_at,
        "filters": dict(filters),
        "rows": [dict(zip(keys, row, strict=True)) for row in rows],
    }
    return json.dumps(render(payload), ensure_ascii=False).encode()
