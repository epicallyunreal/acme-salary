"""Query-parameter helpers shared by the list views. Shape only, no rules."""

from django_filters import BaseInFilter, CharFilter, ChoiceFilter, NumberFilter
from rest_framework.filters import SearchFilter

from apps.core.exceptions import Invalid

MAX_SEARCH_TERMS = 10


class CharInFilter(BaseInFilter, CharFilter):
    """`?country=IN,US` on a text lookup."""


class NumberInFilter(BaseInFilter, NumberFilter):
    """`?gross=1,2` on a numeric lookup with no fixed set of values."""


class ChoiceInFilter(BaseInFilter, ChoiceFilter):
    """`?level=1,2` where every value must be one of the choices, so a stray value is a 400 that
    names the field instead of an integer SQLite cannot hold."""


class BoundedSearchFilter(SearchFilter):
    """DRF's SearchFilter with a ceiling on the number of terms: every term adds a branch per
    field, and SQLite refuses an expression deeper than 1,000 with a 500."""

    def get_search_terms(self, request):
        terms = super().get_search_terms(request)
        if len(terms) > MAX_SEARCH_TERMS:
            raise Invalid({"search": [f"search accepts at most {MAX_SEARCH_TERMS} words"]})
        return terms


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
