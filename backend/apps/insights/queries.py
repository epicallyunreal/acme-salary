"""The insights of SPEC section 9, each one read over one population (DESIGN 1.6).

Sums and counts are aggregated per (group, currency) in SQL, converted in Python with the Decimal
rate and quantised once. Medians convert every value first. Nothing converted is stored.

Two thresholds keep one person's pay off a card, a screenshot or an export (D59). A group of fewer
than five people shows its headcount alone, since a one-person total is that person's cost. The
spread figures, by-level's p10 to p90 and the distribution's range, bands and markers, need
twenty: at exactly five, by-level's five figures were every salary in the group.

`trend` and `cost-bridge` read the people employed on each of several dates (`spans`), at the one
rate effective on `on`, and Include exited does not apply to them (D62). A card may have one
control of its own (`CONTROLS`), which slices or measures and never decides who is counted.
"""

from __future__ import annotations

import calendar
import math
import statistics
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, F, Q, QuerySet, Sum

from apps.compensation.messages import msg
from apps.compensation.models import CompensationRecord
from apps.core import fx
from apps.core.exceptions import Invalid
from apps.core.models import Country, Department
from apps.core.money import q1, q2
from apps.employees.models import Gender

SMALL_GROUP = 5  # under five people a group shows its headcount alone (SPEC section 9, D59)
SPREAD_GROUP = 20  # under twenty, no percentile figures: each would be one person's pay (D59)
BANDS = 12
LEVELS = range(1, 7)
TREND_MONTHS = 24
BRIDGE_MONTHS = 12
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
    on: date
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
    on: date,
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
    return InsightFilters(
        country, department, include_exited, on, reporting, fx.asks_local(currency)
    )


def population(f: InsightFilters) -> QuerySet[CompensationRecord]:
    return population_on(f, f.on)


def population_on(f: InsightFilters, on: date) -> QuerySet[CompensationRecord]:
    """SPEC section 9: the record current on `on` of everyone active then, and with
    `include_exited` the last record of everyone who left before it. Future joiners never.

    Live records of one employee never overlap, so at most one is current. An exited employee's
    last record alone ends after `last_date`, at `last_date + 1`.
    """
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


# Dates (D62)


def last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def months_before(day: date, months: int) -> date:
    """The same day `months` months earlier, or that month's last day when it is shorter, so 29
    February a year back is 28 February."""
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def month_ends(on: date) -> list[date]:
    """The 24 month-ends in the 24 months ending at `on`, oldest first: 31 Oct 2024 to 30 Sep 2026
    for 7 Oct 2026, ending at `on` itself when `on` is a month-end."""
    latest = on if on == last_day(on.year, on.month) else on.replace(day=1) - timedelta(days=1)
    months = latest.year * 12 + latest.month - 1
    ends = []
    for index in range(months - TREND_MONTHS + 1, months + 1):
        year, month = divmod(index, 12)
        ends.append(last_day(year, month + 1))
    return ends


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
    """The reporting currency and the month of its rates (D28). Local currency uses no rate."""
    if f.local:
        rate_month = {"label": fx.local_label(f.currency), "effective_from": None}
    else:
        rate_month = {
            "label": rates.month_label(f.currency),
            "effective_from": rates.month_of(f.currency),
        }
    return {"currency": f.currency, "rate_month": rate_month}


def by_cost(row: dict, name: Callable[[dict], str]) -> tuple:
    """Largest total cost first, equal costs by name. Groups that show their headcount alone follow
    in name order, so the order never hints at a withheld total (D59)."""
    cost = row["total_cost"]
    return (cost is None, -(cost or 0), name(row))


# Insights


