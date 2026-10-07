"""bulk_apply writes exactly what the single-row services would (DESIGN section 1.4)."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection

from apps.audit.models import AuditLog
from apps.compensation import services
from apps.compensation.models import CompensationRecord
from apps.compensation.services import BulkEntry, BulkInvalid, RecordInput, chain_records
from apps.employees import services as employees
from apps.employees.models import Employee
from tests.factories import EmployeeFactory

pytestmark = pytest.mark.django_db

LINES = {
    "BASE": Decimal("1450000"),
    "HRA": Decimal("580000"),
    "ALLOWANCES": Decimal("362500"),
    "TAX": Decimal("478500"),
    "EMPLOYER_CONTRIBUTION": Decimal("174000"),
}
RAISED = {**LINES, "BASE": Decimal("1600000")}


def record_input(effective_from=None, bonus="0", note="", lines=LINES) -> RecordInput:
    return RecordInput(effective_from, Decimal(bonus), note, lines)


def identity(email="new@acme.example", **overrides) -> dict:
    values = dict(
        full_name="New Person",
        email=email,
        department="engineering",
        designation="Engineer",
        level=2,
        country_code="IN",
        gender="male",
        joining_date=date(2024, 3, 1),
    )
    values.update(overrides)
    return values


def rows_of(employee) -> list[dict]:
    rows = []
    for record in CompensationRecord.objects.filter(employee=employee).order_by("version"):
        rows.append(
            {
                "version": record.version,
                "effective_from": record.effective_from,
                "effective_to": record.effective_to,
                "gross": record.gross_annual,
                "net": record.net_annual,
                "cost": record.total_cost_annual,
                "bonus": record.bonus_annual,
                "source": record.source,
                "lines": sorted(
                    (line.component.code, line.annual_amount) for line in record.lines.all()
                ),
            }
        )
    return rows


def audit_of(employee) -> set[tuple]:
    entries = AuditLog.objects.filter(employee=employee)
    return {
        (
            e.action,
            e.entity_type,
            e.before and e.before.get("version"),
            e.after and e.after.get("version"),
        )
        for e in entries
    }


@pytest.fixture
def three(lookups):
    """Three employees with a first record from 2024-03-01."""
    people = [EmployeeFactory(joining_date=date(2024, 3, 1)) for _ in range(3)]
    for employee in people:
        services.add_first_record(employee, record_input())
    return people


def test_a_bulk_create_matches_the_single_path(lookups):
    single = employees.create_employee(
        identity(email="single@acme.example"), record_input(bonus="10000")
    )
    services.revise(
        single.employee,
        record_input(effective_from=date(2025, 4, 1), lines=RAISED, bonus="10000"),
        source="ui",
    )

    result = services.bulk_apply(
        [
            BulkEntry(
                ref="r1",
                identity=identity(email="bulk@acme.example"),
                records=[
                    record_input(bonus="10000"),
                    record_input(effective_from=date(2025, 4, 1), lines=RAISED, bonus="10000"),
                ],
            )
        ],
        source="ui",
    )

    bulk = result.created[0]
    assert (single.employee.employee_code, bulk.employee_code) == ("ACME-000001", "ACME-000002")
    assert rows_of(bulk) == rows_of(single.employee)
    expected = {
        ("revise", "compensation_record", None, 1),
        ("create", "employee", None, None),
        ("revise", "compensation_record", 1, 2),
    }
    assert audit_of(single.employee) == expected
    assert audit_of(bulk) == expected
    strip = {"id", "employee", "created_at"}
    single_before = AuditLog.objects.get(
        employee=single.employee, action="revise", after__version=2
    ).before
    bulk_before = AuditLog.objects.get(employee=bulk, action="revise", after__version=2).before
    assert {k: v for k, v in single_before.items() if k not in strip} == {
        k: v for k, v in bulk_before.items() if k not in strip
    }
    assert result.by_ref["r1"]["action"] == "create"
    assert result.by_ref["r1"]["record"].version == 1
    assert result.audit_entries == 3


def test_bulk_create_returns_primary_keys_on_this_sqlite():
    assert connection.features.can_return_rows_from_bulk_insert is True


def test_bulk_updates_exits_and_revisions_on_existing_employees(three, django_assert_num_queries):
    to_update, to_exit, to_revise = three

    # Lookups, the three employees and their records, the email check, three bulk writes,
    # the lines of the superseded records, the audit insert.
    with django_assert_num_queries(17):
        result = services.bulk_apply(
            [
                BulkEntry(
                    ref=1,
                    employee=to_update,
                    identity_changes={
                        "department": "Sales",
                        "level": 4,
                        "email": "Upper@acme.example",
                    },
                ),
                BulkEntry(ref=2, employee=to_exit, last_date=date(2026, 9, 30)),
                BulkEntry(
                    ref=3,
                    employee=to_revise,
                    identity_changes={"designation": "Lead Engineer"},
                    records=[record_input(effective_from=date(2026, 11, 1), lines=RAISED)],
                ),
            ],
            source="import",
        )

    to_update.refresh_from_db()
    assert (to_update.department.code, to_update.level, to_update.email) == (
        "sales",
        4,
        "upper@acme.example",
    )
    assert result.updated == [to_update]
    to_exit.refresh_from_db()
    assert to_exit.last_date == date(2026, 9, 30)
    assert CompensationRecord.objects.get(employee=to_exit).effective_to == date(2026, 10, 1)
    assert result.exited == [to_exit]
    to_revise.refresh_from_db()
    assert to_revise.designation == "Lead Engineer"
    first, second = CompensationRecord.objects.filter(employee=to_revise).order_by("version")
    assert (first.effective_to, second.effective_from, second.effective_to) == (
        date(2026, 11, 1),
        date(2026, 11, 1),
        None,
    )
    assert result.revised == [second]
    assert {ref: slot["action"] for ref, slot in result.by_ref.items()} == {
        1: "update",
        2: "exit",
        3: "revise",
    }
    actions = {
        e.employee_id: e.action for e in AuditLog.objects.filter(action__in=["update", "exit"])
    }
    assert actions == {to_update.pk: "update", to_exit.pk: "exit", to_revise.pk: "update"}
    exit_entry = AuditLog.objects.get(action="exit")
    assert exit_entry.before["last_date"] is None
    assert exit_entry.after["last_date"] == "2026-09-30"
    assert exit_entry.before["current_record"]["effective_to"] is None
    assert exit_entry.after["current_record"]["effective_to"] == "2026-10-01"
    update_entry = AuditLog.objects.get(action="update", employee=to_update)
    assert update_entry.before["current_record"]["version"] == 1
    revise_entry = AuditLog.objects.filter(action="revise", entity_id=second.pk).get()
    assert (revise_entry.before["version"], revise_entry.before["effective_to"]) == (1, None)
    # SPEC F2: the promotion row writes update on the employee, then revise on the record.
    promotion_update = AuditLog.objects.get(action="update", employee=to_revise)
    assert (promotion_update.before["designation"], promotion_update.after["designation"]) == (
        "Senior Engineer",
        "Lead Engineer",
    )
    assert promotion_update.pk < revise_entry.pk
    assert result.audit_entries == 4


def test_a_revise_only_row_writes_one_revise_entry(three):
    employee = three[0]

    result = services.bulk_apply(
        [
            BulkEntry(
                ref=1, employee=employee, records=[record_input(date(2026, 11, 1), lines=RAISED)]
            )
        ],
        source="import",
    )

    assert result.audit_entries == 1
    assert result.by_ref[1]["action"] == "revise"
    assert result.updated == []
    assert AuditLog.objects.filter(employee=employee, action="update").count() == 0


def test_the_update_snapshot_shows_the_current_record_not_a_scheduled_one(three):
    employee = three[0]
    services.revise(employee, record_input(effective_from=date(2027, 4, 1), lines=RAISED))

    services.bulk_apply(
        [BulkEntry(ref=1, employee=employee, identity_changes={"level": 5})], source="import"
    )

    entry = AuditLog.objects.get(action="update")
    assert entry.before["current_record"]["version"] == 1
    assert entry.after["current_record"]["version"] == 1


def test_a_state_conflict_inside_bulk_names_the_entry(three):
    employee = three[0]
    employees.exit_employee(employee, date(2026, 6, 30))

    with pytest.raises(BulkInvalid) as excinfo:
        services.bulk_apply(
            [BulkEntry(ref="again", employee=employee, last_date=date(2026, 7, 31))],
            source="import",
        )

    assert excinfo.value.ref == "again"
    assert excinfo.value.errors == {"detail": ["employee already exited on 2026-06-30"]}


def test_a_revision_after_an_exit_is_refused_in_bulk_too(three):
    employee = three[0]
    employees.exit_employee(employee, date(2026, 6, 30))

    with pytest.raises(BulkInvalid) as excinfo:
        services.bulk_apply(
            [
                BulkEntry(
                    ref=1, employee=employee, records=[record_input(date(2026, 7, 1), lines=RAISED)]
                )
            ],
            source="import",
        )

    assert excinfo.value.errors == {"detail": ["no revision after the exit on 2026-06-30"]}
    assert CompensationRecord.objects.filter(employee=employee).count() == 1


def test_a_revision_before_an_exit_ends_the_day_after_it_in_bulk_as_single(three):
    employee = three[0]
    employees.exit_employee(employee, date(2026, 12, 31))

    services.bulk_apply(
        [
            BulkEntry(
                ref=1, employee=employee, records=[record_input(date(2026, 11, 1), lines=RAISED)]
            )
        ],
        source="import",
    )

    first, second = CompensationRecord.objects.filter(employee=employee).order_by("version")
    assert (first.effective_to, second.effective_from, second.effective_to) == (
        date(2026, 11, 1),
        date(2026, 11, 1),
        date(2027, 1, 1),
    )
    before = AuditLog.objects.get(action="revise", entity_id=second.pk).before
    assert before["effective_to"] == "2027-01-01"


def test_an_invalid_entry_names_its_ref_and_writes_nothing(lookups):
    entries = [
        BulkEntry(ref="ok", identity=identity(email="ok@acme.example"), records=[record_input()]),
        BulkEntry(
            ref="bad",
            identity=identity(email="bad@acme.example", country_code="US"),
            records=[record_input(lines={"BASE": Decimal("100000"), "HRA": Decimal("1")})],
        ),
    ]

    with pytest.raises(BulkInvalid) as excinfo:
        services.bulk_apply(entries, source="seed")

    assert excinfo.value.ref == "bad"
    assert excinfo.value.errors == {"HRA": ["HRA is not a component for US"]}
    assert Employee.objects.count() == 0


def test_a_new_employee_needs_a_first_record(lookups):
    with pytest.raises(BulkInvalid) as excinfo:
        services.bulk_apply([BulkEntry(ref=1, identity=identity())], source="seed")

    assert excinfo.value.errors == {"records": ["a new employee needs a first record"]}


def test_a_new_employee_with_a_last_date_before_joining_is_refused(lookups):
    with pytest.raises(BulkInvalid) as excinfo:
        services.bulk_apply(
            [
                BulkEntry(
                    ref=1, identity=identity(last_date=date(2024, 1, 1)), records=[record_input()]
                )
            ],
            source="seed",
        )

    assert excinfo.value.errors == {"last_date": ["last_date precedes joining_date"]}


def test_a_new_employee_with_a_last_date_gets_a_closed_history(lookups):
    result = services.bulk_apply(
        [
            BulkEntry(
                ref=1,
                identity=identity(last_date=date(2025, 6, 30)),
                records=[
                    record_input(),
                    record_input(effective_from=date(2025, 4, 1), lines=RAISED),
                ],
            )
        ],
        source="seed",
    )

    first, second = CompensationRecord.objects.filter(employee=result.created[0]).order_by(
        "version"
    )
    assert (first.effective_from, first.effective_to) == (date(2024, 3, 1), date(2025, 4, 1))
    assert (second.effective_from, second.effective_to) == (date(2025, 4, 1), date(2025, 7, 1))


def test_a_history_running_past_the_exit_is_refused(lookups):
    with pytest.raises(BulkInvalid) as excinfo:
        services.bulk_apply(
            [
                BulkEntry(
                    ref=1,
                    identity=identity(last_date=date(2025, 3, 31)),
                    records=[
                        record_input(),
                        record_input(effective_from=date(2025, 4, 1), lines=RAISED),
                    ],
                )
            ],
            source="seed",
        )

    assert excinfo.value.errors == {"detail": ["no revision after the exit on 2025-03-31"]}


def test_more_than_a_thousand_rows_are_written_in_chunks(lookups, django_assert_num_queries):
    entries = [
        BulkEntry(
            ref=n,
            identity=identity(email=f"person{n}@acme.example"),
            records=[record_input(lines={"BASE": Decimal("500000")})],
        )
        for n in range(1001)
    ]

    with django_assert_num_queries(22):
        result = services.bulk_apply(entries, source="seed")

    assert len(result.created) == 1001
    assert all(employee.pk is not None for employee in result.created)
    assert Employee.objects.count() == 1001
    assert CompensationRecord.objects.count() == 1001
    assert AuditLog.objects.count() == 2002
    codes = list(Employee.objects.order_by("employee_code").values_list("employee_code", flat=True))
    assert codes[0] == "ACME-000001"
    assert codes[-1] == "ACME-001001"


THREE = [
    record_input(),
    record_input(effective_from=date(2025, 4, 1)),
    record_input(effective_from=date(2026, 4, 1)),
]


def test_chain_records_ends_each_record_where_the_next_begins():
    chained = chain_records(THREE, joining_date=date(2024, 3, 1), close_at=None)

    assert [(c.effective_from, c.effective_to) for c in chained] == [
        (date(2024, 3, 1), date(2025, 4, 1)),
        (date(2025, 4, 1), date(2026, 4, 1)),
        (date(2026, 4, 1), None),
    ]


def test_chain_records_closes_the_last_record_at_close_at():
    chained = chain_records(THREE, joining_date=date(2024, 3, 1), close_at=date(2026, 7, 1))

    assert chained[-1].effective_to == date(2026, 7, 1)


@pytest.mark.parametrize(
    ("records", "close_at", "message"),
    [
        (
            [
                record_input(effective_from=date(2025, 4, 1)),
                record_input(effective_from=date(2025, 4, 1)),
            ],
            None,
            "strictly increasing",
        ),
        (THREE, date(2026, 4, 1), "cannot end"),
        (
            [record_input(effective_from=date(2024, 3, 1)), record_input()],
            None,
            "only the first record",
        ),
    ],
)
def test_chain_records_rejects_bad_input(records, close_at, message):
    with pytest.raises(ValueError, match=message):
        chain_records(records, joining_date=date(2024, 3, 1), close_at=close_at)
