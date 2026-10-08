"""Query-parameter helpers shared by the list views. Shape only, no rules."""

from collections.abc import Sequence

from django_filters import BaseInFilter, CharFilter, ChoiceFilter, NumberFilter
from rest_framework.filters import SearchFilter

from apps.core.exceptions import Invalid, clip

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


TRUE = frozenset({"1", "true", "yes", "on"})
FALSE = frozenset({"0", "false", "no", "off"})


def parse_bool(value: str | None, *, name: str, default: bool = False) -> bool:
    """A query parameter that is true or false. Anything else is a 400, not a quiet false."""
    if value in (None, ""):
        return default
    given = value.strip().lower()
    if given in TRUE:
        return True
    if given in FALSE:
        return False
    raise Invalid({name: [f"{name} must be true or false"]})


def parse_choice(
    value: str | None, *, name: str, choices: Sequence[str], default: str | None = None
) -> str:
    """One of `choices`, in any case. Nothing given is `default`, or a 400 when there is none.
    Anything else is a 400 that lists them."""
    listed = f"{', '.join(choices[:-1])} or {choices[-1]}"
    if value in (None, ""):
        if default is None:
            raise Invalid({name: [f"{name} must be {listed}"]})
        return default
    given = value.strip().lower()
    if given in choices:
        return given
    raise Invalid({name: [f"{name} must be {listed}, got {clip(value)}"]})
