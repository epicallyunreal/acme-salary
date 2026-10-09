"""Reading a sheet: the header, the file and the cells (SPEC F1, section 7, D48, D53, D54)."""

import csv
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook

from apps.compensation.validators import (
    IDENTITY_COLUMNS,
    Message,
    build_context,
    check_header,
    validate_row,
)
from apps.core.exceptions import Invalid
from apps.imports import parser
from apps.imports.parser import (
    normalize,
    parse_date,
    parse_level,
    parse_number,
    preflight_xlsx,
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


SHEET = "xl/worksheets/sheet1.xml"
XLSX_UNREADABLE = "file is not a readable .xlsx workbook; save it again from Excel and upload it"
UNREADABLE = {"file": [XLSX_UNREADABLE]}
WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"
RELATIONSHIPS = b"http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def repacked(upload: io.BytesIO, name: str, change) -> io.BytesIO:
    """The workbook with its part `name` passed through `change`, or added when it is new."""
    result = io.BytesIO()
    with (
        zipfile.ZipFile(upload) as source,
        zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as target,
    ):
        for item in source.infolist():
            data = source.read(item.filename)
            target.writestr(item, change(data) if item.filename == name else data)
        if name not in source.namelist():
            target.writestr(name, change(b""))
    return result


def with_rows(rows: bytes) -> io.BytesIO:
    """A one-row workbook with raw `<row>` XML added to the end of its sheet."""
    return repacked(
        xlsx(HEADER, asha()),
        SHEET,
        lambda data: data.replace(b"</sheetData>", rows + b"</sheetData>"),
    )


@pytest.fixture
def no_openpyxl(monkeypatch):
    """Fails the test if openpyxl opens the file: the pre-scan has to refuse it first."""

    def opened(*args, **kwargs):
        pytest.fail("openpyxl opened a file the pre-scan should have refused")

    monkeypatch.setattr(parser, "open_workbook", opened)


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


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("3", 3), (3, 3), (3.0, 3), ("3.0", 3), ("9" * 5000, None), (10**6, None), (1e300, None)],
)
def test_parse_level_reads_a_whole_number_and_drops_one_no_level_could_be(cell, expected):
    """A level past 999,999 is reported like any other out-of-range level, and is never kept as
    an int of thousands of digits, which Python will not write back as text."""
    assert parse_level(cell) == expected


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
        ({"designation": None}, {"designation": ["designation is required"]}),
        ({"email": "   "}, {"email": ["email is required"]}),
        ({"level": "9" * 5000}, {"level": ["level must be between 1 and 6"]}),
        ({"full_name": "n" * 10_000}, {"full_name": ["full_name is longer than 120 characters"]}),
        (
            {"BASE": "x" * 1000},
            {"BASE": [f"BASE must be a non-negative number, got {'x' * 63}\u2026"]},
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
    "content_type",
    ["application/vnd.ms-excel", "text/csv; charset=utf-8", "application/csv", "text/plain", None],
)
def test_a_csv_is_taken_under_the_types_browsers_send(content_type):
    assert read(csv_file(HEADER, asha()), "a.csv", content_type).row_count == 1


@pytest.mark.parametrize(
    ("upload", "name", "message"),
    [
        (io.BytesIO(b"not a zip at all"), "a.xlsx", XLSX_UNREADABLE),
        (io.BytesIO(b""), "a.csv", "file has no header row"),
        (csv_file(["", ""], ["x", "y"]), "a.csv", "file has no header row"),
    ],
)
def test_an_unreadable_or_headerless_file_is_refused(upload, name, message):
    with pytest.raises(Invalid) as excinfo:
        read(upload, name, None)

    assert excinfo.value.errors == {"file": [message]}


