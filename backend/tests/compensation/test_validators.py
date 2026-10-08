"""A passing and a failing case per rule in SPEC section 7: field, severity and full text."""

from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from apps.compensation import services
from apps.compensation import validators as v
from apps.compensation.messages import msg
from apps.compensation.services import RecordInput
from apps.compensation.validators import NormalizedRow, build_context, validate_row
from apps.core.exceptions import Conflict, Invalid
from apps.employees import services as employees
from tests.factories import CompensationRecordFactory, EmployeeFactory, department

pytestmark = pytest.mark.django_db

TEMPLATE_COLUMNS = frozenset(
    {
        "legacy_code",
        "full_name",
        "email",
        "department",
        "designation",
        "level",
        "country_code",
        "gender",
        "joining_date",
        "last_date",
        "effective_from",
        "bonus_annual",
        "BASE",
        "HRA",
        "ALLOWANCES",
        "TAX",
        "EMPLOYER_CONTRIBUTION",
    }
)
INDIA_LINES = {
    "BASE": Decimal("1450000"),
    "HRA": Decimal("580000"),
    "ALLOWANCES": Decimal("362500"),
    "TAX": Decimal("478500"),
    "EMPLOYER_CONTRIBUTION": Decimal("174000"),
}
RAISED = {**INDIA_LINES, "BASE": Decimal("1500000")}


def new_row(**overrides) -> NormalizedRow:
    values = dict(
        row_number=2,
        legacy_code="HR-10001",
        full_name="Asha Rao",
        email="asha.rao@acme.example",
        department="engineering",
        designation="Senior Engineer",
        level=3,
        country_code="IN",
        gender="female",
        joining_date=date(2024, 3, 1),
        last_date=None,
        effective_from=None,
        bonus_annual=None,
        amounts=dict(INDIA_LINES),
        columns=TEMPLATE_COLUMNS,
        present=TEMPLATE_COLUMNS - {"last_date", "effective_from", "bonus_annual"},
    )
    values.update(overrides)
    return NormalizedRow(**values)


def messages(row, *rows):
    ctx = build_context(rows=[row, *rows])
    return validate_row(row, ctx)


def find(found, code):
    matches = [m for m in found if m.code == code]
    assert len(matches) <= 1, matches
    return matches[0] if matches else None


def assert_message(found, code, field, severity, text):
    message = find(found, code)
    assert message is not None, [m.message for m in found]
    assert (message.field, message.severity, message.message) == (field, severity, text)


def record_input(effective_from, lines=INDIA_LINES) -> RecordInput:
    return RecordInput(effective_from, Decimal("0"), "", lines)


@pytest.fixture
def existing(lookups):
    """Legacy code HR-10010, joined 2024-03-01, current record from 2025-04-01 with the India
    lines."""
    employee = EmployeeFactory(
        legacy_code="HR-10010",
        full_name="Existing Person",
        email="existing@acme.example",
        department=department("engineering"),
        designation="Senior Engineer",
        level=3,
        gender="female",
        joining_date=date(2024, 3, 1),
    )
    CompensationRecordFactory(employee=employee, effective_from=date(2025, 4, 1), lines=INDIA_LINES)
    return employee


@pytest.fixture
def with_scheduled(existing):
    """`existing` with a revision scheduled for 2027-04-01, written by the service."""
    services.revise(existing, record_input(date(2027, 4, 1), RAISED))
    return existing


@pytest.fixture
def exited(existing):
    """`existing` exited on 2026-06-30 through the service."""
    employees.exit_employee(existing, date(2026, 6, 30))
    return existing


@pytest.fixture
def before_pay(lookups):
    """Legacy code HR-10020, joined 2026-09-01, its only record from 2026-12-01: never current."""
    employee = EmployeeFactory(legacy_code="HR-10020", joining_date=date(2026, 9, 1))
    CompensationRecordFactory(
        employee=employee, effective_from=date(2026, 12, 1), lines=INDIA_LINES
    )
    return employee


def matched_row(employee, **overrides) -> NormalizedRow:
    values = dict(
        legacy_code=employee.legacy_code,
        full_name=employee.full_name,
        email=employee.email,
        department=employee.department.code,
        designation=employee.designation,
        level=employee.level,
        gender=employee.gender,
        joining_date=employee.joining_date,
        last_date=employee.last_date,
    )
    values.update(overrides)
    return new_row(**values)