def summary(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 1: headcount, total cost, mean and median gross, with the countries and
    departments they span."""
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
    }


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


def gap_row(country: dict | None, by_gender: dict[str, list[Decimal]]) -> dict:
    """The medians of women and men and the unadjusted gap, each median only for five people or
    more. Other and undisclosed are counted, never given a median."""
    female, male = by_gender["female"], by_gender["male"]
    row = {
        "country": country,
        "female": {
            "headcount": len(female),
            "median_gross": median(female) if len(female) >= SMALL_GROUP else None,
        },
        "male": {
            "headcount": len(male),
            "median_gross": median(male) if len(male) >= SMALL_GROUP else None,
        },
        "other_count": len(by_gender["other"]),
        "undisclosed_count": len(by_gender["undisclosed"]),
        "gap_pct": None,
        "reason": None,
    }
    if len(female) < SMALL_GROUP or len(male) < SMALL_GROUP:
        row["reason"] = "group too small"
    else:
        women, men = row["female"]["median_gross"], row["male"]["median_gross"]
        row["gap_pct"] = q1((men - women) / men * 100)
    return row


def gender_gap(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 6: per country in the filter, in name order, then overall."""
    values = grosses(f, rates, COUNTRY, GENDER)
    rows = []
    for code, country in lookups.countries.items():
        if not f.country or code in f.country:
            by_gender = {gender: values.get((code, gender), []) for gender in GENDERS}
            rows.append(gap_row({"code": code, "name": country.name}, by_gender))
    overall: dict[str, list[Decimal]] = {gender: [] for gender in GENDERS}
    for (_, gender), group in values.items():
        overall[gender].extend(group)
    rows.append(gap_row(None, overall))
    return {**header(f, rates), "rows": rows}


def trend(
    f: InsightFilters, rates: fx.RateTable, lookups: Lookups, *, measure: str = "total_cost"
) -> dict:
    """Question 7: headcount and total cost at the 24 month-ends ending at `on`, every month at
    the rate effective on `on` (D62). A span adds at the first month-end it covers and drops at
    the first it does not, so one pass over the spans and one over the dates do it. `measure`
    only picks the card's line, and both figures are always here."""
    ends = month_ends(f.on)
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
    for index, month_end in enumerate(ends):
        headcount += people[index]
        for currency, deltas in costs.items():
            running[currency] += deltas[index]
        total = sum((cost * convert.rate(ccy) for ccy, cost in running.items()), Decimal(0))
        shown = headcount >= SMALL_GROUP
        points.append(
            {
                "month_end": month_end,
                "headcount": headcount,
                "total_cost": q2(total) if shown else None,
            }
        )
    return {**header(f, rates), "measure": measure, "latest": ends[-1], "points": points}


BRIDGE_PARTS = ("start", "leavers", "joiners", "pay_changes", "end")
CHANGES = ("leavers", "joiners", "pay_changes")
CHANGE_NAMES = {"leavers": "leavers", "joiners": "joiners", "pay_changes": "pay changes"}


@dataclass(frozen=True)
class Bridge:
    """The year's movement in the reporting currency, each sum converted and quantised once. The
    pay changes are summed from the stayers here, and the card shows the balancing figure."""

    start_date: date
    end_date: date
    people: dict[str, int]
    amounts: dict[str, Decimal]
    summed_pay_changes: Decimal
    currencies: int

    @property
    def pay_changes(self) -> Decimal:
        """End minus start plus leavers minus joiners, so the five parts add up to the cent."""
        a = self.amounts
        return a["end"] - a["start"] + a["leavers"] - a["joiners"]


def bridge(f: InsightFilters, rates: fx.RateTable) -> Bridge:
    """Who was employed a year before `on` and on `on`, and what each cost, at the rate effective
    on `on` (D62). Leavers count at the start alone, joiners at the end alone, stayers at both."""
    end = f.on
    start = months_before(end, BRIDGE_MONTHS)
    at_start: dict[int, Span] = {}
    at_end: dict[int, Span] = {}
    for span in spans(f, start, end):
        if span.counts_on(start):
            at_start[span.employee] = span
        if span.counts_on(end):
            at_end[span.employee] = span
    sums: dict[str, dict[str, Decimal]] = {part: defaultdict(Decimal) for part in BRIDGE_PARTS}
    for employee, span in at_start.items():
        sums["start"][span.currency] += span.total_cost
        if employee in at_end:
            sums["pay_changes"][span.currency] -= span.total_cost
        else:
            sums["leavers"][span.currency] += span.total_cost
    for employee, span in at_end.items():
        sums["end"][span.currency] += span.total_cost
        if employee in at_start:
            sums["pay_changes"][span.currency] += span.total_cost
        else:
            sums["joiners"][span.currency] += span.total_cost
    convert = Converter(f, rates)

    def converted(part: str) -> Decimal:
        return q2(sum((cost * convert.rate(ccy) for ccy, cost in sums[part].items()), Decimal(0)))

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
        currencies=len({span.currency for span in (*at_start.values(), *at_end.values())}),
    )


def cost_bridge(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict:
    """Question 8: start, minus leavers, plus joiners, plus pay changes, end, over the 12 months
    ending at `on` (D62). Start and end need five people each. When leavers, joiners or stayers
    number 1 to 4, all three changes show their people alone, since any one of them could be
    worked out from the others, the short one saying why. A part with nobody shows 0."""
    b = bridge(f, rates)
    amounts = {
        "start": b.amounts["start"],
        # Zero minus, so no leavers is 0.00 and never -0.00.
        "leavers": Decimal(0) - b.amounts["leavers"],
        "joiners": b.amounts["joiners"],
        "pay_changes": b.pay_changes,
        "end": b.amounts["end"],
    }
    short = [part for part in CHANGES if 0 < b.people[part] < SMALL_GROUP]
    parts = []
    for part in BRIDGE_PARTS:
        people, amount, reason = b.people[part], amounts[part], None
        if 0 < people < SMALL_GROUP:
            amount, reason = None, f"fewer than {SMALL_GROUP} people"
        elif part in CHANGES and short:
            amount, reason = None, f"withheld with the {CHANGE_NAMES[short[0]]}"
        parts.append({"part": part, "people": people, "amount": amount, "reason": reason})
    return {
        **header(f, rates),
        "start_date": b.start_date,
        "end_date": b.end_date,
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
    """Question 9: median gross by completed years of service at `on`, or at the last date for
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
        until = min(f.on, left) if left else f.on
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
}

# Each card's control (D62): the parameter, then its values, the first being the default. It
# slices or measures, and never decides who is counted.
CONTROLS: dict[str, tuple[str, tuple[str, ...]]] = {
    "trend": ("measure", ("total_cost", "headcount")),
    "by-tenure": ("level", ("all", "1", "2", "3", "4", "5", "6")),
}
