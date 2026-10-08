"""The timing command's crafted sheet and period cases (D68, D70)."""

import io
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.management.commands import timing
from apps.core.management.commands.timing import crafted_sheet, period_cases
from apps.imports import parser
from apps.imports.models import ImportBatch, ImportRow
from tests.imports.sheets import HEADER


def test_the_crafted_sheet_reads_back_as_one_cut_string_in_every_cell():
    data = crafted_sheet(3, HEADER, 300)
    upload = SimpleUploadedFile("crafted.xlsx", data, content_type=parser.XLSX_TYPE)

    parsed = parser.read(upload, upload.name, upload.content_type)

    cells = [cell for _, row in parsed.rows for cell in row]
    assert list(parsed.header) == HEADER
    assert len(cells) == 3 * len(HEADER)
    assert all(cell is cells[0] for cell in cells)
    assert cells[0] == "x" * 255 + "\u2026"


def test_the_period_cases_are_the_dashboards_presets_and_the_cut_off():
    assert period_cases(date(2026, 10, 7)) == {
        "last 3 months": "from=2026-07-08",
        "last 6 months": "from=2026-04-08",
        "FY to date": "from=2026-04-01",
        "last FY": "from=2025-04-01&to=2026-03-31",
        "since the cut-off": "from=2020-04-01",
    }


def test_the_crafted_case_stages_through_the_api_and_leaves_nothing_behind(
    lookups, api, monkeypatch
):
    """It stages inside a transaction it rolls back, so the live tables keep no batch (D68). The
    HR Manager's client stands in for the command's login."""
    monkeypatch.setattr(timing, "api_client", lambda: api)
    monkeypatch.setattr(parser, "ROW_LIMIT", 4)
    out = io.StringIO()

    timing.Command(stdout=out).time_crafted()

    assert "staging 4 rows (4 error)" in out.getvalue()
    assert (ImportBatch.objects.count(), ImportRow.objects.count()) == (0, 0)