# Structure and types


def test_a_valid_new_row_has_only_the_defaulted_effective_from_info(lookups):
    found = messages(new_row())

    assert [m.code for m in found] == ["effective_defaulted"]
    assert v.worst_severity(found) == "valid"


@pytest.mark.parametrize("code", ["", None])
def test_a_sheet_row_needs_a_legacy_code(lookups, code):
    assert_message(
        messages(new_row(legacy_code=code)),
        "legacy_required",
        "legacy_code",
        "error",
        "legacy_code is required",
    )


def test_a_legacy_code_is_free_text_up_to_32_characters(lookups):
    for fine in ("HR 58213", "acme-17", "x" * 32):
        assert find(messages(new_row(legacy_code=fine)), "legacy_too_long") is None

    assert_message(
        messages(new_row(legacy_code="x" * 33)),
        "legacy_too_long",
        "legacy_code",
        "error",
        "legacy_code is longer than 32 characters",
    )


@pytest.mark.parametrize("email", ["not-an-email", "a@b"])
def test_email_must_be_a_valid_address(lookups, email):
    assert_message(
        messages(new_row(email=email)),
        "email_invalid",
        "email",
        "error",
        "email is not a valid address",
    )


PRESENT = TEMPLATE_COLUMNS - {"last_date", "effective_from", "bonus_annual"}


@pytest.mark.parametrize("name", v.REQUIRED_CELLS)
def test_a_blank_required_cell_is_reported_once_and_by_no_other_rule(lookups, name):
    found = messages(new_row(**{name: None}, present=PRESENT - {name}))

    assert [(m.code, m.severity, m.message) for m in found if m.field == name] == [
        ("cell_required", "error", f"{name} is required")
    ]


def test_a_create_that_leaves_out_a_required_field_is_refused(lookups):
    """A new employee needs every required field, named or not. An edit needs only the fields it
    names, as test_validate_identity_for_an_edit_checks_only_the_given_fields shows."""
    identity = {
        "full_name": "Asha Rao",
        "email": "asha.rao@acme.example",
        "department": "engineering",
        "level": 2,
        "country_code": "IN",
        "gender": "female",
        "joining_date": date(2026, 11, 1),
    }

    with pytest.raises(Invalid) as excinfo:
        v.validate_identity(identity, build_context())

    assert excinfo.value.errors == {"designation": ["designation is required"]}


def test_a_message_repeats_at_most_64_characters_of_a_value():
    """A cell can hold 100,000 characters, and messages are stored on every staged row (D56)."""
    whole = msg("date_invalid", field="joining_date", value="1" * 64)
    cut = msg("date_invalid", field="joining_date", value="1" * 65)

    assert whole == f"joining_date is not a valid date: {'1' * 64}"
    assert cut == f"joining_date is not a valid date: {'1' * 63}\u2026"


def test_unknown_country(lookups):
    assert_message(
        messages(new_row(country_code="XX")),
        "country_unknown",
        "country_code",
        "error",
        "Unknown country_code: XX",
    )


def test_department_matches_by_code_or_name_and_rejects_the_rest(lookups):
    assert find(messages(new_row(department="customer-support")), "department_unknown") is None
    assert find(messages(new_row(department="Customer Support")), "department_unknown") is None
    assert_message(
        messages(new_row(department="Growth")),
        "department_unknown",
        "department",
        "error",
        "Unknown department: Growth",
    )


@pytest.mark.parametrize("level", [0, 7, None])
def test_level_must_be_1_to_6(lookups, level):
    assert_message(
        messages(new_row(level=level)),
        "level_range",
        "level",
        "error",
        "level must be between 1 and 6",
    )


def test_gender_must_be_in_the_enum(lookups):
    assert_message(
        messages(new_row(gender="x")),
        "gender_enum",
        "gender",
        "error",
        "gender must be one of female, male, other, undisclosed",
    )


def test_parse_messages_from_the_parser_are_re_emitted(lookups):
    parsed = v.error("joining_date", "date_invalid", field="joining_date", value="31/02/2024")

    assert_message(
        messages(new_row(joining_date=None, parse_messages=[parsed])),
        "date_invalid",
        "joining_date",
        "error",
        "joining_date is not a valid date: 31/02/2024",
    )


def test_base_is_required(lookups):
    amounts = dict(INDIA_LINES, BASE=None)

    assert_message(
        messages(new_row(amounts=amounts)), "base_required", "BASE", "error", "BASE is required"
    )


