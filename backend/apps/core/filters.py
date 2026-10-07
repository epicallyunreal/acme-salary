"""Query-parameter helpers shared by the list views. Shape only, no rules."""

from django_filters import BaseInFilter, CharFilter, NumberFilter


class CharInFilter(BaseInFilter, CharFilter):
    """`?country=IN,US` on a text lookup."""


class NumberInFilter(BaseInFilter, NumberFilter):
    """`?level=1,2` on a numeric lookup."""


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