def test_more_than_fifteen_thousand_data_rows_are_refused_with_the_true_count():
    """Counting goes on past the limit, so the message gives the real size (SPEC section 8).
    15,000 holds the whole seeded organisation (D64)."""
    rows = [asha(legacy_code=f"HR-{n}") for n in range(15_450)]

    with pytest.raises(Invalid) as excinfo:
        read(csv_file(HEADER, *rows), "big.csv", "text/csv")

    assert excinfo.value.errors == {"rows": ["file has 15,450 data rows, limit 15,000"]}
    with pytest.raises(Invalid) as just_over:
        read(csv_file(HEADER, *rows[:15_001]), "over.csv", "text/csv")
    assert just_over.value.errors == {"rows": ["file has 15,001 data rows, limit 15,000"]}
    assert read(csv_file(HEADER, *rows[:15_000]), "ok.csv", "text/csv").row_count == 15_000


def test_data_under_no_header_is_named_by_its_column_letter():
    header = [*HEADER, None]
    upload = xlsx(header, [*asha(), None], [*asha(legacy_code="HR-2"), "see manager", "x"])

    parsed = read(upload, "a.xlsx", None)

    assert parsed.unnamed == ["R", "S"]


def test_an_xlsx_that_declares_too_small_a_dimension_is_still_read_in_full():
    """The <dimension> a file declares cannot be trusted; every row and column is streamed."""
    forged = repacked(
        xlsx(HEADER, asha(), asha(legacy_code="HR-2"), asha(legacy_code="HR-3")),
        SHEET,
        lambda data: re.sub(rb'<dimension ref="[^"]+"/>', b'<dimension ref="A1:A2"/>', data),
    )

    parsed = read(forged, "forged.xlsx", None)

    assert parsed.row_count == 3
    assert parsed.header == HEADER