@pytest.mark.parametrize(("base", "shown"), [(Decimal("0"), "0.00"), (Decimal("5"), "5.00")])
def test_base_must_be_at_least_ten(lookups, base, shown):
    assert_message(
        messages(new_row(amounts=dict(INDIA_LINES, BASE=base))),
        "base_too_small",
        "BASE",
        "error",
        f"BASE must be at least 10.00, got {shown}",
    )
    assert (
        find(messages(new_row(amounts=dict(INDIA_LINES, BASE=Decimal("10")))), "base_too_small")
        is None
    )


def test_an_amount_above_the_cap_is_an_error(lookups):
    """Errors are for impossible values (D49)."""
    over = new_row(
        amounts=dict(INDIA_LINES, HRA=Decimal("12000000000")), bonus_annual=Decimal("10000000000")
    )
    at_cap = new_row(amounts=dict(INDIA_LINES, HRA=v.MAX_AMOUNT), bonus_annual=v.MAX_AMOUNT)

    found = messages(over)

    assert [(m.field, m.severity, m.message) for m in found if m.code == "amount_too_large"] == [
        ("HRA", "error", "HRA must be at most 9,999,999,999.99, got 12,000,000,000.00"),
        (
            "bonus_annual",
            "error",
            "bonus_annual must be at most 9,999,999,999.99, got 10,000,000,000.00",
        ),
    ]
    assert find(messages(at_cap), "amount_too_large") is None


def test_the_cap_keeps_every_total_inside_its_column(lookups):
    """Derived from the components and the column, so adding a component or narrowing a column
    cannot silently make a total overflow (D49)."""
    from apps.compensation.models import CompensationRecord
    from apps.core.models import Country, SalaryComponent

    column = CompensationRecord._meta.get_field("gross_annual")
    largest = Decimal(10) ** (column.max_digits - column.decimal_places) - Decimal("0.01")
    for country in Country.objects.all():
        kinds = Counter(
            component.kind
            for component in SalaryComponent.objects.filter(is_active=True)
            if component.country_id in (None, country.code)
        )
        gross = (kinds["earning"] + 1) * v.MAX_AMOUNT  # the bonus is an earning too
        total_cost = gross + kinds["employer_contribution"] * v.MAX_AMOUNT
        lowest_net = -kinds["deduction"] * v.MAX_AMOUNT
        assert max(gross, total_cost, -lowest_net) <= largest, country.code


def test_a_bonus_above_base_warns(lookups):
    found = messages(new_row(bonus_annual=Decimal("1500000")))

    assert_message(
        found,
        "bonus_above_base",
        "bonus_annual",
        "warning",
        "bonus_annual 1,500,000.00 is above BASE 1,450,000.00",
    )
    assert find(messages(new_row(bonus_annual=Decimal("1450000"))), "bonus_above_base") is None


def test_a_deduction_above_base_warns(lookups):
    found = messages(new_row(amounts=dict(INDIA_LINES, TAX=Decimal("1500000"))))

    assert_message(
        found,
        "deduction_above_base",
        "TAX",
        "warning",
        "TAX 1,500,000.00 is above BASE 1,450,000.00",
    )
    assert find(messages(new_row()), "deduction_above_base") is None


def test_bonus_must_be_non_negative(lookups):
    assert_message(
        messages(new_row(bonus_annual=Decimal("-1"))),
        "bonus_invalid",
        "bonus_annual",
        "error",
        "bonus_annual must be a non-negative number, got -1",
    )
    assert find(messages(new_row(bonus_annual=Decimal("0"))), "bonus_invalid") is None


def test_a_negative_amount_names_the_field_and_value(lookups):
    amounts = dict(INDIA_LINES, BASE=Decimal("-5000"))

    assert_message(
        messages(new_row(amounts=amounts)),
        "amount_invalid",
        "BASE",
        "error",
        "BASE must be a non-negative number, got -5000",
    )


def test_more_than_two_decimal_places_is_an_error(lookups):
    amounts = dict(INDIA_LINES, BASE=Decimal("1450000.005"))

    assert_message(
        messages(new_row(amounts=amounts)),
        "too_many_decimals",
        "BASE",
        "error",
        "BASE has more than 2 decimal places",
    )
    assert (
        find(
            messages(new_row(amounts=dict(INDIA_LINES, BASE=Decimal("1450000.50")))),
            "too_many_decimals",
        )
        is None
    )
    assert_message(
        messages(new_row(bonus_annual=Decimal("0.001"))),
        "too_many_decimals",
        "bonus_annual",
        "error",
        "bonus_annual has more than 2 decimal places",
    )


