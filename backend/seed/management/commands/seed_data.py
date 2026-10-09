"""`seed_data --active N --exited M --seed S [--reset | --if-empty]` (SPEC section 11).

Builds the demo dataset in one transaction through compensation.services.bulk_apply, so seeded
rows obey the same rules and audit as the UI. --reset and reset_demo are the only code that
removes rows of pay data (CLAUDE.md rule 6).
"""

from __future__ import annotations

import time
from itertools import islice

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.audit.models import AuditLog
from apps.compensation import validators
from apps.compensation.services import bulk_apply
from apps.employees.models import Employee
from seed import profiles
from seed.generator import ordered_entries
from seed.lookups import ensure_lookups, ensure_rates

CHUNK = 1000


def truncate_business_tables() -> None:
    """Delete every business row in dependency order and reset SQLite's id counters, so a reseed
    is byte-identical to a fresh seed (D20). Users are kept."""
    truncate(profiles.BUSINESS_TABLES)


def truncate(labels: tuple[str, ...]) -> None:
    """Delete every row of `labels`, in the order given, and clear their id counters. The seed
    passes every business table and the demo reset the pay tables alone (D72). The one function
    that deletes rows (CLAUDE.md rule 6)."""
    tables = []
    for label in labels:
        model = apps.get_model(label)
        model.objects.all().delete()
        tables.append(model._meta.db_table)
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table])


def ensure_hr_manager(password: str):
    """Create the one account when it is missing, in one write; an existing one keeps its
    password, which is how reset_demo keeps the owner's."""
    user_model = get_user_model()
    user = user_model.objects.filter(email=profiles.HR_MANAGER_EMAIL).first()
    if user is None:
        user = user_model.objects.create_user(
            profiles.HR_MANAGER_EMAIL, password, first_name="HR", last_name="Manager"
        )
    return user


def seed(active: int, exited: int, seed_value: int, *, reset: bool, stdout=None) -> float:
    """The whole seed in one transaction: `active` employees on staff on the reference date
    and `exited` who left before it (D64). Returns the elapsed seconds."""
    password = settings.SEED_ADMIN_PASSWORD
    if not password:
        raise CommandError("SEED_ADMIN_PASSWORD must be set")
    try:
        validate_password(password)
    except ValidationError as exc:
        raise CommandError("SEED_ADMIN_PASSWORD is too weak: " + "; ".join(exc.messages)) from exc

    started = time.perf_counter()
    with transaction.atomic():
        if reset:
            truncate_business_tables()
        ensure_lookups()
        ensure_rates(at=profiles.REFERENCE_DATETIME)
        ensure_hr_manager(password)
        ctx = validators.build_context(today=profiles.REFERENCE_DATE)
        entries = iter(ordered_entries(active, seed_value, exited=exited))
        while chunk := list(islice(entries, CHUNK)):
            bulk_apply(
                chunk,
                source="seed",
                at=profiles.REFERENCE_DATETIME,
                today=profiles.REFERENCE_DATE,
                ctx=ctx,
            )
            if stdout is not None:
                stdout.write(f"  {Employee.objects.count()} employees")
    return time.perf_counter() - started


class Command(BaseCommand):
    help = "Seed the demo dataset deterministically."

    def add_arguments(self, parser):
        parser.add_argument("--active", type=int, default=profiles.ACTIVE_EMPLOYEES)
        parser.add_argument("--exited", type=int, default=profiles.EXITED_EMPLOYEES)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--reset", action="store_true", help="wipe the business tables first")
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help="do nothing when employees exist or the Demo data page emptied the database",
        )

    def handle(self, *args, **options):
        if options["reset"] and options["if_empty"]:
            raise CommandError("--reset and --if-empty exclude each other")
        if Employee.objects.exists():
            if options["if_empty"]:
                self.stdout.write("employees exist, nothing to do")
                return
            if not options["reset"]:
                raise CommandError(
                    "the database has employees; pass --reset to rebuild it or --if-empty to skip"
                )
        # The boot seed fills a fresh volume, or one a first boot left empty part way. A database
        # emptied on the Demo data page carries its one demo_reset entry and stays empty across
        # restarts, until the base file is imported or the operator runs reset_demo (D79).
        elif (
            options["if_empty"]
            and AuditLog.objects.filter(action=AuditLog.Action.DEMO_RESET).exists()
        ):
            self.stdout.write("the database was emptied on the Demo data page, nothing to do")
            return
        active, exited = options["active"], options["exited"]
        if active < 0 or exited < 0:
            raise CommandError("--active and --exited must be 0 or more")
        if exited and not active:
            # Leavers leave month by month in proportion to those on staff (D64).
            raise CommandError("--exited needs --active: leavers follow the headcount")
        elapsed = seed(active, exited, options["seed"], reset=options["reset"], stdout=self.stdout)
        self.stdout.write(
            f"seeded {active} active and {exited} exited employees in {elapsed:.1f} s"
        )
