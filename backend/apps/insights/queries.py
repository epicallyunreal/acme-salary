"""The insights of SPEC section 9, each one read over one population (DESIGN 1.6).

Sums and counts are aggregated per (group, currency) in SQL, converted in Python with the Decimal
rate and quantised once. Medians convert every value first. Nothing converted is stored. A group
of fewer than five people publishes its headcount and total cost only, so a filter that isolates
one person never shows their pay.

TODO(step 7, exports): register each insight's table in apps/exports for /exports/insights/.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Count, F, Q, QuerySet, Sum

from apps.compensation.messages import msg
from apps.compensation.models import CompensationRecord
from apps.core import fx
from apps.core.exceptions import Invalid
from apps.core.models import Country, Department
from apps.core.money import q1, q2

SMALL_GROUP = 5  # SPEC section 9: under five people, headcount and total cost only
BANDS = 12
LEVELS = range(1, 7)
GENDERS = ("female", "male", "other", "undisclosed")

COUNTRY = "employee__country_id"
DEPARTMENT = "employee__department__code"


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
    since the per-country and per-department insights list every code in the filter."""
    errors = {}
    if unknown := [code for code in country if code not in lookups.countries]:
        errors["country"] = [msg("country_unknown", value=code) for code in unknown]
    if unknown := [code for code in department if code not in lookups.departments]:
        errors["department"] = [msg("department_unknown", value=code) for code in unknown]
    if errors:
        raise Invalid(errors)
    currencies = {code: c.currency_code for code, c in lookups.countries.items()}
    reporting = fx.resolve_reporting_currency(currency, list(country), currencies)
    local = (currency or "").strip().lower() == "local"
    return InsightFilters(tuple(country), tuple(department), include_exited, on, reporting, local)


def population(f: InsightFilters) -> QuerySet[CompensationRecord]:
    """SPEC section 9: the record current on `on` of everyone active then, and with
    `include_exited` the last record of everyone who left before it. Future joiners never.

    Live records of one employee never overlap, so at most one is current. An exited employee's
    last record alone ends after `last_date`, at `last_date + 1`.
    """
    on = f.on
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


# Groups


@dataclass
class Group:
    """One group's people, with sums in the reporting currency, not yet quantised."""

    headcount: int = 0
    total_cost: Decimal = Decimal(0)
    gross: Decimal = Decimal(0)
    grosses: list[Decimal] = field(default_factory=list)  # each converted and quantised


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


def percentiles(values: list[Decimal]) -> list[Decimal]:
    """p1 to p99 by the inclusive method, p1 at index 0 and p99 at index 98. One value is every
    percentile (SPEC section 9); callers have already turned away an empty list."""
    if len(values) == 1:
        return [values[0]] * 99
    return [q2(point) for point in statistics.quantiles(values, n=100, method="inclusive")]


def published(group: Group, values: list[Decimal], *, mean: bool = False) -> dict:
    """Headcount and total cost, then the mean and median for a group of five or more."""
    shown = group.headcount >= SMALL_GROUP
    figures = {
        "headcount": group.headcount,
        "total_cost": q2(group.total_cost) if group.headcount else None,
    }
    if mean:
        figures["mean_gross"] = q2(group.gross / group.headcount) if shown else None
    figures["median_gross"] = median(values) if shown else None
    return figures


def header(f: InsightFilters, rates: fx.RateTable) -> dict:
    """The reporting currency and the month of its rates (D28). Local currency uses no rate."""
    if f.local:
        rate_month = {"label": f"local currency ({f.currency})", "effective_from": None}
    else:
        rate_month = {
            "label": rates.month_label(f.currency),
            "effective_from": rates.month_of(f.currency),
        }
    return {"currency": f.currency, "rate_month": rate_month}


def by_cost(row: dict, name: Callable[[dict], str]) -> tuple:
    """Largest total cost first; groups with nobody last; equal costs by name."""
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
    bands, with p10, p50 and p90 marked. Nothing but the headcount for under five people."""
    values = grosses(f, rates)[()]
    payload = {
        **header(f, rates),
        "headcount": len(values),
        "p1": None,
        "p99": None,
        "bands": None,
        "markers": None,
    }
    if len(values) < SMALL_GROUP:
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
        # floor((v - p1) / width) with width = (p99 - p1) / 12, multiplied out so a value on a
        # band's edge lands in that band rather than the one below.
        band = math.floor((value - low) * BANDS / (high - low))
        counts[min(max(band, 0), BANDS - 1)] += 1
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
    """Question 5: min, p25, median, p75 and max gross per level, for five people or more."""
    values = grosses(f, rates, "employee__level")
    rows = []
    for level in LEVELS:
        group = sorted(values.get((level,), []))
        row = {
            "level": level,
            "headcount": len(group),
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "max": None,
        }
        if len(group) >= SMALL_GROUP:
            points = percentiles(group)
            row.update(
                min=group[0], p25=points[24], median=median(group), p75=points[74], max=group[-1]
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
    values = grosses(f, rates, COUNTRY, "employee__gender")
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


INSIGHTS: dict[str, Callable[[InsightFilters, fx.RateTable, Lookups], dict]] = {
    "summary": summary,
    "by-country": by_country,
    "by-department": by_department,
    "distribution": distribution,
    "by-level": by_level,
    "gender-gap": gender_gap,
}