def test_a_component_that_does_not_apply_to_the_country_is_an_error_even_at_zero(lookups):
    us = {"BASE": Decimal("100000"), "HRA": Decimal("0"), "TAX": Decimal("20000")}

    assert_message(
        messages(new_row(country_code="US", amounts=us)),
        "component_not_applicable",
        "HRA",
        "error",
        "HRA is not a component for US",
    )
    blank = {"BASE": Decimal("100000"), "HRA": None}
    found = messages(new_row(country_code="US", amounts=blank))
    assert find(found, "component_not_applicable") is None


# Identity references


def test_email_in_use_by_another_employee(existing):
    """An unknown legacy_code whose email belongs to someone is a mistyped code, never a second
    person (D48)."""
    assert_message(
        messages(new_row(email="existing@acme.example")),
        "email_in_use",
        "email",
        "error",
        f"email already belongs to ACME-{existing.pk}",
    )
    assert find(messages(matched_row(existing)), "email_in_use") is None


def test_country_cannot_change_through_import(existing):
    row = matched_row(existing, country_code="US", amounts={"BASE": Decimal("100000")})

    assert_message(
        messages(row),
        "country_changed",
        "country_code",
        "error",
        "country change is not supported by import",
    )


def test_a_different_last_date_on_an_exited_employee_is_a_conflict(exited):
    assert_message(
        messages(matched_row(exited, last_date=date(2026, 7, 31))),
        "already_exited",
        "last_date",
        "error",
        "employee already exited on 2026-06-30",
    )
    assert (
        find(messages(matched_row(exited, last_date=date(2026, 6, 30))), "already_exited") is None
    )


# Duplicates within the file


def test_duplicate_legacy_code_marks_both_rows(lookups):
    first = new_row(row_number=41)
    second = new_row(row_number=388, email="other@acme.example")
    ctx = build_context(rows=[first, second])

    for row in (first, second):
        assert_message(
            validate_row(row, ctx),
            "legacy_duplicate",
            "legacy_code",
            "error",
            "Duplicate legacy_code in rows 41 and 388",
        )


def test_duplicate_email_marks_both_rows(lookups):
    first = new_row(row_number=12)
    second = new_row(row_number=90, legacy_code="HR-10002")
    ctx = build_context(rows=[first, second])

    for row in (first, second):
        assert_message(
            validate_row(row, ctx),
            "email_duplicate",
            "email",
            "error",
            "Duplicate email in rows 12 and 90",
        )


# Amounts changed, no-op, and the date rules


def test_an_identical_row_is_a_noop_and_skips_the_date_rules(existing):
    row = matched_row(existing, effective_from=date(2020, 1, 1))

    found = messages(row)

    assert row.noop is True
    assert [m.code for m in found] == ["noop"]
    assert_message(found, "noop", "row", "info", "No changes, row will be skipped on apply")


def test_an_identity_change_alone_is_not_a_noop_and_needs_no_effective_from(existing):
    row = matched_row(existing, department="sales")

    found = messages(row)

    assert (row.identity_changed, row.amounts_changed, row.noop) == (True, False, False)
    assert found == []


def test_changed_amounts_need_an_effective_from(existing):
    row = matched_row(existing, amounts=RAISED)

    found = messages(row)

    assert row.amounts_changed is True
    assert_message(
        found,
        "effective_required",
        "effective_from",
        "error",
        "effective_from is required when amounts change",
    )


def test_a_changed_bonus_counts_as_changed_amounts(existing):
    row = matched_row(existing, bonus_annual=Decimal("10000"), effective_from=date(2026, 11, 1))

    messages(row)

    assert row.amounts_changed is True


@pytest.mark.parametrize("field_name", ["joining_date", "last_date", "effective_from"])
def test_a_date_after_2100_is_an_error_and_the_last_day_of_2100_is_not(lookups, field_name):
    """D53: every date is on or before 2100-12-31, so last_date + 1 day always exists."""
    assert_message(
        messages(new_row(**{field_name: date(2101, 1, 1)})),
        "date_too_late",
        field_name,
        "error",
        f"{field_name} must be on or before 2100-12-31, got 2101-01-01",
    )
    edge = messages(new_row(**{field_name: date(2100, 12, 31)}))
    assert find(edge, "date_too_late") is None


