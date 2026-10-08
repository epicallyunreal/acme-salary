"""Lead exports_csv_semicolon_split_formula.

Claim: text a spreadsheet author imports into Legacy code, Full name or Designation reaches the
directory CSV as written, and the CSV guards a ';' only by quoting every field (D60, DESIGN 1.7).
A reader that splits each comma-separated line on ';', honouring a double quote only at the start
of a cell, then finds a cell of its own that starts with '='.

The reader is modelled with Python's csv module and delimiter=';', applied to every line, with no
`sep=` hint honoured. A failure (XFAIL while the marker is in place) means that reader finds a
cell starting like a formula in the exported file. A row the import refuses for the planted column
also holds the invariant. Whether Excel, opening the file in a locale whose list separator is ';',
reads the line the same way is the manual check in the lead's validation plan.
"""

import csv
import io

import pytest

from apps.exports.writers import FORMULA_STARTS
from tests.imports.sheets import new_row, upload_of

pytestmark = pytest.mark.django_db

IMPORTS = "/api/v1/imports/"
EMPLOYEES = "/api/v1/exports/employees/"
REASON = (
    "exports_csv_semicolon_split_formula: accepted in docs/reviews/security-audit-2026-10-08.md, "
    "since the writer escapes the standard formula triggers and quotes every field, and the "
    "split needs a reader whose list separator is ';' and that reopens a quote mid-field, a "
    "specific Excel locale. XFAIL means the behaviour is as accepted; XPASS (a strict failure) "
    "means it changed, so revisit the review."
)


def semicolon_cells(text: str) -> list[str]:
    """Every cell of the file as a reader that splits each line on ';' sees it."""
    cells = []
    for line in text.splitlines():
        cells += next(csv.reader([line], delimiter=";"))
    return cells


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=REASON)
@pytest.mark.parametrize(
    ("column", "planted"),
    [
        ("legacy_code", "HR;=1+1;20001"),
        ("full_name", "Ann;=1+1;Rao"),
        ("designation", "Engineer;=1+1;Lead"),
    ],
    ids=["legacy_code", "full_name", "designation"],
)
def test_imported_text_cannot_start_a_formula_cell_when_the_csv_is_split_on_semicolons(
    api, rates, column, planted
):
    upload = upload_of(new_row(**{column: planted}))
    staged = api.post(IMPORTS, {"file": upload}, format="multipart")
    if staged.status_code != 201:
        pytest.fail(f"the upload answered {staged.status_code}: {staged.content!r}")
    batch = staged.json()
    if batch["error_rows"]:
        # Refusing the planted text at import keeps it out of every export too. A refusal for
        # anything else is a setup problem, never the weakness.
        (row,) = api.get(f"{IMPORTS}{batch['id']}/rows/").json()["results"]
        refused = {m["field"] for m in row["messages"] if m["severity"] == "error"}
        if refused != {column}:
            pytest.fail(f"the row was refused for something else: {row['messages']}")
        return
    approved = api.post(f"{IMPORTS}{batch['id']}/approve/")
    if approved.status_code != 200:
        pytest.fail(f"the approve answered {approved.status_code}: {approved.content!r}")

    # The fixture row joins next month, so the export must take every status to hold it.
    response = api.get(EMPLOYEES, {"file": "csv", "status": "any"})
    if response.status_code != 200:
        pytest.fail(f"the CSV export answered {response.status_code}, not 200")
    text = b"".join(response.streaming_content).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    exported = [row for row in rows if row and row[0].startswith("ACME-")]
    if len(exported) != 1:
        pytest.fail(f"the export holds {len(exported)} employees, not the one imported")

    formulas = [cell for cell in semicolon_cells(text) if cell.startswith(FORMULA_STARTS)]
    assert formulas == [], formulas
