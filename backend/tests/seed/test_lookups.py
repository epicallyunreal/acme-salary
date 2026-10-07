from datetime import date

import pytest

from apps.core.models import Country, Department, ExchangeRate, SalaryComponent
from seed.lookups import ensure_lookups, ensure_rates

pytestmark = pytest.mark.django_db


def test_ensure_lookups_creates_the_tables_once():
    ensure_lookups()
    ensure_lookups()

    assert Country.objects.count() == 6
    assert Department.objects.count() == 12
    assert SalaryComponent.objects.count() == 10
    assert set(Country.objects.values_list("currency_code", flat=True)) == {
        "INR",
        "USD",
        "GBP",
        "EUR",
        "SGD",
    }


def test_components_are_global_or_per_country(lookups):
    india = set(
        SalaryComponent.objects.filter(country__isnull=True).values_list("code", flat=True)
    ) | set(SalaryComponent.objects.filter(country="IN").values_list("code", flat=True))

    assert india == {"BASE", "HRA", "ALLOWANCES", "TAX", "EMPLOYER_CONTRIBUTION"}
    assert SalaryComponent.objects.filter(country="US").count() == 0
    assert set(SalaryComponent.objects.filter(country="SG").values_list("code", flat=True)) == {
        "AWS",
        "CPF",
    }


def test_ensure_rates_creates_sixteen_rows_once_and_chains_the_months(lookups):
    ensure_rates()
    ensure_rates()

    assert ExchangeRate.objects.count() == 16
    september = ExchangeRate.objects.get(
        from_currency="INR", to_currency="USD", effective_from=date(2026, 9, 1)
    )
    october = ExchangeRate.objects.get(
        from_currency="INR", to_currency="USD", effective_from=date(2026, 10, 1)
    )
    assert september.effective_to == date(2026, 10, 1)
    assert october.effective_to is None
