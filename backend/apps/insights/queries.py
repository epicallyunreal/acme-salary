"""The insights of SPEC section 9, each one read over one population (DESIGN 1.6).

Sums and counts are aggregated per (group, currency) in SQL, converted in Python with the Decimal
rate and quantised once. Medians convert every value first. Nothing converted is stored.

Two thresholds keep one person's pay off a card, a screenshot or an export (D59). A group of fewer
than five people shows its headcount alone, since a one-person total is that person's cost. The
spread figures, by-level's p10 to p90 and the distribution's range, bands and markers, need
twenty: at exactly five, by-level's five figures were every salary in the group.

Every insight reads a period, `start` to `end`, the API's `from` and `to` (D64). The cards that
describe who earns what show the state on `end`, and `trend`, `cost-bridge` and the summary's
spend read the people employed on each date of the period (`spans`), Include exited not applying
to them (D62). One rate, the one effective on `end`, converts it all. A card may have one control
of its own (`CONTROLS`), which slices or measures and never decides who is counted.
"""

from __future__ import annotations

import calendar
import math
import statistics
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, F, Q, QuerySet, Sum

from apps.compensation.messages import msg
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.core import fx
from apps.core.dates import last_day
from apps.core.exceptions import Invalid
from apps.core.models import Country, Department, SalaryComponent
from apps.core.money import q1, q2
from apps.employees.models import Gender

SMALL_GROUP = 5  # under five people a group shows its headcount alone (SPEC section 9, D59)
SPREAD_GROUP = 20  # under twenty, no percentile figures: each would be one person's pay (D59)
BANDS = 12
LEVELS = range(1, 7)
# EU Directive 2023/970 Article 10's threshold for a gap between women's and men's pay (D62).
GAP_FLAG = Decimal(5)
# Tenure bands in completed years (D62): each from its lower bound up to, not including, its upper.
TENURE_BANDS = (
    ("under_1", "Under 1 year", 0),
    ("1_to_3", "1 to 3 years", 1),
    ("3_to_5", "3 to 5 years", 3),
    ("5_to_10", "5 to 10 years", 5),
    ("10_plus", "10 years or more", 10),
)
GENDERS = tuple(choice.value for choice in Gender)

COUNTRY = "employee__country_id"
DEPARTMENT = "employee__department__code"
LEVEL = "employee__level"
GENDER = "employee__gender"


@dataclass(frozen=True)
class InsightFilters:
    country: tuple[str, ...]
    department: tuple[str, ...]
    include_exited: bool
    start: date  # the period's first day, the API's `from` (D64)
    end: date  # its last day, `to`, the reporting date of every card that shows a state
    currency: str  # "USD", "EUR", or the one country's local code
    local: bool = False  # currency=local was asked for, so no rate is used


@dataclass(frozen=True)
class Lookups:
    """Every country and department by code, in name order. The filter is checked against them,
    and the per-country and per-department insights list them, the empty ones included."""

    countries: dict[str, Country]
    departments: dict[str, Department]

    @classmethod
    def load(cls) -> Lookups:
        return cls(
            countries={country.code: country for country in Country.objects.order_by("name")},
            departments={dept.code: dept for dept in Department.objects.order_by("name")},
        )


def build_filters(
    lookups: Lookups,
    *,
    country: Sequence[str],
    department: Sequence[str],
    include_exited: bool,
    period: tuple[date, date],
    currency: str | None,
) -> InsightFilters:
    """The filters a request names. A code that names nothing is refused with section 7's words,
    since the per-country and per-department insights list every code in the filter. A code given
    twice is one group."""
    country = tuple(dict.fromkeys(country))
    department = tuple(dict.fromkeys(department))
    errors = {}
    if unknown := [code for code in country if code not in lookups.countries]:
        errors["country"] = [msg("country_unknown", value=code) for code in unknown]
    if unknown := [code for code in department if code not in lookups.departments]:
        errors["department"] = [msg("department_unknown", value=code) for code in unknown]
    if errors:
        raise Invalid(errors)
    currency_by_country = {code: c.currency_code for code, c in lookups.countries.items()}
    reporting = fx.resolve_reporting_currency(currency, list(country), currency_by_country)
    start, end = period
    return InsightFilters(
        country, department, include_exited, start, end, reporting, fx.asks_local(currency)
    )


def population(f: InsightFilters) -> QuerySet[CompensationRecord]:
    """SPEC section 9: the record current on `end` of everyone active then, and with
    `include_exited` the last record of everyone who left before it. Future joiners never.

    Live records of one employee never overlap, so at most one is current. An exited employee's
    last record alone ends after `last_date`, at `last_date + 1`. `trend` and `cost-bridge` read
    `spans` instead, the people employed on each date (D62).
    """
    on = f.end
    active = Q(employee__joining_date__lte=on) & (
        Q(employee__last_date__isnull=True) | Q(employee__last_date__gte=on)
    )
    current = Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gt=on))
    records = CompensationRecord.objects.filter(cancelled_at__isnull=True)
    if f.include_exited:
        exited_last = Q(employee__last_date__lt=on) & Q(effective_to__gt=F("employee__last_date"))
        records = records.filter((active & current) | exited_last)
    else:
        records = records.filter(active & current)
    if f.country:
        records = records.filter(employee__country_id__in=f.country)
    if f.department:
        records = records.filter(employee__department__code__in=f.department)
    return records.order_by()


