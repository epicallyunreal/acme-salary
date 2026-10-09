"""The Demo data page (SPEC F9, D72): the sample files, and the reset that empties the database.

The reset is the one endpoint that deletes (CLAUDE.md rule 6), and it deletes only through
`seed_data`'s truncation, the function the seed's own `--reset` runs. Lookups, exchange rates and
the user are never touched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.http import Http404

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.compensation.messages import msg
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.compensation.validators import template_columns
from apps.core.dates import today_utc
from apps.core.exceptions import Conflict, Forbidden, clip
from apps.employees.models import Employee
from apps.imports import samples
from apps.imports import services as imports
from apps.imports.models import ImportBatch, ImportRow
from seed import profiles
from seed.management.commands.seed_data import truncate

CONFIRM_WORD = "RESET"
DEFAULT_SEED = 42
READING = "an import is being read; try again in a moment"


def counts() -> dict[str, int]:
    """What a reset deletes, and what the dialog shows before one."""
    return {
        "employees": Employee.objects.count(),
        "compensation_records": CompensationRecord.objects.count(),
        "compensation_lines": CompensationLine.objects.count(),
        "import_batches": ImportBatch.objects.count(),
        "import_rows": ImportRow.objects.count(),
        "audit_entries": AuditLog.objects.count(),
    }


def reset_demo(*, actor, password: str, confirm: str) -> dict[str, int]:
    """Empty the pay tables in one transaction and return the counts deleted (F9).

    The password is the logged-in user's, checked here, and `confirm` must be RESET: wrong either
    way is a 403 naming every wrong field. A file being read is a 409, and so is a transaction
    that waits out SQLite's lock on an approve in flight. The one `demo_reset` audit entry carries
    the counts, and the sequence counters are cleared, so the next employee is ACME-1 again.
    """
    errors = {}
    if not actor.check_password(password):
        errors["password"] = ["password did not match"]
    if confirm != CONFIRM_WORD:
        errors["confirm"] = [f"type {CONFIRM_WORD} to confirm"]
    if errors:
        raise Forbidden(errors)
    with imports.reading_lock(READING):
        try:
            with transaction.atomic():
                deleted = counts()
                truncate(profiles.PAY_TABLES)
                audit.record(
                    AuditLog.Action.DEMO_RESET,
                    entity_type="demo_database",
                    entity_id=0,
                    actor=actor,
                    before=deleted,
                    after={},
                )
        except Exception as exc:
            if not imports.waited_out_the_lock(exc):
                raise
            raise Conflict(msg("apply_busy")) from exc
    return deleted


@dataclass(frozen=True)
class SampleFile:
    name: str
    file_name: str
    description: str
    # The options of a generated file for the day it is made, or None for the committed one.
    options: Callable[[date], dict] | None


def next_april_first(day: date) -> date:
    year = day.year if (day.month, day.day) < (4, 1) else day.year + 1
    return date(year, 4, 1)


SAMPLE_FILES = (
    SampleFile(
        "base",
        "base-15000.xlsx",
        "The whole organisation, 10,000 on staff and 5,000 who left, as the seed built it. Into an "
        "empty database it creates everyone; into the seeded one every row is a no-op, the scale "
        "test.",
        None,
    ),
    SampleFile(
        "newhires",
        "newhires.xlsx",
        "500 new employees with fresh legacy codes who joined between 60 days ago and 14 days "
        "ahead, the future ones shown as Upcoming until they join. Each row creates an employee.",
        lambda today: dict(
            effective=today,
            new=500,
            stream="newhires",
            joined_after=samples.hire_window(today)[0],
            joined_until=samples.hire_window(today)[1],
        ),
    ),
    SampleFile(
        "diwali-bonus",
        "diwali-bonus.xlsx",
        "1,000 employees with 5 to 15% of base added to their bonus, effective today. Each row is "
        "a revision.",
        lambda today: dict(effective=today, bonus=1000, share=0),
    ),
    SampleFile(
        "april-raises",
        "april-raises.xlsx",
        "1,000 employees with base up 3 to 8%, components with it, effective 1 April next. Each "
        "row is a scheduled revision.",
        lambda today: dict(effective=next_april_first(today), raises=1000, share=1),
    ),
    SampleFile(
        "promotions",
        "promotions.xlsx",
        "200 employees one level up with the designation to match and base up 12 to 20%, "
        "effective today. Each row changes identity and amounts at once.",
        lambda today: dict(effective=today, promotions=200, share=2),
    ),
    SampleFile(
        "exits",
        "exits.xlsx",
        "100 employees with their last day between 14 days ago and 60 days ahead: the past ones "
        "leave the counts at once, the future ones are scheduled exits and stay active until the "
        "day. Each row is an exit.",
        lambda today: dict(effective=today, exits=100, share=3),
    ),
    SampleFile(
        "fix-me",
        "fix-me.xlsx",
        "50 rows, 30 raises and 20 new joiners, with 6 planted errors to skip or fix in the sheet.",
        # Its joiners follow newhires' 500 in the one stream, so the two files never collide.
        lambda today: dict(
            effective=samples.next_month_first(today),
            raises=30,
            new=20,
            errors=6,
            share=4,
            stream="newhires",
            offset=500,
        ),
    ),
)
BY_NAME = {spec.name: spec for spec in SAMPLE_FILES}


def sample_files_payload() -> dict:
    """The files in page order, the generated ones unavailable while the database is empty."""
    employees = Employee.objects.count()
    return {
        "employees": employees,
        "files": [
            {
                "name": spec.name,
                "file_name": spec.file_name,
                "description": spec.description,
                "available": spec.options is None or employees > 0,
            }
            for spec in SAMPLE_FILES
        ],
    }


def sample_file(
    name: str, *, seed: int = DEFAULT_SEED, today: date | None = None
) -> tuple[str, bytes]:
    """The file's name and bytes: the base file from disk, the rest generated from the live
    tables for `seed` and the day, so legacy codes always match (F9)."""
    spec = BY_NAME.get(name)
    if spec is None:
        raise Http404(f"no sample file named {clip(name)}")
    if spec.options is None:
        return spec.file_name, (Path(settings.SAMPLE_DATA_DIR) / spec.file_name).read_bytes()
    if not Employee.objects.exists():
        raise Conflict("import the base file first")
    today = today or today_utc()
    rows = samples.generated_rows(today=today, seed=seed, **spec.options(today))
    columns = template_columns(samples.database_codes())
    return spec.file_name, samples.file_bytes(columns, rows, ".xlsx")
