"""`timing`: measure the directory, insights, import and seed on the seed of 10,000 employees on
staff and 5,000 who left (D64).

Driven by the /perf-timing skill. Step 2 ships the seed case, step 3 the directory cases,
step 5 the import case, step 6 the insight cases and step 7 the export case. Prints a Markdown
row for docs/PERFORMANCE.md plus the per-case breakdown; the export case prints its lines only.
"""

from __future__ import annotations

import io
import os
import platform
import re
import resource
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from openpyxl import load_workbook

from apps.core.dates import REPORTING_START, period_start, today_utc
from apps.insights.queries import CONTROLS
from seed import profiles

CASES = ("directory", "insights", "import", "export", "seed", "demo-files", "base-import")
# The child case `base-import` runs in a fresh process against a scratch database (D72).
CHILD_CASES = ("base-import-run",)

# Each directory case is the query string of one request (the /perf-timing skill names them).
DIRECTORY_CASES = {
    "unfiltered": "",
    "country filter": "country=IN",
    "department and gross range": "department=engineering&gross_min=50000&gross_max=150000",
    "sort by reporting gross": "ordering=-gross",
    # Every term is matched against the name, the email, legacy_code and ACME-<id> (D48).
    "search by name": "search=rao",
    "search by code": "search=ACME-17",
    # The directory opens on Active (D64); everyone is one choice away.
    "everyone": "status=any",
}

# Each insight is timed unfiltered and with one country (the /perf-timing skill names them).
INSIGHT_NAMES = (
    "summary",
    "by-country",
    "by-department",
    "distribution",
    "by-level",
    "gender-gap",
    "trend",
    "cost-bridge",
    "by-tenure",
    "cost-mix",
)
INSIGHT_FILTERS = {"unfiltered": "", "country filter": "country=IN"}
# Every other value of a card control is timed as well, since each reads its own figures (D62).
INSIGHT_CONTROLS = tuple(
    (name, f"{key}={value}") for name, (key, values) in CONTROLS.items() for value in values[1:]
)
# The insights whose work grows with the period are timed on each preset and the longest range
# as well (D64); the rest read the state on its last day.
PERIOD_INSIGHTS = ("summary", "trend", "cost-bridge")


def period_cases(today: date) -> dict[str, str]:
    """The dashboard's presets besides the default, and the reporting cut-off to today, as `from`
    and `to` (D64, D70)."""
    fy = date(today.year if (today.month, today.day) >= (4, 1) else today.year - 1, 4, 1)
    return {
        "last 3 months": f"from={period_start(today, 3)}",
        "last 6 months": f"from={period_start(today, 6)}",
        "FY to date": f"from={fy}",
        "last FY": f"from={date(fy.year - 1, 4, 1)}&to={fy - timedelta(days=1)}",
        "since the cut-off": f"from={REPORTING_START}",
    }


# The unfiltered directory is exported once in each format (SPEC F6).
EXPORT_FILES = ("csv", "xlsx", "json")


# ru_maxrss is bytes on macOS and kilobytes on Linux.
RSS_SCALE = 1 if sys.platform == "darwin" else 1024


def git_short_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except OSError, subprocess.CalledProcessError:
        return "unknown"


def machine_label() -> str:
    return f"{platform.system()} {platform.machine()}, {os.cpu_count()} cores"


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[round(fraction * (len(ordered) - 1))]


def api_client() -> Client:
    """A test client logged in as the seeded HR Manager, so the timings include auth."""
    host = next((h for h in settings.ALLOWED_HOSTS if not h.startswith((".", "*"))), "localhost")
    client = Client(headers={"host": host})
    response = client.post(
        "/api/v1/auth/login/",
        {"email": profiles.HR_MANAGER_EMAIL, "password": settings.SEED_ADMIN_PASSWORD},
        content_type="application/json",
    )
    if response.status_code != 200:
        raise CommandError(
            f"login as {profiles.HR_MANAGER_EMAIL} failed with {response.status_code}; "
            "is the database seeded and SEED_ADMIN_PASSWORD the seeded one?"
        )
    return Client(headers={"host": host, "authorization": f"Bearer {response.json()['access']}"})


