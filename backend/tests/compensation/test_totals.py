from decimal import Decimal

import pytest

from apps.compensation.services import compute_totals
from apps.core.models import SalaryComponent

pytestmark = pytest.mark.django_db


@pytest.fixture
def components(lookups):
    return SalaryComponent.objects.in_bulk(field_name="code")


INDIA = {
    "BASE": Decimal("1450000"),
    "HRA": Decimal("580000"),
    "ALLOWANCES": Decimal("362500"),
    "TAX": Decimal("478500"),
    "EMPLOYER_CONTRIBUTION": Decimal("174000"),
}


def test_gross_net_and_total_cost_from_lines(components):
    totals = compute_totals(INDIA, Decimal("0"), components)

    assert totals.gross == Decimal("2392500.00")
    assert totals.net == Decimal("1914000.00")
    assert totals.total_cost == Decimal("2566500.00")


def test_bonus_is_part_of_gross_net_and_cost(components):
    totals = compute_totals(INDIA, Decimal("100000"), components)

    assert totals.gross == Decimal("2492500.00")
    assert totals.net == Decimal("2014000.00")
    assert totals.total_cost == Decimal("2666500.00")


def test_deductions_can_exceed_gross_and_net_goes_negative(components):
    totals = compute_totals(
        {"BASE": Decimal("100"), "TAX": Decimal("150")}, Decimal("0"), components
    )

    assert (totals.gross, totals.net, totals.total_cost) == (
        Decimal("100.00"),
        Decimal("-50.00"),
        Decimal("100.00"),
    )


def test_totals_are_quantised_half_up(components):
    totals = compute_totals(
        {"BASE": Decimal("0.005"), "TAX": Decimal("0.001")}, Decimal("0"), components
    )

    # gross is quantised first (0.005 -> 0.01), then net = 0.01 - 0.001 rounds back to 0.01
    assert (totals.gross, totals.net) == (Decimal("0.01"), Decimal("0.01"))


def test_empty_lines_give_zero_totals(components):
    totals = compute_totals({}, Decimal("0"), components)

    assert (totals.gross, totals.net, totals.total_cost) == (Decimal("0.00"),) * 3


def test_unknown_component_is_refused(components):
    with pytest.raises(ValueError, match="unknown component BONUS"):
        compute_totals({"BONUS": Decimal("1")}, Decimal("0"), components)
