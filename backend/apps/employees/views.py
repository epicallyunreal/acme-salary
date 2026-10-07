"""Employee reads and writes over HTTP (SPEC F3, F4, F7, section 8).

Views parse parameters, call one query or service and serialise the result. Writes answer with
the employee's detail shape, read back through the same query as a GET.
"""

from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import (
    GenericAPIView,
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateAPIView,
)
from rest_framework.response import Response

from apps.core import fx
from apps.core.dates import parse_on
from apps.core.filters import parse_csv
from apps.core.models import Country
from apps.employees import queries, services
from apps.employees.filters import DirectoryFilterSet, EmployeeSearchFilter
from apps.employees.models import Employee
from apps.employees.serializers import (
    AuditEntrySerializer,
    EmployeeCreateSerializer,
    EmployeeDetailSerializer,
    EmployeeIdentitySerializer,
    EmployeeListSerializer,
    ExitSerializer,
)


def warnings_data(warnings) -> list[dict[str, str]]:
    """Create and revise answer with the validators' warnings (D27)."""
    return [message.as_dict() for message in warnings]


class ReportingMixin:
    """`on`, the reporting currency and the RateTable, parsed once per request."""

    def local_scope(self) -> tuple[list[str], dict[str, str]]:
        """The country codes `currency=local` may resolve against, and their currencies."""
        raise NotImplementedError

    def reporting(self):
        """Write handlers call this before the service, so a bad `on` or `currency` is a 400
        before anything is written."""
        if not hasattr(self, "_reporting"):
            params = self.request.query_params
            on = parse_on(params.get("on"))
            wanted = params.get("currency")
            codes, currencies = [], {}
            if fx.asks_local(wanted):
                codes, currencies = self.local_scope()
            currency = fx.resolve_reporting_currency(wanted, codes, currencies)
            self._reporting = (on, currency, fx.RateTable.load(on))
        return self._reporting

    def get_serializer_context(self):
        context = super().get_serializer_context()
        on, currency, rates = self.reporting()
        context.update({"on": on, "reporting_currency": currency, "rates": rates})
        return context

    def detail_data(self, pk: int) -> dict:
        employee = queries.detail_queryset().get(pk=pk)
        return EmployeeDetailSerializer(employee, context=self.get_serializer_context()).data


class OneEmployeeMixin(ReportingMixin):
    """Views about one employee. `currency=local` is that employee's own currency (D40)."""

    filter_backends = []

    def get_queryset(self):
        return Employee.objects.select_related("country", "department")

    def get_object(self):
        if not hasattr(self, "_employee"):
            self._employee = super().get_object()
        return self._employee

    def local_scope(self):
        country = self.get_object().country
        return [country.code], {country.code: country.currency_code}


class DirectoryMixin(ReportingMixin):
    """The directory's rows: SPEC F4's filters, search and ordering over the annotated queryset.
    The list pages through them and the export writes them all, so an export holds exactly the
    rows the pages show (SPEC F6)."""

    filter_backends = [DjangoFilterBackend, EmployeeSearchFilter]
    filterset_class = DirectoryFilterSet

    def local_scope(self):
        codes = parse_csv(self.request.query_params.get("country"))
        return codes, dict(Country.objects.values_list("code", "currency_code"))

    def get_queryset(self):
        on, currency, rates = self.reporting()
        return queries.directory_queryset(on, currency, rates)


class EmployeeListCreateView(DirectoryMixin, ListCreateAPIView):
    def get_serializer_class(self):
        return EmployeeCreateSerializer if self.request.method == "POST" else EmployeeListSerializer

    def create(self, request, *args, **kwargs):
        self.reporting()
        body = EmployeeCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        created = services.create_employee(body.identity(), body.record_input(), actor=request.user)
        return Response(
            {**self.detail_data(created.employee.pk), "warnings": warnings_data(created.warnings)},
            status=status.HTTP_201_CREATED,
        )


class EmployeeDetailView(OneEmployeeMixin, RetrieveUpdateAPIView):
    """GET the detail, PATCH identity fields. There is no PUT."""

    serializer_class = EmployeeDetailSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        # The service re-reads the employee it edits, so only GET needs the records prefetched.
        if self.request.method == "PATCH":
            return super().get_queryset()
        return queries.detail_queryset()

    def update(self, request, *args, **kwargs):
        employee = self.get_object()
        self.reporting()
        body = EmployeeIdentitySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.update_identity(employee, body.validated_data, actor=request.user)
        return Response(self.detail_data(employee.pk))


class EmployeeExitView(OneEmployeeMixin, GenericAPIView):
    serializer_class = ExitSerializer

    def post(self, request, *args, **kwargs):
        employee = self.get_object()
        self.reporting()
        body = ExitSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        services.exit_employee(employee, body.validated_data["last_date"], actor=request.user)
        return Response(self.detail_data(employee.pk))


class EmployeeAuditView(ListAPIView):
    """The employee page's audit list, newest first, paginated like every list (D42)."""

    serializer_class = AuditEntrySerializer
    filter_backends = []

    def get_queryset(self):
        employee = get_object_or_404(Employee.objects.only("pk"), pk=self.kwargs["pk"])
        return queries.audit_queryset(employee.pk)