# Dates (D62, D64)


def period_dates(start: date, end: date) -> list[date]:
    """The dates trend reads over a period (D64): `start`, each month-end after it and before
    `end`, and `end`, oldest first, a month-end `start` or `end` counted once."""
    dates = [start]
    month_end = last_day(start.year, start.month)
    while month_end < end:
        if month_end > start:
            dates.append(month_end)
        following = month_end + timedelta(days=1)
        month_end = last_day(following.year, following.month)
    if end > start:
        dates.append(end)
    return dates


def year_fraction(first: date, last: date) -> Decimal:
    """The days from `first` to `last`, both counted, each as a share of its own calendar year,
    so a whole year adds up to 1 (D64). The years between the first and the last add 1 each."""

    def share(start: date, end: date) -> Decimal:
        return Decimal((end - start).days + 1) / (366 if calendar.isleap(start.year) else 365)

    if first.year == last.year:
        return share(first, last)
    return (
        share(first, date(first.year, 12, 31))
        + (last.year - first.year - 1)
        + share(date(last.year, 1, 1), last)
    )


@dataclass(frozen=True)
class Span:
    """The days one live record counts its employee as employed: from `first` up to, not
    including, `stop`, or on and on when `stop` is None."""

    employee: int
    currency: str
    total_cost: Decimal
    first: date
    stop: date | None

    def counts_on(self, day: date) -> bool:
        return self.first <= day and (self.stop is None or day < self.stop)


def spans(f: InsightFilters, first: date, last: date) -> list[Span]:
    """The live records of the filtered employees that count someone as employed on some day from
    `first` to `last`, the dated population `trend` and `cost-bridge` share. A record counts from
    the later of its start and the joining date, and stops at its end or the day after the last
    date. Include exited does not apply, so nobody counts after leaving (D62)."""
    records = CompensationRecord.objects.filter(
        Q(effective_to__isnull=True) | Q(effective_to__gt=first),
        Q(employee__last_date__isnull=True) | Q(employee__last_date__gte=first),
        cancelled_at__isnull=True,
        effective_from__lte=last,
        employee__joining_date__lte=last,
    )
    if f.country:
        records = records.filter(employee__country_id__in=f.country)
    if f.department:
        records = records.filter(employee__department__code__in=f.department)
    found = []
    for employee, currency, cost, start, end, joined, left in records.order_by().values_list(
        "employee_id",
        "currency_code",
        "total_cost_annual",
        "effective_from",
        "effective_to",
        "employee__joining_date",
        "employee__last_date",
    ):
        first_day = max(start, joined)
        stops = [day for day in (end, left and left + timedelta(days=1)) if day]
        stop = min(stops) if stops else None
        if stop is None or first_day < stop:
            found.append(Span(employee, currency, cost, first_day, stop))
    return found


# Groups


@dataclass
class Group:
    """One group's people, with sums in the reporting currency, not yet quantised."""

    headcount: int = 0
    total_cost: Decimal = Decimal(0)
    gross: Decimal = Decimal(0)


class Converter:
    """Each currency's rate into the reporting currency, looked up once."""

    def __init__(self, f: InsightFilters, rates: fx.RateTable) -> None:
        self.to = f.currency
        self.rates = rates
        self._rate: dict[str, Decimal] = {}

    def rate(self, currency: str) -> Decimal:
        if currency not in self._rate:
            self._rate[currency] = self.rates.rate(currency, self.to)
        return self._rate[currency]


def sums(f: InsightFilters, rates: fx.RateTable, *keys: str) -> dict[Any, Group]:
    """Headcount and converted totals per group, from one aggregate per (group, currency)."""
    convert = Converter(f, rates)
    groups: dict[Any, Group] = defaultdict(Group)
    rows = (
        population(f)
        .values(*keys, "currency_code")
        .annotate(people=Count("id"), cost=Sum("total_cost_annual"), gross=Sum("gross_annual"))
    )
    for row in rows:
        rate = convert.rate(row["currency_code"])
        group = groups[tuple(row[key] for key in keys)]
        group.headcount += row["people"]
        group.total_cost += row["cost"] * rate
        group.gross += row["gross"] * rate
    return groups


def grosses(f: InsightFilters, rates: fx.RateTable, *keys: str) -> dict[Any, list[Decimal]]:
    """Every gross converted on its own, per group, for medians and percentiles."""
    convert = Converter(f, rates)
    values: dict[Any, list[Decimal]] = defaultdict(list)
    for gross, currency, *group in population(f).values_list(
        "gross_annual", "currency_code", *keys
    ):
        values[tuple(group)].append(q2(gross * convert.rate(currency)))
    return values


def median(values: list[Decimal]) -> Decimal | None:
    return q2(statistics.median(values)) if values else None


def band_of(value: Decimal, low: Decimal, high: Decimal) -> int:
    """`floor((v - p1) / width)` with `width = (p99 - p1) / 12`, multiplied out so a value on a
    band's lower edge lands in that band, which a rounded width would miss. Values outside p1 to
    p99 are clipped into the end bands."""
    return min(max(math.floor((value - low) * BANDS / (high - low)), 0), BANDS - 1)


