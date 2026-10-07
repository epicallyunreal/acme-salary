"""Compensation rules: totals in this commit, revisions and the bulk entry point in the next."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.core.models import SalaryComponent
from apps.core.money import q2

ZERO = Decimal("0")


@dataclass(frozen=True)
class RecordInput:
    effective_from: date | None
    bonus_annual: Decimal
    note: str
    lines: Mapping[str, Decimal]


@dataclass(frozen=True)
class Totals:
    gross: Decimal
    net: Decimal
    total_cost: Decimal


def compute_totals(
    lines: Mapping[str, Decimal],
    bonus_annual: Decimal,
    components: Mapping[str, SalaryComponent],
) -> Totals:
    """SPEC section 4 rule 2 (DESIGN section 3):

    gross = earning lines + bonus, net = gross - deduction lines,
    total cost = gross + employer contribution lines. Pure, Decimal in and out.
    """
    earnings = ZERO
    deductions = ZERO
    employer = ZERO
    for code, amount in lines.items():
        component = components.get(code)
        if component is None:
            raise ValueError(f"unknown component {code}")
        if component.kind == SalaryComponent.Kind.EARNING:
            earnings += amount
        elif component.kind == SalaryComponent.Kind.DEDUCTION:
            deductions += amount
        else:
            employer += amount
    gross = q2(earnings + (bonus_annual or ZERO))
    return Totals(gross=gross, net=q2(gross - deductions), total_cost=q2(gross + employer))
