"""The demo reset and the sample files (SPEC F9, D72), without HTTP."""

from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.http import Http404
from openpyxl import load_workbook

from apps.audit.models import AuditLog
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.compensation.services import bulk_apply
from apps.compensation.validators import template_columns
from apps.core.exceptions import Conflict, Forbidden
from apps.core.models import Country, Department, ExchangeRate, SalaryComponent
from apps.demo import services
from apps.employees.models import Employee
from apps.imports import services as imports
from apps.imports.management.commands.make_import_file import database_codes
from apps.imports.models import ImportBatch, ImportRow
from seed import profiles
from seed.generator import ordered_entries
from tests.imports.sheets import new_row, upload_of

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"  # UserFactory's
TODAY = date(2026, 10, 7)


def seed(active: int, exited: int, seed_value: int = 42) -> None:
    bulk_apply(
        ordered_entries(active, seed_value, exited=exited),
        source="seed",
        at=profiles.REFERENCE_DATETIME,
        today=profiles.REFERENCE_DATE,
    )


@pytest.fixture
def seeded(lookups, rates):
    """Five on staff and two leavers from the seed, and one staged import."""
    seed(5, 2)
    imports.stage_upload(upload_of(new_row()), actor=None)


def lookup_counts() -> tuple[int, int, int, int]:
    return (
        Country.objects.count(),
        Department.objects.count(),
        SalaryComponent.objects.count(),
        ExchangeRate.objects.count(),
    )


def test_a_reset_empties_the_pay_tables_keeps_the_rest_and_restarts_the_ids(seeded, hr_user):
    before = services.counts()
    assert before["employees"] == 7 and before["import_batches"] == 1
    assert before["audit_entries"] > 0 and before["import_rows"] == 1
    lookups_before = lookup_counts()

    deleted = services.reset_demo(actor=hr_user, password=PASSWORD, confirm="RESET")

    assert deleted == before
    assert services.counts() == {**dict.fromkeys(before, 0), "audit_entries": 1}
    assert lookup_counts() == lookups_before
    assert get_user_model().objects.get(pk=hr_user.pk).check_password(PASSWORD)
    (entry,) = AuditLog.objects.all()
    assert (entry.action, entry.actor_id, entry.employee_id) == ("demo_reset", hr_user.pk, None)
    assert (entry.entity_type, entry.entity_id, entry.before, entry.after) == (
        "demo_database",
        0,
        before,
        {},
    )
    # The sequence counters are cleared, so the next employee is ACME-1 and its record id 1.
    seed(1, 0, seed_value=7)
    assert Employee.objects.get().pk == 1
    assert CompensationRecord.objects.order_by("pk").first().pk == 1
    assert CompensationLine.objects.order_by("pk").first().pk == 1
    assert ImportBatch.objects.count() == 0 and ImportRow.objects.count() == 0


def test_a_wrong_password_or_confirmation_is_refused_naming_each_wrong_field(seeded, hr_user):
    with pytest.raises(Forbidden) as both:
        services.reset_demo(actor=hr_user, password="nope", confirm="reset")
    with pytest.raises(Forbidden) as password:
        services.reset_demo(actor=hr_user, password="nope", confirm="RESET")
    with pytest.raises(Forbidden) as confirm:
        services.reset_demo(actor=hr_user, password=PASSWORD, confirm="Reset")

    assert both.value.errors == {
        "password": ["password did not match"],
        "confirm": ["type RESET to confirm"],
    }
    assert password.value.errors == {"password": ["password did not match"]}
    assert confirm.value.errors == {"confirm": ["type RESET to confirm"]}
    assert Employee.objects.count() == 7
    assert not AuditLog.objects.filter(action="demo_reset").exists()


def test_a_reset_while_a_file_is_being_read_or_applied_is_a_conflict(seeded, hr_user, monkeypatch):
    """The import lock covers a file being read. SQLite's write lock covers an approve in
    flight: the transaction waits out the 20 s and the locked error becomes a 409 (D72)."""
    assert imports._reading.acquire(blocking=False)
    try:
        with pytest.raises(Conflict, match="an import is being read; try again in a moment"):
            services.reset_demo(actor=hr_user, password=PASSWORD, confirm="RESET")
    finally:
        imports._reading.release()

    def locked(labels):
        raise OperationalError("database is locked")

    monkeypatch.setattr(services, "truncate", locked)
    with pytest.raises(Conflict, match="an import is being applied; try again in a moment"):
        services.reset_demo(actor=hr_user, password=PASSWORD, confirm="RESET")

    assert Employee.objects.count() == 7
    assert not AuditLog.objects.filter(action="demo_reset").exists()


def test_the_file_list_and_the_base_file_need_no_data(lookups):
    payload = services.sample_files_payload()

    assert payload["employees"] == 0
    assert [(f["name"], f["available"]) for f in payload["files"]] == [
        ("base", True),
        ("newhires", False),
        ("diwali-bonus", False),
        ("april-raises", False),
        ("promotions", False),
        ("exits", False),
        ("fix-me", False),
    ]
    assert all(f["description"] and f["file_name"].endswith(".xlsx") for f in payload["files"])
    name, data = services.sample_file("base")
    assert name == "base-15000.xlsx"
    assert data == (Path(settings.SAMPLE_DATA_DIR) / "base-15000.xlsx").read_bytes()
    with pytest.raises(Conflict, match="import the base file first"):
        services.sample_file("exits")
    with pytest.raises(Http404):
        services.sample_file("nope")


def rows_of(data: bytes) -> tuple[list, list[dict]]:
    values = list(
        load_workbook(BytesIO(data), read_only=True).worksheets[0].iter_rows(values_only=True)
    )
    header = list(values[0])
    return header, [dict(zip(header, row, strict=True)) for row in values[1:]]


def test_generated_files_come_from_the_live_tables_in_the_templates_shape(seeded):
    """Seven employees on 7 October 2026: exits takes those on staff of share 3, fix-me the
    raises of share 4 with 20 new joiners and its planted errors, newhires 500 who joined in the
    last three months."""
    assert all(f["available"] for f in services.sample_files_payload()["files"])
    columns = template_columns(database_codes())
    on_staff = {e.pk: e for e in Employee.objects.filter(last_date=None)}

    exits_name, exits = services.sample_file("exits", today=TODAY)
    header, rows = rows_of(exits)
    assert exits_name == "exits.xlsx" and header == columns
    assert [Employee.objects.get(legacy_code=r["legacy_code"]).pk % 5 for r in rows] == [3] * len(
        rows
    )
    assert rows and all(r["last_date"].date() == TODAY for r in rows)
    assert len(rows) == sum(pk % 5 == 3 for pk in on_staff)

    _, fixme = services.sample_file("fix-me", today=TODAY)
    header, rows = rows_of(fixme)
    assert header == columns
    assert len(rows) == sum(pk % 5 == 4 for pk in on_staff) + 20
    assert rows[0]["BASE"] == -5000

    _, hires = services.sample_file("newhires", today=TODAY)
    _, rows = rows_of(hires)
    assert len(rows) == 500
    assert all(date(2026, 7, 7) <= r["joining_date"].date() <= TODAY for r in rows)
    assert len({r["legacy_code"] for r in rows}) == 500
