"""`seed_data --employees N --seed S [--reset | --if-empty]` (SPEC section 11).

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

from apps.compensation import validators
from apps.compensation.services import bulk_apply
from apps.employees.models import Employee
from seed import profiles
from seed.generator import generate
from seed.lookups import ensure_lookups, ensure_rates

CHUNK = 1000


def truncate_business_tables() -> None:
    """Delete every business row in dependency order and reset SQLite's id counters, so a reseed
    is byte-identical to a fresh seed (D20). Users are kept."""
    tables = []
    for label in profiles.BUSINESS_TABLES:
        model = apps.get_model(label)
        model.objects.all().delete()
        tables.append(model._meta.db_table)
    if connection.vendor == "sqlite":
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table])


def ensure_hr_manager(password: str):
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        email=profiles.HR_MANAGER_EMAIL, defaults={"first_name": "HR", "last_name": "Manager"}
    )
    if created:
        user.set_password(password)
        user.save(update_fields=["password"])
    return user


def seed(employees: int, seed_value: int, *, reset: bool, stdout=None) -> float:
    """The whole seed in one transaction. Returns the elapsed seconds."""
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
        entries = generate(employees, seed_value)
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
        parser.add_argument("--employees", type=int, default=10000)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--reset", action="store_true", help="wipe the business tables first")
        parser.add_argument(
            "--if-empty", action="store_true", help="do nothing when employees already exist"
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
        elapsed = seed(
            options["employees"], options["seed"], reset=options["reset"], stdout=self.stdout
        )
        self.stdout.write(f"seeded {options['employees']} employees in {elapsed:.1f} s")