def time_requests(client: Client, path: str, repeats: int) -> list[float]:
    """Wall time in ms of `repeats` requests after one unmeasured warm-up."""
    samples: list[float] = []
    for index in range(repeats + 1):
        started = time.perf_counter()
        response = client.get(path)
        elapsed = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            raise CommandError(f"{path} answered {response.status_code}: {response.content[:300]}")
        if index:
            samples.append(elapsed)
    return samples


def exported_rows(file: str, body: bytes) -> int:
    """Data rows in an export, the header left out."""
    import csv
    import json

    from openpyxl import load_workbook

    if file == "csv":
        return sum(1 for _ in csv.reader(io.StringIO(body.decode("utf-8-sig")))) - 1
    if file == "xlsx":
        # A write-only workbook records no dimension, so the rows are counted.
        sheet = load_workbook(io.BytesIO(body), read_only=True).active
        return sum(1 for _ in sheet.iter_rows(values_only=True)) - 1
    return len(json.loads(body)["rows"])


# The worst sheet the upload limits let through (D68): every cell of every row points at one long
# shared string. The parts are the fewest openpyxl reads.
CRAFTED_CELL = 10_000
SHEET_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def crafted_sheet(rows: int, columns: list[str], length: int = CRAFTED_CELL) -> bytes:
    """An .xlsx of the template's `columns` and `rows` rows, each cell the one shared string of
    `length` characters."""
    from openpyxl.utils import get_column_letter

    letters = [get_column_letter(index + 1) for index in range(len(columns))]
    strings = ["x" * length, *columns]
    head = "".join(f'<c r="{c}1" t="s"><v>{i + 1}</v></c>' for i, c in enumerate(letters))
    body = [f'<row r="1">{head}</row>']
    for number in range(2, rows + 2):
        cells = "".join(f'<c r="{c}{number}" t="s"><v>0</v></c>' for c in letters)
        body.append(f'<row r="{number}">{cells}</row>')
    types = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    parts = {
        "[Content_Types].xml": (
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" '
            'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/xl/workbook.xml" ContentType="{types}.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            f'ContentType="{types}.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" '
            f'ContentType="{types}.sharedStrings+xml"/></Types>'
        ),
        "_rels/.rels": (
            f'<Relationships xmlns="{PKG_REL_NS}"><Relationship Id="rId1" '
            f'Type="{REL_NS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            f'<workbook {SHEET_NS} xmlns:r="{REL_NS}"><sheets>'
            '<sheet name="Employees" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{PKG_REL_NS}">'
            f'<Relationship Id="rId1" Type="{REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{REL_NS}/sharedStrings" Target="sharedStrings.xml"/>'
            "</Relationships>"
        ),
        "xl/worksheets/sheet1.xml": (
            f"<worksheet {SHEET_NS}><sheetData>{''.join(body)}</sheetData></worksheet>"
        ),
        "xl/sharedStrings.xml": (
            f"<sst {SHEET_NS}>{''.join(f'<si><t>{text}</t></si>' for text in strings)}</sst>"
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, '<?xml version="1.0"?>' + text)
    return buffer.getvalue()


def run_base_import(path: Path, stdout) -> None:
    """In this process, against its database: migrate, the lookups, the rates and the HR Manager,
    then the base file staged and approved through the API, printing both times and the peak.
    `timing --case base-import` runs it in a child process against a scratch database (D72)."""
    from django.core.management import call_command

    from apps.employees.models import Employee
    from seed.lookups import ensure_lookups, ensure_rates
    from seed.management.commands.seed_data import ensure_hr_manager

    call_command("migrate", verbosity=0)
    if Employee.objects.exists():
        raise CommandError(
            "base-import-run builds an empty database; point DATABASE_PATH at a scratch file"
        )
    ensure_lookups()
    ensure_rates()
    ensure_hr_manager(settings.SEED_ADMIN_PASSWORD)
    client = api_client()
    data = path.read_bytes()
    with io.BytesIO(data) as handle:
        handle.name = path.name
        started = time.perf_counter()
        response = client.post("/api/v1/imports/", {"file": handle})
        staging = time.perf_counter() - started
    if response.status_code != 201:
        raise CommandError(f"staging answered {response.status_code}: {response.content[:300]}")
    body = response.json()
    started = time.perf_counter()
    approved = client.post(f"/api/v1/imports/{body['id']}/approve/")
    approving = time.perf_counter() - started
    if approved.status_code != 200:
        raise CommandError(f"approve answered {approved.status_code}: {approved.content[:300]}")
    applied = approved.json()
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_SCALE
    stdout.write(
        f"base import of {path.name} ({len(data):,} bytes) into an empty database: "
        f"{body['total_rows']} rows staged in {staging:.1f} s and approved in {approving:.1f} s "
        f"({applied['created_rows']} created), process peak {peak / 2**20:.0f} MB"
    )


def time_seed(scratch_db: Path, active: int, exited: int, seed: int) -> float:
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
            "--active",
            str(active),
            "--exited",
            str(exited),
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
    help = "Measure the step targets on the seed and print a PERFORMANCE.md row."

    def add_arguments(self, parser):
        parser.add_argument("--case", choices=("all", *CASES, *CHILD_CASES), default="all")
        parser.add_argument("--active", type=int, default=profiles.ACTIVE_EMPLOYEES)
        parser.add_argument("--exited", type=int, default=profiles.EXITED_EMPLOYEES)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--repeats", type=int, default=20)
        # Each import sheet can run alone, so its peak memory is its own (D64).
        parser.add_argument("--sheet", choices=("both", "all", "new", "crafted"), default="both")
        # The period cases alone spend less of a shared CPU's burst balance on Fly (D65, D70).
        parser.add_argument("--insights", choices=("all", "periods"), default="all")

    def require_seed(self, active: int, exited: int) -> None:
        from apps.employees.models import Employee

        count = Employee.objects.count()
        if count < active + exited:
            raise CommandError(
                f"the database has {count} employees; the timings need the seed of {active} "
                f"active and {exited} exited (python manage.py seed_data --active {active} "
                f"--exited {exited} --seed 42)"
            )

    def time_directory(self, repeats: int) -> str:
        """p50 / p95 of the slowest case; every case is printed."""
        client = api_client()
        worst = (0.0, 0.0)
        for name, query in DIRECTORY_CASES.items():
            samples = time_requests(client, f"/api/v1/employees/?{query}", repeats)
            p50, p95 = percentile(samples, 0.5), percentile(samples, 0.95)
            self.stdout.write(
                f"directory, {name}: p50 {p50:.0f} ms, p95 {p95:.0f} ms ({repeats} requests)"
            )
            if p95 > worst[1]:
                worst = (p50, p95)
        return f"{worst[0]:.0f} / {worst[1]:.0f}"

    def time_insights(self, repeats: int, which: str = "all") -> str:
        """p50 / p95 of the slowest insight and filter; every one is printed. `periods` times
        only the presets and the cut-off to today, for the insights whose work grows with them."""
        client = api_client()
        worst = (0.0, 0.0)
        cases = [] if which == "periods" else [(name, "") for name in INSIGHT_NAMES]
        cases += [] if which == "periods" else list(INSIGHT_CONTROLS)
        for name, control in cases:
            for label, query in INSIGHT_FILTERS.items():
                path = f"/api/v1/insights/{name}/?{'&'.join(q for q in (query, control) if q)}"
                samples = time_requests(client, path, repeats)
                p50, p95 = percentile(samples, 0.5), percentile(samples, 0.95)
                self.stdout.write(
                    f"insight {name}{f' {control}' if control else ''}, {label}: p50 {p50:.0f} ms, "
                    f"p95 {p95:.0f} ms ({repeats} requests)"
                )
                if p95 > worst[1]:
                    worst = (p50, p95)
        for label, query in period_cases(today_utc()).items():
            for name in PERIOD_INSIGHTS:
                samples = time_requests(client, f"/api/v1/insights/{name}/?{query}", repeats)
                p50, p95 = percentile(samples, 0.5), percentile(samples, 0.95)
                self.stdout.write(
                    f"insight {name}, {label}: p50 {p50:.0f} ms, p95 {p95:.0f} ms "
                    f"({repeats} requests)"
                )
                if p95 > worst[1]:
                    worst = (p50, p95)
        return f"{worst[0]:.0f} / {worst[1]:.0f}"

    def time_export(self) -> None:
        """The default directory export, on Active, in each format: rows, size, wall time and
        how far it raised the process's peak memory. SPEC F6 asks for every active employee,
        10,000 on the seed, so a short file is an error (D64)."""
        from apps.employees.models import Employee
        from apps.employees.queries import DEFAULT_STATUS, status_expression

        statuses = Employee.objects.annotate(status=status_expression(today_utc()))
        active = statuses.filter(status=DEFAULT_STATUS).count()

        client = api_client()
        for file in EXPORT_FILES:
            peak_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_SCALE
            started = time.perf_counter()
            response = client.get(f"/api/v1/exports/employees/?file={file}")
            body = b"".join(response.streaming_content) if response.streaming else response.content
            elapsed = time.perf_counter() - started
            peak_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_SCALE
            if response.status_code != 200:
                raise CommandError(f"the {file} export answered {response.status_code}")
            rows = exported_rows(file, body)
            if rows != active:
                raise CommandError(
                    f"the {file} export holds {rows:,} rows, not the {active:,} active employees"
                )
            self.stdout.write(
                f"export, employees as {file}: {rows:,} rows, "
                f"{len(body) / 2**20:.1f} MB in {elapsed:.1f} s, "
                f"peak memory up {(peak_after - peak_before) / 2**20:.0f} MB"
            )

    def time_import(self, seed: int, sheet: str) -> str:
        """Stage and approve the import sheets (D64): `make_import_file --all --raises 1000`,
        the whole organisation with a thousand raises, 15,000 rows whose times are the row's,
        and `--new 10000`, the heaviest create-import the cap of 25,000 leaves room for on the
        seed (D72, D73); the 15,000 creates of the base file have the base-import case. `--sheet
        crafted` stages the crafted sheet alone (D68). Each runs inside a transaction that is
        rolled back, so the database is left as it was."""
        everyone = ""
        if sheet in ("both", "all"):
            everyone = self.time_sheet("--all --raises 1000", {"all": True, "raises": 1000}, seed)
        if sheet in ("both", "new"):
            self.time_sheet("--new 10000", {"new": 10000}, seed)
        if sheet == "crafted":
            self.time_crafted()
        return everyone

    def time_crafted(self) -> None:
        """Stage the crafted sheet through the API, 15,000 rows of one 10,000-character shared
        string, rolled back (D68). Every row is an error, so there is nothing to approve. Prints
        the time and the process's peak memory, which on Fly must stay under 700 MB."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import transaction

        from apps.compensation.validators import template_columns
        from apps.core import queries as core_queries
        from apps.imports.parser import ROW_LIMIT, XLSX_TYPE

        columns = template_columns(c.code for c in core_queries.active_components())
        data = crafted_sheet(ROW_LIMIT, columns)
        client = api_client()
        with transaction.atomic():
            upload = SimpleUploadedFile("crafted.xlsx", data, content_type=XLSX_TYPE)
            started = time.perf_counter()
            response = client.post("/api/v1/imports/", {"file": upload})
            staging = time.perf_counter() - started
            transaction.set_rollback(True)
        if response.status_code != 201:
            raise CommandError(f"staging answered {response.status_code}: {response.content[:300]}")
        body = response.json()
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_SCALE
        self.stdout.write(
            f"import crafted sheet of {len(data):,} bytes, staging {body['total_rows']} rows "
            f"({body['error_rows']} error): {staging:.1f} s, process peak {peak / 2**20:.0f} MB"
        )

    def time_sheet(self, name: str, options: dict, seed: int) -> str:
        """Stage one sheet through the API and approve it, rolled back. Prints both times, how
        far staging raised the process's peak memory and the peak itself."""
        from django.core.management import call_command
        from django.db import transaction

        client = api_client()
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "import.xlsx"
            call_command(
                "make_import_file", out=str(path), seed=seed, stdout=io.StringIO(), **options
            )
            peak_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_SCALE
            with transaction.atomic(), path.open("rb") as handle:
                started = time.perf_counter()
                response = client.post("/api/v1/imports/", {"file": handle})
                staging = time.perf_counter() - started
                peak_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_SCALE
                if response.status_code != 201:
                    raise CommandError(
                        f"staging answered {response.status_code}: {response.content[:300]}"
                    )
                started = time.perf_counter()
                approved = client.post(f"/api/v1/imports/{response.json()['id']}/approve/")
                approving = time.perf_counter() - started
                transaction.set_rollback(True)
        if approved.status_code != 200:
            raise CommandError(f"approve answered {approved.status_code}: {approved.content[:300]}")
        body, applied = response.json(), approved.json()
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * RSS_SCALE
        self.stdout.write(
            f"import {name}, staging {body['total_rows']} rows ({body['valid_rows']} valid, "
            f"{body['warning_rows']} warning, {body['error_rows']} error, {body['noop_rows']} "
            f"no-op): {staging:.1f} s, peak memory up {(peak_after - peak_before) / 2**20:.0f} MB"
        )
        self.stdout.write(
            f"import {name}, approve of {applied['applied_rows']} rows ({applied['revised_rows']} "
            f"revised, {applied['created_rows']} created): {approving:.1f} s, rolled back, "
            f"process peak {peak / 2**20:.0f} MB"
        )
        return f"{staging:.1f} / {approving:.1f}"

    def time_demo_files(self) -> None:
        """Each generated file of the Demo data page on the seed (F9, D72): rows, bytes and the
        time to build it, as a download would."""
        from apps.demo import services as demo

        for spec in demo.SAMPLE_FILES:
            if spec.options is None:
                continue
            started = time.perf_counter()
            name, data = demo.sample_file(spec.name, seed=42)
            elapsed = time.perf_counter() - started
            sheet = load_workbook(io.BytesIO(data), read_only=True).worksheets[0]
            rows = sum(1 for _ in sheet.iter_rows(values_only=True)) - 1
            self.stdout.write(
                f"demo file {name}: {rows:,} rows, {len(data):,} bytes in {elapsed:.1f} s"
            )

    def time_base_import(self, scratch_db: Path) -> str:
        """The base file into an empty database, staged and approved through the API in a fresh
        process against a scratch database, not rolled back (F9, D72): the reset flow a reviewer
        runs, with its peak memory."""
        output = subprocess.run(
            [sys.executable, "manage.py", "timing", "--case", "base-import-run"],
            cwd=Path(__file__).resolve().parents[4],
            env={**os.environ, "DATABASE_PATH": str(scratch_db)},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.stdout.write(output.rstrip("\n"))
        match = re.search(r"staged in ([0-9.]+) s and approved in ([0-9.]+) s", output)
        return f"{match.group(1)} / {match.group(2)}" if match else ""

    def handle(self, *args, **options):
        if options["case"] == "base-import-run":
            run_base_import(Path(settings.SAMPLE_DATA_DIR) / "base-15000.xlsx", self.stdout)
            return
        wanted = CASES if options["case"] == "all" else (options["case"],)
        results: dict[str, str] = {case: "" for case in CASES}

        if "demo-files" in wanted:
            self.require_seed(options["active"], options["exited"])
            self.time_demo_files()

        if "base-import" in wanted:
            with tempfile.TemporaryDirectory() as scratch:
                results["base-import"] = self.time_base_import(Path(scratch) / "base.sqlite3")

        if "directory" in wanted:
            self.require_seed(options["active"], options["exited"])
            results["directory"] = self.time_directory(options["repeats"])

        if "insights" in wanted:
            self.require_seed(options["active"], options["exited"])
            results["insights"] = self.time_insights(options["repeats"], options["insights"])

        if "import" in wanted:
            self.require_seed(options["active"], options["exited"])
            results["import"] = self.time_import(options["seed"], options["sheet"])

        if "export" in wanted:
            self.require_seed(options["active"], options["exited"])
            self.time_export()

        if "seed" in wanted:
            with tempfile.TemporaryDirectory() as scratch:
                try:
                    seconds = time_seed(
                        Path(scratch) / "timing.sqlite3",
                        options["active"],
                        options["exited"],
                        options["seed"],
                    )
                except subprocess.CalledProcessError as exc:
                    raise CommandError(f"seed failed: {exc.stderr[-2000:]}") from exc
            results["seed"] = f"{seconds:.1f}"
            self.stdout.write(
                f"seed: {options['active']} active and {options['exited']} exited employees "
                f"with seed {options['seed']} in "
                f"{seconds:.1f} s (fresh process, migrate excluded, --reset included)"
            )

        today = datetime.now(UTC).date().isoformat()
        row = (
            f"| {today} | {git_short_sha()} | {machine_label()} | {results['directory']} | "
            f"{results['insights']} | {results['import']} | {results['seed']} |"
        )
        self.stdout.write(row)
