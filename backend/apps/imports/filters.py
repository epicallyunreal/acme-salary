"""The review grid's query parameters (SPEC F2). No rules here."""

from django_filters import FilterSet

from apps.core.filters import ChoiceInFilter
from apps.imports.models import ImportRow


class ImportRowFilterSet(FilterSet):
    """`?status=error,warning`; every value must be one of the row statuses."""

    status = ChoiceInFilter(field_name="status", choices=ImportRow.Status.choices)

    class Meta:
        model = ImportRow
        fields = ["status"]
