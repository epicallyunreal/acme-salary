"""DESIGN section 9's thirty-employee insight fixture, built with the factories.

The rates are the fixture's own, from 2026-10-01: INR to USD 0.0125, EUR to USD 1.25, GBP to USD
1.25 and USD to EUR 0.8. Records start on 2024-01-01 unless stated. Every expected figure in the
insight tests was worked out by hand from this table and is written there as a literal; nothing
here computes one.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from apps.employees.models import Employee
from tests.factories import (
    CompensationRecordFactory,
    EmployeeFactory,
    ExchangeRateFactory,
    country,
    department,
)

RATES_FROM = date(2026, 10, 1)
RECORDS_FROM = date(2024, 1, 1)
JOINED = date(2020, 1, 1)
RATES = (
    ("INR", "USD", "0.0125"),
    ("EUR", "USD", "1.25"),
    ("GBP", "USD", "1.25"),
    ("USD", "EUR", "0.8"),
)


def share(gross: Decimal, fraction: str) -> Decimal:
    return gross * Decimal(fraction)


def us_lines(gross: Decimal) -> dict[str, Decimal]:
    return {"BASE": gross, "TAX": share(gross, "0.2"), "EMPLOYER_CONTRIBUTION": share(gross, "0.1")}


def in_lines(gross: Decimal) -> dict[str, Decimal]:
    return {
        "BASE": share(gross, "0.6"),
        "HRA": share(gross, "0.25"),
        "ALLOWANCES": share(gross, "0.15"),
        "TAX": share(gross, "0.1"),
        "EMPLOYER_CONTRIBUTION": share(gross, "0.12"),
    }


def de_lines(gross: Decimal) -> dict[str, Decimal]:
    return {
        "BASE": gross,
        "SOCIAL_INSURANCE": share(gross, "0.2"),
        "EMPLOYER_CONTRIBUTION": share(gross, "0.2"),
    }


def gb_lines(gross: Decimal) -> dict[str, Decimal]:
    return {
        "BASE": gross,
        "NATIONAL_INSURANCE": share(gross, "0.1"),
        "EMPLOYER_CONTRIBUTION": share(gross, "0.14"),
    }


LINES = {"US": us_lines, "IN": in_lines, "DE": de_lines, "GB": gb_lines}


@dataclass
class Fixture:
    people: dict[str, Employee]

    def __getitem__(self, name: str) -> Employee:
        return self.people[name]


def person(
    name: str,
    code: str,
    gross: int,
    *,
    dept: str,
    gender: str,
    level: int,
    joined: date = JOINED,
    starts: date = RECORDS_FROM,
    last_date: date | None = None,
) -> Employee:
    """One employee with one record of `gross`, closed the day after `last_date` if they left."""
    employee = EmployeeFactory(
        full_name=name,
        country=country(code),
        department=department(dept),
        gender=gender,
        level=level,
        joining_date=joined,
        last_date=last_date,
    )
    CompensationRecordFactory(
        employee=employee,
        lines=LINES[code](Decimal(gross)),
        effective_from=starts,
        effective_to=last_date + timedelta(days=1) if last_date else None,
    )
    return employee


def build_fixture() -> Fixture:
    for source, target, rate in RATES:
        ExchangeRateFactory(
            from_currency=source, to_currency=target, rate=Decimal(rate), effective_from=RATES_FROM
        )
    people: dict[str, Employee] = {}

    us_levels = (1, 1, 2, 2, 3, 3, 4, 4, 5, 6)
    for n in range(1, 11):
        people[f"U{n}"] = person(
            f"U{n}",
            "US",
            100_000 + 10_000 * (n - 1),
            dept="engineering" if n <= 5 else "sales",
            gender="male" if n <= 6 else "female",
            level=us_levels[n - 1],
        )
    people["X1"] = person(
        "X1", "US", 120_000, dept="engineering", gender="male", level=3, last_date=date(2026, 6, 30)
    )

    for i in range(12):
        people[f"I{i + 1}"] = person(
            f"I{i + 1}",
            "IN",
            800_000 + 200_000 * i,
            dept="engineering" if i < 6 else "customer-support",
            gender="male" if i % 2 == 0 else "female",
            level=i % 6 + 1,
        )
    people["X2"] = person(
        "X2",
        "IN",
        500_000,
        dept="customer-support",
        gender="female",
        level=1,
        starts=JOINED,
        last_date=date(2020, 12, 31),
    )

    for n, (gross, gender, level) in enumerate(
        ((60_000, "female", 2), (70_000, "female", 3), (80_000, "male", 4), (90_000, "male", 5)),
        start=1,
    ):
        people[f"D{n}"] = person(
            f"D{n}", "DE", gross, dept="engineering", gender=gender, level=level
        )
    people["D5"] = person(
        "D5",
        "DE",
        100_000,
        dept="engineering",
        gender="male",
        level=3,
        joined=date(2026, 12, 1),
        starts=date(2026, 12, 1),
    )
    people["G1"] = person("G1", "GB", 50_000, dept="finance", gender="female", level=2)

    # U1's revision to 130,000 is scheduled for 2027-01-01, so his first record ends then.
    u1 = people["U1"]
    u1.compensation_records.update(effective_to=date(2027, 1, 1))
    CompensationRecordFactory(
        employee=u1, lines=us_lines(Decimal(130_000)), effective_from=date(2027, 1, 1)
    )
    # I3's revision to 5,000,000 INR was scheduled, then cancelled: it counts nowhere.
    CompensationRecordFactory(
        employee=people["I3"],
        lines=in_lines(Decimal(5_000_000)),
        effective_from=date(2026, 12, 1),
        cancelled_at=datetime(2026, 10, 5, 9, 0, tzinfo=UTC),
    )
    return Fixture(people)
