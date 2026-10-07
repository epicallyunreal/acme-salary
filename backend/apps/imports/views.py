"""The import pipeline over HTTP (SPEC F1, F2, section 8, DESIGN 1.5).

Views parse parameters, call one service and serialise the result.
"""

from django.http import HttpResponse
from rest_framework.views import APIView

from apps.imports import template
from apps.imports.parser import XLSX_TYPE


class ImportTemplateView(APIView):
    """GET the XLSX template, for one country (`?country=IN`) or all of them."""

    def get(self, request):
        country = template.template_country(request.query_params.get("country"))
        name = f"acme-import-template-{country}.xlsx" if country else "acme-import-template.xlsx"
        response = HttpResponse(template.build_template(country), content_type=XLSX_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response
