"""Deterministic employee generation (SPEC section 11, DESIGN section 5).

One random.Random(seed) drives every draw in a fixed order, and one Faker per locale is seeded
the same way, so the same arguments give the same entries on any machine. Random draws are the
only floats; they enter Decimal arithmetic exactly once, through dec(). Experience is counted in
whole days. The generator produces BulkEntry values; compensation.services.bulk_apply writes
them.

Each person is drawn from their last review backwards (D64): their level then, which is today's
or their last day's, their experience at that review, a joining date that fits it, the point in
each of the ladder's overlaps where they are promoted, and their pay at that review, from which
every earlier record is back-filled through each 1 April revision.
"""

from __future__ import annotations

import random
import unicodedata
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from faker import Faker

from apps.compensation.services import BulkEntry, RecordInput
from apps.core.dates import REPORTING_START, months_before
from seed import profiles
from seed.profiles import CountrySpec, DepartmentSpec

COUNTRY_WEIGHTS = [spec.share for spec in profiles.COUNTRIES]
DEPARTMENT_WEIGHTS = [spec.share for spec in profiles.DEPARTMENTS]
LEVEL_WEIGHTS = [profiles.LEVEL_SHARES[level] for level in profiles.LEVELS]
# Leavers lean junior: each level's share weighted by how much likelier it is to leave (D64).
LEAVER_LEVEL_WEIGHTS = [
    profiles.LEVEL_SHARES[level] * profiles.LEAVE_WEIGHTS[level] for level in profiles.LEVELS
]
GENDERS = list(profiles.GENDER_SHARES)
GENDER_WEIGHTS = list(profiles.GENDER_SHARES.values())
JITTERED = (
    "HRA",
    "ALLOWANCES",
    "HOLIDAY_ALLOWANCE",
    "AWS",
    "NATIONAL_INSURANCE",
    "SOCIAL_INSURANCE",
    "CPF",
    "TAX",
    "EMPLOYER_CONTRIBUTION",
)
ONE = Decimal("1")
KIND_OF = {spec.code: spec.kind for spec in profiles.COMPONENTS}
DAYS_PER_YEAR = Decimal("365.25")


def dec(value: float) -> Decimal:
    """A random draw into Decimal, once, exactly as Python prints it."""
    return Decimal(repr(value))


def whole(value: Decimal) -> Decimal:
    return value.quantize(ONE, rounding=ROUND_HALF_UP)


def round_to(value: Decimal, step: int) -> Decimal:
    return (value / step).quantize(ONE, rounding=ROUND_HALF_UP) * step


