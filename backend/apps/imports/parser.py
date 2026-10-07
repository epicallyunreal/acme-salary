"""Reading an uploaded sheet (SPEC F1, DESIGN 1.5).

The template's shape, the header check, the file reader and the cell parsers. Every message text
comes from compensation/messages.py, so a sheet reads the same words as the API. The first column
is legacy_code, the code the legacy system gave the employee (D48).
"""

from __future__ import annotations

import csv
import io
import math
import re
import unicodedata
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import PurePath
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from apps.compensation.messages import msg
from apps.compensation.validators import Message, NormalizedRow, error
from apps.core.exceptions import Invalid

IDENTITY_COLUMNS = (
    "legacy_code",
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "country_code",
    "gender",
    "joining_date",
    "last_date",
    "effective_from",
    "bonus_annual",
)
REQUIRED_COLUMNS = (
    "legacy_code",
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "country_code",
    "gender",
    "joining_date",
    "BASE",
)
# The old code headers, read as legacy_code when the sheet has no legacy_code column of its own.
# "employeecode" covers both employee_code and Employee Code (D54).
ALIASES = {
    "employeecode": "legacy_code",
    "employeeid": "legacy_code",
    "empid": "legacy_code",
}
DATE_COLUMNS = ("joining_date", "last_date", "effective_from")
ROW_LIMIT = 10_000
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# A browser sends what the operating system calls the file. Windows with Excel installed calls a
# .csv application/vnd.ms-excel, so that type is accepted for .csv too.
CONTENT_TYPES = {
    ".xlsx": {XLSX_TYPE, "application/octet-stream"},
    ".csv": {
        "text/csv",
        "application/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
}

THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+")  # 1,200 and 1,200,000
LAKHS = re.compile(r"\d{1,2}(?:,\d{2})*,\d{3}")  # 12,00,000
PLAIN_NUMBER = re.compile(r"\d+(?:\.\d*)?|\.\d+")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
WHOLE = re.compile(r"\d+(?:\.0+)?")


def normalize_header(name: Any) -> str:
    """Case-, space-, underscore- and hyphen-insensitive header key."""
    return "".join(ch for ch in str(name).strip().lower() if ch not in " _-")


def template_columns(component_codes: Iterable[str]) -> list[str]:
    return [*IDENTITY_COLUMNS, *component_codes]


# Header


@dataclass
class HeaderResult:
    """Which sheet column feeds which template column, and what is wrong with the header."""

    mapping: dict[int, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    repeated: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return bool(self.missing or self.repeated or self.ambiguous)

    @property
    def warnings(self) -> list[str]:
        return [msg("unknown_column", column=name) for name in self.unknown]

    def errors(self) -> dict[str, list[str]]:
        """The 400 body of a refused upload, every problem with the header at once (SPEC F1)."""
        body = {
            "missing_columns": [msg("missing_column", column=name) for name in self.missing],
            "unknown_columns": self.warnings,
        }
        if self.repeated:
            body["repeated_columns"] = [msg("column_twice", column=name) for name in self.repeated]
        if self.ambiguous:
            body["ambiguous_columns"] = [ambiguous_message(self.ambiguous)]
        return body


def ambiguous_message(names: Sequence[str]) -> str:
    """ "EmployeeID and Emp ID could both be ..."; three or more "could all be" (D54)."""
    listed = f"{', '.join(names[:-1])} and {names[-1]}"
    return msg("legacy_ambiguous", columns=listed, quantity="both" if len(names) == 2 else "all")


def check_header(header: Sequence[Any], component_codes: Iterable[str]) -> HeaderResult:
    """Map the sheet's header onto the template (SPEC F1, D48, D54).

    Matching ignores case, spaces, underscores and hyphens. The old code headers stand in for
    legacy_code only when the sheet has no legacy_code column. Two or more of them leave no way
    to tell which is meant, and neither does a template column given twice, so both refuse the
    upload. A column without a header is left to `read`, which reports it if it holds data.
    """
    targets = {normalize_header(name): name for name in IDENTITY_COLUMNS}
    targets.update({normalize_header(code): code for code in component_codes})
    names = ["" if cell is None else str(cell).strip() for cell in header]
    keys = [normalize_header(name) for name in names]
    has_legacy = normalize_header("legacy_code") in keys
    result = HeaderResult()
    taken: set[str] = set()
    aliases: list[tuple[int, str]] = []
    for index, (name, key) in enumerate(zip(names, keys, strict=True)):
        if not key:
            continue
        column = targets.get(key)
        if column is None and not has_legacy and key in ALIASES:
            aliases.append((index, name))
        elif column is None:
            result.unknown.append(name)
        elif column in taken:
            if column not in result.repeated:
                result.repeated.append(column)
        else:
            taken.add(column)
            result.mapping[index] = column
    if len(aliases) == 1:
        result.mapping[aliases[0][0]] = "legacy_code"
        taken.add("legacy_code")
    elif aliases:
        result.ambiguous = [name for _, name in aliases]
    result.missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in taken and not (column == "legacy_code" and result.ambiguous)
    ]
    return result


# File


@dataclass
class ParsedFile:
    """The header row and the data rows, by their row number in the sheet."""

    header: list[Any]
    rows: list[tuple[int, list[Any]]]
    row_count: int
    # Letters of columns with no header that still hold data: ignored, and said so.
    unnamed: list[str] = field(default_factory=list)


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def check_file_type(file_name: str, content_type: str | None) -> str:
    """The file's extension, once it and the content type agree (SPEC section 8)."""
    extension = PurePath(file_name or "").suffix.lower()
    if extension not in CONTENT_TYPES:
        raise Invalid({"file": [msg("file_extension", name=file_name or "a file with no name")]})
    sent = (content_type or "application/octet-stream").split(";")[0].strip().lower()
    if sent not in CONTENT_TYPES[extension]:
        raise Invalid({"file": [msg("file_content_type", content_type=sent, extension=extension)]})
    return extension


def _binary(upload):
    """The file under a Django upload, or the stream itself in tests."""
    stream = getattr(upload, "file", upload)
    stream.seek(0)
    return stream


def _xlsx_rows(upload) -> Iterator[list[Any]]:
    try:
        workbook = load_workbook(_binary(upload), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise Invalid({"file": [msg("file_unreadable")]}) from exc
    try:
        sheet = workbook.worksheets[0]
        # The dimension the file declares cannot be trusted, so every row is streamed.
        sheet.reset_dimensions()
        for values in sheet.iter_rows(values_only=True):
            yield list(values)
    finally:
        workbook.close()


def _csv_rows(upload) -> Iterator[list[Any]]:
    text = io.TextIOWrapper(_binary(upload), encoding="utf-8-sig", newline="")
    try:
        yield from csv.reader(text)
    except UnicodeDecodeError as exc:
        raise Invalid({"file": [msg("not_utf8")]}) from exc
    finally:
        # Hand the stream back open: Django closes and removes the upload after the request.
        text.detach()


def open_rows(upload, file_name: str, content_type: str | None) -> Iterator[list[Any]]:
    """Every row of the first worksheet, or of the CSV, as a list of cell values."""
    extension = check_file_type(file_name, content_type)
    return _xlsx_rows(upload) if extension == ".xlsx" else _csv_rows(upload)


def read(upload, file_name: str, content_type: str | None) -> ParsedFile:
    """The header and every data row, all-blank rows skipped. Rows are counted while streaming,
    past the limit too, because the sheet's own row count cannot be trusted (SPEC section 8)."""
    rows = open_rows(upload, file_name, content_type)
    header = next(rows, None)
    if header is None or all(is_blank(cell) for cell in header):
        raise Invalid({"file": [msg("file_no_header")]})
    width = len(header)
    headless = {index for index, cell in enumerate(header) if is_blank(cell)}
    kept: list[tuple[int, list[Any]]] = []
    unnamed: set[int] = set()
    count = 0
    for number, cells in enumerate(rows, start=2):
        if all(is_blank(cell) for cell in cells):
            continue
        count += 1
        if count <= ROW_LIMIT:
            kept.append((number, list(cells)))
        for index, cell in enumerate(cells):
            if (index in headless or index >= width) and not is_blank(cell):
                unnamed.add(index)
    if count > ROW_LIMIT:
        raise Invalid({"rows": [msg("row_limit", count=f"{count:,}", limit=f"{ROW_LIMIT:,}")]})
    letters = [get_column_letter(index + 1) for index in sorted(unnamed)]
    return ParsedFile(header=header, rows=kept, row_count=count, unnamed=letters)


# Cells


def parse_number(value: Any, field_name: str) -> Decimal | Message | None:
    """A number cell as Decimal, None when blank, or the message for a value that is not one.

    Currency symbols and spaces are stripped. A comma is a thousands separator only with no dot
    anywhere and in groups that end in three digits (1,200 and 12,00,000); any other comma is the
    decimal-separator error. Decimals are kept as given, so the validators can count them.
    """
    if is_blank(value):
        return None
    invalid = "bonus_invalid" if field_name == "bonus_annual" else "amount_invalid"
    if isinstance(value, bool):
        return error(field_name, invalid, field=field_name, value=str(value).upper())
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return error(field_name, invalid, field=field_name, value=str(value))
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value
    given = str(value).strip()
    cleaned = "".join(ch for ch in given if not ch.isspace() and unicodedata.category(ch) != "Sc")
    sign = ""
    if cleaned[:1] in ("-", "+"):
        sign, cleaned = cleaned[0], cleaned[1:]
    if "," in cleaned:
        if "." in cleaned or not (THOUSANDS.fullmatch(cleaned) or LAKHS.fullmatch(cleaned)):
            return error(field_name, "comma_decimal", value=given)
        cleaned = cleaned.replace(",", "")
    if not PLAIN_NUMBER.fullmatch(cleaned):
        return error(field_name, invalid, field=field_name, value=given)
    return Decimal(f"{sign}{cleaned}")


def parse_date(value: Any, field_name: str) -> date | Message | None:
    """A date cell, or ISO `YYYY-MM-DD` text; openpyxl gives date cells as datetime."""
    if is_blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    given = str(value).strip()
    if ISO_DATE.fullmatch(given):
        try:
            return date.fromisoformat(given)
        except ValueError:
            pass
    return error(field_name, "date_invalid", field=field_name, value=given)


def parse_code(value: Any) -> str | None:
    """legacy_code: trimmed text, and a numeric cell as its integer text (58213.0 is 58213)."""
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse_level(value: Any) -> int | None:
    """A whole number, else None, which the level rule reports."""
    if is_blank(value) or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    given = str(value).strip()
    return int(float(given)) if WHOLE.fullmatch(given) else None


def parse_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize(row_number: int, cells: Sequence[Any], mapping: Mapping[int, str]) -> NormalizedRow:
    """One data row as the validators read it (DESIGN 1.5). Parse problems ride along as
    messages, which the structure rules report with the rest."""
    values = {
        column: cells[index] if index < len(cells) else None for index, column in mapping.items()
    }
    problems: list[Message] = []

    def kept(parsed):
        if isinstance(parsed, Message):
            problems.append(parsed)
            return None
        return parsed

    dates = {name: kept(parse_date(values.get(name), name)) for name in DATE_COLUMNS}
    amounts = {
        column: kept(parse_number(value, column))
        for column, value in values.items()
        if column not in IDENTITY_COLUMNS
    }
    email = parse_text(values.get("email"))
    country = parse_text(values.get("country_code"))
    gender = parse_text(values.get("gender"))
    return NormalizedRow(
        row_number=row_number,
        legacy_code=parse_code(values.get("legacy_code")),
        full_name=parse_text(values.get("full_name")),
        email=email.lower() if email else None,
        department=parse_text(values.get("department")),
        designation=parse_text(values.get("designation")),
        level=parse_level(values.get("level")),
        country_code=country.upper() if country else None,
        gender=gender.lower() if gender else None,
        joining_date=dates["joining_date"],
        last_date=dates["last_date"],
        effective_from=dates["effective_from"],
        bonus_annual=kept(parse_number(values.get("bonus_annual"), "bonus_annual")),
        amounts=amounts,
        columns=frozenset(values),
        present=frozenset(column for column, value in values.items() if not is_blank(value)),
        parse_messages=problems,
    )