def test_validate_exit_refuses_the_last_representable_date(existing):
    """The exit used to overflow last_date + 1 into a 500 (D53)."""
    ctx = build_context(employees=[existing])

    with pytest.raises(Invalid) as excinfo:
        v.validate_exit(existing, date(9999, 12, 31), ctx)

    assert excinfo.value.errors == {
        "last_date": ["last_date must be on or before 2100-12-31, got 9999-12-31"]
    }


@pytest.mark.parametrize(
    ("field_name", "limit"),
    [
        ("full_name", 120),
        ("email", 254),
        ("designation", 80),
        ("department", 64),
        ("country_code", 64),
        ("gender", 64),
    ],
)
def test_a_text_cell_longer_than_its_column_is_an_error(lookups, field_name, limit):
    """D55: an error, never a cut, and the lookup rules do not repeat the long value back."""
    found = messages(new_row(**{field_name: "x" * (limit + 1)}))

    assert_message(
        found,
        "text_too_long",
        field_name,
        "error",
        f"{field_name} is longer than {limit} characters",
    )
    assert not any("x" * (limit + 1) in message.message for message in found)
    assert find(messages(new_row(**{field_name: "x" * limit})), "text_too_long") is None


def test_last_date_before_joining(lookups):
    assert_message(
        messages(new_row(last_date=date(2023, 1, 1))),
        "last_date_before_joining",
        "last_date",
        "error",
        "last_date precedes joining_date",
    )


def test_last_date_before_a_scheduled_revision(with_scheduled):
    assert_message(
        messages(matched_row(with_scheduled, last_date=date(2026, 12, 31))),
        "last_date_scheduled",
        "last_date",
        "error",
        "scheduled revision on 2027-04-01 must be cancelled before exit",
    )
    later = matched_row(with_scheduled, last_date=date(2027, 6, 30))
    assert find(messages(later), "last_date_scheduled") is None


def test_last_date_before_the_current_record(existing):
    assert_message(
        messages(matched_row(existing, last_date=date(2025, 3, 31))),
        "last_date_before_record",
        "last_date",
        "error",
        "last_date precedes the current record (effective 2025-04-01)",
    )
    same_day = matched_row(existing, last_date=date(2025, 4, 1))
    assert find(messages(same_day), "last_date_before_record") is None


def test_clearing_last_date_is_not_supported(exited):
    assert_message(
        messages(matched_row(exited, last_date=None)),
        "last_date_cleared",
        "last_date",
        "error",
        "clearing last_date is not supported by import",
    )
    without_column = matched_row(exited, last_date=None, columns=TEMPLATE_COLUMNS - {"last_date"})
    assert find(messages(without_column), "last_date_cleared") is None


def test_effective_from_before_joining(lookups):
    assert_message(
        messages(new_row(effective_from=date(2024, 1, 1))),
        "effective_before_joining",
        "effective_from",
        "error",
        "effective_from precedes joining_date",
    )


def test_effective_from_must_be_after_the_latest_record(existing):
    assert_message(
        messages(matched_row(existing, amounts=RAISED, effective_from=date(2025, 4, 1))),
        "effective_not_after_latest",
        "effective_from",
        "error",
        "effective_from must be after 2025-04-01 (latest record)",
    )
    next_day = matched_row(existing, amounts=RAISED, effective_from=date(2025, 4, 2))
    assert find(messages(next_day), "effective_not_after_latest") is None


def test_a_revision_after_the_exit_is_refused_and_one_before_it_is_allowed(exited):
    assert_message(
        messages(matched_row(exited, amounts=RAISED, effective_from=date(2026, 7, 1))),
        "revision_after_exit",
        "effective_from",
        "error",
        "no revision after the exit on 2026-06-30",
    )
    before = matched_row(exited, amounts=RAISED, effective_from=date(2026, 6, 1))
    assert find(messages(before), "revision_after_exit") is None


def test_a_new_employee_without_effective_from_gets_the_joining_date(lookups):
    assert_message(
        messages(new_row()),
        "effective_defaulted",
        "effective_from",
        "info",
        "effective_from defaulted to joining_date 2024-03-01",
    )
    assert find(messages(new_row(effective_from=date(2024, 3, 1))), "effective_defaulted") is None


