"""What each export holds (SPEC F6, D60): a header, snake_case keys for JSON and rows of plain
values. The directory's rows come from the filtered queryset the view hands in, and an insight's
from the dict its query returns, before any rendering, so numbers stay numbers.
"""

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db.models import QuerySet

from apps.compensation.models import CompensationRecord
from apps.core import fx
from apps.employees.models import Employee
from apps.employees.queries import pick_shown
from apps.insights.queries import SMALL_GROUP, SPREAD_GROUP

# Rows fetched per query while a directory export is written; the records come one prefetch a chunk.
CHUNK = 1000
OVERALL = "Overall"


@dataclass(frozen=True)
class Table:
    header: tuple[str, ...]
    keys: tuple[str, ...]
    rows: Iterable[tuple[Any, ...]]


def table(columns: tuple[tuple[str, str], ...], rows: Iterable[tuple[Any, ...]]) -> Table:
    return Table(tuple(label for label, _ in columns), tuple(key for _, key in columns), rows)


# The directory


DIRECTORY_COLUMNS = (
    ("Employee code", "employee_code"),
    ("Legacy code", "legacy_code"),
    ("Full name", "full_name"),
    ("Email", "email"),
    ("Department", "department"),
    ("Designation", "designation"),
    ("Level", "level"),
    ("Country", "country"),
    ("Currency", "currency"),
    ("Gross (local)", "gross_local"),
    ("Bonus (local)", "bonus_local"),
    ("Gross ({reporting})", "gross_reporting"),
    ("Status", "status"),
    ("Joining date", "joining_date"),
    ("Last date", "last_date"),
    ("Effective from", "effective_from"),
    ("Version", "version"),
)


def directory_table(
    employees: QuerySet[Employee], *, on: date, rates: fx.RateTable, currency: str
) -> Table:
    """SPEC F6's seventeen columns for every employee the directory's filters, search and ordering
    leave, the pages ignored. The amounts are the shown record's: current on `on`, else the latest.
    The rows are read a chunk at a time as a writer asks for them.

    Every currency a live record is in must have a rate before the first row is read: a CSV has
    sent its 200 by the time a row fails, and would end cut off instead of answering 400."""
    live = CompensationRecord.objects.filter(cancelled_at__isnull=True).order_by()
    for code in live.values_list("currency_code", flat=True).distinct():
        rates.rate(code, currency)

    def rows() -> Iterator[tuple[Any, ...]]:
        for employee in employees.iterator(chunk_size=CHUNK):
            yield directory_row(employee, on, rates, currency)

    columns = tuple((label.format(reporting=currency), key) for label, key in DIRECTORY_COLUMNS)
    return table(columns, rows())


def directory_row(employee: Employee, on: date, rates: fx.RateTable, currency: str) -> tuple:
    record = pick_shown(employee.live_records, on)
    local = record.currency_code if record else employee.country.currency_code
    return (
        employee.employee_code,
        employee.legacy_code,
        employee.full_name,
        employee.email,
        employee.department.name,
        employee.designation,
        employee.level,
        employee.country.name,
        local,
        record.gross_annual if record else None,
        record.bonus_annual if record else None,
        rates.convert(record.gross_annual, local, currency) if record else None,
        employee.status,
        employee.joining_date,
        employee.last_date,
        record.effective_from if record else None,
        record.version if record else None,
    )


# The insights. Every table ends with why a figure is withheld, in the screen's words, and with
# the currency and the rate month every converted figure depends on, since a file travels alone.


def withheld(headcount: int, figure: Any, need: int) -> str | None:
    """`fewer than 5 people` when the API withheld a figure from someone (D59). A group with
    nobody has no figures to withhold."""
    return f"fewer than {need} people" if headcount and figure is None else None


def currency_and_rates(payload: dict) -> tuple[str, str]:
    """The last two columns of every insight table: the reporting currency and the rate month."""
    return payload["currency"], payload["rate_month"]["label"]