def percentiles(values: list[Decimal]) -> list[Decimal]:
    """p1 to p99 by the inclusive method, p1 at index 0 and p99 at index 98. One value is every
    percentile (SPEC section 9); callers have already turned away an empty list."""
    if len(values) == 1:
        return [values[0]] * 99
    return [q2(point) for point in statistics.quantiles(values, n=100, method="inclusive")]


def published(group: Group, values: list[Decimal], *, mean: bool = False) -> dict:
    """The headcount, then the total cost, mean and median for five people or more. A smaller group
    shows its headcount alone (D59). The values are counted as well as the aggregate, in case a
    write landed between the two queries."""
    shown = group.headcount >= SMALL_GROUP and len(values) >= SMALL_GROUP
    figures = {
        "headcount": group.headcount,
        "total_cost": q2(group.total_cost) if shown else None,
    }
    if mean:
        figures["mean_gross"] = q2(group.gross / group.headcount) if shown else None
    figures["median_gross"] = median(values) if shown else None
    return figures


def header(f: InsightFilters, rates: fx.RateTable) -> dict:
    """The period, the reporting currency and the month of its rates (D28, D64). Local currency
    uses no rate."""
    if f.local:
        rate_month = {"label": fx.local_label(f.currency), "effective_from": None}
    else:
        rate_month = {
            "label": rates.month_label(f.currency),
            "effective_from": rates.month_of(f.currency),
        }
    return {"from": f.start, "to": f.end, "currency": f.currency, "rate_month": rate_month}


def by_cost(row: dict, name: Callable[[dict], str]) -> tuple:
    """Largest total cost first, equal costs by name. Groups that show their headcount alone follow
    in name order, so the order never hints at a withheld total (D59)."""
    cost = row["total_cost"]
    return (cost is None, -(cost or 0), name(row))


# Insights


