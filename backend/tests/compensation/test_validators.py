"""A passing and a failing case per rule in SPEC section 7: field, severity and full text."""

from datetime import date
from decimal import Decimal

import pytest

from apps.compensation import validators as v
from apps.compensation.validators import NormalizedRow, build_context, validate_row
from apps.core.exceptions import Conflict, Invalid
from tests.factories import CompensationRecordFactory, EmployeeFactory, department

pytestmark = pytest.mark.django_db

TEMPLATE_COLUMNS = frozenset(
    {
        "EmployeeID",
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


def new_row(**overrides) -> NormalizedRow:
    values = dict(
        row_number=2,
        employee_code="ACME-000001",
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


@pytest.fixture
def existing(lookups):
    """ACME-000010, joined 2024-03-01, current record from 2025-04-01 with the India lines."""
    employee = EmployeeFactory(
        employee_code="ACME-000010",
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


def matched_row(employee, **overrides) -> NormalizedRow:
    values = dict(
        employee_code=employee.employee_code,
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


@pytest.mark.parametrize("code", ["", None, "ACME-1", "acme-000001", "EMP-000001"])
def test_employee_code_must_match_the_pattern(lookups, code):
    found = messages(new_row(employee_code=code))

    assert_message(
        found,
        "code_invalid",
        "EmployeeID",
        "error",
        "EmployeeID is required and must match ACME-NNNNNN",
    )


def test_a_blank_code_is_allowed_when_the_server_assigns_it(lookups):
    assert (
        find(messages(new_row(employee_code=None, allow_blank_code=True)), "code_invalid") is None
    )


@pytest.mark.parametrize("email", ["", "not-an-email", "a@b"])
def test_email_must_be_a_valid_address(lookups, email):
    assert_message(
        messages(new_row(email=email)),
        "email_invalid",
        "email",
        "error",
        "email is not a valid address",
    )


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


@pytest.mark.parametrize("base", [None, Decimal("0")])
def test_base_is_required(lookups, base):
    amounts = dict(INDIA_LINES, BASE=base)

    assert_message(
        messages(new_row(amounts=amounts)), "base_required", "BASE", "error", "BASE is required"
    )


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
    assert (
        find(messages(new_row(country_code="US", amounts=blank)), "component_not_applicable")
        is None
    )


# Identity references


def test_email_in_use_by_another_employee(existing):
    assert_message(
        messages(new_row(email="existing@acme.example")),
        "email_in_use",
        "email",
        "error",
        "email already belongs to ACME-000010",
    )
    assert find(messages(matched_row(existing)), "email_in_use") is None


def test_country_cannot_change_through_import(existing):
    assert_message(
        messages(matched_row(existing, country_code="US", amounts={"BASE": Decimal("100000")})),
        "country_changed",
        "country_code",
        "error",
        "country change is not supported by import",
    )


def test_a_different_last_date_on_an_exited_employee_is_a_conflict(existing):
    existing.last_date = date(2026, 6, 30)
    existing.save()

    assert_message(
        messages(matched_row(existing, last_date=date(2026, 7, 31))),
        "already_exited",
        "last_date",
        "error",
        "employee already exited on 2026-06-30",
    )
    assert (
        find(messages(matched_row(existing, last_date=date(2026, 6, 30))), "already_exited") is None
    )


# Duplicates within the file


def test_duplicate_employee_code_marks_both_rows(lookups):
    first = new_row(row_number=41)
    second = new_row(row_number=388, email="other@acme.example")
    ctx = build_context(rows=[first, second])

    for row in (first, second):
        assert_message(
            validate_row(row, ctx),
            "code_duplicate",
            "EmployeeID",
            "error",
            "Duplicate EmployeeID in rows 41 and 388",
        )


def test_duplicate_email_marks_both_rows(lookups):
    first = new_row(row_number=12)
    second = new_row(row_number=90, employee_code="ACME-000002")
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
    row = matched_row(existing, amounts=dict(INDIA_LINES, BASE=Decimal("1500000")))

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


def test_last_date_before_joining(lookups):
    assert_message(
        messages(new_row(last_date=date(2023, 1, 1))),
        "last_date_before_joining",
        "last_date",
        "error",
        "last_date precedes joining_date",
    )


def test_last_date_before_a_scheduled_revision(existing):
    current = existing.compensation_records.get()
    current.effective_to = date(2027, 4, 1)
    current.save()
    CompensationRecordFactory(employee=existing, effective_from=date(2027, 4, 1), lines=INDIA_LINES)

    assert_message(
        messages(matched_row(existing, last_date=date(2026, 12, 31))),
        "last_date_scheduled",
        "last_date",
        "error",
        "scheduled revision on 2027-04-01 must be cancelled before exit",
    )
    assert (
        find(messages(matched_row(existing, last_date=date(2027, 6, 30))), "last_date_scheduled")
        is None
    )


def test_last_date_before_the_current_record(existing):
    assert_message(
        messages(matched_row(existing, last_date=date(2025, 3, 15))),
        "last_date_before_record",
        "last_date",
        "error",
        "last_date precedes the current record (effective 2025-04-01)",
    )
    assert (
        find(messages(matched_row(existing, last_date=date(2025, 4, 1))), "last_date_before_record")
        is None
    )


def test_clearing_last_date_is_not_supported(existing):
    existing.last_date = date(2026, 6, 30)
    existing.save()

    assert_message(
        messages(matched_row(existing, last_date=None)),
        "last_date_cleared",
        "last_date",
        "error",
        "clearing last_date is not supported by import",
    )
    without_column = matched_row(existing, last_date=None, columns=TEMPLATE_COLUMNS - {"last_date"})
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
    raised = dict(INDIA_LINES, BASE=Decimal("1500000"))

    assert_message(
        messages(matched_row(existing, amounts=raised, effective_from=date(2025, 4, 1))),
        "effective_not_after_latest",
        "effective_from",
        "error",
        "effective_from must be after 2025-04-01 (latest record)",
    )
    next_day = matched_row(existing, amounts=raised, effective_from=date(2025, 4, 2))
    assert find(messages(next_day), "effective_not_after_latest") is None


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


def test_warnings_are_skipped_when_a_matched_row_leaves_amounts_alone(lookups):
    low = EmployeeFactory(
        employee_code="ACME-000020", email="low@acme.example", joining_date=date(2024, 3, 1)
    )
    CompensationRecordFactory(
        employee=low, effective_from=date(2024, 3, 1), lines={"BASE": Decimal("300000")}
    )

    found = messages(matched_row(low, department="sales", amounts={"BASE": Decimal("300000")}))

    assert found == []


def test_worst_severity():
    assert v.worst_severity([]) == "valid"
    assert v.worst_severity([v.info("x", "noop")]) == "valid"
    assert (
        v.worst_severity([v.warning("x", "deductions_exceed_gross"), v.info("x", "noop")])
        == "warning"
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


def test_validate_exit_precedence(existing):
    ctx = build_context(employees=[existing])

    assert v.validate_exit(existing, date(2026, 10, 31), ctx) is None
    with pytest.raises(Invalid):
        v.validate_exit(existing, date(2024, 1, 1), ctx)
    with pytest.raises(Invalid):
        v.validate_exit(existing, date(2025, 3, 15), ctx)

    existing.last_date = date(2026, 6, 30)
    existing.save()
    ctx = build_context(employees=[existing])
    with pytest.raises(Conflict, match="already exited on 2026-06-30"):
        v.validate_exit(existing, date(2026, 7, 31), ctx)


def test_validate_exit_refuses_while_a_scheduled_revision_follows(existing):
    current = existing.compensation_records.get()
    current.effective_to = date(2027, 4, 1)
    current.save()
    CompensationRecordFactory(employee=existing, effective_from=date(2027, 4, 1), lines=INDIA_LINES)
    ctx = build_context(employees=[existing])

    with pytest.raises(
        Conflict, match="scheduled revision on 2027-04-01 must be cancelled before exit"
    ):
        v.validate_exit(existing, date(2026, 12, 31), ctx)