def ascii_slug(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = "".join(ch for ch in folded.lower() if ch.isalnum())
    return slug or "user"


def lines_for(
    country: CountrySpec,
    level: int,
    base: Decimal,
    bonus: Decimal,
    jitter: dict[str, Decimal],
) -> dict[str, Decimal]:
    """The component lines for one record: shares of base, TAX as a share of gross."""
    lines: dict[str, Decimal] = {"BASE": base}
    for code, share in country.components.items():
        lines[code] = whole(base * dec(share) * jitter.get(code, ONE))
    lines["TAX"] = whole(
        gross_of(lines, bonus) * dec(profiles.TAX_SHARE_BY_LEVEL[level]) * jitter.get("TAX", ONE)
    )
    lines["EMPLOYER_CONTRIBUTION"] = whole(
        base * dec(country.employer_share) * jitter.get("EMPLOYER_CONTRIBUTION", ONE)
    )
    return lines


def gross_of(lines: dict[str, Decimal], bonus: Decimal) -> Decimal:
    earnings = (amount for code, amount in lines.items() if KIND_OF[code] == "earning")
    return sum(earnings, Decimal("0")) + bonus


def april_firsts(after: date, until: date) -> list[date]:
    """Every 1 April strictly after `after` and on or before `until`."""
    days = []
    year = after.year if date(after.year, 4, 1) > after else after.year + 1
    while date(year, 4, 1) <= until:
        days.append(date(year, 4, 1))
        year += 1
    return days


def reviews(joining_date: date, end: date) -> list[date]:
    """The days someone's pay is set (D64, D70): joining, then every 1 April after it up to `end`,
    except the first when they joined in the six months before it."""
    aprils = april_firsts(joining_date, end)
    if aprils and joining_date >= months_before(aprils[0], profiles.FIRST_REVIEW_MONTHS):
        aprils = aprils[1:]
    return [joining_date, *aprils]


def with_cutoff(records: list[RecordInput], joining_date: date, end: date) -> list[RecordInput]:
    """`records`, one per review from the joining date, with one starting on the reporting
    cut-off for someone employed then (D70). Where the pay running into 1 April 2020 started
    earlier, a revision that day repeats it, lines and bonus alike, a one-off for that day."""
    starts = [record.effective_from for record in records]
    if not joining_date < REPORTING_START <= end or REPORTING_START in starts:
        return records
    at = bisect_right(starts, REPORTING_START)
    running = records[at - 1]
    cutoff = RecordInput(
        effective_from=REPORTING_START,
        bonus_annual=running.bonus_annual,
        note=profiles.CUTOFF_NOTE,
        lines=dict(running.lines),
    )
    return [*records[:at], cutoff, *records[at:]]


def last_april(day: date) -> date:
    """The latest 1 April on or before `day`."""
    return date(day.year if (day.month, day.day) >= (4, 1) else day.year - 1, 4, 1)


def days(years: int) -> int:
    """Whole years as days, a year being 365.25 of them, rounded half up."""
    return (years * 1461 + 2) // 4


def window(level: int) -> tuple[int, int]:
    """The days of experience, both ends included, inside which the promotion into `level`
    falls: the overlap with the level below, or the one day where L1 and L2 meet. The windows
    lie at least 366 days apart, so no one moves two levels at one April."""
    low = days(profiles.LADDER[level][0])
    high = days(profiles.LADDER[level - 1][1]) - 1
    return low, max(low, high)


def experience_range(level: int) -> tuple[int, int]:
    """The days of experience, both ends included, someone at `level` can have at a review:
    from the level's floor to just before the last day the next promotion can wait for."""
    low = days(profiles.LADDER[level][0])
    if level == profiles.LEVELS[-1]:
        return low, days(profiles.LADDER[level][1]) - 1
    return low, window(level + 1)[1] - 1


@dataclass(frozen=True)
class Career:
    """When someone joined, when their experience began, and where they are promoted."""

    level: int  # at the last review, which is today's or their last day's
    joining_date: date
    experience_start: date
    points: dict[int, int]  # level -> the day of experience they are promoted into it

    def level_on(self, day: date) -> int:
        experience = (day - self.experience_start).days
        return max([1, *(level for level, point in self.points.items() if experience >= point)])


def draw_career(rng: random.Random, level: int, last_date: date | None) -> Career:
    """Experience at the last review, then a joining date that fits it, then the promotion
    points either side of it, so the level path ends at `level` (D64).

    The last review is the latest 1 April on or before the end (the reference date, or the last
    day), unless they joined after it, or in the six months before it, when it is the joining
    date (D70). Years at ACME never exceed total experience, and a leaver stays at least 30 days.
    """
    end = last_date or profiles.REFERENCE_DATE
    april = last_april(end)
    low, high = experience_range(level)
    if last_date is not None:
        low = max(low, profiles.MIN_TENURE_DAYS - (end - april).days)
    experience = low + rng.randrange(high - low + 1)
    earliest = max(profiles.HISTORY_START, april - timedelta(days=experience))
    latest = end - timedelta(days=profiles.MIN_TENURE_DAYS) if last_date else end
    joining_date = earliest + timedelta(days=rng.randrange((latest - earliest).days + 1))
    schedule = reviews(joining_date, end)
    review = schedule[-1]
    points = {}
    for promoted_to in profiles.LEVELS[1:]:
        first, last = window(promoted_to)
        if promoted_to == level:
            last = min(last, experience)
        elif promoted_to == level + 1:
            first = max(first, experience + 1)
        points[promoted_to] = first + rng.randrange(last - first + 1)
    start = review - timedelta(days=experience)
    # A skipped first April leaves 12 to 18 months between joining and the next review, room for
    # two promotion points. The lower then falls on the joining day, inside its window since the
    # windows start at least 730 days apart, so no review moves anyone two levels (D70).
    if len(schedule) > 1:
        joined, second = ((day - start).days for day in schedule[:2])
        for promoted_to in profiles.LEVELS[1:-1]:
            if joined < points[promoted_to] and points[promoted_to + 1] <= second:
                points[promoted_to] = joined
    return Career(level, joining_date, start, points)


def base_at_review(
    country: CountrySpec,
    department: DepartmentSpec,
    career: Career,
    review: date,
    noise: Decimal,
    bonus_share: Decimal,
    jitter: dict[str, Decimal],
) -> Decimal:
    """Pay set by level at the last review: the anchor times the level, the department and the
    noise, plus 2% a year of experience above the level's floor up to 20%, rounded to 100 and
    raised as far as it takes for gross to reach the country's minimum (D64)."""
    level = career.level
    above = (review - career.experience_start).days - days(profiles.LADDER[level][0])
    premium = min(
        dec(profiles.EXPERIENCE_PAY) * Decimal(above) / DAYS_PER_YEAR,
        dec(profiles.EXPERIENCE_PAY_CAP),
    )
    base = round_to(
        Decimal(country.anchor)
        * dec(profiles.LEVEL_MULTIPLIERS[level])
        * dec(department.multiplier)
        * noise
        * (ONE + premium),
        profiles.BASE_ROUNDING,
    )
    minimum = Decimal(country.min_gross)
    while True:
        bonus = round_to(base * bonus_share, profiles.BASE_ROUNDING)
        gross = gross_of(lines_for(country, level, base, bonus, jitter), bonus)
        if gross >= minimum:
            return base
        steps = (base * minimum / gross / profiles.BASE_ROUNDING).quantize(ONE, ROUND_CEILING)
        base = max(steps * profiles.BASE_ROUNDING, base + profiles.BASE_ROUNDING)


class People:
    """One seeded draw stream: the Fakers and the running number that makes emails unique."""

    def __init__(self, seed: int | str, start_number: int) -> None:
        self.rng = random.Random(seed)
        self.number = start_number
        self.fakers: dict[str, Faker] = {}
        for spec in profiles.COUNTRIES:
            if spec.faker_locale not in self.fakers:
                faker = Faker(spec.faker_locale)
                faker.seed_instance(seed)
                self.fakers[spec.faker_locale] = faker

    def person(self, last_date: date | None, level_weights: list[float]) -> BulkEntry:
        rng = self.rng
        number = self.number
        self.number += 1
        country: CountrySpec = rng.choices(profiles.COUNTRIES, COUNTRY_WEIGHTS)[0]
        department: DepartmentSpec = rng.choices(profiles.DEPARTMENTS, DEPARTMENT_WEIGHTS)[0]
        gender = rng.choices(GENDERS, GENDER_WEIGHTS)[0]
        faker = self.fakers[country.faker_locale]
        if gender == "female":
            first = faker.first_name_female()
        elif gender == "male":
            first = faker.first_name_male()
        else:
            first = faker.first_name()
        last = faker.last_name()
        email = f"{ascii_slug(first)}.{ascii_slug(last)}.{number}@{profiles.EMAIL_DOMAIN}"

        level = rng.choices(profiles.LEVELS, level_weights)[0]
        career = draw_career(rng, level, last_date)
        noise = dec(rng.lognormvariate(0, profiles.NOISE_SIGMA))
        bonus_share = Decimal("0")
        if rng.random() < country.bonus_probability:
            bonus_share = dec(rng.uniform(*profiles.BONUS_RANGE))
        jitter = {
            code: dec(rng.uniform(1 - profiles.COMPONENT_JITTER, 1 + profiles.COMPONENT_JITTER))
            for code in JITTERED
        }

        # One record at joining and one at every review since, every one kept (D64, D70).
        end = last_date or profiles.REFERENCE_DATE
        review_days = reviews(career.joining_date, end)
        levels = [career.level_on(day) for day in review_days]
        if levels[-1] != level:
            raise RuntimeError(f"a career drawn for L{level} ends at L{levels[-1]}")
        raises = [
            dec(rng.uniform(*profiles.PROMOTION_RANGE if moved else profiles.RAISE_RANGE))
            for moved in (after > before for before, after in zip(levels, levels[1:], strict=False))
        ]
        bases = [
            base_at_review(country, department, career, review_days[-1], noise, bonus_share, jitter)
        ]
        for pct in reversed(raises):
            bases.append(round_to(bases[-1] / (ONE + pct), profiles.BASE_ROUNDING))
        bases.reverse()

        records = []
        for index, (effective_from, record_level, base) in enumerate(
            zip(review_days, levels, bases, strict=True)
        ):
            if index == 0:
                note = "joining"
            elif record_level > levels[index - 1]:
                note = f"promotion to L{record_level}"
            else:
                note = "annual raise"
            bonus = round_to(base * bonus_share, profiles.BASE_ROUNDING)
            records.append(
                RecordInput(
                    effective_from=effective_from,
                    bonus_annual=bonus,
                    note=note,
                    lines=lines_for(country, record_level, base, bonus, jitter),
                )
            )

        records = with_cutoff(records, career.joining_date, end)

        identity = {
            "full_name": f"{first} {last}",
            "email": email,
            "department": department.code,
            "designation": profiles.designation(department, level),
            "level": level,
            "country_code": country.code,
            "gender": gender,
            "joining_date": career.joining_date,
            "last_date": last_date,
        }
        return BulkEntry(ref=number, identity=identity, records=records)


def month_ends() -> list[date]:
    """The last day of each month from January 2015 to the month before the reference date."""
    ends = []
    year, month = profiles.HISTORY_START.year, profiles.HISTORY_START.month
    while (year, month) < (profiles.REFERENCE_DATE.year, profiles.REFERENCE_DATE.month):
        following = date(year + month // 12, month % 12 + 1, 1)
        ends.append(following - timedelta(days=1))
        year, month = following.year, following.month
    return ends


def headcounts(people: Iterable[BulkEntry]) -> list[int]:
    """How many are employed on each month's last day: joined by then and not yet gone."""
    joined, left = [], []
    for entry in people:
        joined.append(entry.identity["joining_date"])
        if entry.identity["last_date"] is not None:
            left.append(entry.identity["last_date"])
    joined.sort()
    left.sort()
    # Someone whose last day is the month's last day is still employed on it.
    return [bisect_right(joined, end) - bisect_left(left, end) for end in month_ends()]


def leavers_by_month(weights: list[int], exited: int) -> list[tuple[date, int]]:
    """How many leave in each month (its last day, the count), in proportion to `weights`, the
    headcount at each month's end, by largest remainder so they add up to `exited` exactly
    (D64). Integer arithmetic throughout."""
    ends = month_ends()
    total = sum(weights)
    if not exited or not total:
        return [(end, 0) for end in ends]
    counts = [exited * weight // total for weight in weights]
    by_remainder = sorted(
        range(len(ends)), key=lambda index: (-(exited * weights[index] % total), index)
    )
    for index in by_remainder[: exited - sum(counts)]:
        counts[index] += 1
    return list(zip(ends, counts, strict=True))


# Each month's leavers follow everyone employed then, the leavers still there included, which
# depends on the leavers themselves: three passes settle it, the first on those who stay (D64).
LEAVER_PASSES = 3


def leavers(allocation: list[tuple[date, int]], seed: int, start_number: int) -> list[BulkEntry]:
    """One person for each leaver in `allocation`, their last day uniform in its month and at
    least 30 days after 1 January 2015, from a draw stream of their own."""
    people = People(f"{seed}-leavers", start_number)
    earliest = profiles.HISTORY_START + timedelta(days=profiles.MIN_TENURE_DAYS)
    entries = []
    for month_end, count in allocation:
        first = max(month_end.replace(day=1), earliest)
        for _ in range(count):
            last_date = first + timedelta(days=people.rng.randrange((month_end - first).days + 1))
            entries.append(people.person(last_date, LEAVER_LEVEL_WEIGHTS))
    return entries


def generate(
    active: int, seed: int, *, exited: int = 0, start_number: int = 1
) -> Iterator[BulkEntry]:
    """`active` people on staff on the reference date, then `exited` who left before it, each
    month's leavers in proportion to the headcount then, none in their first 30 days (D64)."""
    people = People(seed, start_number)
    staying = [people.person(None, LEVEL_WEIGHTS) for _ in range(active)]
    yield from staying
    if not exited:
        return
    gone: list[BulkEntry] = []
    for _ in range(LEAVER_PASSES):
        allocation = leavers_by_month(headcounts([*staying, *gone]), exited)
        gone = leavers(allocation, seed, start_number + active)
    yield from gone


def legacy_codes(count: int, salt: str, taken: Iterable[str] = ()) -> list[str]:
    """`count` HR- codes drawn without repeats from the numbers not in `taken`, by a generator of
    their own, so drawing them leaves the employee draws above untouched."""
    used = set(taken)
    free = [n for n in profiles.LEGACY_NUMBERS if profiles.LEGACY_CODE_FORMAT.format(n) not in used]
    numbers = random.Random(salt).sample(free, count)
    return [profiles.LEGACY_CODE_FORMAT.format(number) for number in numbers]


def ordered_entries(active: int, seed: int, *, exited: int = 0) -> list[BulkEntry]:
    """The seed's employees in the order the database numbers them: the earliest joiner first,
    leavers among them, ties in generation order, so ACME-1 is the earliest joiner (D48). Each
    carries a legacy_code."""
    entries = sorted(
        generate(active, seed, exited=exited), key=lambda entry: entry.identity["joining_date"]
    )
    for entry, code in zip(entries, legacy_codes(len(entries), f"seed-{seed}"), strict=True):
        entry.identity["legacy_code"] = code
    return entries
