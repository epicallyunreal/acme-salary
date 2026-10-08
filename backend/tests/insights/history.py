"""Two years of history for `trend` and `cost-bridge` (D62), built with the factories.

Every record is a single BASE line, so its total cost is its gross. EUR converts to USD at 1.10
until 30 September 2026 and at 1.25 from 1 October, so on 7 October 2026 every date converts at
1.25. Every expected figure in the tests was worked out by hand from the table below and is
written there as a literal; nothing here computes one.

| Who | Country | Pay | Dates |
| --- | --- | --- | --- |
| A1 | US | 100,000, then 110,000 | joined 2020, raised 1 Apr 2026 |
| A2 | US | 80,000, then 88,000 | joined 2020, raised 1 Apr 2026 |
| A3 | US | 60,000 | joined 2020 |
| A4 | DE | 40,000 EUR, then 44,000 EUR | joined 2020, raised 1 Apr 2026 |
| A5 | DE | 48,000 EUR | joined 2020 |
| X1 | US | 55,000 | joined 2020, left 31 Mar 2025 |
| B1 | US | 65,000 | joined 10 Jan 2025 |
| J1 | US | 70,000 | joined 15 Nov 2025 |
| J2 | US | 50,000 | joined 1 Feb 2026 |
| J3 | DE | 32,000 EUR | joined 15 Jun 2026 |
| J4 | US | 90,000 | joined 30 Sep 2026 |
| J5 | US | 45,000 | joined 1 Oct 2026 |

`with_leavers` adds three who leave during the bridge's year: L1 (US, 30,000, left 31 Jan 2026),
L2 (US, 36,000, left 31 May 2026) and L3 (DE, 24,000 EUR, left 31 Aug 2026).
"""

from datetime import date, timedelta
from decimal import Decimal

from apps.core import services as core_services
from apps.employees.models import Employee
from tests.factories import CompensationRecordFactory, EmployeeFactory, country, department

LONG_AGO = date(2020, 1, 1)
RAISED = date(2026, 4, 1)


def hire(
    name: str,
    code: str,
    pay: int,
    *,
    joined: date = LONG_AGO,
    raised_to: int | None = None,
    left: date | None = None,
) -> Employee:
    """One employee on a single BASE line, raised on 1 April 2026 when `raised_to` is given and
    closed the day after `left`."""
    employee = EmployeeFactory(
        full_name=name,
        country=country(code),
        department=department("engineering"),
        joining_date=joined,
        last_date=left,
    )
    first_ends = RAISED if raised_to else (left + timedelta(days=1) if left else None)
    CompensationRecordFactory(
        employee=employee,
        lines={"BASE": Decimal(pay)},
        effective_from=joined,
        effective_to=first_ends,
    )
    if raised_to:
        CompensationRecordFactory(
            employee=employee, lines={"BASE": Decimal(raised_to)}, effective_from=RAISED
        )
    return employee


def build_history(*, with_leavers: bool = False) -> dict[str, Employee]:
    core_services.set_exchange_rate("EUR", "USD", Decimal("1.10"), date(2024, 1, 1))
    core_services.set_exchange_rate("EUR", "USD", Decimal("1.25"), date(2026, 10, 1))
    people = {
        "A1": hire("A1", "US", 100_000, raised_to=110_000),
        "A2": hire("A2", "US", 80_000, raised_to=88_000),
        "A3": hire("A3", "US", 60_000),
        "A4": hire("A4", "DE", 40_000, raised_to=44_000),
        "A5": hire("A5", "DE", 48_000),
        "X1": hire("X1", "US", 55_000, left=date(2025, 3, 31)),
        "B1": hire("B1", "US", 65_000, joined=date(2025, 1, 10)),
        "J1": hire("J1", "US", 70_000, joined=date(2025, 11, 15)),
        "J2": hire("J2", "US", 50_000, joined=date(2026, 2, 1)),
        "J3": hire("J3", "DE", 32_000, joined=date(2026, 6, 15)),
        "J4": hire("J4", "US", 90_000, joined=date(2026, 9, 30)),
        "J5": hire("J5", "US", 45_000, joined=date(2026, 10, 1)),
    }
    if with_leavers:
        people["L1"] = hire("L1", "US", 30_000, left=date(2026, 1, 31))
        people["L2"] = hire("L2", "US", 36_000, left=date(2026, 5, 31))
        people["L3"] = hire("L3", "DE", 24_000, left=date(2026, 8, 31))
    return people