# Warnings


def test_deductions_above_gross_warn(lookups):
    amounts = {"BASE": Decimal("500000"), "TAX": Decimal("600000")}

    assert_message(
        messages(new_row(amounts=amounts)),
        "deductions_exceed_gross",
        "gross",
        "warning",
        "deductions exceed gross",
    )


def test_gross_below_the_country_minimum_warns(lookups):
    amounts = {"BASE": Decimal("300000")}

    assert_message(
        messages(new_row(amounts=amounts)),
        "gross_below_minimum",
        "gross",
        "warning",
        "gross 300,000 INR is below the India minimum 400,000",
    )


def test_gross_above_ten_times_the_country_median_warns(existing):
    amounts = {"BASE": Decimal("30000000")}

    assert_message(
        messages(new_row(amounts=amounts)),
        "gross_above_median",
        "gross",
        "warning",
        "gross 30,000,000 INR is above ten times the India median 2,392,500",
    )


def test_a_revision_whose_gross_falls_warns_naming_both_figures(existing):
    """D72: the India lines gross 2,392,500.00. One cent under it warns, both figures to two
    decimals with the currency after. The same gross spread differently does not."""
    lower = {**INDIA_LINES, "BASE": Decimal("1449999.99")}
    moved = {**INDIA_LINES, "BASE": Decimal("1449000"), "HRA": Decimal("581000")}

    found = messages(matched_row(existing, effective_from=date(2026, 11, 1), amounts=lower))
    equal = messages(matched_row(existing, effective_from=date(2026, 11, 1), amounts=moved))

    assert_message(
        found,
        "gross_falls",
        "gross",
        "warning",
        "gross falls from 2,392,500.00 to 2,392,499.99 INR",
    )
    assert find(equal, "gross_falls") is None
    assert find(equal, "noop") is None


def test_the_api_and_the_seed_see_the_falling_gross_too(existing):
    """D72: one rule, the record scope the API and the seed's bulk entries run. The API returns
    it as a warning, and a seed entry with it is written, never refused."""
    ctx = build_context(employees=[existing])
    lower = {**INDIA_LINES, "BASE": Decimal("1000000")}

    warnings = v.validate_record(
        ctx,
        employee=existing,
        country_code="IN",
        joining_date=existing.joining_date,
        effective_from=date(2026, 11, 1),
        bonus_annual=Decimal("0"),
        lines=lower,
    )
    result = services.bulk_apply(
        [
            services.BulkEntry(
                ref=1, employee=existing, records=[record_input(date(2026, 11, 1), lower)]
            )
        ],
        source="seed",
        today=date(2026, 10, 7),
    )

    assert [w.message for w in warnings] == ["gross falls from 2,392,500.00 to 1,942,500.00 INR"]
    assert len(result.revised) == 1


def test_an_equal_gross_through_the_record_scope_warns_nothing(existing):
    """The edge the API and the seed share with the import: the same gross again is no fall."""
    warnings = v.validate_record(
        build_context(employees=[existing]),
        employee=existing,
        country_code="IN",
        joining_date=existing.joining_date,
        effective_from=date(2026, 11, 1),
        bonus_annual=Decimal("0"),
        lines=INDIA_LINES,
    )

    assert [w.message for w in warnings] == []


def test_a_row_that_repeats_a_scheduled_revision_is_a_noop(with_scheduled):
    """D72: a generated file imported twice. The row's date and amounts are the scheduled
    revision's, so it changes nothing and the date rules do not run. Another amount on that date
    is still a revision dated on the latest record."""
    repeat = messages(matched_row(with_scheduled, effective_from=date(2027, 4, 1), amounts=RAISED))
    other = messages(
        matched_row(
            with_scheduled,
            effective_from=date(2027, 4, 1),
            amounts={**RAISED, "BASE": Decimal("1600000")},
        )
    )

    assert_message(repeat, "noop", "row", "info", "No changes, row will be skipped on apply")
    assert find(repeat, "effective_not_after_latest") is None
    assert_message(
        other,
        "effective_not_after_latest",
        "effective_from",
        "error",
        "effective_from must be after 2027-04-01 (latest record)",
    )


