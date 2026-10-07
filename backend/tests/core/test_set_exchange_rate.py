from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.audit.models import AuditLog
from apps.core.exceptions import Invalid
from apps.core.models import ExchangeRate
from apps.core.services import set_exchange_rate

pytestmark = pytest.mark.django_db

SEP = date(2026, 9, 1)
OCT = date(2026, 10, 1)


def test_first_rate_for_a_pair_is_open_ended_and_audited():
    row = set_exchange_rate("inr", "usd", Decimal("0.01195"), SEP)

    assert (row.from_currency, row.to_currency, row.effective_to) == ("INR", "USD", None)
    entry = AuditLog.objects.get()
    assert (entry.action, entry.entity_type, entry.entity_id) == (
        "set_rate",
        "exchange_rate",
        row.pk,
    )
    assert entry.before is None
    assert entry.after["rate"] == "0.01195000"
    assert entry.after["effective_from"] == "2026-09-01"


def test_the_next_month_closes_the_previous_row():
    first = set_exchange_rate("INR", "USD", Decimal("0.01195"), SEP)
    second = set_exchange_rate("INR", "USD", Decimal("0.01200"), OCT)

    first.refresh_from_db()
    assert first.effective_to == OCT
    assert second.effective_to is None
    entry = AuditLog.objects.filter(entity_id=second.pk).get()
    assert entry.before["effective_from"] == "2026-09-01"
    assert entry.before["rate"] == "0.01195000"


def test_refuses_a_date_that_is_not_the_first_of_a_month():
    with pytest.raises(Invalid) as excinfo:
        set_exchange_rate("INR", "USD", Decimal("0.012"), date(2026, 10, 15))

    assert excinfo.value.errors == {"effective_from": ["must be the first day of a month"]}


def test_refuses_a_date_before_the_latest_row():
    set_exchange_rate("INR", "USD", Decimal("0.012"), OCT)

    with pytest.raises(Invalid) as excinfo:
        set_exchange_rate("INR", "USD", Decimal("0.011"), SEP)

    assert excinfo.value.errors == {"effective_from": ["on or before the latest row 2026-10-01"]}


def test_the_same_month_needs_replace():
    set_exchange_rate("INR", "USD", Decimal("0.012"), OCT)

    with pytest.raises(Invalid) as excinfo:
        set_exchange_rate("INR", "USD", Decimal("0.013"), OCT)

    assert excinfo.value.errors == {
        "effective_from": ["a rate for October 2026 exists, pass --replace"]
    }


def test_replace_updates_the_month_in_place():
    set_exchange_rate("INR", "USD", Decimal("0.012"), OCT)

    row = set_exchange_rate("INR", "USD", Decimal("0.013"), OCT, replace=True)

    assert ExchangeRate.objects.count() == 1
    assert row.rate == Decimal("0.013")
    entry = AuditLog.objects.order_by("-id").first()
    assert (entry.before["rate"], entry.after["rate"]) == ("0.01200000", "0.01300000")


def test_rate_must_be_positive_and_the_pair_distinct():
    with pytest.raises(Invalid) as excinfo:
        set_exchange_rate("USD", "USD", Decimal("0"), OCT)

    assert set(excinfo.value.errors) == {"to_currency", "rate"}


def test_management_command_records_a_rate_and_reports_bad_input():
    out = StringIO()
    call_command(
        "set_exchange_rate", "INR", "USD", "0.012", "--effective-from", "2026-10-01", stdout=out
    )

    assert out.getvalue().strip() == "1 INR = 0.012 USD from 2026-10-01"
    with pytest.raises(CommandError, match="effective_from"):
        call_command("set_exchange_rate", "INR", "USD", "0.011", "--effective-from", "2026-09-01")
    with pytest.raises(CommandError, match="bad argument"):
        call_command("set_exchange_rate", "INR", "USD", "x", "--effective-from", "2026-11-01")
