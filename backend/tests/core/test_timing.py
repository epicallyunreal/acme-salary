"""The timing command's crafted sheet and period cases (D68, D70)."""

import io
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.compensation.validators import template_columns
from apps.core.management.commands import timing
from apps.core.management.commands.timing import crafted_sheet, period_cases, run_base_import
from apps.employees.models import Employee
from apps.imports import parser
from apps.imports.management.commands.make_import_file import base_rows, profile_codes, write_file
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


def test_the_base_import_case_builds_an_empty_database_through_the_api(
    db, settings, hr_user, monkeypatch, tmp_path
):
    """At small scale (D72): the lookups, the rates and the HR Manager are made, the file staged
    and approved through the API, not rolled back, and both times printed."""
    settings.SEED_ADMIN_PASSWORD = "Timing-Test-Pw-5512"
    hr_user.set_password(settings.SEED_ADMIN_PASSWORD)
    hr_user.save()
    monkeypatch.setattr(timing, "api_client", lambda: api_for(hr_user))
    path = tmp_path / "base-30.xlsx"
    write_file(path, template_columns(profile_codes()), base_rows(20, 10, 42))
    out = io.StringIO()

    run_base_import(path, out)

    assert Employee.objects.count() == 30
    assert Employee.objects.exclude(last_date=None).count() == 10
    assert ImportBatch.objects.get().status == "approved"
    assert "30 rows staged in" in out.getvalue() and "(30 created), process peak" in out.getvalue()


def api_for(user):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def test_the_demo_files_case_builds_each_generated_file_on_the_seed(lookups, rates):
    """Seven employees stand in for the seed: six lines, one per generated file (D72)."""
    from apps.compensation.services import bulk_apply
    from seed import profiles
    from seed.generator import ordered_entries

    bulk_apply(
        ordered_entries(5, 42, exited=2),
        source="seed",
        at=profiles.REFERENCE_DATETIME,
        today=profiles.REFERENCE_DATE,
    )
    out = io.StringIO()

    timing.Command(stdout=out).time_demo_files()

    lines = out.getvalue().strip().splitlines()
    assert [line.split(":")[0] for line in lines] == [
        "demo file newhires.xlsx",
        "demo file diwali-bonus.xlsx",
        "demo file april-raises.xlsx",
        "demo file promotions.xlsx",
        "demo file exits.xlsx",
        "demo file fix-me.xlsx",
    ]
    assert all(" rows, " in line and " bytes in " in line for line in lines)
    assert lines[0].split(":")[1].strip().startswith("500 rows")


def test_the_base_import_run_refuses_a_database_that_holds_employees(db, lookups, tmp_path):
    """Run by hand against the live database it would stage into it; it builds an empty one."""
    from django.core.management import CommandError

    from tests.factories import EmployeeFactory

    EmployeeFactory()
    with pytest.raises(CommandError, match="scratch"):
        run_base_import(tmp_path / "none.xlsx", io.StringIO())
