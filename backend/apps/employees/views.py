"""Directory and detail reads (SPEC F4, section 8). Create, edit and exit arrive in step 4.

Views parse `on` and `currency`, load one RateTable for the request, and hand off to queries.
"""

from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from rest_framework.generics import ListAPIView, RetrieveAPIView

from apps.compensation.models import CompensationLine, CompensationRecord
from apps.core import fx
from apps.core.dates import parse_on
from apps.core.filters import parse_csv
from apps.core.models import Country
from apps.employees import queries
from apps.employees.filters import DirectoryFilterSet
from apps.employees.models import Employee
from apps.employees.serializers import EmployeeDetailSerializer, EmployeeListSerializer


class ReportingMixin:
    """`on`, the reporting currency and the RateTable, parsed once per request."""

    def local_scope(self) -> tuple[list[str], dict[str, str]]:
        """The country codes `currency=local` may resolve against, and their currencies."""
        raise NotImplementedError

    def reporting(self):
        if not hasattr(self, "_reporting"):
            params = self.request.query_params
            on = parse_on(params.get("on"))
            wanted = params.get("currency")
            codes, currencies = [], {}
            if (wanted or "").strip().lower() == "local":
                codes, currencies = self.local_scope()
            currency = fx.resolve_reporting_currency(wanted, codes, currencies)
            self._reporting = (on, currency, fx.RateTable.load(on))
        return self._reporting

    def get_serializer_context(self):
        context = super().get_serializer_context()
        on, currency, rates = self.reporting()
        context.update({"on": on, "reporting_currency": currency, "rates": rates})
        return context


class EmployeeListView(ReportingMixin, ListAPIView):
    serializer_class = EmployeeListSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_class = DirectoryFilterSet
    search_fields = ["full_name", "employee_code", "email"]

    def local_scope(self):
        codes = parse_csv(self.request.query_params.get("country"))
        return codes, dict(Country.objects.values_list("code", "currency_code"))

    def get_queryset(self):
        on, currency, rates = self.reporting()
        return queries.directory_queryset(on, currency, rates)


class EmployeeDetailView(ReportingMixin, RetrieveAPIView):
    """`currency=local` on one employee is that employee's own currency."""

    serializer_class = EmployeeDetailSerializer
    filter_backends = []

    def get_queryset(self):
        lines = CompensationLine.objects.select_related("component").order_by(
            "component__sort_order", "component__code"
        )
        records = (
            CompensationRecord.objects.filter(cancelled_at__isnull=True)
            .prefetch_related(Prefetch("lines", queryset=lines))
            .order_by("-effective_from")
        )
        return Employee.objects.select_related("country", "department").prefetch_related(
            Prefetch("compensation_records", queryset=records, to_attr="live_records")
        )

    def get_object(self):
        if not hasattr(self, "_employee"):
            self._employee = super().get_object()
        return self._employee

    def local_scope(self):
        country = self.get_object().country
        return [country.code], {country.code: country.currency_code}
