"""factory_boy factories. Small by construction: the minimum rows a test needs, never the seed."""

from datetime import date
from decimal import Decimal

import factory
from django.contrib.auth import get_user_model

from apps.audit.models import AuditLog
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.compensation.services import compute_totals
from apps.core.models import Country, Department, ExchangeRate, SalaryComponent
from apps.employees.models import Employee
from apps.imports.models import ImportBatch, ImportRow


def ensure_lookups_loaded() -> None:
    if not Country.objects.exists():
        from seed.lookups import ensure_lookups

        ensure_lookups()


def country(code: str) -> Country:
    ensure_lookups_loaded()
    return Country.objects.get(code=code)


def department(code: str) -> Department:
    ensure_lookups_loaded()
    return Department.objects.get(code=code)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    email = factory.Sequence(lambda n: f"user{n}@acme.example")
    password = factory.django.Password("correct-horse-battery")


class EmployeeFactory(factory.django.DjangoModelFactory):
    """An Indian engineer who joined on 1 January 2020. Codes start at ACME-900001 so they never
    collide with seeded ones."""

    class Meta:
        model = Employee

    employee_code = factory.Sequence(lambda n: f"ACME-9{n + 1:05d}")
    full_name = factory.Sequence(lambda n: f"Employee {n + 1}")
    email = factory.Sequence(lambda n: f"employee{n + 1}@acme.example")
    gender = "female"
    department = factory.LazyFunction(lambda: department("engineering"))
    designation = "Senior Engineer"
    level = 3
    country = factory.LazyFunction(lambda: country("IN"))
    joining_date = date(2020, 1, 1)
    last_date = None


class CompensationRecordFactory(factory.django.DjangoModelFactory):
    """A record with lines given as a mapping; totals are computed by the service.

    `lines` defaults to a single BASE line of 1,000,000 in the employee's currency."""

    class Meta:
        model = CompensationRecord

    lines = {"BASE": Decimal("1000000")}
    employee = factory.SubFactory(EmployeeFactory)
    version = factory.LazyAttribute(
        lambda o: CompensationRecord.objects.filter(employee=o.employee).count() + 1
    )
    currency_code = factory.LazyAttribute(lambda o: o.employee.country.currency_code)
    bonus_annual = Decimal("0")
    effective_from = factory.LazyAttribute(lambda o: o.employee.joining_date)
    effective_to = None
    source = "ui"
    note = ""

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        lines = {code: Decimal(str(amount)) for code, amount in kwargs.pop("lines").items()}
        components = SalaryComponent.objects.in_bulk(lines.keys(), field_name="code")
        totals = compute_totals(lines, kwargs.get("bonus_annual", Decimal("0")), components)
        record = model_class.objects.create(
            gross_annual=totals.gross,
            net_annual=totals.net,
            total_cost_annual=totals.total_cost,
            **kwargs,
        )
        CompensationLine.objects.bulk_create(
            [
                CompensationLine(record=record, component=components[code], annual_amount=amount)
                for code, amount in lines.items()
            ]
        )
        return record


class ExchangeRateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExchangeRate

    from_currency = "INR"
    to_currency = "USD"
    rate = Decimal("0.012")
    effective_from = date(2026, 10, 1)
    effective_to = None


class ImportBatchFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImportBatch

    file_name = "upload.xlsx"
    file_size = 1024
    status = "review"


class ImportRowFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImportRow

    batch = factory.SubFactory(ImportBatchFactory)
    row_number = factory.Sequence(lambda n: n + 2)
    status = "valid"
    validation_status = "valid"
    action = "create"


class AuditLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuditLog

    action = "create"
    entity_type = "employee"
    entity_id = 1
