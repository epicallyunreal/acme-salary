"""The generator is a pure function of (count, seed) and respects the profile rules."""

from datetime import date, timedelta

from apps.compensation.validators import CODE_PATTERN
from seed import profiles
from seed.generator import april_firsts, ascii_slug, generate, lines_for

COUNTRIES = {spec.code: spec for spec in profiles.COUNTRIES}


def test_same_seed_same_entries_and_a_different_seed_differs():
    first = list(generate(20, 42))
    again = list(generate(20, 42))
    other = list(generate(20, 7))

    assert [e.identity for e in first] == [e.identity for e in again]
    assert [e.records for e in first] == [e.records for e in again]
    assert [e.identity["full_name"] for e in first] != [e.identity["full_name"] for e in other]


def test_codes_emails_and_dates_follow_the_rules():
    entries = list(generate(60, 42))

    codes = [e.identity["employee_code"] for e in entries]
    assert codes == [f"ACME-{n:06d}" for n in range(1, 61)]
    assert all(CODE_PATTERN.match(code) for code in codes)
    emails = [e.identity["email"] for e in entries]
    assert len(set(emails)) == 60
    assert all(email.endswith("@acme.example") and email.isascii() for email in emails)
    start, end = profiles.JOINING_RANGE
    for entry in entries:
        identity = entry.identity
        assert start <= identity["joining_date"] <= end
        if identity["last_date"] is not None:
            assert identity["joining_date"] + timedelta(days=30) <= identity["last_date"]
            assert identity["last_date"] <= profiles.REFERENCE_DATE
        assert identity["country_code"] in COUNTRIES
        assert 1 <= identity["level"] <= 6
        assert identity["designation"]


def test_records_are_the_joining_record_plus_at_most_three_raises_in_order():
    for entry in generate(60, 42):
        records = entry.records
        assert 1 <= len(records) <= 4
        assert records[0].effective_from == entry.identity["joining_date"]
        dates = [record.effective_from for record in records]
        assert dates == sorted(dates) and len(set(dates)) == len(dates)
        for record in records[1:]:
            assert (record.effective_from.month, record.effective_from.day) == (4, 1)
            if entry.identity["last_date"] is not None:
                assert record.effective_from <= entry.identity["last_date"]
        country = COUNTRIES[entry.identity["country_code"]]
        allowed = {"BASE", "TAX", "EMPLOYER_CONTRIBUTION", *country.components}
        for record in records:
            assert set(record.lines) == allowed
            assert all(amount >= 0 for amount in record.lines.values())
            assert record.lines["BASE"] % profiles.BASE_ROUNDING == 0


def test_lines_for_india_follow_the_shares():
    country = COUNTRIES["IN"]
    lines = lines_for(country, 3, profiles.BASE_ROUNDING * 14500, 0, {})

    assert lines["HRA"] == 580000
    assert lines["ALLOWANCES"] == 362500
    assert lines["TAX"] == 478500  # 20 percent of gross 2,392,500
    assert lines["EMPLOYER_CONTRIBUTION"] == 174000


def test_start_number_offsets_the_codes():
    entries = list(generate(2, 42, start_number=10001))

    assert [e.identity["employee_code"] for e in entries] == ["ACME-010001", "ACME-010002"]


def test_april_firsts():
    assert april_firsts(date(2024, 3, 1), date(2026, 10, 6)) == [
        date(2024, 4, 1),
        date(2025, 4, 1),
        date(2026, 4, 1),
    ]
    assert april_firsts(date(2024, 4, 1), date(2026, 10, 6)) == [date(2025, 4, 1), date(2026, 4, 1)]
    assert april_firsts(date(2026, 5, 1), date(2026, 10, 6)) == []


def test_ascii_slug():
    assert ascii_slug("Jürgen") == "jurgen"
    assert ascii_slug("O'Neil-Smith") == "oneilsmith"
    assert ascii_slug("张") == "user"
