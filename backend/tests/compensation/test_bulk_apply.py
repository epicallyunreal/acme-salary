"""bulk_apply writes exactly what the single-row services would (DESIGN section 1.4)."""

from datetime import date
from decimal import Decimal

import pytest

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


def audit_of(employee) -> list[tuple[str, str, int | None, int | None]]:
    entries = AuditLog.objects.filter(employee=employee).order_by("id")
    return [
        (
            e.action,
            e.entity_type,
            e.before and e.before.get("version"),
            e.after and e.after.get("version"),
        )
        for e in entries
    ]


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
    assert set(audit_of(single.employee)) == expected
    assert set(audit_of(bulk)) == expected
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


def test_bulk_updates_exits_and_revisions_on_existing_employees(lookups):
    to_update, to_exit, to_revise = (
        EmployeeFactory(joining_date=date(2024, 3, 1)) for _ in range(3)
    )
    for employee in (to_update, to_exit, to_revise):
        services.add_first_record(employee, record_input())

    result = services.bulk_apply(
        [
            BulkEntry(
                ref=1, employee=to_update, identity_changes={"department": "Sales", "level": 4}
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
    assert (to_update.department.code, to_update.level) == ("sales", 4)
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
    assert actions == {to_update.pk: "update", to_exit.pk: "exit"}
    exit_entry = AuditLog.objects.get(action="exit")
    assert exit_entry.before["last_date"] is None
    assert exit_entry.after["last_date"] == "2026-09-30"
    assert exit_entry.after["current_record"]["effective_to"] == "2026-10-01"
    assert exit_entry.before["current_record"]["effective_to"] is None
    revise_entry = AuditLog.objects.filter(action="revise", entity_id=second.pk).get()
    assert (revise_entry.before["version"], revise_entry.before["effective_to"]) == (1, None)
    assert result.audit_entries == 3


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


def test_more_than_a_thousand_rows_are_written_in_chunks(lookups):
    entries = [
        BulkEntry(
            ref=n,
            identity=identity(email=f"person{n}@acme.example"),
            records=[record_input(lines={"BASE": Decimal("500000")})],
        )
        for n in range(1001)
    ]

    result = services.bulk_apply(entries, source="seed")

    assert len(result.created) == 1001
    assert Employee.objects.count() == 1001
    assert CompensationRecord.objects.count() == 1001
    assert AuditLog.objects.count() == 2002
    codes = list(Employee.objects.order_by("employee_code").values_list("employee_code", flat=True))
    assert codes[0] == "ACME-000001"
    assert codes[-1] == "ACME-001001"


def test_chain_records():
    records = [
        record_input(),
        record_input(effective_from=date(2025, 4, 1)),
        record_input(effective_from=date(2026, 4, 1)),
    ]

    chained = chain_records(records, joining_date=date(2024, 3, 1), close_at=None)
    assert [(c.effective_from, c.effective_to) for c in chained] == [
        (date(2024, 3, 1), date(2025, 4, 1)),
        (date(2025, 4, 1), date(2026, 4, 1)),
        (date(2026, 4, 1), None),
    ]
    closed = chain_records(records, joining_date=date(2024, 3, 1), close_at=date(2026, 7, 1))
    assert closed[-1].effective_to == date(2026, 7, 1)

    with pytest.raises(ValueError, match="strictly increasing"):
        chain_records(
            [
                record_input(effective_from=date(2025, 4, 1)),
                record_input(effective_from=date(2025, 4, 1)),
            ],
            joining_date=date(2024, 3, 1),
            close_at=None,
        )
    with pytest.raises(ValueError, match="cannot end"):
        chain_records(records, joining_date=date(2024, 3, 1), close_at=date(2026, 4, 1))
    with pytest.raises(ValueError, match="only the first record"):
        chain_records(
            [record_input(effective_from=date(2024, 3, 1)), record_input()],
            joining_date=date(2024, 3, 1),
            close_at=None,
        )