SUMMARY_COLUMNS = (
    ("Headcount", "headcount"),
    ("Total cost", "total_cost"),
    ("Mean gross", "mean_gross"),
    ("Median gross", "median_gross"),
    ("Countries", "countries"),
    ("Departments", "departments"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)


def summary_table(payload: dict) -> Table:
    row = (
        payload["headcount"],
        payload["total_cost"],
        payload["mean_gross"],
        payload["median_gross"],
        payload["countries"],
        payload["departments"],
        withheld(payload["headcount"], payload["total_cost"], SMALL_GROUP),
        *currency_and_rates(payload),
    )
    return table(SUMMARY_COLUMNS, [row])


BY_COUNTRY_COLUMNS = (
    ("Country code", "country_code"),
    ("Country", "country"),
    ("Headcount", "headcount"),
    ("Total cost", "total_cost"),
    ("Median gross", "median_gross"),
    ("Share %", "share_pct"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)


def by_country_table(payload: dict) -> Table:
    rows = [
        (
            row["country"]["code"],
            row["country"]["name"],
            row["headcount"],
            row["total_cost"],
            row["median_gross"],
            row["share_pct"],
            withheld(row["headcount"], row["total_cost"], SMALL_GROUP),
            *currency_and_rates(payload),
        )
        for row in payload["rows"]
    ]
    return table(BY_COUNTRY_COLUMNS, rows)


BY_DEPARTMENT_COLUMNS = (
    ("Department code", "department_code"),
    ("Department", "department"),
    ("Headcount", "headcount"),
    ("Total cost", "total_cost"),
    ("Mean gross", "mean_gross"),
    ("Median gross", "median_gross"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)


def by_department_table(payload: dict) -> Table:
    rows = [
        (
            row["department"]["code"],
            row["department"]["name"],
            row["headcount"],
            row["total_cost"],
            row["mean_gross"],
            row["median_gross"],
            withheld(row["headcount"], row["total_cost"], SMALL_GROUP),
            *currency_and_rates(payload),
        )
        for row in payload["rows"]
    ]
    return table(BY_DEPARTMENT_COLUMNS, rows)


DISTRIBUTION_COLUMNS = (
    ("Band", "band"),
    ("From", "from"),
    ("To", "to"),
    ("People", "people"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)


def distribution_table(payload: dict) -> Table:
    """One row per band, numbered from 1. Without bands, under twenty people or with nobody, one
    row carries the headcount alone (D60)."""
    if payload["bands"] is None:
        headcount = payload["headcount"]
        reason = withheld(headcount, payload["bands"], SPREAD_GROUP)
        return table(
            DISTRIBUTION_COLUMNS,
            [(None, None, None, headcount, reason, *currency_and_rates(payload))],
        )
    rows = [
        (
            band["index"] + 1,
            band["from"],
            band["to"],
            band["count"],
            None,
            *currency_and_rates(payload),
        )
        for band in payload["bands"]
    ]
    return table(DISTRIBUTION_COLUMNS, rows)


BY_LEVEL_COLUMNS = (
    ("Level", "level"),
    ("Headcount", "headcount"),
    ("p10", "p10"),
    ("p25", "p25"),
    ("Median", "median"),
    ("p75", "p75"),
    ("p90", "p90"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)


def by_level_table(payload: dict) -> Table:
    rows = [
        (
            row["level"],
            row["headcount"],
            row["p10"],
            row["p25"],
            row["median"],
            row["p75"],
            row["p90"],
            withheld(row["headcount"], row["median"], SPREAD_GROUP),
            *currency_and_rates(payload),
        )
        for row in payload["rows"]
    ]
    return table(BY_LEVEL_COLUMNS, rows)


GENDER_GAP_COLUMNS = (
    ("Country code", "country_code"),
    ("Country", "country"),
    ("Gender", "gender"),
    ("Headcount", "headcount"),
    ("Median gross", "median_gross"),
    ("Gap %", "gap_pct"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)


def gender_gap_table(payload: dict) -> Table:
    """One row per group and gender: female and male with their medians, other and undisclosed
    counted and never given one (SPEC section 9). The group's gap and its reason, `group too
    small` as the card says, repeat on each of its rows."""
    rows = []
    for row in payload["rows"]:
        group = row["country"]
        code, name = (group["code"], group["name"]) if group else (None, OVERALL)
        genders = (
            ("female", row["female"]["headcount"], row["female"]["median_gross"]),
            ("male", row["male"]["headcount"], row["male"]["median_gross"]),
            ("other", row["other_count"], None),
            ("undisclosed", row["undisclosed_count"], None),
        )
        for gender, headcount, median in genders:
            rows.append(
                (
                    code,
                    name,
                    gender,
                    headcount,
                    median,
                    row["gap_pct"],
                    row["reason"],
                    *currency_and_rates(payload),
                )
            )
    return table(GENDER_GAP_COLUMNS, rows)


TREND_COLUMNS = (
    ("Month-end", "month_end"),
    ("Headcount", "headcount"),
    ("Total cost", "total_cost"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)


def trend_table(payload: dict) -> Table:
    """One row per month-end, both figures whatever the card draws (D62)."""
    rows = [
        (
            point["month_end"],
            point["headcount"],
            point["total_cost"],
            withheld(point["headcount"], point["total_cost"], SMALL_GROUP),
            *currency_and_rates(payload),
        )
        for point in payload["points"]
    ]
    return table(TREND_COLUMNS, rows)


BRIDGE_COLUMNS = (
    ("Part", "part"),
    ("Date", "date"),
    ("People", "people"),
    ("Amount", "amount"),
    ("Reason", "reason"),
    ("Currency", "currency"),
    ("Rates", "rates"),
)
BRIDGE_LABELS = {
    "start": "Start",
    "leavers": "Leavers",
    "joiners": "Joiners",
    "pay_changes": "Pay changes",
    "end": "End",
}


def cost_bridge_table(payload: dict) -> Table:
    """One row per part, the balancing pay change among them, so the amounts add up (D62)."""
    dates = {"start": payload["start_date"], "end": payload["end_date"]}
    rows = [
        (
            BRIDGE_LABELS[part["part"]],
            dates.get(part["part"]),
            part["people"],
            part["amount"],
            part["reason"],
            *currency_and_rates(payload),
        )
        for part in payload["parts"]
    ]
    return table(BRIDGE_COLUMNS, rows)


INSIGHT_TABLES: dict[str, Callable[[dict], Table]] = {
    "summary": summary_table,
    "by-country": by_country_table,
    "by-department": by_department_table,
    "distribution": distribution_table,
    "by-level": by_level_table,
    "gender-gap": gender_gap_table,
    "trend": trend_table,
    "cost-bridge": cost_bridge_table,
}
