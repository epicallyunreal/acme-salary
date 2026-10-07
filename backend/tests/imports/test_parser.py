"""Reading a sheet: the header, the file and the cells (SPEC F1, section 7, D48, D53, D54)."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook

from apps.compensation.validators import Message, build_context, validate_row
from apps.core.exceptions import Invalid
from apps.imports.parser import (
    IDENTITY_COLUMNS,
    check_header,
    normalize,
    parse_date,
    parse_number,
    read,
)

INDIA = ["BASE", "HRA", "ALLOWANCES", "TAX", "EMPLOYER_CONTRIBUTION"]
EVERY_COMPONENT = [
    "BASE",
    "AWS",
    "HOLIDAY_ALLOWANCE",
    "HRA",
    "ALLOWANCES",
    "TAX",
    "CPF",
    "NATIONAL_INSURANCE",
    "SOCIAL_INSURANCE",
    "EMPLOYER_CONTRIBUTION",
]
HEADER = [*IDENTITY_COLUMNS, *INDIA]


def asha(**cells) -> list:
    values = {
        "legacy_code": "HR-10001",
        "full_name": "Asha Rao",
        "email": "Asha.Rao@acme.example",
        "department": "engineering",
        "designation": "Senior Engineer",
        "level": 3,
        "country_code": "IN",
        "gender": "female",
        "joining_date": datetime(2024, 3, 1),
        "last_date": None,
        "effective_from": None,
        "bonus_annual": None,
        "BASE": 1450000,
        "HRA": 580000,
        "ALLOWANCES": 362500,
        "TAX": 478500,
        "EMPLOYER_CONTRIBUTION": 174000,
    }
    values.update(cells)
    return [values[column] for column in HEADER]


def xlsx(*rows) -> io.BytesIO:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    stream = io.BytesIO()
    workbook.save(stream)
    return stream


def csv_file(*rows, prefix: bytes = b"", encoding: str = "utf-8") -> io.BytesIO:
    text = io.StringIO()
    csv.writer(text).writerows(rows)
    return io.BytesIO(prefix + text.getvalue().encode(encoding))


def message_of(parsed) -> str:
    assert isinstance(parsed, Message), parsed
    return parsed.message


# Header


def test_the_template_header_maps_every_column_in_place():
    result = check_header(HEADER, EVERY_COMPONENT)

    assert result.mapping == dict(enumerate(HEADER))
    assert (result.missing, result.unknown, result.rejected) == ([], [], False)


def test_headers_match_whatever_the_case_spaces_underscores_or_hyphens():
    header = ["Legacy Code", "FULL_NAME", "E-mail", "department", "Designation", "LEVEL"]
    header += ["Country Code", "gender", "joining date", "base"]

    result = check_header(header, EVERY_COMPONENT)

    assert list(result.mapping.values()) == [
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
    ]
    assert result.rejected is False


def test_a_missing_required_column_refuses_and_an_unknown_one_is_a_warning():
    header = [column for column in HEADER if column != "country_code"] + ["Remarks"]

    result = check_header(header, EVERY_COMPONENT)

    assert result.rejected is True
    assert result.errors() == {
        "missing_columns": ["Missing required column: country_code"],
        "unknown_columns": ["Ignored unknown column: Remarks"],
    }


@pytest.mark.parametrize("alias", ["EmployeeID", "Employee Code", "Emp ID", "employee_code"])
def test_one_old_code_header_stands_in_for_legacy_code(alias):
    result = check_header([alias, *HEADER[1:]], EVERY_COMPONENT)

    assert result.mapping[0] == "legacy_code"
    assert result.rejected is False


def test_with_a_legacy_code_column_the_old_code_headers_are_ignored_with_a_warning():
    result = check_header([*HEADER, "EmployeeID", "Emp ID"], EVERY_COMPONENT)

    assert result.mapping[0] == "legacy_code"
    assert result.warnings == [
        "Ignored unknown column: EmployeeID",
        "Ignored unknown column: Emp ID",
    ]
    assert result.rejected is False


@pytest.mark.parametrize(
    ("aliases", "message"),
    [
        (
            ["EmployeeID", "Emp ID"],
            "EmployeeID and Emp ID could both be the legacy code; "
            "rename the right one to legacy_code",
        ),
        (
            ["employee_code", "Employee Code"],
            "employee_code and Employee Code could both be the legacy code; "
            "rename the right one to legacy_code",
        ),
        (
            ["EmployeeID", "Employee Code", "Emp ID"],
            "EmployeeID, Employee Code and Emp ID could all be the legacy code; "
            "rename the right one to legacy_code",
        ),
    ],
)
def test_two_or_more_old_code_headers_and_no_legacy_code_refuse_the_upload(aliases, message):
    """D54: nothing says which column is meant, so none is guessed."""
    result = check_header([*aliases, *HEADER[1:]], EVERY_COMPONENT)

    assert result.rejected is True
    assert result.errors() == {
        "missing_columns": [],
        "unknown_columns": [],
        "ambiguous_columns": [message],
    }


@pytest.mark.parametrize(("twice", "column"), [("email", "email"), ("base", "BASE")])
def test_a_template_column_given_twice_refuses_the_upload(twice, column):
    """D54: two columns for one field leave no way to tell which value is meant."""
    result = check_header([*HEADER, twice], EVERY_COMPONENT)

    assert result.rejected is True
    assert result.errors()["repeated_columns"] == [
        f"{column} appears twice in the header; remove one"
    ]


# Cells


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1,200", Decimal("1200")),
        ("12,00,000", Decimal("1200000")),
        ("1,200,000", Decimal("1200000")),
        ("₹ 1,45,000", Decimal("145000")),
        ("$1,200", Decimal("1200")),
        (" 1450000.50 ", Decimal("1450000.50")),
        ("-5000", Decimal("-5000")),
        ("1.234", Decimal("1.234")),
        (1450000, Decimal("1450000")),
        (1450000.5, Decimal("1450000.5")),
        ("", None),
        (None, None),
    ],
)
def test_parse_number_reads_thousands_symbols_and_numeric_cells(cell, expected):
    """SPEC F1: a comma before exactly three digits with no dot is a thousands separator.
    Decimals are kept as given, so the validators can count them."""
    assert parse_number(cell, "BASE") == expected


@pytest.mark.parametrize(
    ("cell", "field_name", "message"),
    [
        ("1.200.000,50", "BASE", "use a dot as the decimal separator, got 1.200.000,50"),
        ("1,5", "BASE", "use a dot as the decimal separator, got 1,5"),
        ("1,200.50", "BASE", "use a dot as the decimal separator, got 1,200.50"),
        ("abc", "HRA", "HRA must be a non-negative number, got abc"),
        ("1e5", "BASE", "BASE must be a non-negative number, got 1e5"),
        (True, "BASE", "BASE must be a non-negative number, got TRUE"),
        ("abc", "bonus_annual", "bonus_annual must be a non-negative number, got abc"),
    ],
)
def test_parse_number_names_the_field_and_the_value_it_cannot_read(cell, field_name, message):
    parsed = parse_number(cell, field_name)

    assert (parsed.field, parsed.severity, message_of(parsed)) == (field_name, "error", message)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        (datetime(2024, 3, 1, 0, 0), date(2024, 3, 1)),
        (date(2024, 3, 1), date(2024, 3, 1)),
        (" 2024-03-01 ", date(2024, 3, 1)),
        ("", None),
    ],
)
def test_parse_date_reads_date_cells_and_iso_text(cell, expected):
    assert parse_date(cell, "joining_date") == expected


@pytest.mark.parametrize("cell", ["31/02/2024", "2024-02-31", "1 March 2024", 45352])
def test_parse_date_refuses_anything_else_with_the_value(cell):
    assert message_of(parse_date(cell, "joining_date")) == (
        f"joining_date is not a valid date: {cell}"
    )


def test_normalize_reads_a_template_row():
    cells = asha(
        legacy_code=58213.0,
        email="  Asha.Rao@ACME.example ",
        country_code="in",
        gender="Female",
        level=3.0,
        HRA=None,
        bonus_annual="",
    )

    row = normalize(7, cells, dict(enumerate(HEADER)))

    assert (row.row_number, row.legacy_code, row.email, row.country_code, row.gender) == (
        7,
        "58213",
        "asha.rao@acme.example",
        "IN",
        "female",
    )
    assert (row.level, row.joining_date, row.last_date, row.bonus_annual) == (
        3,
        date(2024, 3, 1),
        None,
        None,
    )
    assert row.amounts == {
        "BASE": Decimal("1450000"),
        "HRA": None,
        "ALLOWANCES": Decimal("362500"),
        "TAX": Decimal("478500"),
        "EMPLOYER_CONTRIBUTION": Decimal("174000"),
    }
    assert row.columns == frozenset(HEADER)
    assert row.present == frozenset(HEADER) - {"last_date", "effective_from", "bonus_annual", "HRA"}
    assert row.parse_messages == []


@pytest.mark.parametrize(
    ("cells", "messages"),
    [
        ({"BASE": -5000}, {"BASE": ["BASE must be a non-negative number, got -5000"]}),
        ({"BASE": "abc"}, {"BASE": ["BASE must be a non-negative number, got abc"]}),
        (
            {"BASE": "1.200.000,50"},
            {"BASE": ["use a dot as the decimal separator, got 1.200.000,50"]},
        ),
        (
            {"joining_date": "31/02/2024"},
            {"joining_date": ["joining_date is not a valid date: 31/02/2024"]},
        ),
        (
            {"last_date": datetime(9999, 12, 31)},
            {"last_date": ["last_date must be on or before 2100-12-31, got 9999-12-31"]},
        ),
    ],
)
def test_a_cell_problem_reaches_the_row_as_one_message_on_its_field(lookups, cells, messages):
    """SPEC F1 acceptance: BASE = -5000 is an error naming the field and the value. A cell that
    is not a number is reported once, not again as a missing BASE."""
    row = normalize(2, asha(**cells), dict(enumerate(HEADER)))

    found = validate_row(row, build_context(rows=[row]))

    errors: dict[str, list[str]] = {}
    for message in found:
        if message.severity == "error":
            errors.setdefault(message.field, []).append(message.message)
    assert errors == messages


# Files


def test_read_streams_an_xlsx_skipping_blank_rows_and_keeping_sheet_row_numbers():
    upload = xlsx(HEADER, asha(), [None] * len(HEADER), asha(legacy_code="HR-10002"))

    parsed = read(upload, "october.xlsx", "application/octet-stream")

    assert parsed.header == HEADER
    assert [number for number, _ in parsed.rows] == [2, 4]
    assert parsed.row_count == 2
    assert parsed.rows[0][1][8] == datetime(2024, 3, 1)
    assert parsed.unnamed == []


def test_read_takes_a_utf8_csv_with_or_without_a_byte_order_mark():
    plain = read(csv_file(HEADER, asha()), "a.csv", "text/csv")
    with_bom = read(csv_file(HEADER, asha(), prefix=b"\xef\xbb\xbf"), "a.csv", "text/csv")

    assert plain.header == with_bom.header == HEADER
    assert with_bom.rows[0][1][1] == "Asha Rao"


def test_a_csv_that_is_not_utf8_is_refused():
    upload = csv_file(HEADER, asha(full_name="Andrés Núñez"), encoding="latin-1")

    with pytest.raises(Invalid) as excinfo:
        read(upload, "a.csv", "text/csv")

    assert excinfo.value.errors == {"file": ["file is not UTF-8"]}


@pytest.mark.parametrize(
    ("name", "content_type", "message"),
    [
        ("salaries.txt", "text/plain", "file must end in .xlsx or .csv, got salaries.txt"),
        ("salaries.xlsx", "text/csv", "file content type text/csv does not match .xlsx"),
        (
            "salaries.csv",
            "application/pdf",
            "file content type application/pdf does not match .csv",
        ),
    ],
)
def test_the_extension_and_the_content_type_must_agree(name, content_type, message):
    with pytest.raises(Invalid) as excinfo:
        read(csv_file(HEADER), name, content_type)

    assert excinfo.value.errors == {"file": [message]}


@pytest.mark.parametrize(
    "content_type", ["application/vnd.ms-excel", "text/csv; charset=utf-8", None]
)
def test_a_csv_is_taken_under_the_types_browsers_send(content_type):
    assert read(csv_file(HEADER, asha()), "a.csv", content_type).row_count == 1


@pytest.mark.parametrize(
    ("upload", "name", "message"),
    [
        (io.BytesIO(b"not a zip at all"), "a.xlsx", "file is not a readable .xlsx workbook"),
        (io.BytesIO(b""), "a.csv", "file has no header row"),
        (csv_file(["", ""], ["x", "y"]), "a.csv", "file has no header row"),
    ],
)
def test_an_unreadable_or_headerless_file_is_refused(upload, name, message):
    with pytest.raises(Invalid) as excinfo:
        read(upload, name, None)

    assert excinfo.value.errors == {"file": [message]}


def test_more_than_ten_thousand_data_rows_are_refused_with_the_true_count():
    rows = [asha(legacy_code=f"HR-{n}") for n in range(10_001)]

    with pytest.raises(Invalid) as excinfo:
        read(csv_file(HEADER, *rows), "big.csv", "text/csv")

    assert excinfo.value.errors == {"rows": ["file has 10,001 data rows, limit 10,000"]}
    assert read(csv_file(HEADER, *rows[:10_000]), "ok.csv", "text/csv").row_count == 10_000


def test_data_under_no_header_is_named_by_its_column_letter():
    header = [*HEADER, None]
    upload = xlsx(header, [*asha(), None], [*asha(legacy_code="HR-2"), "see manager", "x"])

    parsed = read(upload, "a.xlsx", None)

    assert parsed.unnamed == ["R", "S"]
