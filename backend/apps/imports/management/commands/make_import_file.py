"""`make_import_file --out <path> [--new N] [--raises N] [--bonus N] [--promotions N] [--exits N]
[--errors N] [--all] [--base] [--effective YYYY-MM-DD] [--share K] [--joined-after YYYY-MM-DD]
[--joined-until YYYY-MM-DD] [--stream NAME] [--offset N]` (SPEC section 11, D72).

The command line over `apps/imports/samples.py`, which builds the rows: the Demo data page
calls the same module (D73). Used by /perf-timing, the step 5 sample and the page's files.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.compensation.validators import IDENTITY_COLUMNS, template_columns
from apps.core.dates import today_utc
from apps.imports.samples import (
    SHARES,
    base_rows,
    database_codes,
    generated_rows,
    next_month_first,
    profile_codes,
    write_file,
)
from seed import profiles


class Command(BaseCommand):
    help = "Write a template-shaped import file from the live tables, or the seed's base file."

    def add_arguments(self, parser):
        parser.add_argument("--out", required=True)
        parser.add_argument("--new", type=int, default=0)
        parser.add_argument("--raises", type=int, default=0)
        parser.add_argument("--bonus", type=int, default=0)
        parser.add_argument("--promotions", type=int, default=0)
        parser.add_argument("--exits", type=int, default=0)
        parser.add_argument("--errors", type=int, default=0)
        parser.add_argument("--all", action="store_true")
        parser.add_argument("--base", action="store_true")
        parser.add_argument("--effective", type=date.fromisoformat, default=None)
        parser.add_argument("--share", type=int, choices=range(SHARES), default=None)
        parser.add_argument("--joined-after", type=date.fromisoformat, default=None)
        parser.add_argument("--joined-until", type=date.fromisoformat, default=None)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--stream", default="import", help="the joiners' stream, by name")
        parser.add_argument("--offset", type=int, default=0, help="joiners of the stream to skip")

    def handle(self, *args, **options):
        path = Path(options["out"])
        # call_command passes a date option as given, a string or a date.
        for name in ("effective", "joined_after", "joined_until"):
            if isinstance(options[name], str):
                options[name] = date.fromisoformat(options[name])
        if options["base"]:
            rows = base_rows(profiles.ACTIVE_EMPLOYEES, profiles.EXITED_EMPLOYEES, options["seed"])
            codes = profile_codes()
        else:
            today = today_utc()
            try:
                rows = generated_rows(
                    today=today,
                    effective=options["effective"] or next_month_first(today),
                    seed=options["seed"],
                    share=options["share"],
                    raises=options["raises"],
                    bonus=options["bonus"],
                    promotions=options["promotions"],
                    exits=options["exits"],
                    new=options["new"],
                    errors=options["errors"],
                    everyone=options["all"],
                    joined_after=options["joined_after"],
                    joined_until=options["joined_until"],
                    stream=options["stream"],
                    offset=options["offset"],
                )
            except ValueError as exc:  # a joining window that ends before it starts
                raise CommandError(str(exc)) from exc
            codes = database_codes()
        try:
            write_file(path, template_columns(codes), rows)
        except ValueError as exc:  # not .xlsx or .csv
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"wrote {len(rows)} rows to {path} ({len(IDENTITY_COLUMNS) + len(codes)} columns)"
        )