def test_warnings_are_skipped_when_a_matched_row_leaves_amounts_alone(lookups):
    low = EmployeeFactory(
        legacy_code="HR-10020", email="low@acme.example", joining_date=date(2024, 3, 1)
    )
    CompensationRecordFactory(
        employee=low, effective_from=date(2024, 3, 1), lines={"BASE": Decimal("300000")}
    )

    found = messages(matched_row(low, department="sales", amounts={"BASE": Decimal("300000")}))

    assert found == []


def test_worst_severity():
    assert v.worst_severity([]) == "valid"
    assert v.worst_severity([v.info("x", "noop")]) == "valid"
    assert v.worst_severity([v.warning("x", "deductions_exceed_gross"), v.info("x", "noop")]) == (
        "warning"
    )
    assert (
        v.worst_severity([v.warning("x", "deductions_exceed_gross"), v.error("x", "base_required")])
        == "error"
    )


# API entry points


def test_validate_identity_for_a_create_without_a_code(lookups):
    ctx = build_context(emails=["asha.rao@acme.example"])
    identity = {
        "full_name": "Asha Rao",
        "email": "asha.rao@acme.example",
        "department": "engineering",
        "designation": "Engineer",
        "level": 2,
        "country_code": "IN",
        "gender": "female",
        "joining_date": date(2026, 11, 1),
    }

    assert v.validate_identity(identity, ctx) == []

    with pytest.raises(Invalid) as excinfo:
        v.validate_identity({**identity, "email": "nope", "level": 9}, ctx)
    assert excinfo.value.errors == {
        "email": ["email is not a valid address"],
        "level": ["level must be between 1 and 6"],
    }


def test_validate_identity_checks_a_new_employees_last_date(lookups):
    ctx = build_context()
    identity = {
        "full_name": "Asha Rao",
        "email": "asha.rao@acme.example",
        "department": "engineering",
        "designation": "Engineer",
        "level": 2,
        "country_code": "IN",
        "gender": "female",
        "joining_date": date(2026, 11, 1),
        "last_date": date(2026, 1, 1),
    }

    with pytest.raises(Invalid) as excinfo:
        v.validate_identity(identity, ctx)

    assert excinfo.value.errors == {"last_date": ["last_date precedes joining_date"]}


def test_validate_identity_for_an_edit_checks_only_the_given_fields(existing):
    ctx = build_context(employees=[existing], emails=["existing@acme.example"])

    assert v.validate_identity({"designation": "Lead Engineer"}, ctx, employee=existing) == []


def test_validate_record_for_a_first_record_and_a_revision(existing):
    ctx = build_context(employees=[existing])

    warnings = v.validate_record(
        ctx,
        employee=None,
        country_code="IN",
        joining_date=date(2026, 11, 1),
        effective_from=None,
        bonus_annual=Decimal("0"),
        lines={"BASE": Decimal("300000")},
    )
    assert [w.code for w in warnings] == ["gross_below_minimum"]

    with pytest.raises(Invalid) as excinfo:
        v.validate_record(
            ctx,
            employee=existing,
            country_code="IN",
            joining_date=existing.joining_date,
            effective_from=date(2025, 4, 1),
            bonus_annual=Decimal("0"),
            lines=INDIA_LINES,
        )
    assert excinfo.value.errors == {
        "effective_from": ["effective_from must be after 2025-04-01 (latest record)"]
    }


def test_validate_record_raises_a_conflict_for_a_revision_after_the_exit(exited):
    ctx = build_context(employees=[exited])

    with pytest.raises(Conflict, match="no revision after the exit on 2026-06-30"):
        v.validate_record(
            ctx,
            employee=exited,
            country_code="IN",
            joining_date=exited.joining_date,
            effective_from=date(2026, 7, 1),
            bonus_annual=Decimal("0"),
            lines=RAISED,
        )


def test_validate_exit_precedence(existing):
    ctx = build_context(employees=[existing])

    assert v.validate_exit(existing, date(2026, 10, 31), ctx) is None
    with pytest.raises(Invalid) as before_joining:
        v.validate_exit(existing, date(2024, 1, 1), ctx)
    assert before_joining.value.errors == {"last_date": ["last_date precedes joining_date"]}
    with pytest.raises(Invalid) as before_record:
        v.validate_exit(existing, date(2025, 3, 31), ctx)
    assert before_record.value.errors == {
        "last_date": ["last_date precedes the current record (effective 2025-04-01)"]
    }


