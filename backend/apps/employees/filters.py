"""The directory's query parameters (SPEC F4), mapped onto the annotated queryset. No rules here."""

from django_filters import ChoiceFilter, DateFilter, FilterSet, NumberFilter, OrderingFilter

from apps.core.filters import CharInFilter, NumberInFilter
from apps.employees.models import Employee
from apps.employees.queries import gross_bound

STATUS_CHOICES = [("active", "active"), ("exited", "exited"), ("upcoming", "upcoming")]


class StableOrderingFilter(OrderingFilter):
    """Every ordering ends with `id`, so pages never shuffle between requests."""

    def filter(self, qs, value):
        if not value:
            return qs
        ordering = [self.get_ordering_value(param) for param in value]
        return qs.order_by(*ordering, "id")


class DirectoryFilterSet(FilterSet):
    country = CharInFilter(field_name="country__code")
    department = CharInFilter(field_name="department__code")
    designation = CharInFilter(field_name="designation")
    level = NumberInFilter(field_name="level")
    status = ChoiceFilter(field_name="status", choices=STATUS_CHOICES)
    gross_min = NumberFilter(method="filter_gross_min")
    gross_max = NumberFilter(method="filter_gross_max")
    joined_after = DateFilter(field_name="joining_date", lookup_expr="gte")
    joined_before = DateFilter(field_name="joining_date", lookup_expr="lte")
    ordering = StableOrderingFilter(
        fields=(
            ("full_name", "full_name"),
            ("employee_code", "employee_code"),
            ("department__name", "department"),
            ("country__name", "country"),
            ("designation", "designation"),
            ("level", "level"),
            ("gross", "gross"),
            ("joining_date", "joining_date"),
        )
    )

    class Meta:
        model = Employee
        fields: list[str] = []

    def filter_gross_min(self, queryset, name, value):
        return queryset.filter(gross__gte=gross_bound(value, "min"))

    def filter_gross_max(self, queryset, name, value):
        return queryset.filter(gross__lte=gross_bound(value, "max"))
