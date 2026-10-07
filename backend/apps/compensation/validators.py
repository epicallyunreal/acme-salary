"""The one validator module (SPEC section 7, CLAUDE.md rule 4).

Rules are small functions over a NormalizedRow and a ValidationContext, registered in RULES in the
order SPEC F1 fixes: structure and types, identity references, duplicates within the file, amounts
changed, no-op, date rules, then warnings. The import pipeline, the API services and the seed all
call them; the rules themselves never query, build_context() loads what they need once (the
country medians lazily, on the first rule that asks).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as django_validate_email
from django.db.models import Q

from apps.compensation.messages import msg
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.core import queries as core_queries
from apps.core.dates import today_utc
from apps.core.exceptions import Conflict, Invalid
from apps.core.models import Country, Department, SalaryComponent
from apps.core.money import format_amount, format_cents, q2, to_str
from apps.employees.models import LEGACY_CODE_MAX, Employee, Gender, employee_code_of

IDENTITY_FIELDS = (
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "gender",
    "joining_date",
    "last_date",
)
GENDERS = {choice.value for choice in Gender}
ZERO = Decimal("0")
TEN = Decimal("10")
# Every line and the bonus fit in ten integer digits, so no total of them can reach the limit of
# the DecimalField(14, 2) totals, whatever the number of components (D49). Errors are for
# impossible values; the warnings below are for unusual ones.
MAX_AMOUNT = Decimal("9999999999.99")
MIN_BASE = Decimal("10")
CHUNK = 500

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Message:
    field: str
    severity: Severity
    message: str
    code: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "severity": self.severity, "message": self.message}


def error(field_name: str, key: str, **values) -> Message:
    return Message(field_name, "error", msg(key, **values), key)


def warning(field_name: str, key: str, **values) -> Message:
    return Message(field_name, "warning", msg(key, **values), key)


def info(field_name: str, key: str, **values) -> Message:
    return Message(field_name, "info", msg(key, **values), key)


@dataclass
class NormalizedRow:
    """One row of an import, or one API call shaped like one."""

    row_number: int | None = None
    # An import row names its employee by legacy_code; an API call names it by id (D48).
    legacy_code: str | None = None
    employee_id: int | None = None
    full_name: str | None = None
    email: str | None = None
    department: str | None = None
    designation: str | None = None
    level: int | None = None
    country_code: str | None = None
    gender: str | None = None
    joining_date: date | None = None
    last_date: date | None = None
    effective_from: date | None = None
    bonus_annual: Decimal | None = None
    amounts: dict[str, Decimal | None] = field(default_factory=dict)
    columns: frozenset[str] = frozenset()
    present: frozenset[str] = frozenset()
    parse_messages: list[Message] = field(default_factory=list)
    # set while validating
    is_new: bool = True
    identity_changed: bool = False
    amounts_changed: bool = False
    noop: bool = False


def current_q(on: date) -> Q:
    return Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gt=on))


def active_q(on: date) -> Q:
    return Q(employee__joining_date__lte=on) & (
        Q(employee__last_date__isnull=True) | Q(employee__last_date__gte=on)
    )


def load_country_medians(on: date) -> dict[str, Decimal]:
    """Median gross per country over the records current on `on`, for the ten-times warning."""
    by_country: dict[str, list[Decimal]] = defaultdict(list)
    population = CompensationRecord.objects.filter(cancelled_at__isnull=True).filter(
        current_q(on) & active_q(on)
    )
    for country_code, gross in population.values_list("employee__country_id", "gross_annual"):
        by_country[country_code].append(gross)
    return {code: q2(Decimal(statistics.median(values))) for code, values in by_country.items()}


@dataclass
class ValidationContext:
    """Everything the rules need, loaded once. Rules read it and never query."""

    today: date
    countries: dict[str, Country]
    departments: dict[str, Department]
    components_by_country: dict[str, dict[str, SalaryComponent]]
    employees_by_id: dict[int, Employee] = field(default_factory=dict)
    employees_by_legacy: dict[str, Employee] = field(default_factory=dict)
    email_owner: dict[str, int] = field(default_factory=dict)
    first_by_employee: dict[int, CompensationRecord] = field(default_factory=dict)
    latest_by_employee: dict[int, CompensationRecord] = field(default_factory=dict)
    open_by_employee: dict[int, CompensationRecord] = field(default_factory=dict)
    current_by_employee: dict[int, CompensationRecord] = field(default_factory=dict)
    scheduled_by_employee: dict[int, list[date]] = field(default_factory=dict)
    current_lines_by_employee: dict[int, dict[str, Decimal]] = field(default_factory=dict)
    current_bonus_by_employee: dict[int, Decimal] = field(default_factory=dict)
    rows_of_legacy: dict[str, list[int]] = field(default_factory=dict)
    rows_of_email: dict[str, list[int]] = field(default_factory=dict)
    _medians: dict[str, Decimal] | None = field(default=None, repr=False)

    def employee_for(self, row: NormalizedRow) -> Employee | None:
        """The employee an API call names, else the one an import row's legacy_code matches."""
        if row.employee_id is not None:
            return self.employees_by_id.get(row.employee_id)
        if row.legacy_code:
            return self.employees_by_legacy.get(row.legacy_code)
        return None

    def department_for(self, value: str | None) -> Department | None:
        if not value:
            return None
        return self.departments.get(value.strip().lower())

    def components_for(self, country_code: str | None) -> dict[str, SalaryComponent]:
        return self.components_by_country.get(country_code or "", {})

    def shown_record_for(self, employee: Employee) -> CompensationRecord | None:
        """Current today, else the latest live record: what the detail page shows."""
        return self.current_by_employee.get(employee.pk) or self.latest_by_employee.get(employee.pk)

    def median_gross_for(self, country_code: str) -> Decimal | None:
        """Loaded on the first call, because only the bounds warning needs it."""
        if self._medians is None:
            self._medians = load_country_medians(self.today)
        return self._medians.get(country_code)


