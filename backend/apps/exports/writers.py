"""The three export formats (SPEC F6, DESIGN 1.7). Each takes a header, or the keys, and rows of
plain values: text, int, Decimal, date or None.

A CSV or XLSX cell whose text starts like a formula gets a leading single quote, so a spreadsheet
shows it instead of running it. Numbers are written as numbers and never escaped, so a negative
amount stays a number. JSON holds values, not cells, and is written as it is (D60).
"""

import csv
import io
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from itertools import batched
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from apps.core.money import render, to_str

FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
# Excel reads a CSV as UTF-8 only when it starts with a byte order mark.
BOM = "﻿"
# Rows per chunk of a streamed CSV, as Django's own streaming example batches them.
BATCH = 100


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
    return to_str(value) if isinstance(value, Decimal) else escape_cell(value)


def csv_stream(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Iterator[bytes]:
    """The header, then the rows a hundred at a time, so a whole directory never sits in memory.
    Dates are ISO text and an empty value an empty cell."""
    writer = csv.writer(_Echo())
    yield (BOM + writer.writerow(header)).encode()
    for batch in batched(rows, BATCH, strict=False):  # the last batch may be short
        yield "".join(
            writer.writerow([_csv_cell(value) for value in row]) for row in batch
        ).encode()


def _xlsx_cell(value: Any) -> Any:
    """XML cannot hold most control characters, and openpyxl refuses the whole workbook over one,
    so each is replaced by U+FFFD, which shows where something was."""
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("�", escape_cell(value))
    return value


def xlsx_bytes(header: Sequence[str], rows: Iterable[Sequence[Any]], *, sheet: str) -> bytes:
    """A one-sheet workbook in openpyxl's write-only mode, which writes each row as it comes.
    Amounts and levels are numbers and dates are dates."""
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
