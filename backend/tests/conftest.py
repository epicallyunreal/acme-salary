from datetime import date

import pytest
from freezegun import freeze_time

from tests.factories import UserFactory

TODAY = date(2026, 10, 7)


@pytest.fixture(autouse=True)
def today():
    """Every test runs on 7 October 2026 at 09:00 UTC, so date rules are deterministic."""
    with freeze_time("2026-10-07T09:00:00Z"):
        yield TODAY


@pytest.fixture
def hr_user(db):
    return UserFactory(email="hr@acme.example")


@pytest.fixture
def lookups(db):
    """The six countries, twelve departments and ten components, keyed by country code."""
    from apps.core.models import Country
    from seed.lookups import ensure_lookups

    ensure_lookups()
    return {country.code: country for country in Country.objects.all()}


@pytest.fixture
def rates(lookups):
    """The sixteen seeded rate rows, September and October 2026."""
    from seed.lookups import ensure_rates
    from seed.profiles import REFERENCE_DATETIME

    ensure_rates(at=REFERENCE_DATETIME)
