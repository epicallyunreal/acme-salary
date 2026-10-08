"""Determinism and invariants of seed_data (SPEC section 11 rule 8).

The two tests of 500 active and 250 exited employees are marked slow; the command's contracts
run on every commit.
"""

from collections import Counter
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

from apps.audit.models import AuditLog
from apps.compensation.models import CompensationRecord
from apps.core.models import Country, ExchangeRate
from apps.employees.models import Employee
from seed import profiles
from seed.dump import dump_hash
from seed.management.commands import seed_data as seed_module

GOLDEN = Path(__file__).with_name("golden.txt")

pytestmark = pytest.mark.django_db


def seed(active: int, exited: int = 0, **options) -> str:
    out = StringIO()
    call_command("seed_data", active=active, exited=exited, seed=42, stdout=out, **options)
    return out.getvalue()


@pytest.mark.slow
def test_seed_matches_the_golden_hash_and_a_reset_reproduces_it():
    seed(500, 250)

    assert dump_hash() == GOLDEN.read_text().strip()

    seed(500, 250, reset=True)

    assert dump_hash() == GOLDEN.read_text().strip()
    assert Employee.objects.order_by("id").first().pk == 1
    assert CompensationRecord.objects.order_by("id").first().pk == 1


@pytest.mark.slow
def test_shares_and_invariants():
    seed(500, 250)

    assert Employee.objects.count() == 750
    assert Employee.objects.filter(last_date__isnull=True).count() == 500
    assert Employee.objects.filter(last_date__lt=profiles.REFERENCE_DATE).count() == 250
    assert dict(Counter(Employee.objects.values_list("country_id", flat=True))) == {
        "DE": 81,
        "GB": 99,
        "IN": 327,
        "NL": 62,
        "SG": 32,
        "US": 149,
    }
    assert dict(Counter(Employee.objects.values_list("level", flat=True))) == {
        1: 229,
        2: 186,
        3: 137,
        4: 104,
        5: 66,
        6: 28,
    }
    assert dict(Counter(Employee.objects.values_list("gender", flat=True))) == {
        "female": 343,
        "male": 389,
        "other": 12,
        "undisclosed": 6,
    }
    # Every revision since joining is kept, 583 of them promotions (D64).
    assert CompensationRecord.objects.count() == 2878
    assert CompensationRecord.objects.filter(note__startswith="promotion to L").count() == 583

    for employee in Employee.objects.prefetch_related("compensation_records"):
        records = sorted(employee.compensation_records.all(), key=lambda r: r.effective_from)
        assert records[0].effective_from == employee.joining_date
        assert all(record.cancelled_at is None for record in records)
        for earlier, later in zip(records, records[1:], strict=False):
            assert earlier.effective_to == later.effective_from
        if employee.last_date is None:
            assert records[-1].effective_to is None
        else:
            assert records[-1].effective_to == employee.last_date + timedelta(days=1)
        assert [record.version for record in records] == list(range(1, len(records) + 1))
        # Each promotion names the next level up, the last of them the level now (D64).
        promoted = [int(r.note[-1]) for r in records if r.note.startswith("promotion to L")]
        joined_at = employee.level - len(promoted)
        assert joined_at >= 1 and promoted == list(range(joined_at + 1, employee.level + 1))

    # The database numbered them in joining order, leavers among them, so ACME-1 is the earliest
    # joiner, and each carries its own HR- legacy_code (D48).
    joined = list(Employee.objects.order_by("pk").values_list("joining_date", flat=True))
    assert joined == sorted(joined)
    codes = list(Employee.objects.values_list("legacy_code", flat=True))
    assert len(set(codes)) == 750
    assert all(code and code.startswith("HR-") and len(code) == 8 for code in codes)

    # 750 create entries, 2,878 revise entries and 16 set_rate entries.
    assert AuditLog.objects.count() == 3644
    assert set(AuditLog.objects.values_list("timestamp", flat=True)) == {
        profiles.REFERENCE_DATETIME
    }
    assert ExchangeRate.objects.count() == 16
    assert get_user_model().objects.filter(email=profiles.HR_MANAGER_EMAIL).exists()


def test_if_empty_skips_and_a_bare_rerun_is_refused():
    seed(20, 10)
    hash_before = dump_hash()

    assert "nothing to do" in seed(20, 10, if_empty=True)
    assert dump_hash() == hash_before
    with pytest.raises(CommandError, match="pass --reset"):
        seed(20, 10)


@pytest.mark.parametrize(
    ("active", "exited", "message"),
    [(-1, 0, "0 or more"), (5, -1, "0 or more"), (0, 5, "leavers follow the headcount")],
)
def test_a_negative_count_or_leavers_with_nobody_on_staff_is_refused(active, exited, message):
    """Leavers are placed month by month in proportion to those on staff, so with nobody on staff
    none could be placed, and the command would say it seeded them (D64)."""
    with pytest.raises(CommandError, match=message):
        seed(active, exited)

    assert Employee.objects.count() == 0


def test_reset_and_if_empty_exclude_each_other():
    with pytest.raises(CommandError, match="exclude each other"):
        seed(20, 10, reset=True, if_empty=True)


def test_a_reset_keeps_the_users_and_their_passwords():
    seed(20, 10)
    user_model = get_user_model()
    hr = user_model.objects.get(email=profiles.HR_MANAGER_EMAIL)
    hr.set_password("owner-chosen-password")
    hr.save()

    seed(20, 10, reset=True)

    assert user_model.objects.get(pk=hr.pk).check_password("owner-chosen-password")
    assert user_model.objects.count() == 1
    assert Employee.objects.count() == 30


def test_reset_demo_runs_the_fixed_seed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "seed.management.commands.reset_demo.seed",
        lambda active, exited, seed_value, *, reset, stdout=None: (
            calls.append((active, exited, seed_value, reset)) or 1.5
        ),
    )

    out = StringIO()
    call_command("reset_demo", stdout=out)

    assert calls == [(10000, 5000, 42, True)]
    assert "demo reset in 1.5 s" in out.getvalue()


def test_a_failure_mid_seed_leaves_every_business_table_empty(monkeypatch):
    monkeypatch.setattr(seed_module, "CHUNK", 10)
    real_bulk_apply = seed_module.bulk_apply
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("disk full")
        return real_bulk_apply(*args, **kwargs)

    monkeypatch.setattr(seed_module, "bulk_apply", flaky)

    with pytest.raises(RuntimeError, match="disk full"):
        seed(20, 10)

    assert calls["n"] == 2
    assert Employee.objects.count() == 0
    assert CompensationRecord.objects.count() == 0
    assert AuditLog.objects.count() == 0
    assert ExchangeRate.objects.count() == 0
    assert Country.objects.count() == 0


@pytest.mark.parametrize(
    ("password", "message"),
    [(None, "must be set"), ("password", "too weak"), ("12345678", "too weak")],
)
def test_a_missing_or_weak_seed_password_is_refused(settings, password, message):
    settings.SEED_ADMIN_PASSWORD = password

    with pytest.raises(CommandError, match=message):
        seed(5)

    assert Employee.objects.count() == 0
