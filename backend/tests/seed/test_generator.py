"""The generator is a pure function of its counts and seed and respects the profile rules (D64)."""

import random
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.compensation.services import RecordInput
from apps.core.dates import REPORTING_START, months_before
from seed import profiles
from seed.generator import (
    LEAVER_LEVEL_WEIGHTS,
    Career,
    april_firsts,
    ascii_slug,
    base_at_review,
    days,
    draw_career,
    experience_range,
    generate,
    headcounts,
    last_april,
    leavers_by_month,
    legacy_codes,
    lines_for,
    month_ends,
    ordered_entries,
    reviews,
    window,
    with_cutoff,
)

COUNTRIES = {spec.code: spec for spec in profiles.COUNTRIES}
END = profiles.REFERENCE_DATE
DEPARTMENTS = {spec.code: spec for spec in profiles.DEPARTMENTS}
PROMOTION = re.compile(r"promotion to L(\d)")


def entries(active=60, exited=30, seed=42):
    return list(generate(active, seed, exited=exited))


def bases(entry):
    return [record.lines["BASE"] for record in entry.records]


def test_same_seed_same_entries_and_a_different_seed_differs():
    first, again, other = entries(20, 10), entries(20, 10), entries(20, 10, seed=7)

    assert [e.identity for e in first] == [e.identity for e in again]
    assert [e.records for e in first] == [e.records for e in again]
    assert [e.identity["full_name"] for e in first] != [e.identity["full_name"] for e in other]


def test_the_counts_are_exact_and_the_leavers_come_after_those_who_stay():
    people = entries(60, 30)

    assert [e.identity["last_date"] is None for e in people] == [True] * 60 + [False] * 30
    assert [e.ref for e in people] == list(range(1, 91))


def test_emails_and_dates_follow_the_rules():
    people = entries()

    assert all("employee_code" not in e.identity for e in people)
    emails = [e.identity["email"] for e in people]
    assert len(set(emails)) == 90
    assert all(email.endswith("@acme.example") and email.isascii() for email in emails)
    for entry in people:
        identity = entry.identity
        assert profiles.HISTORY_START <= identity["joining_date"] <= profiles.REFERENCE_DATE
        if identity["last_date"] is not None:
            assert identity["joining_date"] + timedelta(days=30) <= identity["last_date"]
            assert identity["last_date"] < profiles.REFERENCE_DATE
        assert identity["country_code"] in COUNTRIES
        assert 1 <= identity["level"] <= 6
        assert identity["designation"] == profiles.designation(
            DEPARTMENTS[identity["department"]], identity["level"]
        )


def test_a_record_at_joining_at_every_review_since_and_on_the_cut_off():
    """Every revision is kept (D64). Everyone employed on 1 April 2020 has a record starting that
    day, a review or the cut-off's own (D70)."""
    for entry in entries():
        end = entry.identity["last_date"] or profiles.REFERENCE_DATE
        joined = entry.identity["joining_date"]
        expected = set(reviews(joined, end))
        if joined <= REPORTING_START <= end:
            expected.add(REPORTING_START)
        assert [record.effective_from for record in entry.records] == sorted(expected)
        country = COUNTRIES[entry.identity["country_code"]]
        allowed = {"BASE", "TAX", "EMPLOYER_CONTRIBUTION", *country.components}
        for record in entry.records:
            assert set(record.lines) == allowed
            assert all(amount >= 0 for amount in record.lines.values())
            assert record.lines["BASE"] % profiles.BASE_ROUNDING == 0


def test_promotions_move_one_level_at_a_time_up_to_the_level_now():
    for entry in entries():
        notes = [record.note for record in entry.records]
        assert notes[0] == "joining"
        promoted = [int(m.group(1)) for note in notes[1:] if (m := PROMOTION.fullmatch(note))]
        assert all(
            note in ("annual raise", profiles.CUTOFF_NOTE) or PROMOTION.fullmatch(note)
            for note in notes[1:]
        )
        level = entry.identity["level"]
        joined_at = level - len(promoted)
        assert joined_at >= 1
        assert promoted == list(range(joined_at + 1, level + 1))