def build_context(
    *,
    today: date | None = None,
    legacy_codes: Iterable[str] = (),
    emails: Iterable[str] = (),
    employees: Iterable[Employee] = (),
    rows: Iterable[NormalizedRow] = (),
) -> ValidationContext:
    """The queries behind a validation run: lookups, the matched employees and their records."""
    today = today or today_utc()
    rows = list(rows)
    legacy_codes = {code for code in legacy_codes if code} | {
        row.legacy_code for row in rows if row.legacy_code
    }
    emails = {email.lower() for email in emails if email} | {
        row.email.lower() for row in rows if row.email
    }

    ctx = ValidationContext(
        today=today,
        countries={country.code: country for country in Country.objects.all()},
        departments={},
        components_by_country={},
    )
    for department in Department.objects.all():
        ctx.departments[department.code.lower()] = department
        ctx.departments[department.name.lower()] = department
    components = list(core_queries.active_components())
    for country_code in ctx.countries:
        ctx.components_by_country[country_code] = {
            c.code: c for c in core_queries.components_for_country(country_code, components)
        }

    by_id = {employee.pk: employee for employee in employees}
    by_legacy = {employee.legacy_code: employee for employee in employees if employee.legacy_code}
    code_list = sorted(legacy_codes - set(by_legacy))
    for start in range(0, len(code_list), CHUNK):
        found = Employee.objects.filter(
            legacy_code__in=code_list[start : start + CHUNK]
        ).select_related("country", "department")
        for employee in found:
            by_legacy[employee.legacy_code] = employee
            by_id.setdefault(employee.pk, employee)
    ctx.employees_by_id = by_id
    ctx.employees_by_legacy = by_legacy

    email_list = sorted(emails)
    for start in range(0, len(email_list), CHUNK):
        for email, owner in Employee.objects.filter(
            email__in=email_list[start : start + CHUNK]
        ).values_list("email", "pk"):
            ctx.email_owner[email.lower()] = owner

    ids = list(by_id)
    for start in range(0, len(ids), CHUNK):
        # The author comes along: bulk_apply snapshots these records for its audit entries.
        records = (
            CompensationRecord.objects.filter(
                employee_id__in=ids[start : start + CHUNK], cancelled_at__isnull=True
            )
            .select_related("created_by")
            .order_by("employee_id", "effective_from")
        )
        for record in records:
            ctx.first_by_employee.setdefault(record.employee_id, record)
            ctx.latest_by_employee[record.employee_id] = record
            if record.effective_to is None:
                ctx.open_by_employee[record.employee_id] = record
            if record.effective_from > today:
                ctx.scheduled_by_employee.setdefault(record.employee_id, []).append(
                    record.effective_from
                )
            if record.effective_from <= today and (
                record.effective_to is None or record.effective_to > today
            ):
                ctx.current_by_employee[record.employee_id] = record
    # A future joiner has no current record: the latest one stands in for the comparison.
    comparison = {
        employee_id: ctx.current_by_employee.get(employee_id, latest)
        for employee_id, latest in ctx.latest_by_employee.items()
    }
    record_to_employee = {record.pk: employee_id for employee_id, record in comparison.items()}
    for employee_id, record in comparison.items():
        ctx.current_bonus_by_employee[employee_id] = record.bonus_annual
    record_ids = list(record_to_employee)
    for start in range(0, len(record_ids), CHUNK):
        lines = CompensationLine.objects.filter(
            record_id__in=record_ids[start : start + CHUNK]
        ).values_list("record_id", "component__code", "annual_amount")
        for record_id, code, amount in lines:
            ctx.current_lines_by_employee.setdefault(record_to_employee[record_id], {})[code] = (
                amount
            )

    for row in rows:
        if row.row_number is None:
            continue
        if row.legacy_code:
            ctx.rows_of_legacy.setdefault(row.legacy_code, []).append(row.row_number)
        if row.email:
            ctx.rows_of_email.setdefault(row.email.lower(), []).append(row.row_number)
    return ctx


