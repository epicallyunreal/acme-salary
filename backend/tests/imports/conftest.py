from datetime import date
from decimal import Decimal

import pytest

from apps.compensation import services as compensation
from apps.compensation.services import RecordInput
from tests.factories import EmployeeFactory
from tests.imports.sheets import LINES


@pytest.fixture
def staff(lookups):
    """Seven people from the legacy system, each paid from joining on 2024-03-01."""
    people = {}
    for number, name in enumerate(
        [
            "Asha Rao",
            "Ben Shah",
            "Chloe Iyer",
            "Dev Nair",
            "Esha Pillai",
            "Farah Khan",
            "Gita Menon",
        ]
    ):
        first = name.split()[0].lower()
        employee = EmployeeFactory(
            full_name=name,
            email=f"{first}@acme.example",
            legacy_code=f"HR-1000{number + 1}",
            joining_date=date(2024, 3, 1),
        )
        compensation.add_first_record(employee, RecordInput(None, Decimal("0"), "", LINES))
        people[first] = employee
    return people
