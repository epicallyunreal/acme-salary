from datetime import date

import freezegun
import pytest
import rest_framework.throttling  # noqa: F401  (the note below)
from django.core.cache import cache
from freezegun import freeze_time
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories import UserFactory

TODAY = date(2026, 10, 7)

# pytest times tests with its own clock; frozen, `--durations` reports nonsense.
freezegun.configure(extend_ignore_list=["_pytest."])

# DRF binds `SimpleRateThrottle.timer` to `time.time` when first imported. Imported above, before
# any test freezes time, it keeps the real clock; under a freeze it would bind freezegun's fake,
# a plain function that then takes `self`, and every throttled request would raise.


@pytest.fixture(autouse=True)
def today():
    """Every test runs on 7 October 2026 at 09:00 UTC, so date rules are deterministic."""
    with freeze_time("2026-10-07T09:00:00Z"):
        yield TODAY


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """The login throttle counts in the process cache; every test starts with an empty one."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def hr_user(db):
    return UserFactory(email="hr@acme.example")


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def api(hr_user):
    """An APIClient carrying the HR Manager's access token."""
    client = APIClient()
    token = RefreshToken.for_user(hr_user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


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
