"""Lead exports_csv_line_break_split_formula, raised by the security reviewer at the step 13 close.

Claim: text an import puts into Legacy code, Full name or Designation may hold a line break, a
comma or a tab. A reader that ignores quotes starts a record at each line break and is then
outside the quotes for the rest of the value, so its own separator, a comma, a semicolon or a tab,
starts a cell there too, and text after it that starts like a formula would begin a cell of its
own. Pasting into a sheet splits on tabs with no line break at all.

The readers are modelled as splitting the file on every line break, quotes or not, then each line
on ',', ';' or a tab with Python's csv module, honouring a double quote only at the start of a
cell. A failure means one of them finds a cell starting like a formula in the exported file.
Line breaks, commas and tabs in names stay allowed (D76), so a refusal at import, or a stored
value that differs from the planted text, fails this test rather than passing it.

Fixed on 9 October (D76): the CSV writer puts a single quote after a comma, semicolon, tab or line
break that a formula start follows, directly or after one double quote.
"""

import csv
import re

import pytest

from apps.employees.models import Employee
from apps.exports.writers import FORMULA_STARTS
from tests.imports.sheets import new_row, upload_of

pytestmark = pytest.mark.django_db

IMPORTS = "/api/v1/imports/"
EMPLOYEES = "/api/v1/exports/employees/"
LINE_BREAK = re.compile(r"\r\n|\r|\n")


def cells_as_split(text: str, delimiter: str) -> list[str]:
    """Every cell of the file as a reader that ignores quotes across lines, and splits each line
    on `delimiter`, sees it."""
    cells = []
    for line in LINE_BREAK.split(text):
        cells += next(csv.reader([line], delimiter=delimiter), [])
    return cells


@pytest.mark.parametrize(
    ("column", "planted"),
    [
        ("full_name", "Ann\n=1+1"),
        ("full_name", "Ann\r\n=1+1"),
        ("full_name", "Ann\r=1+1"),
        ("designation", "Engineer\n@SUM(1)"),
        ("full_name", 'Ann\n"=1+1'),
        ("full_name", "Ann\nX,=1+1,"),
        ("full_name", "Ann\nX\t=1+1\tx"),
        ("full_name", "Ann\t=1+1\tx"),
    ],
    ids=[
        "newline",
        "crlf",
        "lone_cr",
        "designation",
        "after_a_quote",
        "comma_after_a_break",
        "tab_after_a_break",
        "tab",
    ],
)
@pytest.mark.parametrize("delimiter", [",", ";", "\t"], ids=["comma", "semicolon", "tab"])
def test_imported_text_cannot_start_a_formula_cell_when_the_csv_is_split_without_quotes(
    api, rates, column, planted, delimiter
):
    staged = api.post(
        IMPORTS, {"file": upload_of(new_row(**{column: planted}))}, format="multipart"
    )
    if staged.status_code != 201:
        pytest.fail(f"the upload answered {staged.status_code}: {staged.content!r}")
    batch = staged.json()
    if batch["error_rows"]:
        pytest.fail("the row was refused, and line breaks, commas and tabs are allowed (D76)")
    approved = api.post(f"{IMPORTS}{batch['id']}/approve/")
    if approved.status_code != 200:
        pytest.fail(f"the approve answered {approved.status_code}: {approved.content!r}")
    if getattr(Employee.objects.get(), column) != planted:
        pytest.fail("the import changed the planted text, so the export would not carry it")

    # The fixture row joins next month, so the export must take every status to hold it.
    response = api.get(EMPLOYEES, {"file": "csv", "status": "any"})
    if response.status_code != 200:
        pytest.fail(f"the CSV export answered {response.status_code}, not 200")
    text = b"".join(response.streaming_content).decode("utf-8-sig")

    formulas = [c for c in cells_as_split(text, delimiter) if c.startswith(FORMULA_STARTS)]
    assert formulas == [], formulas
