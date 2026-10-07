"""`timing`: measure the directory, insights, import and seed on the 10,000-row seed.

Driven by the /perf-timing skill. Step 2 ships the seed case; the directory, insight and import
cases land with the steps that build them. Prints a Markdown row for docs/PERFORMANCE.md.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

CASES = ("directory", "insights", "import", "seed")


def git_short_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return "unknown"


def machine_label() -> str:
    return f"{platform.system()} {platform.machine()}, {os.cpu_count()} cores"


def time_seed(scratch_db: Path, employees: int, seed: int) -> float:
    """Wall time of `seed_data --reset` in a fresh process against a scratch database."""
    env = {**os.environ, "DATABASE_PATH": str(scratch_db)}
    manage = str(Path(__file__).resolve().parents[4] / "manage.py")
    subprocess.run([sys.executable, manage, "migrate", "--noinput", "-v", "0"], env=env, check=True)
    started = time.perf_counter()
    subprocess.run(
        [
            sys.executable,
            manage,
            "seed_data",
            "--employees",
            str(employees),
            "--seed",
            str(seed),
            "--reset",
        ],
        env=env,
        check=True,
        capture_output=True,
    )
    return time.perf_counter() - started


class Command(BaseCommand):
    help = "Measure the step targets on the 10,000-row seed and print a PERFORMANCE.md row."

    def add_arguments(self, parser):
        parser.add_argument("--case", choices=("all", *CASES), default="all")
        parser.add_argument("--employees", type=int, default=10000)
        parser.add_argument("--seed", type=int, default=42)

    def handle(self, *args, **options):
        wanted = CASES if options["case"] == "all" else (options["case"],)
        results: dict[str, str] = {case: "" for case in CASES}

        for case in ("directory", "insights", "import"):
            if case in wanted:
                results[case] = "not built yet"

        if "seed" in wanted:
            with tempfile.TemporaryDirectory() as scratch:
                try:
                    seconds = time_seed(
                        Path(scratch) / "timing.sqlite3", options["employees"], options["seed"]
                    )
                except subprocess.CalledProcessError as exc:
                    raise CommandError(f"seed failed: {exc.stderr[-2000:]}") from exc
            results["seed"] = f"{seconds:.1f}"
            self.stdout.write(
                f"seed: {options['employees']} employees with seed {options['seed']} in "
                f"{seconds:.1f} s (fresh process, migrate excluded, --reset included)"
            )

        today = datetime.now(UTC).date().isoformat()
        row = (
            f"| {today} | {git_short_sha()} | {machine_label()} | {results['directory']} | "
            f"{results['insights']} | {results['import']} | {results['seed']} |"
        )
        self.stdout.write(row)