@pytest.mark.parametrize(
    ("part", "change"),
    [
        (SHEET, lambda data: data[: len(data) // 2]),
        (
            SHEET,
            lambda data: data.replace(
                b"</sheetData>", b'<row r="3"><c r="A3" t="s"><v>999</v></c></row></sheetData>'
            ),
        ),
        ("xl/workbook.xml", lambda data: data[: len(data) // 2]),
        ("xl/workbook.xml", lambda data: re.sub(rb"<sheets>.*</sheets>", b"<sheets/>", data)),
    ],
    ids=["sheet cut short", "shared string out of range", "workbook cut short", "no worksheet"],
)
def test_whatever_openpyxl_raises_on_a_crafted_file_is_a_400_not_a_crash(part, change):
    with pytest.raises(Invalid) as excinfo:
        read(repacked(xlsx(HEADER, asha()), part, change), "crafted.xlsx", None)

    assert excinfo.value.errors == UNREADABLE


def test_a_csv_cell_past_the_field_limit_is_a_400_not_a_crash():
    upload = csv_file(HEADER, asha(full_name="x" * 131_073))

    with pytest.raises(Invalid) as excinfo:
        read(upload, "a.csv", "text/csv")

    assert excinfo.value.errors == {
        "file": ["file is not a readable .csv; save it again from Excel and upload it"]
    }


def test_a_csv_row_or_header_wider_than_200_cells_is_refused():
    extra = 201 - len(HEADER)

    with pytest.raises(Invalid) as row:
        read(csv_file(HEADER, asha(), [*asha(), *["x"] * extra]), "wide.csv", "text/csv")
    with pytest.raises(Invalid) as header:
        read(csv_file([*HEADER, *["note"] * extra]), "wide.csv", "text/csv")

    assert row.value.errors == {"file": ["row 3 has more than 200 cells"]}
    assert header.value.errors == {"file": ["row 1 has more than 200 cells"]}


# What a workbook may cost before openpyxl opens it (D56)


def test_an_xlsx_that_unpacks_past_50_mb_is_refused_before_openpyxl_opens_it(no_openpyxl):
    upload = xlsx(HEADER, asha())
    with (
        zipfile.ZipFile(upload, "a", zipfile.ZIP_DEFLATED) as archive,
        archive.open("xl/media/padding.bin", "w") as part,
    ):
        for _ in range(51):
            part.write(bytes(1024 * 1024))

    with pytest.raises(Invalid) as excinfo:
        read(upload, "padded.xlsx", None)

    assert excinfo.value.errors == {"file": ["file unpacks to more than 50 MB"]}


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (b'<row r="1048577"><c><v>1</v></c></row>', "row 1,048,577 is past row 1,048,576"),
        (
            b'<row r="999999999999999999"><c><v>1</v></c></row>',
            "row 999,999,999,999,999,999 is past row 1,048,576",
        ),
        (b'<row r="3"><c r="GS3"><v>1</v></c></row>', "row 3 has more than 200 cells"),
        (b'<row r="3">' + b"<c/>" * 201 + b"</row>", "row 3 has more than 200 cells"),
        (b"<row>" + b"<c/>" * 201 + b"</row>", "row 3 has more than 200 cells"),
        (b'<row r="1048577.0"><c><v>1</v></c></row>', "row 1,048,577 is past row 1,048,576"),
    ],
    ids=[
        "past the last row",
        "far past it",
        "a cell at column 201",
        "201 cells",
        "no numbers",
        "a whole float",
    ],
)
def test_a_row_past_excels_last_or_wider_than_200_cells_is_refused(no_openpyxl, rows, message):
    """openpyxl builds every filler row up to a row's number, and every cell up to a row's last
    one, so a single cell at column ZZZ costs 18,278 of them."""
    with pytest.raises(Invalid) as excinfo:
        read(with_rows(rows), "wide.xlsx", None)

    assert excinfo.value.errors == {"file": [message]}


def test_the_pre_scan_lets_excels_last_row_and_column_200_through():
    assert (
        preflight_xlsx(with_rows(b'<row r="1048576"><c r="GR1048576"><v>1</v></c></row>')) is None
    )
    assert preflight_xlsx(with_rows(b'<row r="3">' + b"<c/>" * 200 + b"</row>")) is None


def test_every_part_of_the_zip_is_scanned_whatever_its_name(no_openpyxl):
    """openpyxl opens every worksheet at load, and a sheet can live under any name."""
    far = b'<worksheet><sheetData><row r="2000000"/></sheetData></worksheet>'
    upload = repacked(xlsx(HEADER, asha()), "xl/hidden/notes.bin", lambda _: far)

    with pytest.raises(Invalid) as excinfo:
        read(upload, "hidden.xlsx", None)

    assert excinfo.value.errors == {"file": ["row 2,000,000 is past row 1,048,576"]}


def test_the_element_budget_is_for_the_whole_file(monkeypatch, no_openpyxl):
    """openpyxl builds styles.xml, among others, as one tree: 12 million empty elements, 50 KB
    zipped, took it past 1.2 GB. The budget is 2,000,000 for the file as a whole, against about
    560,000 in a full 15,000-row template, so parts each under it are not enough."""
    assert parser.MAX_ELEMENTS == 2_000_000
    monkeypatch.setattr(parser, "MAX_ELEMENTS", 1_000)
    part = b"<notes>" + b"<x/>" * 400 + b"</notes>"
    upload = repacked(xlsx(HEADER, asha()), "xl/extra/one.xml", lambda _: part)
    upload = repacked(upload, "xl/extra/two.xml", lambda _: part)

    with pytest.raises(Invalid) as excinfo:
        read(upload, "dense.xlsx", None)

    assert excinfo.value.errors == {"file": ["file is too big to read"]}


def test_elements_openpyxl_builds_into_objects_have_a_budget_of_their_own(monkeypatch, no_openpyxl):
    """Style formats, merged ranges and defined names become objects of up to 680 bytes each:
    1.9 million style formats in an 18 KB file took openpyxl to 1,223 MB (D56)."""
    assert parser.MAX_OBJECT_ELEMENTS == 300_000
    monkeypatch.setattr(parser, "MAX_OBJECT_ELEMENTS", 1_000)
    formats = b"<styleSheet><cellXfs>" + b"<xf/>" * 1_000 + b"</cellXfs></styleSheet>"
    upload = repacked(xlsx(HEADER, asha()), "xl/styles.xml", lambda _: formats)

    with pytest.raises(Invalid) as excinfo:
        read(upload, "styled.xlsx", None)

    assert excinfo.value.errors == {"file": ["file is too big to read"]}


def test_cells_and_shared_strings_do_not_count_against_the_object_budget(monkeypatch):
    """openpyxl streams them, row by row and string by string."""
    monkeypatch.setattr(parser, "MAX_OBJECT_ELEMENTS", 1_000)
    rows = [asha(legacy_code=f"HR-{n}") for n in range(100)]

    assert read(xlsx(HEADER, *rows), "cells.xlsx", None).row_count == 100


def test_a_part_that_is_not_xml_is_passed_over():
    """Images and printer settings are binary. The scan reads past them, and openpyxl never
    parses them."""
    image = b"\x89PNG\r\n\x1a\n" + bytes(64)
    upload = repacked(xlsx(HEADER, asha()), "xl/media/image1.png", lambda _: image)

    assert read(upload, "pictured.xlsx", None).row_count == 1


def test_only_the_first_worksheet_is_opened():
    """openpyxl sized every sheet a workbook lists, once per entry, so entries naming one large
    part read it as many times (D57). A second sheet is never opened now, a broken one included."""
    upload = repacked(
        xlsx(HEADER, asha()),
        "xl/workbook.xml",
        lambda data: data.replace(
            b"</sheets>", b'<sheet name="Notes" sheetId="2" r:id="rId90"/></sheets>'
        ),
    )
    upload = repacked(
        upload,
        WORKBOOK_RELS,
        lambda data: data.replace(
            b"</Relationships>",
            b'<Relationship Id="rId90" Type="' + RELATIONSHIPS + b'/worksheet" '
            b'Target="worksheets/notes.xml"/></Relationships>',
        ),
    )
    upload = repacked(upload, "xl/worksheets/notes.xml", lambda _: b"<worksheet><sheetData><row>")

    assert read(upload, "two-sheets.xlsx", None).row_count == 1


def test_an_external_link_is_never_followed():
    """openpyxl read a linked part once per reference to it, so 40 references to one part took
    it past 1 GB (D57). A link is never opened now, a broken one included."""
    upload = repacked(
        xlsx(HEADER, asha()),
        "xl/workbook.xml",
        lambda data: data.replace(
            b"</sheets>",
            b'</sheets><externalReferences><externalReference r:id="rId91"/></externalReferences>',
        ),
    )
    upload = repacked(
        upload,
        WORKBOOK_RELS,
        lambda data: data.replace(
            b"</Relationships>",
            b'<Relationship Id="rId91" Type="' + RELATIONSHIPS + b'/externalLink" '
            b'Target="externalLinks/externalLink1.xml"/></Relationships>',
        ),
    )
    upload = repacked(upload, "xl/externalLinks/externalLink1.xml", lambda _: b"<externalLink><x")

    assert read(upload, "linked.xlsx", None).row_count == 1


def test_an_entity_declaration_is_refused_as_unreadable(no_openpyxl):
    """No entity is ever expanded, as defusedxml would refuse it too."""
    laughs = b'<!DOCTYPE d [<!ENTITY a "aaaaaaaaaa">]><d>&a;</d>'
    upload = repacked(xlsx(HEADER, asha()), "xl/extra.xml", lambda _: laughs)

    with pytest.raises(Invalid) as excinfo:
        read(upload, "laughs.xlsx", None)

    assert excinfo.value.errors == UNREADABLE


def archive_of(parts: int) -> io.BytesIO:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for n in range(parts):
            archive.writestr(f"xl/part{n}.xml", "<x/>")
    stream.seek(0)
    return stream


def test_a_workbook_with_too_many_parts_is_refused_before_any_is_read():
    """D73: a thousand parts is far past any workbook; the archive itself would be the cost.
    Exactly a thousand still passes the count."""
    assert preflight_xlsx(archive_of(parser.MAX_ZIP_PARTS)) is None

    with pytest.raises(Invalid) as refused:
        preflight_xlsx(archive_of(parser.MAX_ZIP_PARTS + 1))

    assert refused.value.errors == {"file": ["file holds more than 1,000 parts"]}
