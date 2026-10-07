"""Read-side lookups for the core app. Which components apply to a country lives here once, for
the validators (SPEC section 7, "component is not for this country") and the /meta/ endpoint."""

from __future__ import annotations

from collections.abc import Sequence

from django.db.models import QuerySet

from apps.core.models import SalaryComponent


def active_components() -> QuerySet[SalaryComponent]:
    return SalaryComponent.objects.filter(is_active=True).order_by("sort_order", "code")


def applies_to(component: SalaryComponent, country_code: str) -> bool:
    """A component is global or belongs to the country (SPEC section 5)."""
    return component.country_id is None or component.country_id == country_code


def components_for_country(
    country_code: str, components: Sequence[SalaryComponent] | None = None
) -> list[SalaryComponent]:
    """The global components plus the country's own, in sort order. Pass `components` to reuse
    one query across several countries."""
    pool = list(active_components()) if components is None else components
    return [component for component in pool if applies_to(component, country_code)]
