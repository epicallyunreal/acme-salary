"""Compensation history, revisions and cancellation over HTTP (SPEC F3, section 8, DESIGN 1.4).

`PATCH /compensation/{id}/` is P1 and is not registered.
"""

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListCreateAPIView
from rest_framework.response import Response

from apps.compensation import services
from apps.compensation.models import CompensationRecord
from apps.compensation.serializers import RecordInputSerializer
from apps.employees import queries
from apps.employees.serializers import CompensationRecordSerializer
from apps.employees.views import OneEmployeeMixin, ReportingMixin, warnings_data


class CompensationHistoryView(OneEmployeeMixin, ListCreateAPIView):
    """GET the full history newest first, cancelled rows included, unpaginated. POST a revision."""

    serializer_class = CompensationRecordSerializer
    pagination_class = None

    def record_data(self, employee_id: int, record_id: int) -> dict:
        record = queries.history_queryset(employee_id).get(pk=record_id)
        return CompensationRecordSerializer(record, context=self.get_serializer_context()).data

    def list(self, request, *args, **kwargs):
        employee = self.get_object()
        records = queries.history_queryset(employee.pk)
        return Response(
            CompensationRecordSerializer(
                records, many=True, context=self.get_serializer_context()
            ).data
        )

    def create(self, request, *args, **kwargs):
        employee = self.get_object()
        self.reporting()
        body = RecordInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        written = services.revise(employee, body.record_input(), actor=request.user)
        return Response(
            {
                **self.record_data(employee.pk, written.record.pk),
                "warnings": warnings_data(written.warnings),
            },
            status=status.HTTP_201_CREATED,
        )


class CompensationRecordView(ReportingMixin, GenericAPIView):
    """DELETE cancels a scheduled revision: the row is marked, nothing is removed (D20)."""

    serializer_class = CompensationRecordSerializer
    filter_backends = []
    queryset = CompensationRecord.objects.select_related("employee__country")

    def get_object(self):
        if not hasattr(self, "_record"):
            self._record = super().get_object()
        return self._record

    def local_scope(self):
        country = self.get_object().employee.country
        return [country.code], {country.code: country.currency_code}

    def delete(self, request, *args, **kwargs):
        record = self.get_object()
        self.reporting()
        record = services.cancel(record, actor=request.user)
        fresh = queries.history_queryset(record.employee_id).get(pk=record.pk)
        return Response(
            CompensationRecordSerializer(fresh, context=self.get_serializer_context()).data
        )