def test_validate_exit_refuses_an_exited_employee_whatever_the_date(exited):
    ctx = build_context(employees=[exited])

    for day in (date(2026, 7, 31), date(2026, 6, 30)):
        with pytest.raises(Conflict, match="employee already exited on 2026-06-30"):
            v.validate_exit(exited, day, ctx)


def test_validate_exit_refuses_while_a_scheduled_revision_follows(with_scheduled):
    ctx = build_context(employees=[with_scheduled])

    with pytest.raises(
        Conflict, match="scheduled revision on 2027-04-01 must be cancelled before exit"
    ):
        v.validate_exit(with_scheduled, date(2026, 12, 31), ctx)


def test_the_api_never_sets_either_code():
    """The database numbers every employee and only an import records a legacy_code, so an API
    body carrying either key is a 400 whatever it holds (D48)."""
    v.refuse_codes({"full_name": "New Person"})

    with pytest.raises(Invalid) as excinfo:
        v.refuse_codes({"employee_code": "ACME-17", "legacy_code": None})

    assert excinfo.value.errors == {
        "employee_code": ["employee_code is assigned by the system"],
        "legacy_code": ["legacy_code is set only by an import"],
    }


def test_joining_date_cannot_move_past_the_first_record(existing):
    ctx = build_context(employees=[existing])

    assert v.validate_identity({"joining_date": date(2025, 4, 1)}, ctx, employee=existing) == []
    with pytest.raises(Invalid) as excinfo:
        v.validate_identity({"joining_date": date(2025, 4, 2)}, ctx, employee=existing)

    assert excinfo.value.errors == {
        "joining_date": ["joining_date is after the first record (effective 2025-04-01)"]
    }


def test_an_import_row_cannot_move_joining_date_past_the_first_record(existing):
    moved = find(
        messages(matched_row(existing, joining_date=date(2025, 5, 1))), "joining_after_first_record"
    )
    on_the_day = find(
        messages(matched_row(existing, joining_date=date(2025, 4, 1))),
        "joining_after_first_record",
    )

    assert (moved.field, moved.severity, moved.message) == (
        "joining_date",
        "error",
        "joining_date is after the first record (effective 2025-04-01)",
    )
    assert on_the_day is None


def test_an_exit_before_pay_starts_hands_back_the_record_to_cancel(before_pay):
    """D50: no scheduled-revision conflict, and validate_exit returns the record the exit cancels.
    From the start date on, the exit closes the record as usual."""
    ctx = build_context(employees=[before_pay])
    only = ctx.first_by_employee[before_pay.pk]
    row = matched_row(before_pay, last_date=date(2026, 10, 31))

    assert messages(row) == []
    assert v.validate_exit(before_pay, date(2026, 10, 31), ctx) is only
    assert v.validate_exit(before_pay, date(2026, 12, 1), ctx) is None


@pytest.mark.parametrize(
    ("starts", "cancels"), [(date(2026, 10, 8), True), (date(2026, 10, 7), False)]
)
def test_validate_exit_draws_the_line_at_today(lookups, starts, cancels):
    """Pay from tomorrow has not started and is cancelled; pay from today has, and the 400 holds."""
    employee = EmployeeFactory(joining_date=date(2026, 9, 1))
    CompensationRecordFactory(employee=employee, effective_from=starts, lines=INDIA_LINES)
    ctx = build_context(employees=[employee])
    day_before = date.fromordinal(starts.toordinal() - 1)

    if cancels:
        assert v.validate_exit(employee, day_before, ctx) is ctx.first_by_employee[employee.pk]
    else:
        with pytest.raises(Invalid) as excinfo:
            v.validate_exit(employee, day_before, ctx)
        assert excinfo.value.errors == {
            "last_date": [f"last_date precedes the current record (effective {starts})"]
        }


def test_the_scheduled_conflict_names_a_revision_not_the_first_record(before_pay):
    """Version 1 cannot be cancelled (D26), so the 409 names the revision that can be."""
    services.revise(before_pay, record_input(date(2027, 4, 1), RAISED))
    ctx = build_context(employees=[before_pay])

    assert_message(
        messages(matched_row(before_pay, last_date=date(2026, 10, 31))),
        "last_date_scheduled",
        "last_date",
        "error",
        "scheduled revision on 2027-04-01 must be cancelled before exit",
    )
    assert v.unstarted_only_record(before_pay, date(2026, 10, 31), ctx) is None