def test_a_raise_is_3_to_8_percent_a_promotion_12_to_20_and_the_cut_off_no_change():
    """Each base is rounded to 100, so the ratio may stray from its range by 100 either way. The
    cut-off's revision is the one that changes nothing, lines and bonus alike (D70)."""
    for entry in entries():
        for previous, record, before, after in zip(
            entry.records, entry.records[1:], bases(entry), bases(entry)[1:], strict=False
        ):
            if record.note == profiles.CUTOFF_NOTE:
                assert (record.lines, record.bonus_annual) == (
                    previous.lines,
                    previous.bonus_annual,
                )
                continue
            low, high = (
                profiles.PROMOTION_RANGE
                if record.note.startswith("promotion")
                else profiles.RAISE_RANGE
            )
            slack = Decimal(100) / before
            assert Decimal(str(low)) - slack <= after / before - 1 <= Decimal(str(high)) + slack


def test_the_ladder_in_days():
    assert [days(years) for years in (3, 5, 6, 12, 30)] == [1096, 1826, 2192, 4383, 10958]
    assert [window(level) for level in (2, 3, 4, 5, 6)] == [
        (1096, 1096),
        (1826, 2191),
        (2557, 2921),
        (3653, 4017),
        (4383, 4747),
    ]
    assert [experience_range(level) for level in (1, 2, 3, 4, 5, 6)] == [
        (0, 1095),
        (1096, 2190),
        (1826, 2920),
        (2557, 4016),
        (3653, 4746),
        (4383, 10957),
    ]


@pytest.mark.parametrize(
    "last_date", [None, date(2015, 2, 3), date(2020, 4, 15), date(2026, 9, 30)]
)
@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_a_career_ends_at_its_level_and_fits_the_ladder(level, last_date):
    """Drawn a hundred times: the experience at the last review is inside the level's range,
    the level path never falls and reaches `level` there, years at ACME never exceed
    experience, and a leaver stays at least 30 days."""
    rng = random.Random(level)
    end = last_date or profiles.REFERENCE_DATE
    for _ in range(100):
        career = draw_career(rng, level, last_date)
        schedule = reviews(career.joining_date, end)
        review = schedule[-1]
        low, high = experience_range(level)
        assert low <= (review - career.experience_start).days <= high
        assert career.level_on(review) == level
        assert career.experience_start <= career.joining_date
        assert profiles.HISTORY_START <= career.joining_date <= end
        if last_date is not None:
            assert (last_date - career.joining_date).days >= 30
        path = [career.level_on(day) for day in schedule]
        assert path == sorted(path)
        assert all(b - a <= 1 for a, b in zip(path, path[1:], strict=False))
        for promoted_to, point in career.points.items():
            first, last = window(promoted_to)
            assert first <= point <= last


def test_a_first_april_within_six_months_of_joining_is_skipped():
    """Joined from 1 October to 31 March, the April that follows brings no raise and no
    promotion. 30 September is six months and a day before it (D70)."""
    end = profiles.REFERENCE_DATE

    assert reviews(date(2025, 9, 30), end) == [date(2025, 9, 30), date(2026, 4, 1)]
    assert reviews(date(2025, 10, 1), end) == [date(2025, 10, 1)]
    assert reviews(date(2026, 3, 31), end) == [date(2026, 3, 31)]
    assert reviews(date(2019, 12, 15), end)[:3] == [
        date(2019, 12, 15),
        date(2021, 4, 1),
        date(2022, 4, 1),
    ]
    assert reviews(date(2026, 4, 1), end) == [date(2026, 4, 1)]


def test_the_cut_off_repeats_the_pay_of_a_joiner_of_the_six_months_before_it():
    """Of everyone employed on 1 April 2020, only a joiner of October 2019 to March 2020 has no
    review that day, and gets the cut-off's revision instead (D70)."""
    people = entries(200, 100)
    split = [e for e in people if any(r.note == profiles.CUTOFF_NOTE for r in e.records)]

    assert split
    for entry in split:
        joined = entry.identity["joining_date"]
        assert months_before(REPORTING_START, 6) <= joined < REPORTING_START
        (at,) = [i for i, r in enumerate(entry.records) if r.note == profiles.CUTOFF_NOTE]
        cutoff, running = entry.records[at], entry.records[at - 1]
        assert cutoff.effective_from == REPORTING_START
        assert (cutoff.lines, cutoff.bonus_annual) == (running.lines, running.bonus_annual)
    for entry in people:
        end = entry.identity["last_date"] or profiles.REFERENCE_DATE
        if entry.identity["joining_date"] <= REPORTING_START <= end:
            assert REPORTING_START in {record.effective_from for record in entry.records}


def pay(day, base, note="annual raise"):
    return RecordInput(
        effective_from=day, bonus_annual=Decimal(1000), note=note, lines={"BASE": Decimal(base)}
    )