def summary(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 1: headcount, total cost, mean and median gross on `end`, with the countries and
    departments they span, and what the period cost (D64)."""
    groups = sums(f, rates, COUNTRY, DEPARTMENT)
    everyone = Group()
    for group in groups.values():
        everyone.headcount += group.headcount
        everyone.total_cost += group.total_cost
        everyone.gross += group.gross
    values = grosses(f, rates)[()]
    return {
        **header(f, rates),
        **published(everyone, values, mean=True),
        "countries": len({country for country, _ in groups}),
        "departments": len({department for _, department in groups}),
        "spent": spent(f, rates),
    }


def spent(f: InsightFilters, rates: fx.RateTable) -> dict:
    """What the period cost (D64): each record's annual total cost for the days it was current
    within it, a day costing the annual figure over the days in its calendar year, summed per
    currency, converted once and quantised once. Everyone employed on any day of the period is
    counted, as trend counts them, Include exited not applying.

    The amount is withheld when 1 to 4 people were employed on any day of the period. A day's cost
    is part of the total, so with the trend's own points on the page, or the total over a day
    shorter, it would give back what trend withholds on that day (D59, D68)."""
    convert = Converter(f, rates)
    by_currency: dict[str, Decimal] = defaultdict(Decimal)
    people = set()
    # The headcount changes on the days someone starts counting and the days after they stop.
    changes: dict[date, int] = defaultdict(int)
    for span in spans(f, f.start, f.end):
        first = max(span.first, f.start)
        last = f.end if span.stop is None else min(span.stop - timedelta(days=1), f.end)
        people.add(span.employee)
        changes[first] += 1
        if last < f.end:
            changes[last + timedelta(days=1)] -= 1
        by_currency[span.currency] += span.total_cost * year_fraction(first, last)
    total = sum((amount * convert.rate(ccy) for ccy, amount in by_currency.items()), Decimal(0))
    shown = len(people) >= SMALL_GROUP and not few_on_a_day(changes)
    return {"headcount": len(people), "total_cost": q2(total) if shown else None}


def few_on_a_day(changes: Mapping[date, int]) -> bool:
    """Whether the headcount these day-by-day changes add up to is 1 to 4 on any day. A day
    nobody is employed hides nobody."""
    headcount = 0
    for day in sorted(changes):
        headcount += changes[day]
        if 0 < headcount < SMALL_GROUP:
            return True
    return False


def by_country(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 2: per country in the filter, every country without one."""
    groups = sums(f, rates, COUNTRY)
    values = grosses(f, rates, COUNTRY)
    overall = q2(sum((group.total_cost for group in groups.values()), Decimal(0)))
    rows = []
    for code in f.country or tuple(lookups.countries):
        figures = published(groups.get((code,), Group()), values.get((code,), []))
        total = figures["total_cost"]
        share = q1(total / overall * 100) if total is not None and overall else None
        country = {"code": code, "name": lookups.countries[code].name}
        rows.append({"country": country, **figures, "share_pct": share})
    rows.sort(key=lambda row: by_cost(row, lambda r: r["country"]["name"]))
    return {**header(f, rates), "rows": rows}


def by_department(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 3: per department in the filter, all twelve without one."""
    groups = sums(f, rates, DEPARTMENT)
    values = grosses(f, rates, DEPARTMENT)
    rows = []
    for code in f.department or tuple(lookups.departments):
        figures = published(groups.get((code,), Group()), values.get((code,), []), mean=True)
        department = {"code": code, "name": lookups.departments[code].name}
        rows.append({"department": department, **figures})
    rows.sort(key=lambda row: by_cost(row, lambda r: r["department"]["name"]))
    return {**header(f, rates), "rows": rows}


def distribution(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 4: gross in twelve equal bands from p1 to p99, values outside clipped into the end
    bands, with p10, p50 and p90 marked. The headcount alone for under twenty people (D59)."""
    values = grosses(f, rates)[()]
    payload = {
        **header(f, rates),
        "headcount": len(values),
        "p1": None,
        "p99": None,
        "bands": None,
        "markers": None,
    }
    if len(values) < SPREAD_GROUP:
        return payload
    points = percentiles(values)
    low, high = points[0], points[98]
    payload.update(
        p1=low, p99=high, markers={"p10": points[9], "p50": points[49], "p90": points[89]}
    )
    if low == high:
        payload["bands"] = [{"index": 0, "from": low, "to": high, "count": len(values)}]
        return payload
    counts = [0] * BANDS
    for value in values:
        counts[band_of(value, low, high)] += 1
    width = (high - low) / BANDS
    payload["bands"] = [
        {
            "index": index,
            "from": q2(low + index * width),
            "to": q2(low + (index + 1) * width) if index < BANDS - 1 else high,
            "count": counts[index],
        }
        for index in range(BANDS)
    ]
    return payload


def by_level(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 5: p10, p25, median, p75 and p90 gross per level, for twenty people or more. No
    min or max: each is one person's pay (D59)."""
    values = grosses(f, rates, LEVEL)
    rows = []
    for level in LEVELS:
        group = values.get((level,), [])
        row = {
            "level": level,
            "headcount": len(group),
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
        }
        if len(group) >= SPREAD_GROUP:
            points = percentiles(group)
            row.update(
                p10=points[9], p25=points[24], median=median(group), p75=points[74], p90=points[89]
            )
        rows.append(row)
    return {**header(f, rates), "rows": rows}


def gender_reason(women: int, men: int, counting: str = "") -> str | None:
    """Why a gender comparison is withheld, in the card's words (D62): `fewer than 5 women`,
    `fewer than 5 men`, or both, `counting` saying who is counted, ` with a bonus`."""
    short = [who for who, n in (("women", women), ("men", men)) if n < SMALL_GROUP]
    if not short:
        return None
    return " and ".join(f"fewer than {SMALL_GROUP} {who}" for who in short) + counting


def group_reason(women: int, men: int) -> str | None:
    """A group's reason, or none for a group with nobody, as every other table words it (D62)."""
    return gender_reason(women, men) if women or men else None


def compared(women: list, men: list) -> bool:
    return len(women) >= SMALL_GROUP and len(men) >= SMALL_GROUP


def gap_pct(women: Decimal | None, men: Decimal | None) -> Decimal | None:
    """The unadjusted gap as a share of men's pay, to one decimal."""
    if women is None or men is None or not men:
        return None
    return q1((men - women) / men * 100)


def average(values: list[Decimal]) -> Decimal:
    """Unrounded, for a gap: a mean amount is never published in the new views (D62)."""
    return sum(values, Decimal(0)) / len(values)


def gap_row(country: dict | None, by_gender: dict[str, list[Decimal]]) -> dict:
    """The medians of women and men and the unadjusted gap, each median only for five people or
    more. Other and undisclosed are counted, never given a median."""
    female, male = by_gender["female"], by_gender["male"]
    reason = group_reason(len(female), len(male))
    women = median(female) if len(female) >= SMALL_GROUP else None
    men = median(male) if len(male) >= SMALL_GROUP else None
    return {
        "country": country,
        "female": {"headcount": len(female), "median_gross": women},
        "male": {"headcount": len(male), "median_gross": men},
        "other_count": len(by_gender["other"]),
        "undisclosed_count": len(by_gender["undisclosed"]),
        "gap_pct": gap_pct(women, men) if compared(female, male) else None,
        "reason": reason,
    }


def gender_groups(
    f: InsightFilters, lookups: Lookups, values: dict[Any, list]
) -> list[tuple[dict | None, dict[str, list]]]:
    """Each country in the filter, in name order, then overall, with its values per gender."""
    found = []
    overall: dict[str, list] = {gender: [] for gender in GENDERS}
    for code, country in lookups.countries.items():
        if not f.country or code in f.country:
            by_gender = {gender: values.get((code, gender), []) for gender in GENDERS}
            found.append(({"code": code, "name": country.name}, by_gender))
            for gender, group in by_gender.items():
                overall[gender].extend(group)
    found.append((None, overall))
    return found


def gender_gap(
    f: InsightFilters, rates: fx.RateTable, lookups: Lookups, *, view: str = "pay_gap"
) -> dict:
    """Question 6, on annual pay, in four views (D62): Pay gap, per country and overall, Bonus,
    Quartiles and By level. Other and undisclosed are counted beside each. A comparison needs 5
    women and 5 men, and the quartiles 20 people as well. The new views publish counts, shares,
    medians and gaps, never a mean amount, which would add up across rows and give a withheld
    one back (D62)."""
    if view == "bonus":
        return {**header(f, rates), "view": view, "rows": bonus_rows(f, rates, lookups)}
    if view == "quartiles":
        return {**header(f, rates), "view": view, **pay_quartiles(f, rates)}
    if view == "by_level":
        return {**header(f, rates), "view": view, **level_gaps(f, rates, lookups)}
    values = grosses(f, rates, COUNTRY, GENDER)
    groups = gender_groups(f, lookups, values)
    rows = [gap_row(country, by_gender) for country, by_gender in groups]
    return {**header(f, rates), "view": view, "rows": rows}


def bonus_rows(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> list[dict]:
    """Bonus: who receives one, a bonus above zero in its own currency, and the mean and median
    bonus gap among those who do. The shares need 5 women and 5 men in the group, the gaps 5 of
    each with a bonus. Each bonus is `None` for someone without one."""
    convert = Converter(f, rates)
    values: dict[Any, list[Decimal | None]] = defaultdict(list)
    for bonus, currency, country, gender in population(f).values_list(
        "bonus_annual", "currency_code", COUNTRY, GENDER
    ):
        values[(country, gender)].append(q2(bonus * convert.rate(currency)) if bonus > 0 else None)
    rows = []
    for country, by_gender in gender_groups(f, lookups, values):
        women, men = by_gender["female"], by_gender["male"]
        paid = {g: [b for b in by_gender[g] if b is not None] for g in ("female", "male")}
        shares = compared(women, men)
        gaps = shares and compared(paid["female"], paid["male"])
        if not shares:
            reason = group_reason(len(women), len(men))
        elif not gaps:
            reason = gender_reason(len(paid["female"]), len(paid["male"]), " with a bonus")
        else:
            reason = None
        rows.append(
            {
                "country": country,
                "female": bonus_side(women, paid["female"], shares=shares, gaps=gaps),
                "male": bonus_side(men, paid["male"], shares=shares, gaps=gaps),
                "other_count": len(by_gender["other"]),
                "undisclosed_count": len(by_gender["undisclosed"]),
                "mean_gap_pct": gap_pct(average(paid["female"]), average(paid["male"]))
                if gaps
                else None,
                "median_gap_pct": gap_pct(median(paid["female"]), median(paid["male"]))
                if gaps
                else None,
                "reason": reason,
            }
        )
    return rows


def bonus_side(everyone: list, receiving: list[Decimal], *, shares: bool, gaps: bool) -> dict:
    """One gender of a group in the Bonus view: the receiving share when the group can be
    compared, the median bonus when those receiving one can."""
    return {
        "headcount": len(everyone),
        "receiving": len(receiving) if shares else None,
        "receiving_pct": q1(Decimal(len(receiving)) / len(everyone) * 100) if shares else None,
        "median_bonus": median(receiving) if gaps else None,
    }


def pay_quartiles(f: InsightFilters, rates: fx.RateTable) -> dict:
    """Quartiles: women and men ranked by gross in the reporting currency, ties by employee id,
    cut at floor(k * n / 4), the lowest quartile first, as the UK method compares women and men.
    Other and undisclosed are counted once beside it, never placed in a quartile. It needs 20
    women and men, 5 of each. A simplification of the UK method, which splits tied pay across a
    boundary by gender (D62)."""
    convert = Converter(f, rates)
    ranked = []
    beside = {"other": 0, "undisclosed": 0}
    for gross, currency, employee, gender in population(f).values_list(
        "gross_annual", "currency_code", "employee_id", GENDER
    ):
        if gender in beside:
            beside[gender] += 1
        else:
            ranked.append((q2(gross * convert.rate(currency)), employee, gender))
    ranked.sort()
    n = len(ranked)
    women = sum(1 for _, _, gender in ranked if gender == "female")
    payload = {
        "headcount": n,
        "other_count": beside["other"],
        "undisclosed_count": beside["undisclosed"],
        "quartiles": None,
        "reason": None,
    }
    if n == 0:
        return payload
    if n < SPREAD_GROUP:
        return {**payload, "reason": f"fewer than {SPREAD_GROUP} people"}
    if reason := gender_reason(women, n - women):
        return {**payload, "reason": reason}
    cuts = [k * n // 4 for k in range(5)]
    quartiles = []
    for index in range(4):
        group = [gender for _, _, gender in ranked[cuts[index] : cuts[index + 1]]]
        female, male = group.count("female"), group.count("male")
        quartiles.append(
            {
                "quartile": index + 1,
                "headcount": len(group),
                "female": female,
                "male": male,
                "female_pct": q1(Decimal(female) / len(group) * 100),
                "male_pct": q1(Decimal(male) / len(group) * 100),
            }
        )
    return {**payload, "quartiles": quartiles}


def level_gaps(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """By level: per country in the filter, in name order, and per level 1 to 6, the women's and
    men's medians and the mean and median gap, each as a share of men's pay, flagged when the
    mean gap, before rounding, is 5% or more either way (EU Directive 2023/970 Article 10). Each
    needs 5 women and 5 men in that country and level. Other and undisclosed are counted per
    country beside the view, never per level (D62)."""
    values = grosses(f, rates, COUNTRY, LEVEL, GENDER)
    rows, others = [], []
    for code, country in lookups.countries.items():
        if f.country and code not in f.country:
            continue
        name = {"code": code, "name": country.name}
        others.append(
            {
                "country": name,
                **{
                    f"{gender}_count": sum(
                        len(values.get((code, level, gender), [])) for level in LEVELS
                    )
                    for gender in ("other", "undisclosed")
                },
            }
        )
        for level in LEVELS:
            women = values.get((code, level, "female"), [])
            men = values.get((code, level, "male"), [])
            shown = compared(women, men) and average(men) > 0
            mean_gap = (average(men) - average(women)) / average(men) * 100 if shown else None
            rows.append(
                {
                    "country": name,
                    "level": level,
                    "female": {
                        "headcount": len(women),
                        "median_gross": median(women) if shown else None,
                    },
                    "male": {"headcount": len(men), "median_gross": median(men) if shown else None},
                    "mean_gap_pct": q1(mean_gap) if shown else None,
                    "median_gap_pct": gap_pct(median(women), median(men)) if shown else None,
                    "flagged": shown and abs(mean_gap) >= GAP_FLAG,
                    "reason": group_reason(len(women), len(men)),
                }
            )
    return {"rows": rows, "others": others}


def trend(
    f: InsightFilters, rates: fx.RateTable, lookups: Lookups, *, measure: str = "total_cost"
) -> dict:
    """Question 7: headcount and total cost on the period's first day, each month-end between and
    its last day, every date at the rate effective on `end` (D62, D64). A span adds at the first
    date it covers and drops at the first it does not, so one pass over the spans and one over
    the dates do it. `measure` only picks the card's line, and both figures are always here."""
    ends = period_dates(f.start, f.end)
    convert = Converter(f, rates)
    people = [0] * (len(ends) + 1)
    costs: dict[str, list[Decimal]] = defaultdict(lambda: [Decimal(0)] * (len(ends) + 1))
    for span in spans(f, ends[0], ends[-1]):
        start = bisect_left(ends, span.first)
        stop = len(ends) if span.stop is None else bisect_left(ends, span.stop)
        if start < stop:
            people[start] += 1
            people[stop] -= 1
            costs[span.currency][start] += span.total_cost
            costs[span.currency][stop] -= span.total_cost
    points = []
    headcount = 0
    running: dict[str, Decimal] = defaultdict(Decimal)
    for index, day in enumerate(ends):
        headcount += people[index]
        for currency, deltas in costs.items():
            running[currency] += deltas[index]
        total = sum((cost * convert.rate(ccy) for ccy, cost in running.items()), Decimal(0))
        shown = headcount >= SMALL_GROUP
        points.append(
            {
                "date": day,
                "headcount": headcount,
                "total_cost": q2(total) if shown else None,
            }
        )
    return {**header(f, rates), "measure": measure, "points": points}


BRIDGE_PARTS = ("start", "leavers", "joiners", "pay_changes", "end")
CHANGES = ("leavers", "joiners", "pay_changes")
CHANGE_NAMES = {"leavers": "leavers", "joiners": "joiners", "pay_changes": "pay changes"}


@dataclass(frozen=True)
class Bridge:
    """The period's movement in the reporting currency, each sum converted and quantised once. The
    pay changes are summed from the stayers here, and the card shows the balancing figure."""

    start_date: date
    end_date: date
    people: dict[str, int]
    amounts: dict[str, Decimal]
    summed_pay_changes: Decimal

    @property
    def pay_changes(self) -> Decimal:
        """End minus start plus leavers minus joiners, so the five parts add up to the cent."""
        amounts = self.amounts
        return amounts["end"] - amounts["start"] + amounts["leavers"] - amounts["joiners"]


def bridge(f: InsightFilters, rates: fx.RateTable) -> Bridge:
    """Who was employed on the period's first day and on its last, and what each cost, at the
    rate effective on the last (D62, D64), so the start and end are trend's first and last
    points. Leavers count at the start alone, joiners at the end alone, stayers at both."""
    start, end = f.start, f.end
    at_start: dict[int, Span] = {}
    at_end: dict[int, Span] = {}
    for span in spans(f, start, end):
        if span.counts_on(start):
            at_start[span.employee] = span
        if span.counts_on(end):
            at_end[span.employee] = span
    part_sums: dict[str, dict[str, Decimal]] = {part: defaultdict(Decimal) for part in BRIDGE_PARTS}
    for employee, span in at_start.items():
        part_sums["start"][span.currency] += span.total_cost
        if employee in at_end:
            part_sums["pay_changes"][span.currency] -= span.total_cost
        else:
            part_sums["leavers"][span.currency] += span.total_cost
    for employee, span in at_end.items():
        part_sums["end"][span.currency] += span.total_cost
        if employee in at_start:
            part_sums["pay_changes"][span.currency] += span.total_cost
        else:
            part_sums["joiners"][span.currency] += span.total_cost
    convert = Converter(f, rates)

    def converted(part: str) -> Decimal:
        by_currency = part_sums[part].items()
        return q2(sum((cost * convert.rate(ccy) for ccy, cost in by_currency), Decimal(0)))

    stayers = len(at_start.keys() & at_end.keys())
    return Bridge(
        start_date=start,
        end_date=end,
        people={
            "start": len(at_start),
            "leavers": len(at_start) - stayers,
            "joiners": len(at_end) - stayers,
            "pay_changes": stayers,
            "end": len(at_end),
        },
        amounts={part: converted(part) for part in ("start", "leavers", "joiners", "end")},
        summed_pay_changes=converted("pay_changes"),
    )


def cost_bridge(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 8: start, minus leavers, plus joiners, plus pay changes, end, over the period
    (D62, D64). Start and end need five people each. When leavers, joiners or stayers
    number 1 to 4, the changes with people in them show their people alone, since any one could
    be worked out from the others: the short one says why and the rest name it. A part with
    nobody shows 0.00, which gives nothing away."""
    movement = bridge(f, rates)
    amounts = {
        "start": movement.amounts["start"],
        "leavers": -movement.amounts["leavers"],
        "joiners": movement.amounts["joiners"],
        "pay_changes": movement.pay_changes,
        "end": movement.amounts["end"],
    }
    short = [part for part in CHANGES if 0 < movement.people[part] < SMALL_GROUP]
    parts = []
    for part in BRIDGE_PARTS:
        people, amount, reason = movement.people[part], amounts[part], None
        if 0 < people < SMALL_GROUP:
            amount, reason = None, f"fewer than {SMALL_GROUP} people"
        elif part in CHANGES and short and people:
            amount, reason = None, f"withheld with the {CHANGE_NAMES[short[0]]}"
        parts.append({"part": part, "people": people, "amount": amount, "reason": reason})
    return {
        **header(f, rates),
        "start_date": movement.start_date,
        "end_date": movement.end_date,
        "parts": parts,
    }


def completed_years(start: date, end: date) -> int:
    """Whole years from `start` to `end`, counted on anniversaries, so 29 February's falls on 28
    February in the years without one."""
    try:
        anniversary = start.replace(year=end.year)
    except ValueError:
        anniversary = date(end.year, 2, 28)
    return end.year - start.year - (1 if end < anniversary else 0)


def tenure_band(years: int) -> str:
    """The last band whose lower bound the years reach."""
    return [key for key, _, low in TENURE_BANDS if years >= low][-1]


def by_tenure(
    f: InsightFilters, rates: fx.RateTable, lookups: Lookups, *, level: str = "all"
) -> dict:
    """Question 9: median gross by completed years of service at `end`, or at the last date for
    someone who left, within one level or all of them (D62). Under five people a band shows its
    headcount alone."""
    convert = Converter(f, rates)
    records = population(f)
    if level != "all":
        records = records.filter(employee__level=int(level))
    values: dict[str, list[Decimal]] = {key: [] for key, _, _ in TENURE_BANDS}
    for gross, currency, joined, left in records.values_list(
        "gross_annual", "currency_code", "employee__joining_date", "employee__last_date"
    ):
        until = min(f.end, left) if left else f.end
        band = tenure_band(completed_years(joined, until))
        values[band].append(q2(gross * convert.rate(currency)))
    rows = [
        {
            "band": key,
            "label": label,
            "headcount": len(values[key]),
            "median_gross": median(values[key]) if len(values[key]) >= SMALL_GROUP else None,
        }
        for key, label, _ in TENURE_BANDS
    ]
    return {**header(f, rates), "level": level, "rows": rows}


EARNING = SalaryComponent.Kind.EARNING
DEDUCTION = SalaryComponent.Kind.DEDUCTION
EMPLOYER = SalaryComponent.Kind.EMPLOYER_CONTRIBUTION


@dataclass(frozen=True)
class Component:
    code: str
    name: str
    kind: str
    sort_order: int


@dataclass
class Mix:
    """One country's pay in the reporting currency: each component and how many hold it, then
    bonus, gross and total cost."""

    headcount: int = 0
    components: dict[Component, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    holders: dict[Component, int] = field(default_factory=lambda: defaultdict(int))
    bonus: Decimal = Decimal(0)
    bonus_holders: int = 0
    gross: Decimal = Decimal(0)
    total_cost: Decimal = Decimal(0)


BONUS = Component("BONUS", "Bonus", EARNING, 0)
NET = Component("NET", "Net pay", EARNING, 0)


def cost_mix(
    f: InsightFilters, rates: fx.RateTable, lookups: Lookups, *, view: str = "cost"
) -> dict:
    """Question 10: one bar per country in the filter, all six without one, in name order (D62).
    `view=cost` gives base, each allowance of the country, bonus and the employer contribution
    as shares of total cost, `view=take_home` net pay and each deduction as shares of gross. The
    amounts are summed per country and currency and converted, so a country whose records are in
    two currencies still adds up, and each share is rounded to one decimal on its own.

    A share times the country's total cost on by-country gives back what its holders are paid,
    so a country shows its headcount alone when it has fewer than five people, or when a segment
    it shows is held by 1 to 4 of them, the short segment named (D62). `segments` gives every
    segment of the shown bars in one order, for the card to stack them."""
    convert = Converter(f, rates)
    records = population(f)
    mixes: dict[str, Mix] = defaultdict(Mix)
    for row in records.values(COUNTRY, "currency_code").annotate(
        people=Count("id"),
        bonus=Sum("bonus_annual"),
        bonus_holders=Count("id", filter=Q(bonus_annual__gt=0)),
        gross=Sum("gross_annual"),
        cost=Sum("total_cost_annual"),
    ):
        rate = convert.rate(row["currency_code"])
        mix = mixes[row[COUNTRY]]
        mix.headcount += row["people"]
        mix.bonus += row["bonus"] * rate
        mix.bonus_holders += row["bonus_holders"]
        mix.gross += row["gross"] * rate
        mix.total_cost += row["cost"] * rate
    lines = (
        CompensationLine.objects.filter(record__in=records)
        .order_by()
        .values(
            "record__employee__country_id",
            "record__currency_code",
            "component__code",
            "component__name",
            "component__kind",
            "component__sort_order",
        )
        .annotate(amount=Sum("annual_amount"), holders=Count("id", filter=Q(annual_amount__gt=0)))
    )
    for row in lines:
        component = Component(
            row["component__code"],
            row["component__name"],
            row["component__kind"],
            row["component__sort_order"],
        )
        rate = convert.rate(row["record__currency_code"])
        mix = mixes[row["record__employee__country_id"]]
        mix.components[component] += row["amount"] * rate
        mix.holders[component] += row["holders"]
    rows, shown = [], []
    for code in f.country or tuple(lookups.countries):
        mix = mixes.get(code, Mix())
        parts = mix_parts(mix, view)
        held = {**mix.holders, BONUS: mix.bonus_holders, NET: mix.headcount}
        short = [c.name for c in parts if 0 < held[c] < SMALL_GROUP]
        reason = None
        if 0 < mix.headcount < SMALL_GROUP:
            reason = f"fewer than {SMALL_GROUP} people"
        elif short:
            reason = f"{short[0]} held by fewer than {SMALL_GROUP} people"
        segments = None
        if mix.headcount and reason is None and mix.total_cost > 0 and mix.gross > 0:
            segments = mix_segments(mix, parts, view)
            shown.extend(parts)
        rows.append(
            {
                "country": {"code": code, "name": lookups.countries[code].name},
                "headcount": mix.headcount,
                "segments": segments,
                "reason": reason,
            }
        )
    rows.sort(key=lambda row: row["country"]["name"])
    order = [{"code": c.code, "name": c.name} for c in ordered(set(shown), view)]
    return {**header(f, rates), "view": view, "segments": order, "rows": rows}


def ordered(components: set[Component] | list[Component], view: str) -> list[Component]:
    """Component order: base and the other earnings, bonus, then the employer's contribution, or
    net pay then each deduction, each kind by its sort order."""
    rank = {BONUS: (1, 0, ""), NET: (0, 0, "")}
    if view == "take_home":
        kinds = {DEDUCTION: 1}
    else:
        kinds = {EARNING: 0, EMPLOYER: 2}
    return sorted(
        components,
        key=lambda c: rank.get(c) or (kinds.get(c.kind, 3), c.sort_order, c.code),
    )


def mix_parts(mix: Mix, view: str) -> list[Component]:
    """The segments a country's bar shows in this view, in order."""
    if view == "take_home":
        return ordered([NET, *(c for c in mix.components if c.kind == DEDUCTION)], view)
    kept = [c for c in mix.components if c.kind in (EARNING, EMPLOYER)]
    return ordered([*kept, BONUS], view)


def mix_segments(mix: Mix, parts: list[Component], view: str) -> list[dict]:
    """Each segment's share of total cost, or of gross for take-home pay."""
    deductions = sum((mix.components[c] for c in parts if c.kind == DEDUCTION), Decimal(0))
    amounts = {**mix.components, BONUS: mix.bonus, NET: mix.gross - deductions}
    whole = mix.gross if view == "take_home" else mix.total_cost
    return [
        {"code": c.code, "name": c.name, "share_pct": q1(amounts[c] / whole * 100)} for c in parts
    ]


INSIGHTS: dict[str, Callable[..., dict]] = {
    "summary": summary,
    "by-country": by_country,
    "by-department": by_department,
    "distribution": distribution,
    "by-level": by_level,
    "gender-gap": gender_gap,
    "trend": trend,
    "cost-bridge": cost_bridge,
    "by-tenure": by_tenure,
    "cost-mix": cost_mix,
}

# Each card's control (D62): the parameter, then its values, the first being the default. It
# slices or measures, and never decides who is counted.
CONTROLS: dict[str, tuple[str, tuple[str, ...]]] = {
    "trend": ("measure", ("total_cost", "headcount")),
    "by-tenure": ("level", ("all", "1", "2", "3", "4", "5", "6")),
    "cost-mix": ("view", ("cost", "take_home")),
    "gender-gap": ("view", ("pay_gap", "bonus", "quartiles", "by_level")),
}
