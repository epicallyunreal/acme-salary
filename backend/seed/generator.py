"""Deterministic employee generation (SPEC section 11, DESIGN section 5).

One random.Random(seed) drives every draw in a fixed order per employee, and one Faker per
locale is seeded the same way, so the same arguments give the same entries on any machine.
Random draws are the only floats; they enter Decimal arithmetic exactly once, through dec().
The generator produces BulkEntry values; compensation.services.bulk_apply writes them.
"""

from __future__ import annotations

import random
import unicodedata
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from faker import Faker

from apps.compensation.services import BulkEntry, RecordInput
from seed import profiles
from seed.profiles import CountrySpec, DepartmentSpec

COUNTRY_WEIGHTS = [spec.share for spec in profiles.COUNTRIES]
DEPARTMENT_WEIGHTS = [spec.share for spec in profiles.DEPARTMENTS]
LEVEL_WEIGHTS = [profiles.LEVEL_SHARES[level] for level in profiles.LEVELS]
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
    earnings = sum(
        (amount for code, amount in lines.items() if KIND_OF[code] == "earning"), Decimal("0")
    )
    gross = earnings + bonus
    lines["TAX"] = whole(gross * dec(profiles.TAX_SHARE_BY_LEVEL[level]) * jitter.get("TAX", ONE))
    lines["EMPLOYER_CONTRIBUTION"] = whole(
        base * dec(country.employer_share) * jitter.get("EMPLOYER_CONTRIBUTION", ONE)
    )
    return lines


def april_firsts(after: date, until: date) -> list[date]:
    """Every 1 April strictly after `after` and on or before `until`."""
    days = []
    year = after.year if date(after.year, 4, 1) > after else after.year + 1
    while date(year, 4, 1) <= until:
        days.append(date(year, 4, 1))
        year += 1
    return days


def generate(count: int, seed: int, *, start_number: int = 1) -> Iterator[BulkEntry]:
    rng = random.Random(seed)
    fakers: dict[str, Faker] = {}
    for spec in profiles.COUNTRIES:
        if spec.faker_locale not in fakers:
            faker = Faker(spec.faker_locale)
            faker.seed_instance(seed)
            fakers[spec.faker_locale] = faker

    for index in range(count):
        number = start_number + index
        country: CountrySpec = rng.choices(profiles.COUNTRIES, COUNTRY_WEIGHTS)[0]
        department: DepartmentSpec = rng.choices(profiles.DEPARTMENTS, DEPARTMENT_WEIGHTS)[0]
        level = rng.choices(profiles.LEVELS, LEVEL_WEIGHTS)[0]
        gender = rng.choices(GENDERS, GENDER_WEIGHTS)[0]
        faker = fakers[country.faker_locale]
        if gender == "female":
            first = faker.first_name_female()
        elif gender == "male":
            first = faker.first_name_male()
        else:
            first = faker.first_name()
        last = faker.last_name()
        full_name = f"{first} {last}"
        email = f"{ascii_slug(first)}.{ascii_slug(last)}.{number}@{profiles.EMAIL_DOMAIN}"

        start, end = profiles.JOINING_RANGE
        joining_date = start + timedelta(days=rng.randrange((end - start).days + 1))
        last_date = None
        if rng.random() < profiles.EXIT_SHARE:
            earliest = joining_date + timedelta(days=profiles.EXIT_MIN_TENURE_DAYS)
            if earliest <= profiles.REFERENCE_DATE:
                span = (profiles.REFERENCE_DATE - earliest).days
                last_date = earliest + timedelta(days=rng.randrange(span + 1))

        noise = dec(rng.lognormvariate(0, profiles.NOISE_SIGMA))
        base = round_to(
            Decimal(country.anchor)
            * dec(profiles.LEVEL_MULTIPLIERS[level])
            * dec(department.multiplier)
            * noise,
            profiles.BASE_ROUNDING,
        )
        bonus_share = Decimal("0")
        if rng.random() < country.bonus_probability:
            bonus_share = dec(rng.uniform(*profiles.BONUS_RANGE))
        jitter = {
            code: dec(rng.uniform(1 - profiles.COMPONENT_JITTER, 1 + profiles.COMPONENT_JITTER))
            for code in JITTERED
        }

        history_end = min(last_date or profiles.REFERENCE_DATE, profiles.REFERENCE_DATE)
        raise_days = april_firsts(joining_date, history_end)
        raises = [dec(rng.uniform(*profiles.RAISE_RANGE)) for _ in raise_days]

        bases = [base]
        for pct in raises:
            bases.append(round_to(bases[-1] * (ONE + pct), profiles.BASE_ROUNDING))
        kept = list(zip(raise_days, bases[1:], strict=True))[-profiles.KEPT_RAISES :]

        records = []
        for effective_from, record_base in [(joining_date, base), *kept]:
            bonus = round_to(record_base * bonus_share, profiles.BASE_ROUNDING)
            records.append(
                RecordInput(
                    effective_from=effective_from,
                    bonus_annual=bonus,
                    note="joining" if effective_from == joining_date else "annual raise",
                    lines=lines_for(country, level, record_base, bonus, jitter),
                )
            )

        identity = {
            "employee_code": profiles.EMPLOYEE_CODE_FORMAT.format(number),
            "full_name": full_name,
            "email": email,
            "department": department.code,
            "designation": profiles.designation(department, level),
            "level": level,
            "country_code": country.code,
            "gender": gender,
            "joining_date": joining_date,
            "last_date": last_date,
        }
        yield BulkEntry(ref=number, identity=identity, records=records)