def test_the_cut_off_splits_only_pay_running_into_it_from_earlier():
    """D70: a December 2019 joiner who left on 1 April 2020 gets a one-day cut-off record that
    repeats their pay. One who left on 31 March gets none, and neither does anyone with a review
    or a joining date on 1 April 2020."""
    joined = pay(date(2019, 12, 15), 50_000, "joining")
    later = pay(date(2021, 4, 1), 52_000)
    split = with_cutoff([joined], date(2019, 12, 15), date(2020, 4, 1))

    assert [record.effective_from for record in split] == [date(2019, 12, 15), REPORTING_START]
    assert split[1] == pay(REPORTING_START, 50_000, profiles.CUTOFF_NOTE)
    assert with_cutoff([joined], date(2019, 12, 15), date(2020, 3, 31)) == [joined]
    assert [r.effective_from for r in with_cutoff([joined, later], joined.effective_from, END)] == [
        date(2019, 12, 15),
        REPORTING_START,
        date(2021, 4, 1),
    ]
    reviewed = [pay(date(2019, 9, 30), 50_000, "joining"), pay(REPORTING_START, 52_000)]
    assert with_cutoff(reviewed, date(2019, 9, 30), END) == reviewed
    started = [pay(REPORTING_START, 50_000, "joining")]
    assert with_cutoff(started, REPORTING_START, END) == started


def test_a_skipped_april_never_moves_anyone_two_levels():
    """Ten thousand careers. Where a skipped first April left two promotion points before the next
    review, the lower moved to the joining day, so no review moves anyone two levels (D70)."""
    rng = random.Random(7)
    moved = 0
    for n in range(10_000):
        level = 2 + n % 5
        career = draw_career(rng, level, None)
        schedule = reviews(career.joining_date, profiles.REFERENCE_DATE)
        path = [career.level_on(day) for day in schedule]
        assert path[-1] == level
        assert all(b - a <= 1 for a, b in zip(path, path[1:], strict=False))
        joined = (career.joining_date - career.experience_start).days
        moved += len(schedule) > 1 and joined in career.points.values()
        for promoted_to, point in career.points.items():
            assert window(promoted_to)[0] <= point <= window(promoted_to)[1]

    assert moved


def test_every_active_l1_joined_after_1_april_2023():
    rng = random.Random(1)

    assert all(draw_career(rng, 1, None).joining_date > date(2023, 4, 1) for _ in range(300))


def test_pay_at_the_review_follows_the_level_and_experience_up_to_20_percent():
    """A US engineer, no noise, bonus or jitter. Level 3 with 10 years' experience is 1,827 days,
    5.00205 years, above its floor, so 10.0041% more: 135,000 x 1.15 x 1.100041 = 170,781.4,
    rounded to 170,800. Level 6 with 22 years is 10 years above its floor, capped at 20%:
    135,000 x 3 x 1.15 x 1.2 = 558,900."""
    us, engineering = COUNTRIES["US"], DEPARTMENTS["engineering"]
    review = date(2026, 4, 1)

    def base(level, experience_years):
        start = review - timedelta(days=days(experience_years))
        career = Career(level, date(2020, 1, 1), start, {})
        return base_at_review(us, engineering, career, review, Decimal(1), Decimal(0), {})

    assert base(3, 10) == Decimal("170800")
    assert base(6, 22) == Decimal("558900")


def test_pay_is_raised_until_gross_reaches_the_country_minimum():
    """Noise of 0.1 puts a US support L1 at 5,900, below the 35,000 minimum: raised to it."""
    us, support = COUNTRIES["US"], DEPARTMENTS["customer-support"]
    review = date(2026, 4, 1)
    career = Career(1, review, review, {})

    base = base_at_review(us, support, career, review, Decimal("0.1"), Decimal(0), {})

    assert base == Decimal("35000")


def test_the_months_run_from_january_2015_to_the_month_before_the_reference_date():
    ends = month_ends()

    assert (len(ends), ends[0], ends[1], ends[-1]) == (
        141,
        date(2015, 1, 31),
        date(2015, 2, 28),
        date(2026, 9, 30),
    )


def test_leavers_split_by_largest_remainder_and_add_up_exactly():
    weights = [0] * 141
    weights[:4] = [1, 2, 3, 4]
    counts = [count for _, count in leavers_by_month(weights, 10)]
    assert counts[:4] == [1, 2, 3, 4] and sum(counts) == 10

    weights[:4] = [1, 1, 1, 0]
    counts = [count for _, count in leavers_by_month(weights, 2)]
    assert counts[:4] == [1, 1, 0, 0]


