"""The directory's query parameters (SPEC F4), mapped onto the annotated queryset. No rules here."""

from django.db.models import Q
from django_filters import ChoiceFilter, DateFilter, FilterSet, NumberFilter, OrderingFilter

from apps.core.exceptions import Invalid
from apps.core.filters import BoundedSearchFilter, CharInFilter, ChoiceInFilter
from apps.employees.models import Employee
from apps.employees.queries import STATUSES, gross_bound, parse_employee_code

# `any` returns everyone, since without `status` the directory holds its active employees (D64).
STATUS_CHOICES = [(status, status) for status in (*STATUSES, "any")]
# Each title is one more OR, and SQLite refuses an expression deeper than 1,000 with a 500 (D61).
MAX_DESIGNATIONS = 20


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
    designation = CharInFilter(method="filter_designation")
    level = ChoiceInFilter(field_name="level", choices=[(str(n), str(n)) for n in range(1, 7)])
    status = ChoiceFilter(method="filter_status", choices=STATUS_CHOICES)
    gross_min = NumberFilter(method="filter_gross_min")
    gross_max = NumberFilter(method="filter_gross_max")
    joined_after = DateFilter(field_name="joining_date", lookup_expr="gte")
    joined_before = DateFilter(field_name="joining_date", lookup_expr="lte")
    ordering = StableOrderingFilter(
        fields=(
            ("full_name", "full_name"),
            # The code is ACME-<id>, so its order is the id's (D48).
            ("id", "employee_code"),
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

    def __init__(self, data=None, *args, **kwargs):
        """Active when `status` is not given, so the directory and its export open on the
        employees on staff, as the grid does (D64)."""
        if data is not None and not data.get("status"):
            data = data.copy()
            data["status"] = "active"
        super().__init__(data, *args, **kwargs)

    def filter_status(self, queryset, name, value):
        return queryset if value == "any" else queryset.filter(status=value)

    def filter_designation(self, queryset, name, values):
        """Each title exactly, in any case: `product manager` finds `Product Manager`."""
        if len(values) > MAX_DESIGNATIONS:
            message = f"designation accepts at most {MAX_DESIGNATIONS} titles"
            raise Invalid({"designation": [message]})
        matching = Q()
        for value in values:
            matching |= Q(designation__iexact=value)
        return queryset.filter(matching)

    def filter_gross_min(self, queryset, name, value):
        return queryset.filter(gross__gte=gross_bound(value, "min"))

    def filter_gross_max(self, queryset, name, value):
        return queryset.filter(gross__lte=gross_bound(value, "max"))


class EmployeeSearchFilter(BoundedSearchFilter):
    """`?search=` for people typing (SPEC F4, D48). Each word matches part of a name or an email,
    a legacy_code in any case, or an ACME code read as its number, so ACME-0017 and acme-17 both
    find ACME-17. Words combine with AND, as DRF's SearchFilter does."""

    def filter_queryset(self, request, queryset, view):
        for term in self.get_search_terms(request):
            condition = (
                Q(full_name__icontains=term)
                | Q(email__icontains=term)
                | Q(legacy_code__iexact=term)
            )
            number = parse_employee_code(term)
            if number is not None:
                condition |= Q(pk=number)
            queryset = queryset.filter(condition)
        return queryset
