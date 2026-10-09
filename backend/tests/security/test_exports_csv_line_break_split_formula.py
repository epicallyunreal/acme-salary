"""Lead exports_csv_line_break_split_formula, raised by the security reviewer at the step 13 close.

Claim: text an import puts into Legacy code, Full name or Designation may hold a line break, and a
reader that ignores quotes starts a record at each line break, so text after it that starts like a
formula would begin a cell of its own, as text after a semicolon did before D76.

The reader is modelled as splitting the file on every line break, quotes or not, then each line on
';' with Python's csv module, honouring a double quote only at the start of a cell. A failure means
that reader finds a cell starting like a formula in the exported file. Line breaks in names stay
allowed (D76), so a refusal at import fails this test rather than passing it.

Fixed on 9 October (D76): the CSV writer puts a single quote after a line break that a formula
start follows, directly or after one double quote, as it does after a semicolon.
"""

import csv

import pytest

from apps.exports.writers import FORMULA_STARTS
from tests.imports.sheets import new_row, upload_of

pytestmark = pytest.mark.django_db

IMPORTS = "/api/v1/imports/"
EMPLOYEES = "/api/v1/exports/employees/"


def cells_split_on_lines_and_semicolons(text: str) -> list[str]:
    """Every cell of the file as a reader that ignores quotes across lines sees it."""
    cells = []
    for line in text.splitlines():
        cells += next(csv.reader([line], delimiter=";"), [])
    return cells


@pytest.mark.parametrize(
    ("column", "planted"),
    [
        ("full_name", "Ann\n=1+1"),
        ("full_name", "Ann\r\n=1+1"),
        ("full_name", "Ann\r=1+1"),
        ("designation", "Engineer\n@SUM(1)"),
        ("full_name", 'Ann\n"=1+1'),
    ],
    ids=["newline", "crlf", "lone_cr", "designation", "after_a_quote"],
)
def test_imported_text_cannot_start_a_formula_cell_when_the_csv_is_split_on_line_breaks(
    api, rates, column, planted
):
    staged = api.post(
        IMPORTS, {"file": upload_of(new_row(**{column: planted}))}, format="multipart"
    )
    if staged.status_code != 201:
        pytest.fail(f"the upload answered {staged.status_code}: {staged.content!r}")
    batch = staged.json()
    if batch["error_rows"]:
        pytest.fail("the row was refused, and line breaks in names are allowed (D76)")
    approved = api.post(f"{IMPORTS}{batch['id']}/approve/")
    if approved.status_code != 200:
        pytest.fail(f"the approve answered {approved.status_code}: {approved.content!r}")

    # The fixture row joins next month, so the export must take every status to hold it.
    response = api.get(EMPLOYEES, {"file": "csv", "status": "any"})
    if response.status_code != 200:
        pytest.fail(f"the CSV export answered {response.status_code}, not 200")
    text = b"".join(response.streaming_content).decode("utf-8-sig")
    if planted.splitlines()[0] not in text:
        pytest.fail("the export does not hold the planted text")

    formulas = [
        c for c in cells_split_on_lines_and_semicolons(text) if c.startswith(FORMULA_STARTS)
    ]
    assert formulas == [], formulas