def test_someone_whose_last_day_ends_a_month_counts_on_it():
    stay = generate(1, 42)
    [person] = list(stay)
    person.identity["joining_date"] = date(2015, 1, 10)
    person.identity["last_date"] = date(2015, 2, 28)

    counts = headcounts([person])

    assert counts[:3] == [1, 1, 0]


@pytest.mark.slow
def test_the_full_seed_leaves_at_a_steady_rate():
    """10,000 who stay and 5,000 who leave: each full year's leavers over its mean headcount at
    the month-ends, about 11% from 2015 to 2025 (D64)."""
    people = list(generate(profiles.ACTIVE_EMPLOYEES, 42, exited=profiles.EXITED_EMPLOYEES))
    counts = headcounts(people)
    ends = month_ends()
    for year in range(2015, 2026):
        months = [count for end, count in zip(ends, counts, strict=True) if end.year == year]
        left = sum(1 for e in people if (e.identity["last_date"] or date.max).year == year)
        assert 0.10 <= left / (sum(months) / len(months)) <= 0.12


def test_lines_for_india_follow_the_shares():
    country = COUNTRIES["IN"]
    lines = lines_for(country, 3, profiles.BASE_ROUNDING * 14500, 0, {})

    assert lines["HRA"] == 580000
    assert lines["ALLOWANCES"] == 362500
    assert lines["TAX"] == 478500  # 20 percent of gross 2,392,500
    assert lines["EMPLOYER_CONTRIBUTION"] == 174000


def test_start_number_offsets_the_email_numbers():
    people = list(generate(2, 42, start_number=10001))

    assert [e.identity["email"].split("@")[0].rsplit(".", 1)[1] for e in people] == [
        "10001",
        "10002",
    ]


def test_ordered_entries_put_the_earliest_joiner_first_and_keep_ties_in_generation_order():
    """The database numbers employees in this order, leavers among them, so ACME-1 is the
    earliest joiner (D48)."""
    ordered = ordered_entries(150, 42, exited=50)

    keys = [(e.identity["joining_date"], e.ref) for e in ordered]
    assert keys == sorted(keys)
    assert sorted(e.ref for e in ordered) == list(range(1, 201))


def test_ordering_and_legacy_codes_leave_the_employee_draws_unchanged():
    by_ref = {e.ref: e for e in entries()}

    for entry in ordered_entries(60, 42, exited=30):
        identity = dict(entry.identity)
        identity.pop("legacy_code")
        assert identity == by_ref[entry.ref].identity
        assert entry.records == by_ref[entry.ref].records


def test_legacy_codes_are_hr_codes_without_repeats_and_reproducible():
    codes = [e.identity["legacy_code"] for e in ordered_entries(500, 42)]

    assert all(re.fullmatch(r"HR-\d{5}", code) for code in codes)
    assert len(set(codes)) == 500
    assert codes == [e.identity["legacy_code"] for e in ordered_entries(500, 42)]


def test_legacy_codes_skip_the_taken_ones():
    taken = set(legacy_codes(89990, "fill"))

    fresh = legacy_codes(10, "new", taken)

    assert len(set(fresh)) == 10 and not set(fresh) & taken


def test_april_firsts_and_the_last_april():
    assert april_firsts(date(2024, 3, 1), date(2026, 10, 6)) == [
        date(2024, 4, 1),
        date(2025, 4, 1),
        date(2026, 4, 1),
    ]
    assert april_firsts(date(2024, 4, 1), date(2026, 10, 6)) == [date(2025, 4, 1), date(2026, 4, 1)]
    assert april_firsts(date(2026, 5, 1), date(2026, 10, 6)) == []
    assert [
        last_april(day) for day in (date(2026, 10, 6), date(2026, 4, 1), date(2026, 3, 31))
    ] == [
        date(2026, 4, 1),
        date(2026, 4, 1),
        date(2025, 4, 1),
    ]


def test_ascii_slug():
    assert ascii_slug("Jürgen") == "jurgen"
    assert ascii_slug("O'Neil-Smith") == "oneilsmith"
    assert ascii_slug("张") == "user"


def test_leavers_are_drawn_twice_as_often_at_l1_and_one_and_a_half_times_at_l2():
    """The owner's weights (D64): each level's share of the staff times how likely it is to leave,
    L1 twice and L2 one and a half times as likely as L3 to L6."""
    assert LEAVER_LEVEL_WEIGHTS == pytest.approx([0.5, 0.375, 0.2, 0.15, 0.1, 0.05])