# Rules. Each takes (row, ctx) and returns messages. Groups follow SPEC F1's order.


def check_legacy_code(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    """A sheet names each employee by the code the legacy system gave them (D48)."""
    if not row.legacy_code:
        return [error("legacy_code", "legacy_required")]
    if len(row.legacy_code) > LEGACY_CODE_MAX:
        return [error("legacy_code", "legacy_too_long", limit=LEGACY_CODE_MAX)]
    return []


def check_email_format(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if not row.email:
        return [error("email", "email_invalid")]
    try:
        django_validate_email(row.email)
    except DjangoValidationError:
        return [error("email", "email_invalid")]
    return []


def check_country_exists(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if row.country_code not in ctx.countries:
        return [error("country_code", "country_unknown", value=row.country_code or "")]
    return []


def check_department_exists(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if ctx.department_for(row.department) is None:
        return [error("department", "department_unknown", value=row.department or "")]
    return []


def check_level_range(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if row.level is None or not 1 <= row.level <= 6:
        return [error("level", "level_range")]
    return []


def check_gender_enum(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if row.gender not in GENDERS:
        return [error("gender", "gender_enum")]
    return []


def check_parse_messages(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    return list(row.parse_messages)


def check_base_required(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    """A blank BASE is missing; a given one below 10, zero included, is too small (D49). A
    negative one is the non-negative rule's."""
    base = row.amounts.get("BASE")
    if base is None:
        return [error("BASE", "base_required")]
    if ZERO <= base < MIN_BASE:
        return [
            error(
                "BASE",
                "base_too_small",
                minimum=format_cents(MIN_BASE),
                value=format_cents(base),
            )
        ]
    return []


def check_amounts_in_range(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    """A line or a bonus above MAX_AMOUNT is impossible pay, and would overflow a total (D49)."""
    over = [
        (code, value)
        for code, value in row.amounts.items()
        if value is not None and value > MAX_AMOUNT
    ]
    if row.bonus_annual is not None and row.bonus_annual > MAX_AMOUNT:
        over.append(("bonus_annual", row.bonus_annual))
    return [
        error(
            code,
            "amount_too_large",
            field=code,
            limit=format_cents(MAX_AMOUNT),
            value=format_cents(value),
        )
        for code, value in over
    ]


def check_bonus_non_negative(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if row.bonus_annual is not None and row.bonus_annual < ZERO:
        return [error("bonus_annual", "bonus_invalid", value=to_str(row.bonus_annual))]
    return []


def check_amounts_non_negative(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    # SPEC section 7 quotes the value as given (`got -5000`), without separators.
    return [
        error(code, "amount_invalid", field=code, value=to_str(value))
        for code, value in row.amounts.items()
        if value is not None and value < ZERO
    ]


def _too_precise(value: Decimal | None) -> bool:
    return value is not None and value == value and value.as_tuple().exponent < -2


def check_decimal_places(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    messages = [
        error(code, "too_many_decimals", field=code)
        for code, value in row.amounts.items()
        if _too_precise(value)
    ]
    if _too_precise(row.bonus_annual):
        messages.append(error("bonus_annual", "too_many_decimals", field="bonus_annual"))
    return messages


def check_components_applicable(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if row.country_code not in ctx.countries:
        return []
    applicable = ctx.components_for(row.country_code)
    return [
        error(code, "component_not_applicable", code=code, country=row.country_code)
        for code, value in row.amounts.items()
        if value is not None and code not in applicable
    ]


def check_email_in_use(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if not row.email:
        return []
    owner = ctx.email_owner.get(row.email.lower())
    employee = ctx.employee_for(row)
    if owner is not None and (employee is None or owner != employee.pk):
        # An unknown legacy_code whose email belongs to someone is a mistyped code, never a
        # second person (D48).
        return [error("email", "email_in_use", code=employee_code_of(owner))]
    return []


def check_country_unchanged(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if employee is not None and row.country_code and row.country_code != employee.country_id:
        return [error("country_code", "country_changed")]
    return []


def check_already_exited(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if (
        employee is not None
        and employee.last_date is not None
        and row.last_date is not None
        and row.last_date != employee.last_date
    ):
        return [error("last_date", "already_exited", date=employee.last_date.isoformat())]
    return []


def check_duplicate_legacy(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    rows = ctx.rows_of_legacy.get(row.legacy_code or "", [])
    if len(rows) > 1:
        return [error("legacy_code", "legacy_duplicate", first=rows[0], second=rows[1])]
    return []


def check_duplicate_email(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    rows = ctx.rows_of_email.get((row.email or "").lower(), [])
    if len(rows) > 1:
        return [error("email", "email_duplicate", first=rows[0], second=rows[1])]
    return []


def check_identity_changed(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if employee is None:
        row.identity_changed = True
        return []
    department = ctx.department_for(row.department)
    current = {
        "full_name": employee.full_name,
        "email": employee.email,
        "department": employee.department_id,
        "designation": employee.designation,
        "level": employee.level,
        "gender": employee.gender,
        "joining_date": employee.joining_date,
        "last_date": employee.last_date,
    }
    proposed = {
        "full_name": row.full_name,
        "email": (row.email or "").lower(),
        "department": department.pk if department else None,
        "designation": row.designation,
        "level": row.level,
        "gender": row.gender,
        "joining_date": row.joining_date,
        "last_date": row.last_date,
    }
    row.identity_changed = any(
        proposed[name] != current[name] for name in IDENTITY_FIELDS if name in row.columns
    )
    return []


def check_amounts_changed(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if employee is None:
        row.amounts_changed = True
        return []
    current_lines = ctx.current_lines_by_employee.get(employee.pk, {})
    current_bonus = ctx.current_bonus_by_employee.get(employee.pk, ZERO)
    codes = set(current_lines) | {code for code, value in row.amounts.items() if value is not None}
    changed = any(
        q2(row.amounts.get(code) if row.amounts.get(code) is not None else Decimal("-1"))
        != q2(current_lines.get(code, Decimal("-1")))
        for code in codes
    )
    changed = changed or q2(row.bonus_annual or ZERO) != q2(current_bonus)
    row.amounts_changed = changed
    return []


def check_noop(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if row.is_new or row.identity_changed or row.amounts_changed:
        return []
    row.noop = True
    return [info("row", "noop")]


def _joining(row: NormalizedRow, ctx: ValidationContext) -> date | None:
    if row.joining_date is not None:
        return row.joining_date
    employee = ctx.employee_for(row)
    return employee.joining_date if employee else None


def _exit_requested(row: NormalizedRow, employee: Employee | None) -> bool:
    return (
        employee is not None
        and row.last_date is not None
        and (employee.last_date is None or row.last_date != employee.last_date)
    )


def check_last_date_after_joining(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    joining = _joining(row, ctx)
    if row.last_date is not None and joining is not None and row.last_date < joining:
        return [error("last_date", "last_date_before_joining")]
    return []


def check_joining_before_first_record(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    """A joining_date moved past the first record would leave pay before the employee joined
    (D45). Version 1 cannot be cancelled (D26), so exit and re-create is the way round in v1."""
    employee = ctx.employee_for(row)
    if employee is None or "joining_date" not in row.columns or row.joining_date is None:
        return []
    first = ctx.first_by_employee.get(employee.pk)
    if first is not None and row.joining_date > first.effective_from:
        return [
            error(
                "joining_date",
                "joining_after_first_record",
                date=first.effective_from.isoformat(),
            )
        ]
    return []


def unstarted_only_record(
    employee: Employee, last_date: date, ctx: ValidationContext
) -> CompensationRecord | None:
    """The employee's only live record when it starts after last_date and has never been current.
    An exit before pay starts cancels it rather than waiting on a cancel that version 1 refuses
    (D50). A first record that has been current keeps the last_date rules."""
    first = ctx.first_by_employee.get(employee.pk)
    if first is None or first is not ctx.latest_by_employee.get(employee.pk):
        return None
    if first.effective_from > ctx.today and first.effective_from > last_date:
        return first
    return None


def check_last_date_vs_scheduled(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if not _exit_requested(row, employee):
        return []
    if unstarted_only_record(employee, row.last_date, ctx) is not None:
        return []
    # A first record that has never been current cannot be cancelled (D26), so the message names
    # the revision to cancel, after which the exit cancels the first record itself (D50).
    first = ctx.first_by_employee.get(employee.pk)
    uncancellable = first.effective_from if first and first.effective_from > ctx.today else None
    after = sorted(
        day
        for day in ctx.scheduled_by_employee.get(employee.pk, [])
        if day > row.last_date and day != uncancellable
    )
    if after:
        return [error("last_date", "last_date_scheduled", date=after[0].isoformat())]
    return []


def check_last_date_vs_open_record(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if not _exit_requested(row, employee):
        return []
    open_record = ctx.open_by_employee.get(employee.pk)
    if (
        open_record is not None
        and open_record.effective_from <= ctx.today
        and open_record.effective_from > row.last_date
    ):
        return [
            error(
                "last_date",
                "last_date_before_record",
                date=open_record.effective_from.isoformat(),
            )
        ]
    return []


def check_last_date_cleared(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if (
        employee is not None
        and employee.last_date is not None
        and "last_date" in row.columns
        and row.last_date is None
    ):
        return [error("last_date", "last_date_cleared")]
    return []


def check_effective_from_required(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if not row.is_new and row.amounts_changed and row.effective_from is None:
        return [error("effective_from", "effective_required")]
    return []


def check_effective_from_after_joining(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    joining = _joining(row, ctx)
    if row.effective_from is not None and joining is not None and row.effective_from < joining:
        return [error("effective_from", "effective_before_joining")]
    return []


def check_effective_from_after_latest(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    employee = ctx.employee_for(row)
    if employee is None or not row.amounts_changed or row.effective_from is None:
        return []
    latest = ctx.latest_by_employee.get(employee.pk)
    if latest is not None and row.effective_from <= latest.effective_from:
        return [
            error(
                "effective_from",
                "effective_not_after_latest",
                date=latest.effective_from.isoformat(),
            )
        ]
    return []


def check_revision_after_exit(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    """A revision dated after an exit would reopen a closed history (D36). One dated on or
    before last_date is allowed and ends at last_date + 1."""
    employee = ctx.employee_for(row)
    if not row.amounts_changed or row.effective_from is None:
        return []
    if "last_date" in row.columns:
        exit_day = row.last_date
    else:
        exit_day = employee.last_date if employee is not None else None
    if exit_day is not None and row.effective_from > exit_day:
        return [error("effective_from", "revision_after_exit", date=exit_day.isoformat())]
    return []


def check_effective_from_defaulted(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    if row.is_new and row.effective_from is None and row.joining_date is not None:
        return [info("effective_from", "effective_defaulted", date=row.joining_date.isoformat())]
    return []


def _gross_and_deductions(
    row: NormalizedRow, ctx: ValidationContext
) -> tuple[Decimal, Decimal] | None:
    components = ctx.components_for(row.country_code)
    if not components:
        return None
    gross = row.bonus_annual or ZERO
    deductions = ZERO
    for code, value in row.amounts.items():
        component = components.get(code)
        if component is None or value is None:
            continue
        if component.kind == SalaryComponent.Kind.EARNING:
            gross += value
        elif component.kind == SalaryComponent.Kind.DEDUCTION:
            deductions += value
    return q2(gross), q2(deductions)


def check_bonus_above_base(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    base = row.amounts.get("BASE")
    bonus = row.bonus_annual
    if base is None or bonus is None or bonus <= base:
        return []
    return [
        warning(
            "bonus_annual", "bonus_above_base", bonus=format_cents(bonus), base=format_cents(base)
        )
    ]


def check_deductions_above_base(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    base = row.amounts.get("BASE")
    if base is None:
        return []
    components = ctx.components_for(row.country_code)
    return [
        warning(
            code,
            "deduction_above_base",
            code=code,
            amount=format_cents(value),
            base=format_cents(base),
        )
        for code, value in row.amounts.items()
        if value is not None
        and value > base
        and code in components
        and components[code].kind == SalaryComponent.Kind.DEDUCTION
    ]


def check_deductions_exceed_gross(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    totals = _gross_and_deductions(row, ctx)
    if totals is None:
        return []
    gross, deductions = totals
    if deductions > gross:
        return [warning("gross", "deductions_exceed_gross")]
    return []


def check_gross_vs_country_bounds(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    country = ctx.countries.get(row.country_code or "")
    totals = _gross_and_deductions(row, ctx)
    if country is None or totals is None:
        return []
    gross, _ = totals
    messages = []
    if gross < country.min_gross_annual:
        messages.append(
            warning(
                "gross",
                "gross_below_minimum",
                gross=format_amount(gross),
                currency=country.currency_code,
                country=country.name,
                minimum=format_amount(country.min_gross_annual),
            )
        )
    median = ctx.median_gross_for(country.code)
    if median and gross > median * TEN:
        messages.append(
            warning(
                "gross",
                "gross_above_median",
                gross=format_amount(gross),
                currency=country.currency_code,
                country=country.name,
                median=format_amount(median),
            )
        )
    return messages


Rule = Callable[[NormalizedRow, ValidationContext], list[Message]]


@dataclass(frozen=True)
class RuleSpec:
    fn: Rule
    group: str
    scopes: frozenset[str]


def rule(fn: Rule, group: str, *scopes: str) -> RuleSpec:
    return RuleSpec(fn, group, frozenset(scopes))


RULES: list[RuleSpec] = [
    rule(check_legacy_code, "structure", "import"),
    rule(check_email_format, "structure", "import", "identity"),
    rule(check_country_exists, "structure", "import", "identity"),
    rule(check_department_exists, "structure", "import", "identity"),
    rule(check_level_range, "structure", "import", "identity"),
    rule(check_gender_enum, "structure", "import", "identity"),
    rule(check_parse_messages, "structure", "import"),
    rule(check_base_required, "structure", "import", "record"),
    rule(check_bonus_non_negative, "structure", "import", "record"),
    rule(check_amounts_non_negative, "structure", "import", "record"),
    rule(check_amounts_in_range, "structure", "import", "record"),
    rule(check_decimal_places, "structure", "import", "record"),
    rule(check_components_applicable, "structure", "import", "record"),
    rule(check_email_in_use, "references", "import", "identity"),
    rule(check_country_unchanged, "references", "import", "identity"),
    rule(check_already_exited, "references", "import", "exit"),
    rule(check_duplicate_legacy, "duplicates", "import"),
    rule(check_duplicate_email, "duplicates", "import"),
    rule(check_identity_changed, "changes", "import"),
    rule(check_amounts_changed, "changes", "import"),
    rule(check_noop, "noop", "import"),
    rule(check_last_date_after_joining, "dates", "import", "identity", "exit"),
    rule(check_joining_before_first_record, "dates", "import", "identity"),
    rule(check_last_date_vs_scheduled, "dates", "import", "exit"),
    rule(check_last_date_vs_open_record, "dates", "import", "exit"),
    rule(check_last_date_cleared, "dates", "import"),
    rule(check_effective_from_required, "dates", "import", "record"),
    rule(check_effective_from_after_joining, "dates", "import", "record"),
    rule(check_effective_from_after_latest, "dates", "import", "record"),
    rule(check_revision_after_exit, "dates", "import", "record"),
    rule(check_effective_from_defaulted, "dates", "import", "record"),
    rule(check_deductions_exceed_gross, "warnings", "import", "record"),
    rule(check_bonus_above_base, "warnings", "import", "record"),
    rule(check_deductions_above_base, "warnings", "import", "record"),
    rule(check_gross_vs_country_bounds, "warnings", "import", "record"),
]

CONFLICT_CODES = {"already_exited", "last_date_scheduled", "revision_after_exit"}


def run_rules(row: NormalizedRow, ctx: ValidationContext, scope: str) -> list[Message]:
    row.is_new = ctx.employee_for(row) is None
    messages: list[Message] = []
    for spec in RULES:
        if scope not in spec.scopes:
            continue
        if row.noop and spec.group == "dates":
            continue
        if spec.group == "warnings" and not row.is_new and not row.amounts_changed:
            continue
        messages.extend(spec.fn(row, ctx))
    return messages


def validate_row(row: NormalizedRow, ctx: ValidationContext) -> list[Message]:
    """Every rule, in F1's order, for one import row."""
    return run_rules(row, ctx, "import")


def worst_severity(messages: Iterable[Message]) -> str:
    severities = {message.severity for message in messages}
    if "error" in severities:
        return "error"
    if "warning" in severities:
        return "warning"
    return "valid"


def errors_of(messages: Iterable[Message]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for message in messages:
        if message.severity == "error":
            errors.setdefault(message.field, []).append(message.message)
    return errors


def raise_for_errors(messages: Sequence[Message]) -> list[Message]:
    """Raise Conflict for a state conflict, Invalid for any other error, else return warnings."""
    for message in messages:
        if message.severity == "error" and message.code in CONFLICT_CODES:
            raise Conflict(message.message)
    errors = errors_of(messages)
    if errors:
        raise Invalid(errors)
    return [message for message in messages if message.severity == "warning"]


# API entry points: the same rules over a row built from plain values.


def row_from_identity(identity: Mapping[str, Any], employee: Employee | None) -> NormalizedRow:
    columns = frozenset(identity)
    return NormalizedRow(
        legacy_code=identity.get("legacy_code"),
        employee_id=employee.pk if employee else None,
        full_name=_or_existing(identity, "full_name", employee),
        email=_or_existing(identity, "email", employee),
        department=_department_value(identity, employee),
        designation=_or_existing(identity, "designation", employee),
        level=_or_existing(identity, "level", employee),
        country_code=identity.get("country_code") or (employee.country_id if employee else None),
        gender=_or_existing(identity, "gender", employee),
        joining_date=_or_existing(identity, "joining_date", employee),
        last_date=identity.get("last_date") if employee is None else employee.last_date,
        columns=columns,
        present=frozenset(name for name in columns if identity.get(name) not in (None, "")),
    )


def _or_existing(identity: Mapping[str, Any], name: str, employee: Employee | None):
    if name in identity:
        return identity[name]
    return getattr(employee, name, None) if employee else None


def _department_value(identity: Mapping[str, Any], employee: Employee | None) -> str | None:
    if "department" in identity:
        return identity["department"]
    return employee.department.code if employee else None


# The API never sets either code: the database numbers every employee, and only an import
# that creates one records its legacy_code (D48).
SYSTEM_CODES = {"employee_code": "code_assigned", "legacy_code": "legacy_import_only"}


def refuse_codes(values: Mapping[str, Any], employee: Employee | None = None) -> None:
    """A create or an edit through the API that carries either code is a 400, whatever value it
    holds, so a client cannot believe it set one. An edit cannot move the employee to another
    country either (SPEC F3). Every refusal comes back in the one 400."""
    errors = {name: [msg(key)] for name, key in SYSTEM_CODES.items() if name in values}
    if (
        employee is not None
        and "country_code" in values
        and values["country_code"] != employee.country_id
    ):
        errors["country_code"] = [msg("country_fixed")]
    if errors:
        raise Invalid(errors)


def validate_identity(
    identity: Mapping[str, Any], ctx: ValidationContext, *, employee: Employee | None = None
) -> list[Message]:
    """Create (employee None) or edit. Raises Invalid, returns warnings."""
    row = row_from_identity(identity, employee)
    return raise_for_errors(run_rules(row, ctx, "identity"))


def row_from_record(
    *,
    employee: Employee | None,
    country_code: str,
    joining_date: date,
    effective_from: date | None,
    bonus_annual: Decimal,
    lines: Mapping[str, Decimal],
    last_date: date | None = None,
) -> NormalizedRow:
    columns = {"effective_from", "bonus_annual", *lines}
    if last_date is not None:
        columns.add("last_date")
    row = NormalizedRow(
        employee_id=employee.pk if employee else None,
        country_code=country_code,
        joining_date=joining_date,
        last_date=last_date,
        effective_from=effective_from,
        bonus_annual=bonus_annual,
        amounts=dict(lines),
        columns=frozenset(columns),
    )
    row.amounts_changed = True
    row.identity_changed = False
    return row


def validate_record(
    ctx: ValidationContext,
    *,
    employee: Employee | None,
    country_code: str,
    joining_date: date,
    effective_from: date | None,
    bonus_annual: Decimal,
    lines: Mapping[str, Decimal],
    last_date: date | None = None,
) -> list[Message]:
    """A first record (employee None) or a revision. Raises Conflict or Invalid, returns warnings.

    `last_date` is the exit date of a new employee whose history is being written in bulk.
    """
    row = row_from_record(
        employee=employee,
        country_code=country_code,
        joining_date=joining_date,
        effective_from=effective_from,
        bonus_annual=bonus_annual,
        lines=lines,
        last_date=last_date,
    )
    return raise_for_errors(run_rules(row, ctx, "record"))


def validate_exit(
    employee: Employee, last_date: date, ctx: ValidationContext
) -> CompensationRecord | None:
    """Exit rules in F3's precedence. 409 for conflicts, 400 for the rest. Returns the unstarted
    only record the exit cancels (D50), else None."""
    if employee.last_date is not None:
        raise Conflict(msg("already_exited", date=employee.last_date.isoformat()))
    row = NormalizedRow(
        employee_id=employee.pk,
        country_code=employee.country_id,
        joining_date=employee.joining_date,
        last_date=last_date,
        columns=frozenset({"last_date"}),
        present=frozenset({"last_date"}),
    )
    row.is_new = False
    for spec in RULES:
        if "exit" not in spec.scopes:
            continue
        for message in spec.fn(row, ctx):
            if message.code in CONFLICT_CODES:
                raise Conflict(message.message)
            raise Invalid({message.field: [message.message]})
    return unstarted_only_record(employee, last_date, ctx)
