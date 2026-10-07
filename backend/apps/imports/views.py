"""The import pipeline over HTTP (SPEC F1, F2, section 8, DESIGN 1.5).

Views parse parameters, call one query or service and serialise the result.
"""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import PayloadTooLarge
from apps.core.filters import BoundedSearchFilter
from apps.imports import queries, services, template
from apps.imports.filters import ImportRowFilterSet
from apps.imports.models import ImportBatch
from apps.imports.parser import XLSX_TYPE
from apps.imports.serializers import ImportBatchSerializer, ImportRowSerializer, UploadSerializer

# Room for the multipart boundaries and part headers around a file at the limit.
MULTIPART_ALLOWANCE = 64 * 1024


def declared_length(request) -> int:
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return 0


class ImportListCreateView(ListCreateAPIView):
    """GET the batches newest first. POST a multipart upload, staged for review."""

    serializer_class = ImportBatchSerializer
    filter_backends = []
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        return queries.batch_queryset()

    def create(self, request, *args, **kwargs):
        # Refused before the body is read; the parser would otherwise spool all of it first.
        if declared_length(request) > services.MAX_UPLOAD_BYTES + MULTIPART_ALLOWANCE:
            raise PayloadTooLarge()
        body = UploadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        batch = services.stage_upload(body.validated_data["file"], actor=request.user)
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ImportDetailView(RetrieveAPIView):
    """GET one batch's summary and counts."""

    serializer_class = ImportBatchSerializer
    filter_backends = []

    def get_queryset(self):
        return queries.batch_queryset()


class ImportRowListView(ListAPIView):
    """GET a batch's staged rows in sheet order, `?status=` comma-separated and `?search=` over
    legacy_code and full_name, paginated."""

    serializer_class = ImportRowSerializer
    filter_backends = [DjangoFilterBackend, BoundedSearchFilter]
    filterset_class = ImportRowFilterSet
    search_fields = ["legacy_code", "full_name"]

    def get_queryset(self):
        batch = get_object_or_404(ImportBatch.objects.only("pk"), pk=self.kwargs["pk"])
        return queries.rows_queryset(batch.pk)


class ImportTemplateView(APIView):
    """GET the XLSX template, for one country (`?country=IN`) or all of them."""

    def get(self, request):
        country = template.template_country(request.query_params.get("country"))
        name = f"acme-import-template-{country}.xlsx" if country else "acme-import-template.xlsx"
        response = HttpResponse(template.build_template(country), content_type=XLSX_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
