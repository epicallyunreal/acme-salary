from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.core.models import ExchangeRate

pytestmark = pytest.mark.django_db


@pytest.fixture
def rate_row(db):
    return ExchangeRate.objects.create(
        from_currency="INR",
        to_currency="USD",
        rate=Decimal("0.012"),
        effective_from=date(2026, 10, 1),
    )


def test_record_writes_one_entry_with_rendered_snapshots(rate_row, hr_user):
    entry = audit.record(
        "set_rate",
        entity=rate_row,
        actor=hr_user,
        before=None,
        after={"rate": Decimal("0.012"), "effective_from": date(2026, 10, 1)},
    )

    stored = AuditLog.objects.get(pk=entry.pk)
    assert (stored.action, stored.entity_type, stored.entity_id) == (
        "set_rate",
        "exchange_rate",
        rate_row.pk,
    )
    assert stored.actor == hr_user
    assert stored.before is None
    assert stored.after == {"rate": "0.012", "effective_from": "2026-10-01"}
    assert stored.timestamp == datetime(2026, 10, 7, 9, 0, tzinfo=UTC)


def test_at_sets_the_timestamp_for_the_seed(rate_row):
    at = datetime(2026, 10, 6, tzinfo=UTC)

    entry = audit.record("set_rate", entity=rate_row, actor=None, before=None, after={}, at=at)

    assert entry.timestamp == at
    assert entry.actor is None


def test_bulk_record_inserts_every_entry(rate_row):
    entries = [
        audit.build("set_rate", entity=rate_row, before=None, after={"n": i}) for i in range(3)
    ]

    assert audit.bulk_record(entries) == 3
    assert list(AuditLog.objects.order_by("id").values_list("after", flat=True)) == [
        {"n": 0},
        {"n": 1},
        {"n": 2},
    ]
