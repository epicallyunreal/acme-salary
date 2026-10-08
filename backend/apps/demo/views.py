"""The Demo data page's routes under /api/v1/admin/ (SPEC section 8, F9, D72)."""

from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import LoginRateThrottle
from apps.core.exceptions import Invalid
from apps.demo import services
from apps.demo.serializers import ResetSerializer
from apps.imports.parser import XLSX_TYPE


class ResetDemoView(APIView):
    """GET the live counts, POST `{password, confirm}` to empty the database and get the counts
    deleted. The POST is throttled on scope `reset`, five an hour per client address, keyed as
    the login throttle is, so wrong passwords count."""

    throttle_scope = "reset"

    def get_throttles(self):
        return [LoginRateThrottle()] if self.request.method == "POST" else []

    def get(self, request):
        return Response(services.counts())

    def post(self, request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        deleted = services.reset_demo(actor=request.user, **serializer.validated_data)
        return Response(deleted)


class SampleFileListView(APIView):
    def get(self, request):
        return Response(services.sample_files_payload())


class SampleFileView(APIView):
    """One sample file as an .xlsx attachment, the generated ones for `?seed=`, 42 by default."""

    def get(self, request, name: str):
        given = request.query_params.get("seed")
        try:
            seed = int(given) if given not in (None, "") else services.DEFAULT_SEED
        except ValueError as exc:
            raise Invalid({"seed": ["seed must be a whole number"]}) from exc
        file_name, data = services.sample_file(name, seed=seed)
        response = HttpResponse(data, content_type=XLSX_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{file_name}"'
        return response
